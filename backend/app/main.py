import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .db.database import make_database
from .db.models import Entity, Repository, SourceFile
from .schemas import Graph, OpenProject, Project
from .services.extractor import stable
from .services.graph_builder import build_graph
from .services.scanner import MAX_FILE_BYTES, scan


def create_app(database_path: Path, token: str, origin="http://127.0.0.1:5173"):
    if not token or len(token) < 24:
        raise ValueError("A launch token of at least 24 characters is required")
    sessions = make_database(database_path)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
    jobs = {}
    lock = Lock()

    @asynccontextmanager
    async def lifespan(_):
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(
        title="Nodeglass",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.sessions = sessions
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        source = request.headers.get("origin")
        if source and source != origin:
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        if request.method != "OPTIONS" and not secrets.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {token}"
        ):
            return JSONResponse(
                {"detail": "Launch authentication required"}, status_code=401
            )
        return await call_next(request)

    def repository(session, project_id):
        item = session.get(Repository, project_id)
        if not item:
            raise HTTPException(404, "Repository not found")
        return item

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/projects/open", response_model=Project)
    def open_project(body: OpenProject):
        try:
            root = Path(body.path).expanduser().resolve(strict=True)
            if not root.is_dir():
                raise ValueError("Select a directory")
            next(root.iterdir(), None)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, f"Cannot open repository: {exc}") from exc
        with sessions.begin() as session:
            key = stable(str(root))
            item = session.get(Repository, key)
            if not item:
                item = Repository(id=key, path=str(root), name=root.name)
                session.add(item)
            return Project(id=item.id, path=item.path, name=item.name)

    def run_scan(project_id):
        try:
            with sessions() as session:
                scan(session, repository(session, project_id), jobs[project_id])
        except Exception as exc:
            logging.getLogger(__name__).exception("Repository scan failed")
            jobs[project_id].update(status="error", message=str(exc))

    @app.post("/api/projects/{project_id}/scan", status_code=202)
    def start_scan(project_id: str):
        with sessions() as session:
            repository(session, project_id)
        with lock:
            if any(j["status"] == "running" for j in jobs.values()):
                raise HTTPException(409, "An analysis is already running")
            jobs[project_id] = {
                "status": "running",
                "discovered": 0,
                "parsed": 0,
                "skipped": 0,
                "errors": 0,
            }
            executor.submit(run_scan, project_id)
        return dict(jobs[project_id])

    @app.get("/api/projects/{project_id}/status")
    def status(project_id: str):
        with sessions() as session:
            repository(session, project_id)
        return dict(jobs.get(project_id, {"status": "idle"}))

    @app.get("/api/projects/{project_id}/files")
    def files(project_id: str):
        with sessions() as session:
            repository(session, project_id)
            rows = session.scalars(
                select(SourceFile)
                .where(SourceFile.repository_id == project_id)
                .order_by(SourceFile.path)
            )
            return [
                {
                    "id": f.id,
                    "path": f.path,
                    "language": f.language,
                    "status": f.status,
                    "errors": f.errors,
                    "size": f.size,
                }
                for f in rows
            ]

    @app.get("/api/projects/{project_id}/symbols")
    def symbols(
        project_id: str,
        q: str = Query("", max_length=200),
        file_id: str | None = None,
        limit: int = Query(500, ge=1, le=2000),
    ):
        with sessions() as session:
            repository(session, project_id)
            query = select(Entity).where(
                Entity.repository_id == project_id,
                Entity.kind.in_(
                    ["function", "method", "class", "variable", "parameter", "hook"]
                ),
            )
            if q:
                query = query.where(Entity.name.contains(q, autoescape=True))
            if file_id:
                query = query.where(Entity.file_id == file_id)
            return [
                describe(e)
                for e in session.scalars(
                    query.order_by(Entity.file_id, Entity.start_byte).limit(limit)
                )
                if e.kind != "hook" or e.details.get("verified")
            ]

    def describe(e):
        return {
            "id": e.id,
            "name": e.name,
            "qualified_name": e.qualified_name,
            "kind": e.kind,
            "file_id": e.file_id,
            "line": e.line,
            "column": e.column,
            "scope_id": e.scope_id,
            "resolution": e.resolution,
            "metadata": e.details,
        }

    @app.get("/api/projects/{project_id}/symbols/{symbol_id}")
    def symbol(project_id: str, symbol_id: str):
        with sessions() as session:
            repo = repository(session, project_id)
            e = session.get(Entity, symbol_id)
            if not e or e.repository_id != project_id:
                raise HTTPException(404, "Symbol not found")
            f = session.get(SourceFile, e.file_id)
            snippet, warning = "", None
            try:
                root = Path(repo.path)
                path = (root / f.path).resolve(strict=True)
                if (
                    not path.is_relative_to(root)
                    or path.stat().st_size > MAX_FILE_BYTES
                ):
                    raise ValueError("Source path is unsafe or oversized")
                source = path.read_bytes()
                from hashlib import sha256

                if sha256(source).hexdigest() != f.content_hash:
                    raise ValueError(
                        "Source has changed; rescan for an accurate preview"
                    )
                lines = source.decode("utf-8").splitlines()
                snippet = "\n".join(
                    lines[
                        max(0, e.line - 2) : min(
                            len(lines), e.end_line + 1, e.line + 60
                        )
                    ]
                )
            except (OSError, UnicodeError, ValueError) as exc:
                warning = str(exc)
            related = list(
                session.scalars(
                    select(Entity).where(Entity.repository_id == project_id)
                )
            )
            related_by_id = {item.id: item for item in related}

            def belongs(item):
                scope = item.scope_id
                while scope and scope != symbol_id:
                    parent = related_by_id.get(scope)
                    if not parent or parent.kind in {"function", "method", "class"}:
                        return False
                    scope = parent.scope_id
                return scope == symbol_id

            def caller_info(item):
                scope = related_by_id.get(item.scope_id)
                while scope and scope.kind not in {"function", "method"}:
                    scope = related_by_id.get(scope.scope_id)
                return describe(item) | {"caller_id": scope.id if scope else None,
                                         "caller_name": scope.qualified_name if scope else "module"}

            return {
                **describe(e),
                "file": f.path,
                "snippet": snippet,
                "snippet_line": max(1, e.line - 1),
                "warning": warning,
                "callers": [
                    caller_info(c)
                    for c in related
                    if c.kind == "call" and c.target_id == symbol_id
                ],
                "callees": [
                    describe(c) | {"target_id": c.target_id}
                    for c in related
                    if c.kind == "call" and belongs(c)
                ],
                "references": [
                    describe(r)
                    for r in related
                    if r.kind == "reference" and r.target_id == symbol_id
                ],
            }

    @app.get("/api/projects/{project_id}/graph", response_model=Graph)
    def graph(
        project_id: str,
        view: Literal["dependency", "calls", "flow"] = "dependency",
        start: str | None = None,
        direction: Literal["upstream", "downstream"] = "downstream",
        depth: int = Query(2, ge=0, le=10),
        limit: int = Query(200, ge=1, le=500),
        file_id: str | None = None,
        edge_types: str | None = None,
    ):
        with sessions() as session:
            repository(session, project_id)
            fs = list(
                session.scalars(
                    select(SourceFile)
                    .where(SourceFile.repository_id == project_id)
                    .order_by(SourceFile.path)
                )
            )
            es = list(
                session.scalars(
                    select(Entity)
                    .where(Entity.repository_id == project_id)
                    .order_by(Entity.file_id, Entity.start_byte)
                )
            )
            return build_graph(
                fs,
                es,
                view,
                start,
                direction,
                depth,
                limit,
                file_id,
                set(edge_types.split(",")) if edge_types else None,
            )

    @app.get(
        "/api/projects/{project_id}/functions/{symbol_id}/flow", response_model=Graph
    )
    def flow(project_id: str, symbol_id: str, limit: int = Query(200, ge=1, le=500)):
        return graph(project_id, "flow", symbol_id, "downstream", 2, limit, None, None)

    @app.get("/api/projects/{project_id}/execution", response_model=Graph)
    def execution(
        project_id: str,
        start: str,
        direction: Literal["upstream", "downstream"] = "downstream",
        depth: int = Query(2, ge=0, le=10),
        limit: int = Query(200, ge=1, le=500),
    ):
        return graph(project_id, "calls", start, direction, depth, limit, None, None)

    return app
