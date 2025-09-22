import os
import sys
import time
import socket
import threading
import importlib
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _start_server(port: int):
    # Ensure WS endpoints enabled; do not auto-open browser during tests
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    # Repo root in path
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import main
    importlib.reload(main)
    from uvicorn import Config, Server

    config = Config(app=main.app, host="127.0.0.1", port=port, log_level="info")
    server = Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait briefly for readiness
    deadline = time.time() + 10
    import urllib.request
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


@pytest.mark.parametrize("path", ["/"])
def test_chat_submit_triggers_processing_and_submitted(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + path)
        # Create project
        unique_title = f"Submit Flow {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")

        # Submit chat
        page.fill("#chatInput", "analyze with code the redshift we would see from a star 100KPC away from us")
        page.locator("#chatForm button[type=submit]").click()

        # 1) Visible processing acknowledgment appears quickly (… or ...)
        expect(page.locator("#msgs")).to_contain_text(r"Processing(\u2026|\.\.\.)", use_regex=True, timeout=5000)
        # 2) The server-side 'submitted' stage should appear soon after
        expect(page.locator("#msgs")).to_contain_text("submitted", timeout=5000)
    finally:
        _stop_server(server, thread)