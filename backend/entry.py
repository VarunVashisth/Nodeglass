"""Loopback server with inherited token and one-line port handshake."""

import json
import os
import socket
from pathlib import Path

import uvicorn

from backend.app.main import create_app


def main():
    token = os.environ.get("NODEGLASS_TOKEN", "")
    data = Path(
        os.environ.get(
            "NODEGLASS_DATA_DIR", str(Path.home() / ".local/share/Nodeglass")
        )
    )
    app = create_app(
        data / "analysis.sqlite3",
        token,
        os.environ.get("NODEGLASS_ORIGIN", "http://127.0.0.1:5173"),
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", int(os.environ.get("NODEGLASS_PORT", "0"))))
    sock.listen(128)
    print(json.dumps({"port": sock.getsockname()[1], "protocol": 1}), flush=True)
    uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", log_level="warning", access_log=False)
    ).run(sockets=[sock])


if __name__ == "__main__":
    main()
