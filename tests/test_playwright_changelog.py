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
    # Ensure shell API is enabled and browser auto-open disabled for tests
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
def test_changelog_page_is_not_merge(page: Page, path: str):
    """Ensure the Changelog page renders changelog details (table with When/Action/Summary)
    and is distinct from the Merge page (which shows branch cards and merge buttons).
    """
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + path)

        # Create project
        unique_title = f"Changelog Demo {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")

        # Extract project id to build Changelog URL
        import re as _re
        m = _re.search(r"/project/(\d+)", page.url)
        assert m, "could not extract project id after create"
        proj_id = m.group(1)

        # Visit Changelog page (Main branch context)
        page.goto(f"{base}/changelog?project_id={proj_id}&branch_id=1")

        # Assertions: has changelog H1 and table columns; not the merge H1
        from playwright.sync_api import expect
        expect(page.get_by_role("heading", name=_re.compile(r"^Changelog:"))).to_be_visible()
        expect(page.locator("thead >> text=When")).to_be_visible()
        expect(page.locator("thead >> text=Action")).to_be_visible()
        expect(page.locator("thead >> text=Summary")).to_be_visible()

        # Negative: no Merge page H1 on Changelog
        assert page.get_by_role("heading", name=_re.compile(r"^Merge:"), exact=False).count() == 0

        # Navigate to Merge via header and confirm it looks different
        page.get_by_role("link", name="Merge").click()
        # On /merge without project context, app may redirect or show guidance; click the project if listed
        # If redirected to /merge/{project_id}, just assert Merge heading is visible
        try:
            page.wait_for_url("**/merge/**", timeout=10000)
        except Exception:
            # If still on landing, try link with project context
            page.goto(f"{base}/merge/{proj_id}")
            page.wait_for_url("**/merge/**", timeout=10000)
        expect(page.get_by_role("heading", name=_re.compile(r"^Merge:"))).to_be_visible()
    finally:
        _stop_server(server, thread)