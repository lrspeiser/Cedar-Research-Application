import os
import json
import time
import tempfile
import shutil
import importlib
import sys

from starlette.testclient import TestClient
import pytest

# Ensure repo root is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _reload_app_with_env():
    tmp = tempfile.mkdtemp(prefix="cedarpy_ws_chat_")
    os.environ["CEDARPY_DATA_DIR"] = tmp
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    # Load app
    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _cleanup(tmp_dir: str):
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.mark.timeout(60)
@pytest.mark.e2e
def test_ws_chat_plan_execute_debug_prompt_and_final():
    # Require a real OpenAI API key; treat absence as a hard failure per policy
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    assert api_key and api_key.strip(), "Missing OPENAI_API_KEY; CI must provide real credentials"

    main, tmp = _reload_app_with_env()
    try:
        with TestClient(main.app) as client:
            # Create project
            title = f"WS Chat Orchestrator {int(time.time())}"
            r = client.post("/projects/create", data={"title": title})
            assert r.status_code in (200, 303)
            # Resolve project id via home page
            home = client.get("/").text
            import re as _re
            m = _re.search(r"/project/(\d+)", home)
            assert m, "project id not found"
            pid = int(m.group(1))

            # WebSocket chat
            with client.websocket_connect(f"/ws/chat/{pid}") as ws:
                ws.send_text(json.dumps({
                    "action": "chat",
                    "content": "what is 2+2",
                    "branch_id": 1,
                    "thread_id": None,
                    "debug": True,
                }))
                got_debug = False
                got_submitted = False
                got_action = False
                got_final = False
                for _ in range(200):
                    msg = ws.receive_text()
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "debug":
                        # Full prompt messages must be present and include our system prompt
                        prompt = data.get("prompt")
                        assert isinstance(prompt, list) and len(prompt) >= 3
                        assert any(isinstance(m, dict) and m.get("role") == "system" for m in prompt)
                        got_debug = True
                    elif t == "info" and data.get("stage") == "submitted":
                        got_submitted = True
                    elif t == "action":
                        # Could be plan/final; presence is enough to prove orchestrator loop
                        got_action = True
                    elif t == "final":
                        got_final = True
                        break
                    elif t == "error":
                        pytest.fail(f"backend error: {data.get('error')}")
                assert got_debug and got_submitted and got_action and got_final
    finally:
        _cleanup(tmp)
