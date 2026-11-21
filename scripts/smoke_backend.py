"""Exercise the real startup handshake, authenticated HTTP API and shutdown."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packaged", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = (
        [str(root / "dist/nodeglass-backend/nodeglass-backend")]
        if args.packaged
        else [sys.executable, "-m", "backend.entry"]
    )
    token = secrets.token_hex(32)
    with tempfile.TemporaryDirectory() as data:
        process = subprocess.Popen(
            command,
            cwd=root,
            env={**os.environ, "NODEGLASS_TOKEN": token, "NODEGLASS_DATA_DIR": data},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            handshake = json.loads(process.stdout.readline())
            url = f"http://127.0.0.1:{handshake['port']}"
            with httpx.Client(
                base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=10
            ) as client:
                for _ in range(100):
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        time.sleep(0.05)
                assert httpx.get(url + "/health").status_code == 401
                project = client.post(
                    "/api/projects/open", json={"path": str(root / "fixtures/example")}
                ).json()
                base = "/api/projects/" + project["id"]
                assert client.post(base + "/scan").status_code == 202
                for _ in range(200):
                    state = client.get(base + "/status").json()
                    if state["status"] != "running":
                        break
                    time.sleep(0.05)
                assert state["status"] == "complete", state
                graph = client.get(base + "/graph?view=calls").json()
                assert len(graph["edges"]) >= 4
                assert any(e["metadata"].get("conditional") for e in graph["edges"])
                print(
                    f"PASS: {'packaged' if args.packaged else 'Python'} backend handshake, authentication, scan, graph API"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
            assert process.returncode in (0, -15), process.stderr.read()
            print("PASS: graceful backend shutdown")


if __name__ == "__main__":
    main()
