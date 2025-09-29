import os
import sys
import time
import socket
import threading
import importlib
from pathlib import Path
from playwright.sync_api import Page, expect


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _start_server(port: int):
    # Ensure shell API and no automatic browser
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    # Stabilize LLM behavior in CI
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


def test_upload_autochat_includes_details(page: Page):
    port = _find_free_port()
    server, thread = _start_server(port)
    tmp_path = None
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + "/")

        # Create a project with a unique title
        unique_title = f"Upload Details {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")

        # Upload a small text file
        page.get_by_test_id("upload-input").set_input_files(
            str(Path.cwd() / ".pw_upload_details.txt")
        )
        tmp_path = Path.cwd() / ".pw_upload_details.txt"
        tmp_path.write_text("first line\nsecond line\nthird line\n", encoding="utf-8")
        page.get_by_test_id("upload-submit").click()

        # Wait for redirect back to project with msg=File+uploaded
        expect(page).to_have_url(
            lambda url: "msg=File+uploaded" in url, timeout=15000
        )

        # Verify the chat shows the processing bubble
        expect(page.locator("#msgs")).to_contain_text("Processing", timeout=10000)

        # Verify the first user message includes the details prefix and JSON keys
        msgs = page.locator("#msgs")
        expect(msgs).to_contain_text("User uploaded a file with the following details:")
        expect(msgs).to_contain_text("\"file_id\":")
        expect(msgs).to_contain_text("\"storage_path\":")
        expect(msgs).to_contain_text(".pw_upload_details.txt")
    finally:
        _stop_server(server, thread)
        try:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
