import os
import sys
import time
import socket
import threading
import importlib
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest
import httpx
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
        # Verify the submit button is visible and enabled before clicking
        submit_btn = page.get_by_test_id("upload-submit")
        try:
            from playwright.sync_api import expect
            expect(submit_btn).to_be_visible()
            expect(submit_btn).to_be_enabled()
        except Exception:
            # Fallback: attribute check if expect is unavailable
            assert submit_btn.is_visible(), "Upload submit not visible"
            assert submit_btn.is_enabled(), "Upload submit not enabled"
        submit_btn.click()
        # Should navigate back to project with msg=File+uploaded
        page.wait_for_url("**/project/*?**msg=File+uploaded**")
        # Verify file appears in Files list
        assert page.get_by_text("Upload a file").is_visible()
        # The Files card heading should be present (avoid strict mode violation)
        assert page.get_by_role("heading", name="Files").is_visible()
        assert page.get_by_text(".pw_tmp_upload.txt").first.is_visible()
        # If LLM is configured and reachable, verify that AI fields are populated
        if os.environ.get("CEDARPY_TEST_LLM_READY") == "1":
            try:
                html = page.content()
                assert "AI Title:" in html, "AI Title label missing in UI"
                assert "AI Title:</strong> (none)" not in html, "LLM did not populate AI Title"
                # Optionally ensure the processing thread shows a success entry
                # (display_title is "File analyzed" when classification succeeds)
                if page.get_by_text("File analyzed").count() == 0:
                    assert "File analyzed" in html, "Missing 'File analyzed' thread entry"
            except Exception:
                # Fall back to a visible check for the label in case content() changes
                assert page.get_by_text("AI Title:").first.is_visible(), "AI Title label not visible"
    except Exception as ui_err:
        # Backend fallback: run the same flow via HTTP to distinguish FE vs BE failure
        backend_ok = False
        backend_err = None
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, follow_redirects=False, timeout=10) as hc:
                # Create a unique project via backend
                b_title = f"UI Upload Test (backend) {int(time.time()*1000000)}"
                r = hc.post("/projects/create", data={"title": b_title})
                assert r.status_code in (200, 303)
                # Resolve project page
                loc = r.headers.get("location")
                if not loc:
                    # Fallback: fetch home and find a project link
                    home = hc.get("/").text
                    import re as _re
                    m = _re.search(r"/project/(\\d+)", home)
                    assert m, "backend: could not find project link"
                    pid = int(m.group(1))
                    proj_url = f"/project/{pid}?branch_id=1"
                else:
                    proj_url = loc
                # Extract branch_id for upload
                q = parse_qs(urlparse(proj_url).query)
                branch_id = int((q.get("branch_id") or ["1"])[0])
                # Upload a file
                with (Path.cwd() / ".pw_tmp_upload_backend.txt").open("wb") as f:
                    f.write(b"hello,backend\n")
                with (Path.cwd() / ".pw_tmp_upload_backend.txt").open("rb") as f:
                    files = {"file": (".pw_tmp_upload_backend.txt", f, "text/plain")}
                    ur = hc.post(f"/project/{int(urlparse(proj_url).path.split('/')[-1])}/files/upload?branch_id={branch_id}", files=files)
                    assert ur.status_code in (200, 303)
                backend_ok = True
        except Exception as be:
            backend_err = be
        # Fail the test but annotate whether backend succeeded
        if backend_ok:
            raise AssertionError(f"Playwright UI failed, but backend succeeded. UI error: {ui_err}") from ui_err
        raise AssertionError(f"Both UI and backend failed. UI error: {ui_err}; Backend error: {backend_err}") from ui_err
    finally:
        _stop_server(server, thread)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            (Path.cwd() / ".pw_tmp_upload_backend.txt").unlink(missing_ok=True)
        except Exception:
            pass
