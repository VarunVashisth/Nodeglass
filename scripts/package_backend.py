"""Build on each target OS before running frontend's npm run package/dist."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "nodeglass-backend",
        "--paths",
        str(root),
        "--collect-all",
        "tree_sitter_python",
        "--collect-all",
        "tree_sitter_javascript",
        "--collect-all",
        "tree_sitter_typescript",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.lifespan.on",
        str(root / "backend/entry.py"),
    ],
    cwd=root,
    check=True,
)
