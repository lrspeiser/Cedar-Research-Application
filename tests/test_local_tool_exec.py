import os
import json
import socket
import threading
from pathlib import Path

import pytest
import httpx

from uvicorn import Config, Server
import importlib
import sys

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _start_server(port: int):
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    os.environ.setdefault("CEDARPY_TEST_MODE", "1")
    # import main
    import main
    importlib.reload(main)
    config = Config(app=main.app, host="127.0.0.1", port=port, log_level="info")
    server = Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait briefly for readiness
    import time
    import urllib.request
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as r:
                if r.status < 500:
                    break
        except Exception:
            pass
        time.sleep(0.2)
    return server, t


def _stop_server(server, thread):
    try:
        server.should_exit = True
    except Exception:
        pass
    try:
        thread.join(timeout=5)
    except Exception:
        pass


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


@pytest.mark.timeout(30)
@pytest.mark.local
def test_tool_exec_db_code_web_locally():
    port = _free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, timeout=10) as hc:
            # Create a project for DB/code
            r = hc.post("/projects/create", data={"title": "Local Tool Test"})
            assert r.status_code in (200, 303)
            # Resolve project id
            home = hc.get("/").text
            import re
            m = re.search(r"/project/(\d+)", home)
            assert m, "project id not found"
            pid = int(m.group(1))

            # db
            db_res = hc.post("/api/test/tool", json={"function": "db", "project_id": pid, "args": {"sql": "SELECT 2+2 AS v"}}).json()
            assert db_res.get("success") is True
            assert db_res.get("columns") == ["v"]
            assert db_res.get("rows") and db_res["rows"][0][0] in (4, "4")

            # code
            code_src = "print(2+2)"
            code_res = hc.post("/api/test/tool", json={"function": "code", "project_id": pid, "args": {"source": code_src}}).json()
            assert code_res.get("ok") is True
            assert "4" in (code_res.get("logs") or "")

            # web
            web_res = hc.post("/api/test/tool", json={"function": "web", "args": {"url": "https://example.org"}}).json()
            assert web_res.get("ok") is True
            assert web_res.get("title") is not None
    finally:
        _stop_server(server, thread)
