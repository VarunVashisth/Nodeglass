from hashlib import sha256
from pathlib import Path

from pathspec import GitIgnoreSpec
from sqlalchemy import delete, insert, select

from ..db.models import Entity, SourceFile
from .extractor import extract, stable
from .parser import EXTENSIONS, parse
from .resolver import resolve

IGNORED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".next",
    ".pytest_cache",
}
MAX_FILE_BYTES = 2 * 1024 * 1024


def discover(root):
    """Do not follow symlinks. Apply nested gitignore files with local paths."""

    def visit(folder, rules):
        ignore = folder / ".gitignore"
        if ignore.is_file() and not ignore.is_symlink():
            try:
                rules = [
                    *rules,
                    (folder, GitIgnoreSpec.from_lines(ignore.read_text().splitlines())),
                ]
            except (OSError, UnicodeError):
                pass
        for item in sorted(folder.iterdir()):
            if item.is_symlink():
                continue
            directory = item.is_dir()
            if directory and item.name in IGNORED:
                continue
            ignored = False
            for base, spec in rules:
                match = spec.check_file(
                    item.relative_to(base).as_posix() + ("/" if directory else "")
                )
                if match.include is not None:
                    ignored = match.include
            if ignored:
                continue
            if directory:
                yield from visit(item, rules)
            elif item.is_file():
                yield item

    yield from visit(root, [])


def scan(session, repository, progress):
    root = Path(repository.path)
    existing = {
        f.path: f
        for f in session.scalars(
            select(SourceFile).where(SourceFile.repository_id == repository.id)
        )
    }
    paths = list(discover(root))
    progress.update(
        discovered=len(paths), parsed=0, skipped=0, errors=0, unchanged=0, deleted=0
    )
    seen = set()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        seen.add(relative)
        language = EXTENSIONS.get(path.suffix.lower(), "unsupported")
        file = existing.get(relative)
        errors = []
        try:
            stat = path.stat()
            if stat.st_size > MAX_FILE_BYTES:
                raise ValueError("File exceeds the 2 MiB analysis limit")
            source = path.read_bytes()
            digest = sha256(source).hexdigest()
            if file and file.content_hash == digest and file.language == language:
                progress["unchanged"] += 1
                progress["skipped"] += 1
                file.modified = stat.st_mtime
                continue
            if language != "unsupported":
                source.decode("utf-8")
                if b"\0" in source:
                    raise ValueError("Binary source file")
            status = "unsupported" if language == "unsupported" else "parsed"
        except (OSError, UnicodeError, ValueError) as exc:
            source = b""
            digest = ""
            stat = None
            status = "error"
            errors = [{"message": str(exc)}]
        if file:
            session.execute(delete(Entity).where(Entity.file_id == file.id))
        else:
            file = SourceFile(
                id=stable(repository.id, relative),
                repository_id=repository.id,
                path=relative,
            )
            session.add(file)
        file.language = language
        file.content_hash = digest
        file.size = stat.st_size if stat else 0
        file.modified = stat.st_mtime if stat else 0
        file.status = status
        file.errors = errors
        session.flush()
        if status == "parsed":
            try:
                rows, errors = extract(
                    repository.id, file.id, source, parse(source, language), language
                )
                # Insert scope parents before children; targets are populated in the resolution pass.
                if rows:
                    session.execute(insert(Entity), rows)
                    session.flush()
                file.errors = errors
                file.status = "syntax_error" if errors else "parsed"
                progress["parsed"] += 1
            except (ValueError, RecursionError) as exc:
                file.status = "error"
                file.errors = [{"message": str(exc)}]
        else:
            progress["skipped"] += 1
        progress["errors"] += len(file.errors)
    for relative, file in existing.items():
        if relative not in seen:
            session.delete(file)
            progress["deleted"] += 1
    session.flush()
    files = list(
        session.scalars(
            select(SourceFile).where(SourceFile.repository_id == repository.id)
        )
    )
    entities = list(
        session.scalars(select(Entity).where(Entity.repository_id == repository.id))
    )
    resolve(files, entities)
    session.commit()
    progress.update(
        status="complete",
        errors=sum(len(f.errors) for f in files),
        symbols=sum(
            e.kind in {"function", "class", "method", "variable", "parameter"}
            for e in entities
        ),
    )
