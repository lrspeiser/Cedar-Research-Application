import os
import json
import time
import shutil
import tempfile
import importlib

from starlette.testclient import TestClient


def _reload_app_with_temp_env():
    # Isolate data dir per test run
    tmp = tempfile.mkdtemp(prefix="cedarpy_test_")
    os.environ["CEDARPY_DATA_DIR"] = tmp
    # Force shell API and set token to simplify auth in tests
    os.environ["CEDARPY_SHELL_API_ENABLED"] = "1"
    os.environ["CEDARPY_SHELL_API_TOKEN"] = "testtoken"
    # (Optional) ensure default host/port values won't conflict if used elsewhere
    os.environ.setdefault("CEDARPY_HOST", "127.0.0.1")
    os.environ.setdefault("CEDARPY_PORT", "8000")

    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _cleanup_temp_env(tmp_dir: str):
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def test_ws_end_to_end_shell_and_sql():
    main, tmp = _reload_app_with_temp_env()
    try:
        with TestClient(main.app) as client:
            token_q = "?token=testtoken"

            # 1) WebSocket health check
            with client.websocket_connect(f"/ws/health{token_q}") as ws:
                msg = ws.receive_text()
                assert msg == "WS-OK"

            # 2) Shell: start a job and stream output over WS
            run_resp = client.post(
                "/api/shell/run",
                headers={"X-API-Token": "testtoken"},
                json={"script": "echo hello ws"},
            )
            assert run_resp.status_code == 200, run_resp.text
            job = run_resp.json()
            job_id = job["job_id"]
            assert job_id

            saw_hello = False
            with client.websocket_connect(f"/ws/shell/{job_id}{token_q}") as ws:
                # Read up to N messages until EOF marker
                for _ in range(200):
                    line = ws.receive_text()
                    if line == "__CEDARPY_EOF__":
                        break
                    if "hello ws" in line:
                        saw_hello = True
                assert saw_hello, "did not see 'hello ws' in shell stream"

            # 3) SQL: create table, insert, select via WS
            with client.websocket_connect(f"/ws/sql/1{token_q}") as ws:
                ws.send_text(json.dumps({"sql": "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, name TEXT)"}))
                out = json.loads(ws.receive_text())
                assert out.get("ok") is True

                ws.send_text(json.dumps({"sql": "INSERT INTO demo (name) VALUES ('Alice')"}))
                out = json.loads(ws.receive_text())
                assert out.get("ok") is True

                ws.send_text(json.dumps({"sql": "SELECT * FROM demo ORDER BY id"}))
                out = json.loads(ws.receive_text())
                assert out.get("ok") is True
                rows = out.get("rows") or []
                # rows is a list of lists; expect at least one row with 'Alice'
                assert any("Alice" in [str(v) for v in r] for r in rows)
    finally:
        _cleanup_temp_env(tmp)