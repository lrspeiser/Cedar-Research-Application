import os
import json
import time
import shutil
import tempfile
import importlib
import sys

from starlette.testclient import TestClient


# Ensure repo root is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


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


def test_ws_end_to_end_shell_and_sql_and_branches():
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
            saw_eof = False
            with client.websocket_connect(f"/ws/shell/{job_id}{token_q}") as ws:
                # Read up to N messages until EOF marker
                for _ in range(200):
                    line = ws.receive_text()
                    if line == "__CEDARPY_EOF__":
                        saw_eof = True
                        break
                    if "hello ws" in line:
                        saw_hello = True
                assert saw_hello, "did not see 'hello ws' in shell stream"
                assert saw_eof, "did not receive EOF marker in shell stream"

            # Verify shell status includes a log file path that contains our output
            stat = client.get(f"/api/shell/status/{job_id}", headers={"X-API-Token": "testtoken"})
            assert stat.status_code == 200
            info = stat.json()
            logp = info.get("log_path")
            assert logp and os.path.isfile(logp)
            with open(logp, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()
            assert "hello ws" in data

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

            # 4) Branch-aware flow using ws/sqlx: create non-Main branch, insert in branch, verify visibility rules, then undo
            # Create project and branches via HTTP UI endpoints
            # Create project
            resp = client.post("/projects/create", data={"title": "WS Demo"})
            assert resp.status_code in (200, 303)
            # Find project id by loading home
            home = client.get("/")
            assert home.status_code == 200
            # crude parse
            import re as _re
            m = _re.search(r"/project/(\d+)", home.text)
            assert m, "project id not found"
            pid = int(m.group(1))
            # Create branch 'B1'
            resp = client.post(f"/project/{pid}/branches/create", data={"name": "B1"})
            assert resp.status_code in (200, 303)

            # Resolve branch ids via ws/sql (not branch-aware)
            with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as wsg:
                # Get Main and B1 ids
                wsg.send_text(json.dumps({"sql": "SELECT id FROM branches WHERE name='Main' AND project_id = %d" % pid}))
                out = json.loads(wsg.receive_text()); assert out.get("ok") is True
                main_id = out.get("rows")[0][0]
                wsg.send_text(json.dumps({"sql": "SELECT id FROM branches WHERE name='B1' AND project_id = %d" % pid}))
                out = json.loads(wsg.receive_text()); assert out.get("ok") is True
                b1_id = out.get("rows")[0][0]

            # ws/sqlx on Main: create table if not exists, then insert/select/undo in branch
            with client.websocket_connect(f"/ws/sqlx/{pid}{token_q}") as wsx:
                wsx.send_text(json.dumps({"action": "exec", "sql": "CREATE TABLE IF NOT EXISTS notes_demo (id INTEGER PRIMARY KEY, project_id INTEGER, branch_id INTEGER, body TEXT)"}))
                out = json.loads(wsx.receive_text()); assert out.get("ok") is True

                # Insert in branch B1 (explicit ids to satisfy strict policy)
                wsx.send_text(json.dumps({"action": "exec", "branch_name": "B1", "sql": f"INSERT INTO notes_demo (project_id, branch_id, body) VALUES ({pid}, {b1_id}, 'hidden?')"}))
                out_ins = json.loads(wsx.receive_text()); assert out_ins.get("ok") is True
                last_log_id = out_ins.get("last_log_id")
                assert last_log_id is not None

                # Select in Main for Main branch rows only (should not see 'hidden?')
                wsx.send_text(json.dumps({"action": "exec", "sql": f"SELECT body FROM notes_demo WHERE project_id={pid} AND branch_id={main_id} ORDER BY id"}))
                out_main = json.loads(wsx.receive_text()); assert out_main.get("ok") is True
                rows_main = out_main.get("rows") or []
                assert all("hidden?" not in [str(v) for v in r] for r in rows_main)

                # Select in B1 context explicitly (should see 'hidden?')
                wsx.send_text(json.dumps({"action": "exec", "sql": f"SELECT body FROM notes_demo WHERE project_id={pid} AND branch_id={b1_id} ORDER BY id"}))
                out_b1 = json.loads(wsx.receive_text()); assert out_b1.get("ok") is True
                rows_b1 = out_b1.get("rows") or []
                assert any("hidden?" in [str(v) for v in r] for r in rows_b1)

                # Undo last change in B1
                import time as _t
                _t.sleep(0.05)
                wsx.send_text(json.dumps({"action": "undo_last", "branch_id": b1_id, "log_id": last_log_id}))
                out_undo = json.loads(wsx.receive_text()); assert out_undo.get("ok") is True

                # Verify row gone in B1
                wsx.send_text(json.dumps({"action": "exec", "sql": f"SELECT body FROM notes_demo WHERE project_id={pid} AND branch_id={b1_id} ORDER BY id"}))
                out_b1_after = json.loads(wsx.receive_text()); assert out_b1_after.get("ok") is True
                rows_b1_after = out_b1_after.get("rows") or []
                assert all("hidden?" not in [str(v) for v in r] for r in rows_b1_after)
    finally:
        _cleanup_temp_env(tmp)