"""
Core workflow tests for CedarPy:
- Image upload processing
- PDF upload and metadata recording
- Math chat via CodeAgent
- Research chat via ResearchAgent

LLM-dependent tests: These tests will only run when CEDARPY_TEST_LLM_READY=1 and
OpenAI keys are available. See README.md (Testing and .env setup) for how to
configure API keys used by the app and test environment. Code that invokes web
services includes explicit logging and will surface errors rather than falling
back silently, per project rules.
"""

import os
import io
import json
import re
import tempfile
import uuid
import pytest

from starlette.testclient import TestClient
from urllib.parse import urlparse, parse_qs


def _reload_app_isolated_env():
    tmp = tempfile.mkdtemp(prefix="cedarpy_core_tests_")
    # Isolate data and enable shell API for test-only endpoints/WS auth
    os.environ["CEDARPY_DATA_DIR"] = tmp
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_SHELL_API_TOKEN", "testtoken")
    os.environ.setdefault("CEDARPY_TEST_MODE", "1")  # Force test mode for isolated environments
    # Ensure LLM features are enabled unless keys are missing (conftest sets readiness flag)
    os.environ.pop("CEDARPY_FILE_LLM", None)

    import sys as _sys, importlib
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in _sys.path:
        _sys.path.insert(0, repo_root)
    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _create_project(client: TestClient, title: str | None = None) -> int:
    if not title:
        title = f"Core Flow {uuid.uuid4().hex[:6]}"
    r = client.post("/projects/create", data={"title": title})
    assert r.status_code in (200, 303), f"create project failed: {r.status_code} {r.text}"
    home = client.get("/")
    assert home.status_code == 200
    m = re.search(r"/project/(\d+)", home.text)
    assert m, "project id not found"
    return int(m.group(1))


def _resolve_main_branch_id(client: TestClient, pid: int) -> int:
    token_q = "?token=testtoken"
    with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
        ws.send_text(json.dumps({"sql": f"SELECT id FROM branches WHERE name='Main' AND project_id = {pid}"}))
        out = json.loads(ws.receive_text()); assert out.get("ok") is True
        return int(out.get("rows")[0][0])


def _last_file_row(client: TestClient, pid: int) -> dict:
    token_q = "?token=testtoken"
    with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
        ws.send_text(json.dumps({"sql": "SELECT id, filename, display_name, file_type, mime_type, size_bytes FROM files ORDER BY id DESC LIMIT 1"}))
        out = json.loads(ws.receive_text()); assert out.get("ok") is True
        cols = out.get("columns"); row = out.get("rows")[0]
        return {cols[i]: row[i] for i in range(len(cols))}


@pytest.mark.timeout(60)
def test_upload_image_png_basic():
    main, tmp = _reload_app_isolated_env()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            bid = _resolve_main_branch_id(client, pid)

            # Tiny 1x1 PNG
            png_bytes = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01"
                b"\x0b\xe7\x02\x9a\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            files = {"file": ("tiny.png", io.BytesIO(png_bytes), "image/png")}
            r = client.post(f"/project/{pid}/files/upload?branch_id={bid}", files=files, follow_redirects=False)
            assert r.status_code in (200, 303), f"upload failed: {r.status_code} {r.text}"

            row = _last_file_row(client, pid)
            assert (row.get("mime_type") or "").startswith("image/")
            assert (row.get("file_type") or "").lower() in ("png", "image", "img", "png?" )
    finally:
        try:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


@pytest.mark.timeout(60)
def test_upload_pdf_basic_and_visible_in_db():
    main, tmp = _reload_app_isolated_env()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            bid = _resolve_main_branch_id(client, pid)

            # Minimal PDF bytes (not a full spec PDF but sufficient for upload+store)
            pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
            files = {"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
            r = client.post(f"/project/{pid}/files/upload?branch_id={bid}", files=files, follow_redirects=False)
            assert r.status_code in (200, 303), f"upload failed: {r.status_code} {r.text}"

            row = _last_file_row(client, pid)
            assert (row.get("mime_type") or "").startswith("application/pdf")
            assert str(row.get("display_name") or "").endswith(".pdf")
    finally:
        try:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


@pytest.mark.timeout(90)
def test_chat_math_question_codeagent_path():
    # Skip if LLM not ready or we're in stubbed test mode or keys are missing
    llm_ready = os.getenv("CEDARPY_TEST_LLM_READY") == "1"
    has_keys = bool(os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY"))
    if not llm_ready or os.getenv("CEDARPY_TEST_MODE") == "1" or not has_keys:
        pytest.skip("LLM not reachable, running in stub mode, or API keys missing; skipping math chat test")

    main, tmp = _reload_app_isolated_env()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            bid = _resolve_main_branch_id(client, pid)

            r = client.post(f"/project/{pid}/threads/chat?branch_id={bid}", data={"content": "What is 2+2? Only return the number."})
            assert r.status_code in (200, 303)

            # Find most recent thread
            token_q = "?token=testtoken"
            with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
                ws.send_text(json.dumps({"sql": "SELECT id FROM threads ORDER BY id DESC LIMIT 1"}))
                out = json.loads(ws.receive_text()); assert out.get("ok") is True
                thr_id = int(out.get("rows")[0][0])

                ws.send_text(json.dumps({"sql": f"SELECT role, content FROM thread_messages WHERE thread_id={thr_id} ORDER BY id DESC LIMIT 5"}))
                out2 = json.loads(ws.receive_text()); assert out2.get("ok") is True
                rows = out2.get("rows") or []
                asst_msgs = [c for (role, c) in rows if role == "assistant" and isinstance(c, str)]
                joined = "\n".join(asst_msgs).lower()
                assert any(tok in joined for tok in ["4", "four"])  # lenient: CodeAgent formats may vary
    finally:
        try:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


@pytest.mark.timeout(120)
def test_chat_web_research_question_sources_present():
    llm_ready = os.getenv("CEDARPY_TEST_LLM_READY") == "1"
    has_keys = bool(os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY"))
    if not llm_ready or os.getenv("CEDARPY_TEST_MODE") == "1" or not has_keys:
        pytest.skip("LLM not reachable, running in stub mode, or API keys missing; skipping research chat test")

    main, tmp = _reload_app_isolated_env()
    try:
        with TestClient(main.app) as client:
            pid = _create_project(client)
            bid = _resolve_main_branch_id(client, pid)

            prompt = "Find two authoritative sources about MOND (Modified Newtonian Dynamics) with citations and links."
            r = client.post(f"/project/{pid}/threads/chat?branch_id={bid}", data={"content": prompt})
            assert r.status_code in (200, 303)

            token_q = "?token=testtoken"
            with client.websocket_connect(f"/ws/sql/{pid}{token_q}") as ws:
                ws.send_text(json.dumps({"sql": "SELECT id FROM threads ORDER BY id DESC LIMIT 1"}))
                out = json.loads(ws.receive_text()); assert out.get("ok") is True
                thr_id = int(out.get("rows")[0][0])

                ws.send_text(json.dumps({"sql": f"SELECT role, content FROM thread_messages WHERE thread_id={thr_id} ORDER BY id"}))
                out2 = json.loads(ws.receive_text()); assert out2.get("ok") is True
                rows = out2.get("rows") or []
                content = "\n".join([r[1] for r in rows if r and r[0] == "assistant" and isinstance(r[1], str)])
                # Expect at least some link-like content
                assert any(tok in content for tok in ["http://", "https://", "doi.org", "arxiv.org"])  # lenient check
    finally:
        try:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
