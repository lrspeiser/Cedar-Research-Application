import os
import sys
import time
import socket
import threading
import importlib

import pytest
from playwright.sync_api import Page


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _start_server(port: int):
    # Ensure env flags
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    # import app
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
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


@pytest.mark.parametrize("path", ["/shell"]) 
def test_shell_ui_open_world(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        url = f"http://127.0.0.1:{port}{path}"
        page.goto(url)
        # Click Open World
        page.click("#openWorldBtn")
        # Wait until output shows the shell run
        locator = page.locator("#output")
        locator.wait_for(state="visible")
        page.wait_for_timeout(200)  # small stabilization
        # Wait up to 5s for the hello world text
        page.wait_for_function("() => document.querySelector('#output') && document.querySelector('#output').textContent.includes('hello world')", timeout=5000)
        output_text = locator.inner_text()
        # Print the output so CI log shows the content
        print("UI_OUTPUT:\n" + output_text)
        assert "hello world" in output_text
    finally:
        _stop_server(server, thread)