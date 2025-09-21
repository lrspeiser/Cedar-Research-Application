import os
import sys
import time
import socket
import threading
import importlib
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
import re


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

        # 1) Visible processing acknowledgment appears quickly (allow Unicode … or ASCII ...)
        expect(page.locator("#msgs")).to_contain_text(re.compile(r"Processing(\u2026|\.\.\.)"), timeout=5000)

        # 2) Server-side stages should show (submitted/planning/finalizing) or explicit timeout.
        # Allow generous time for LLM and align with server timeout (90s)
        page.wait_for_function(
            "() => { const el = document.querySelector('#msgs'); if (!el) return false; const t = el.innerText || ''; return t.includes('finalizing') || t.includes('timeout'); }",
            timeout=95000,
        )

        # 3) The processing text is eventually replaced (no longer present)
        # It may be replaced by the final text or a timeout message
        page.wait_for_function(
            "() => { const el = document.querySelector('#msgs'); if (!el) return false; const t = el.innerText || ''; return !(/Processing(\\u2026|\\.\\.\\.)/.test(t)); }",
            timeout=95000,
        )

        # 4) Assistant prompt bubble exists and is clickable to reveal the full JSON prompt
        page.locator("#msgs .msg.assistant .meta .title", has_text="Assistant").first.click()
        expect(page.locator("#msgs pre").first).to_contain_text('"role"', timeout=5000)

    finally:
        _stop_server(server, thread)
