import os
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
@pytest.mark.skipif(os.getenv("CI", "").lower() == "true", reason="Enable after CI installs Qt runtime")
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

        # Poll the UI via HTTP to ensure upload finished (URL will include msg=File+uploaded and page will list file)
        deadline2 = time.time() + 30
        uploaded = False
        last_html = None
        while time.time() < deadline2:
            try:
                # Find the newest project via home page
                home = httpx.get(base + "/", timeout=2.0).text
                import re
                m = re.search(r"/project/(\\d+)", home)
                if m:
                    proj_url = f"/project/{m.group(1)}?branch_id=1"
                    page_html = httpx.get(base + proj_url, timeout=2.0).text
                    last_html = page_html
                    if "msg=File+uploaded" in page_html or tmp_file.name in page_html:
                        uploaded = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
        assert uploaded, "Harness did not complete upload flow"

    finally:
        try:
            proc.terminate()
        except Exception:
            pass
