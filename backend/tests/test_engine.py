import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.db.database import make_database
from backend.app.db.models import Entity, Repository, SourceFile
from backend.app.main import create_app
from backend.app.services.extractor import extract
from backend.app.services.graph_builder import build_graph
from backend.app.services.parser import parse
from backend.app.services.scanner import scan

TOKEN = "test-launch-token-" + "x" * 32


@pytest.fixture
def engine(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(Path(__file__).parents[2] / "fixtures/example", root)
    session = make_database(tmp_path / "analysis.db")()
    repo = Repository(id="repo", path=str(root), name="repo")
    session.add(repo)
    session.commit()
    yield session, repo, root
    session.close()


def analyze(engine):
    session, repo, _ = engine
    progress = {}
    scan(session, repo, progress)
    files = list(session.scalars(select(SourceFile)))
    entities = list(session.scalars(select(Entity)))
    return files, entities, progress


def test_acceptance_graph(engine):
    fs, es, progress = analyze(engine)
    assert progress["parsed"] == 3
    file_by_id = {f.id: f.path for f in fs}
    deps = build_graph(fs, es)
    assert {
        (file_by_id[e["source"]], file_by_id[e["target"]]) for e in deps["edges"]
    } == {("main.py", "auth.py"), ("main.py", "database.py")}
    calls = build_graph(fs, es, "calls")
    names = {n["id"]: n["label"] for n in calls["nodes"]}
    pairs = {
        (names[e["source"]], names[e["target"]])
        for e in calls["edges"]
        if e["type"] == "CALLS"
    }
    assert {
        ("main", "login"),
        ("login", "get_user"),
        ("login", "authenticate"),
    } <= pairs
    conditional = next(
        e for e in calls["edges"] if names[e["target"]] == "authenticate"
    )
    assert conditional["metadata"]["conditional"] is True
    assert any(
        e.kind == "hook" and e.name == "SCRIPT" and e.details["verified"] for e in es
    )
    login = next(e for e in es if e.kind == "function" and e.name == "login")
    flow = build_graph(fs, es, "flow", login.id)
    assert {"CONTROL_FLOW", "RETURNS", "DATA_DEPENDS_ON"} <= {
        e["type"] for e in flow["edges"]
    }
    assert all(
        e["source"] in {n["id"] for n in flow["nodes"]}
        and e["target"] in {n["id"] for n in flow["nodes"]}
        for e in flow["edges"]
    )


def test_rescan_changes_and_deletions(engine):
    fs, es, _ = analyze(engine)
    ids = {e.id for e in es}
    _, es, progress = analyze(engine)
    assert progress["unchanged"] == 3
    assert {e.id for e in es} == ids
    root = engine[2]
    (root / "auth.py").write_text("def renamed():\n    return True\n")
    _, es, progress = analyze(engine)
    assert progress["parsed"] == 1
    assert (
        next(e for e in es if e.kind == "call" and e.name == "authenticate").target_id
        is None
    )
    (root / "database.py").unlink()
    fs, es, progress = analyze(engine)
    assert progress["deleted"] == 1
    assert len(fs) == 2
    assert (
        next(e for e in es if e.kind == "call" and e.name == "get_user").target_id
        is None
    )
    session = engine[0]
    assert session.scalar(select(func.count(Entity.id))) == len({e.id for e in es})


@pytest.mark.parametrize(
    ("language", "source"),
    [
        (
            "python",
            "class Service:\n    def run(self, x: int = 3) -> bool:\n        def inner(y):\n            return y\n        z = inner(x)\n        if z:\n            return True\n",
        ),
        (
            "javascript",
            "export class Service { run(x = 3) { function inner(y) { return y; } const z = inner(x); if (z) return true; }}",
        ),
        (
            "typescript",
            "export class Service { run(x: number = 3): boolean { function inner(y: number) { return y; } const z = inner(x); if (z) return true; return false; }}",
        ),
        (
            "tsx",
            "export function View(props: {name: string}) { const click = () => props.name; return <button onClick={click}>{props.name}</button>; }",
        ),
    ],
)
def test_languages(language, source):
    rows, errors = extract(
        "repo", "file", source.encode(), parse(source.encode(), language), language
    )
    assert not errors
    assert any(e["kind"] == "function" for e in rows)
    assert any(e["kind"] == "return" for e in rows)
    if language != "tsx":
        assert {"class", "method", "parameter", "assignment", "control", "call"} <= {
            e["kind"] for e in rows
        }
        method = next(e for e in rows if e["kind"] == "method")
        assert method["qualified_name"] == "Service.run"
        assert (
            next(e for e in rows if e["name"] == "inner" and e["kind"] == "function")[
                "qualified_name"
            ]
            == "Service.run.inner"
        )


def test_lexical_aliases_unknown_receivers_and_cycles(engine):
    root = engine[2]
    (root / "a.py").write_text(
        "from b import target as alias\ndef target():\n    return 1\ndef outer():\n    def target():\n        return 2\n    target()\n    alias()\n    unknown.target()\ndef recurse():\n    return recurse()\n"
    )
    (root / "b.py").write_text(
        "from a import outer\ndef target():\n    return outer()\n"
    )
    fs, es, _ = analyze(engine)
    by_id = {e.id: e for e in es}
    local = next(e for e in es if e.kind == "call" and e.name == "target")
    assert by_id[local.target_id].qualified_name == "outer.target"
    alias = next(e for e in es if e.kind == "call" and e.name == "alias")
    assert by_id[alias.target_id].name == "target"
    assert by_id[alias.target_id].file_id != alias.file_id
    assert (
        next(
            e for e in es if e.kind == "call" and e.name == "unknown.target"
        ).resolution
        == "unresolved"
    )
    recursive = next(e for e in es if e.kind == "function" and e.name == "recurse")
    graph = build_graph(fs, es, "calls", recursive.id, depth=10)
    assert len(graph["nodes"]) == 1
    assert graph["edges"][0]["source"] == graph["edges"][0]["target"]
    assert len(build_graph(fs, es, "calls", recursive.id, depth=0)["nodes"]) == 1


def test_js_import_alias_and_arrow(engine):
    root = engine[2]
    (root / "helper.ts").write_text("export function target(x: number) { return x; }")
    (root / "index.ts").write_text(
        'import {target as alias} from "./helper"; export const run = (x: number) => alias(x); function caller() { return run(1); }'
    )
    _, es, _ = analyze(engine)
    alias = next(e for e in es if e.kind == "call" and e.name == "alias")
    assert alias.resolution == "resolved"
    assert (
        next(e for e in es if e.kind == "call" and e.name == "run").resolution
        == "resolved"
    )


def test_framework_hooks(engine):
    root = engine[2]
    (root / "routes.py").write_text(
        'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/users")\nasync def users():\n    return []\n@fake.post("/fake")\ndef bogus():\n    return None\n'
    )
    (root / "routes.ts").write_text(
        'import express from "express"; const app = express(); function users() { return []; } app.get("/users", users); fake.get("/bogus", users);'
    )
    _, es, _ = analyze(engine)
    hooks = [e for e in es if e.kind == "hook" and e.name != "SCRIPT"]
    assert sum(e.details.get("verified", False) for e in hooks) == 2
    assert all(e.target_id for e in hooks if e.details["verified"])


def test_unicode_syntax_unsupported_and_ignore(engine):
    root = engine[2]
    (root / ".gitignore").write_text("ignored.py\n")
    (root / "ignored.py").write_text("def ignored(): pass")
    (root / "notes.txt").write_text("not source")
    (root / "bad.py").write_bytes(b"\xff")
    (root / "syntax.py").write_text("def broken(:\n  pass")
    (root / "unicode.py").write_text('message = "é"\ndef café():\n    return message\n')
    (root / "outside.py").symlink_to("/etc/passwd")
    fs, es, progress = analyze(engine)
    assert "ignored.py" not in {f.path for f in fs}
    assert "outside.py" not in {f.path for f in fs}
    assert next(f for f in fs if f.path == "notes.txt").status == "unsupported"
    assert next(f for f in fs if f.path == "bad.py").status == "error"
    assert next(f for f in fs if f.path == "syntax.py").errors
    cafe = next(e for e in es if e.kind == "function" and e.name == "café")
    source = (root / "unicode.py").read_bytes()
    assert source[cafe.start_byte : cafe.end_byte].decode().startswith("def café")
    assert progress["errors"] >= 2


def test_api_auth_scan_graph_and_validation(tmp_path):
    app = create_app(tmp_path / "api.db", TOKEN)
    root = Path(__file__).parents[2] / "fixtures/example"
    with TestClient(app) as client:
        assert client.get("/health").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        assert client.get("/health").json()["status"] == "ok"
        assert (
            client.get(
                "/health", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/projects/open", json={"path": str(tmp_path / "missing")}
            ).status_code
            == 400
        )
        project = client.post("/api/projects/open", json={"path": str(root)}).json()
        base = "/api/projects/" + project["id"]
        assert client.post(base + "/scan").status_code == 202
        for _ in range(200):
            status = client.get(base + "/status").json()
            if status["status"] != "running":
                break
            time.sleep(0.01)
        assert status["status"] == "complete", status
        assert len(client.get(base + "/files").json()) == 3
        graph = client.get(base + "/graph?view=calls").json()
        assert len(graph["edges"]) >= 4
        assert client.get(base + "/graph?depth=99").status_code == 422
        assert client.get("/api/projects/missing/graph").status_code == 404
        symbols = client.get(base + "/symbols?q=login").json()
        detail = client.get(base + "/symbols/" + symbols[0]["id"]).json()
        assert len(detail["callees"]) == 2
        assert "def login" in detail["snippet"]
        assert (
            client.get(base + "/functions/" + symbols[0]["id"] + "/flow").status_code
            == 200
        )
        limited = client.get(base + "/graph?limit=1").json()
        assert limited["truncated"] is True


def test_block_shadowing_methods_inheritance_and_depth(engine):
    root = engine[2]
    (root / "scope.ts").write_text("""function target() {return 1;}
function run() {
  if (true) { const target = unknown; target(); }
  return target();
}
class Base { method() { return 1; } }
class Child extends Base {}
const service = new Base();
function use() { return service.method(); }
""")
    fs, es, _ = analyze(engine)
    calls = [e for e in es if e.kind == "call" and e.name == "target"]
    assert calls[0].target_id is None
    assert calls[1].target_id is not None
    method = next(e for e in es if e.kind == "call" and e.name == "service.method")
    assert method.resolution == "resolved"
    child = next(e for e in es if e.kind == "class" and e.name == "Child")
    assert child.details["resolved_bases"][0]["target_id"] is not None
    run = next(e for e in es if e.kind == "function" and e.name == "run")
    graph = build_graph(fs, es, "calls", run.id, depth=1)
    assert len(graph["nodes"]) == 3
    upstream = build_graph(fs, es, "calls", calls[1].target_id, "upstream", depth=1)
    assert run.id in {n["id"] for n in upstream["nodes"]}
    assert all(e["metadata"]["line"] for e in graph["edges"])


def test_relative_imports_ambiguous_definitions_and_await(engine):
    root = engine[2]
    (root / "pkg").mkdir()
    (root / "pkg/__init__.py").write_text("")
    (root / "pkg/util.py").write_text("def helper():\n    return True\n")
    (root / "pkg/main.py").write_text(
        "from .util import helper as check\nasync def work():\n    return await check()\ndef duplicate(): pass\ndef duplicate(): pass\ndef caller():\n    return duplicate()\n"
    )
    _, es, _ = analyze(engine)
    check = next(e for e in es if e.kind == "call" and e.name == "check")
    assert check.resolution == "resolved"
    assert check.details["conditional"] is False
    assert (
        next(e for e in es if e.kind == "call" and e.name == "duplicate").resolution
        == "ambiguous"
    )
    assert any(e.kind == "control" and e.name == "await" for e in es)


def test_failure_rolls_back_last_good_scan(engine, monkeypatch):
    session, repo, root = engine
    _, es, _ = analyze(engine)
    ids = {e.id for e in es}
    (root / "auth.py").write_text("def new_name(): pass\n")
    from backend.app.services import scanner

    def fail(*args):
        raise RuntimeError("Resolution failed")

    monkeypatch.setattr(scanner, "resolve", fail)
    with pytest.raises(RuntimeError):
        scan(session, repo, {})
    session.rollback()
    assert {e.id for e in session.scalars(select(Entity))} == ids


def test_duplicate_imports_named_expressions_and_no_execution(engine):
    root = engine[2]
    sentinel = root / "must-not-exist"
    (root / "safe.py").write_text(
        f'import os, os\nopen({str(sentinel)!r}, "w").write("executed")\n'
    )
    (root / "named.js").write_text(
        "const alias = function inner() { return inner(); }; function caller() { return alias(); }"
    )
    fs, es, _ = analyze(engine)
    assert not sentinel.exists()
    assert len([e for e in es if e.kind == "import" and e.name == "os"]) == 2
    inner = next(e for e in es if e.kind == "call" and e.name == "inner")
    alias = next(e for e in es if e.kind == "call" and e.name == "alias")
    assert inner.target_id == alias.target_id
    assert alias.target_id is not None
    main = next(f for f in fs if f.path == "main.py")
    focused = build_graph(fs, es, "dependency", main.id, limit=1)
    assert focused["nodes"][0]["id"] == main.id
    assert focused["truncated"] is True
