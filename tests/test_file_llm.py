import os
import io
import json
import re
import tempfile
import importlib
import pytest

from starlette.testclient import TestClient


def _reload_app_with_temp_env_llm():
    tmp = tempfile.mkdtemp(prefix="cedarpy_test_llm_")
    os.environ["CEDARPY_DATA_DIR"] = tmp
    os.environ["CEDARPY_SHELL_API_ENABLED"] = "1"
    # Use a token to simplify ws auth like other tests
    os.environ["CEDARPY_SHELL_API_TOKEN"] = "testtoken"
    # Ensure LLM classification is enabled by default
    os.environ.pop("CEDARPY_FILE_LLM", None)

    # Import/reload main from repo root
    import sys as _sys
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in _sys.path:
        _sys.path.insert(0, repo_root)
    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _create_project(client: TestClient, title: str = "LLM Demo"):
    r = client.post("/projects/create", data={"title": title})
    assert r.status_code in (200, 303)
    home = client.get("/")
    assert home.status_code == 200
    m = re.search(r"/project/(\d+)", home.text)
    assert m, "project id not found"
    pid = int(m.group(1))
    return pid


def _resolve_branch_ids(client: TestClient, pid: int):
    token_q = "?token=testtoken"
    with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
        ws.send_text(json.dumps({"sql": f"SELECT id FROM branches WHERE name='Main' AND project_id = {pid}"}))
        out = json.loads(ws.receive_text()); assert out.get("ok") is True
        main_id = out.get("rows")[0][0]
    return main_id


def test_upload_emits_processing_and_updates_metadata_json():
    main, tmp = _reload_app_with_temp_env_llm()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            main_id = _resolve_branch_ids(client, pid)

            # Upload a small text file
            content = b"hello world\nalpha,beta\n"
            files = {"file": ("sample.txt", io.BytesIO(content), "text/plain")}
            r = client.post(f"/project/{pid}/files/upload?branch_id={main_id}", files=files)
            assert r.status_code in (200, 303)

            # Query latest file and verify metadata_json contains sample_text
            token_q = "?token=testtoken"
            with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
                ws.send_text(json.dumps({"sql": "SELECT id, metadata_json, ai_title, ai_category, structure FROM files ORDER BY id DESC LIMIT 1"}))
                out = json.loads(ws.receive_text()); assert out.get("ok") is True
                cols = out.get("columns"); row = out.get("rows")[0]
                rowd = {cols[i]: row[i] for i in range(len(cols))}
                md = rowd.get("metadata_json") or {}
                # The interpreter should have embedded sample_text
                assert "sample_text" in md

                # Verify a processing thread and system message were created
                ws.send_text(json.dumps({"sql": "SELECT id FROM threads ORDER BY id DESC LIMIT 1"}))
                thr_out = json.loads(ws.receive_text()); assert thr_out.get("ok") is True
                thr_id = thr_out.get("rows")[0][0]

                ws.send_text(json.dumps({"sql": f"SELECT role, display_title FROM thread_messages WHERE thread_id = {thr_id} ORDER BY id"}))
                msg_out = json.loads(ws.receive_text()); assert msg_out.get("ok") is True
                msgs = msg_out.get("rows") or []
                # Expect at least one system message indicating submission
                assert any((m[0] == "system" and (m[1] or "").lower().startswith("submitting file")) for m in msgs)
    finally:
        # Best-effort cleanup
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


def test_upload_sets_ai_fields_via_llm():
    # Require a working key; otherwise skip with a clear message (no fallback tests)
    if os.getenv("CEDARPY_TEST_LLM_READY") != "1":
        pytest.skip("OpenAI key not working or missing; LLM tests were not run.")

    main, tmp = _reload_app_with_temp_env_llm()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            main_id = _resolve_branch_ids(client, pid)
            content = b"some csv,data\n1,2\n"
            files = {"file": ("data.csv", io.BytesIO(content), "text/csv")}
            r = client.post(f"/project/{pid}/files/upload?branch_id={main_id}", files=files)
            assert r.status_code in (200, 303)

            token_q = "?token=testtoken"
            with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
                # Verify AI fields were populated
                ws.send_text(json.dumps({"sql": "SELECT id, ai_title, ai_category, structure FROM files ORDER BY id DESC LIMIT 1"}))
                out = json.loads(ws.receive_text()); assert out.get("ok") is True
                cols = out.get("columns"); row = out.get("rows")[0]
                rowd = {cols[i]: row[i] for i in range(len(cols))}
                assert (rowd.get("structure") or "").strip() != ""
                assert (rowd.get("ai_title") or "").strip() != ""

                # Check thread messages indicate analysis performed (not skipped)
                ws.send_text(json.dumps({"sql": "SELECT id FROM threads ORDER BY id DESC LIMIT 1"}))
                thr_out = json.loads(ws.receive_text()); assert thr_out.get("ok") is True
                thr_id = thr_out.get("rows")[0][0]
                ws.send_text(json.dumps({"sql": f"SELECT role, display_title FROM thread_messages WHERE thread_id = {thr_id} ORDER BY id DESC LIMIT 2"}))
                msg_out = json.loads(ws.receive_text()); assert msg_out.get("ok") is True
                msgs = msg_out.get("rows") or []
                assert any((m[0] == "assistant" and (m[1] or "").lower().startswith("file analyzed")) for m in msgs)
    finally:
        # Best-effort cleanup
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
