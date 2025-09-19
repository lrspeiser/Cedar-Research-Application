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
def test_merge_dashboard_shows_unique_and_merges(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + path)
        # Create project
        unique_title = f"Merge Demo {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")
        # Create a new branch via the inline form toggle (+ pill)
        page.locator("a.pill[title='New branch']").click()
        page.fill("#branchCreateForm input[name=name]", "feature-x")
        page.locator("#branchCreateForm button[type=submit]").click()
        page.wait_for_url("**/project/*?branch_id=*")
        # Upload a file on the branch to create changelog unique entries
        upload_input = page.get_by_test_id("upload-input")
        tmp_path = Path.cwd() / ".pw_tmp_merge.txt"
        tmp_path.write_text("hello,merge-branch\n", encoding="utf-8")
        upload_input.set_input_files(str(tmp_path))
        page.get_by_test_id("upload-submit").click(no_wait_after=True)
        page.wait_for_url("**/project/*?**msg=File+uploaded**", wait_until="domcontentloaded")
        # Open Merge page
        page.goto(base + "/merge")
        page.get_by_role("link", name="Open").first.click()
        page.wait_for_url("**/merge/*")
        # Verify Branch: feature-x card exists and shows unique list or at least the card
        assert page.get_by_role("heading", name="Branch: feature-x").is_visible()
        # Run merge from this page
        page.get_by_role("button", name="Merge feature-x → Main").click()
        page.wait_for_url("**/project/*?**msg=*", wait_until="domcontentloaded")
        # After merge, return to merge page and verify unique list is empty
        # Extract project id from current URL and navigate directly
        import re as _re
        m = _re.search(r"/project/(\d+)", page.url)
        assert m, "could not extract project id after merge"
        proj_id = m.group(1)
        page.goto(f"{base}/merge/{proj_id}")
        # Link back to this project exists
        assert page.get_by_role("heading", name="Branch: feature-x").is_visible()
        assert page.get_by_text("(no unique items found)").first.is_visible()
    finally:
        _stop_server(server, thread)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass