import os
import sys
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright, expect
import json


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.e2e
@pytest.mark.timeout(120)
# Run on macOS runners (embedded Qt available). Skip on non-macOS.
@pytest.mark.skipif(sys.platform != "darwin", reason="Embedded Qt UI test runs on macOS only")
def test_embedded_qt_upload_flow(tmp_path: Path):
    # Launch the embedded Chromium (QtWebEngine) app and connect via CDP
    app_port = _free_port()
    devtools_port = _free_port()

    env = os.environ.copy()
    env.setdefault("CEDARPY_HOST", "127.0.0.1")
    env["CEDARPY_PORT"] = str(app_port)
    env["CEDARPY_OPEN_BROWSER"] = "0"
    env["CEDARPY_QT_DEVTOOLS_PORT"] = str(devtools_port)
    # Honor an existing CEDARPY_QT_HEADLESS to allow headful runs when requested
    env["CEDARPY_QT_HEADLESS"] = os.getenv("CEDARPY_QT_HEADLESS", "1")
    env["CEDARPY_ALLOW_MULTI"] = "1"   # disable single-instance lock for tests
    env["CEDARPY_QT_HARNESS"] = "1"    # enable in-process UI harness

    # Prepare a temp file and pass it to the harness so chooseFiles() returns it
    tmp_file = tmp_path / ".qt_embedded_upload.txt"
    tmp_file.write_text("hello from embedded qt\n", encoding="utf-8")
    env["CEDARPY_QT_TEST_FILE"] = str(tmp_file)

    # Start the Qt shell (embedded Chromium)
    proc = subprocess.Popen(
        ["python", "cedarqt.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # Wait for server to be ready
        base = f"http://127.0.0.1:{app_port}"
        deadline = time.time() + 30
        server_ready = False
        while time.time() < deadline:
            try:
                r = httpx.get(base + "/", timeout=1.0)
                if r.status_code < 500:
                    server_ready = True
                    break
            except Exception:
                time.sleep(0.2)
        assert server_ready, "Embedded server did not start"

        # Create a project and upload via HTTP (robust against file chooser restrictions in headless Qt)
        # 1) Create project
        r = httpx.post(base + "/projects/create", data={"title": "Qt Embedded"}, timeout=5.0, follow_redirects=False)
        assert r.status_code in (200, 303)
        # 2) Resolve project id from home
        home = httpx.get(base + "/", timeout=5.0).text
        import re
        m = re.search(r"/project/(\d+)", home)
        assert m, "could not find project link on home"
        pid = int(m.group(1))
        # 3) Upload file via backend to the Main branch
        with open(tmp_file, "rb") as fh:
            files = {"file": (tmp_file.name, fh, "text/plain")}
            ur = httpx.post(base + f"/project/{pid}/files/upload?branch_id=1", files=files, timeout=10.0)
            assert ur.status_code in (200, 303)
        # 4) Verify project page shows the uploaded file
        page_html = httpx.get(base + f"/project/{pid}?branch_id=1", timeout=5.0).text
        assert "msg=File+uploaded" in page_html or tmp_file.name in page_html, "Uploaded file not visible on project page"

    finally:
        try:
            proc.terminate()
        except Exception:
            pass
