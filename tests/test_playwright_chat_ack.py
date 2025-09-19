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
    # Forward OpenAI keys from environment if present to exercise real LLM per policy
    # (CI passes OPENAI_API_KEY via secrets; locally this can be unset but test will still show processing ack)
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
def test_chat_processing_ack_and_final(page: Page, path: str):
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        page.goto(base + path)
        # Create project
        unique_title = f"Chat ACK {int(time.time()*1000000)}"
        page.fill("input[name=title]", unique_title)
        page.locator("form[action='/projects/create'] button[type=submit]").click()
        page.wait_for_url("**/project/*")

        # Submit a simple chat message
        page.fill("#chatInput", "what is 2+2")
        page.locator("#chatForm button[type=submit]").click()

        # 1) Visible processing acknowledgment appears quickly
        expect(page.locator("#msgs").get_by_text("Processing…")).to_be_visible(timeout=3000)

        # 2) Server-side stages should show (submitted/planning/finalizing/persisted). We check finalizing and persisted.
        # Allow generous time for LLM
        expect(page.locator("#msgs").get_by_text("finalizing")).to_be_visible(timeout=60000)
        expect(page.locator("#msgs").get_by_text("persisted")).to_be_visible(timeout=60000)

        # 3) The processing text is eventually replaced (no longer present)
        # It may be replaced by the final text (e.g., "2+2=4")
        expect(page.locator("#msgs").get_by_text("Processing…")).to_have_count(0, timeout=60000)

        # 4) Optionally, when LLM keys are provided, the final bubble should include "4" for this trivial query
        if os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY"):
            # Look for assistant bubble content containing "4"
            # Be lenient: any visible '4' within the msgs area after completion
            assert page.locator("#msgs").get_by_text("4").count() >= 1
    finally:
        _stop_server(server, thread)
