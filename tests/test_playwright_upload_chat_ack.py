import os
import sys
import time
import socket
import threading
import importlib
import re
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
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    # Use test LLM stub if available to ensure steps progress
    os.environ.setdefault("CEDARPY_TEST_MODE", "1")
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
def test_upload_autochat_shows_processing_filename(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + path)
        # Create project
        unique_title = f"Upload AutoChat {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")

        # Navigate to Upload tab and upload a uniquely named file
        page.get_by_test_id("open-uploader").click()
        upload_input = page.get_by_test_id("upload-input")
        fname = f".pw_upload_autochat_{int(time.time()*1000000)}.txt"
        tmp_path = Path.cwd() / fname
        tmp_path.write_text("hello,upload-autochat\n", encoding="utf-8")
        upload_input.set_input_files(str(tmp_path))
        page.get_by_test_id("upload-submit").click()

        # After redirect, auto-chat should start and show the Processing <filename>… bubble
        expect(page).to_have_url(re.compile(r".*/project/\d+\?.*msg=File\+uploaded.*"), timeout=15000)
        expect(page.locator("#msgs")).to_contain_text(f"Processing {fname}", timeout=10000)
    finally:
        _stop_server(server, thread)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass