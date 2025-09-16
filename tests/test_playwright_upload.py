import os
import sys
import time
import socket
import threading
import importlib
from pathlib import Path

import pytest
from playwright.sync_api import Page


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _start_server(port: int):
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
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
def test_project_upload_flow(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        url = f"http://127.0.0.1:{port}{path}"
        page.goto(url)
        # Create a project: fill title and click the submit button (label may be "Create" or "Create Project")
        # Use a unique project title to avoid UNIQUE constraint failures across runs
        unique_title = f"UI Upload Test {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        if page.get_by_text("Create Project").count() > 0:
            page.get_by_text("Create Project").click()
        else:
            page.locator("form[action='/projects/create'] button[type=submit]").click()
        # Wait for project page
        page.wait_for_url(f"**/project/*")
        # Upload a file via the form hooks
        upload_input = page.get_by_test_id("upload-input")
        # Create a temporary file
        tmp_path = Path.cwd() / ".pw_tmp_upload.txt"
        tmp_path.write_text("hello,playwright\n", encoding="utf-8")
        upload_input.set_input_files(str(tmp_path))
        page.get_by_test_id("upload-submit").click()
        # Should navigate back to project with msg=File+uploaded
        page.wait_for_url("**/project/*?**msg=File+uploaded**")
        # Verify file appears in Files list
        assert page.get_by_text("Upload a file").is_visible()
        # The Files card heading should be present (avoid strict mode violation)
        assert page.get_by_role("heading", name="Files").is_visible()
        assert page.get_by_text(".pw_tmp_upload.txt").first.is_visible()
    finally:
        _stop_server(server, thread)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
