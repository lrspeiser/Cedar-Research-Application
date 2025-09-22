import os
import io
import json
import time
import importlib
import tempfile
import shutil
from typing import Dict, Any

import pytest
from starlette.testclient import TestClient
import sys, os as _os
# Ensure repo root on sys.path so `import main` resolves to main.py in repo root
_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Test plan
# - Create an isolated data dir per test run
# - Spin up app
# - Create project
# - Exercise /api/test/tool for each supported tool:
#   db, code, web, download, extract, image, shell, notes, compose, tabular_import
# Notes:
# - Requires network for web/download; uses example.org
# - tabular_import requires a real OpenAI API key; test will assert presence


def _reload_app_isolated_env() -> Any:
    tmp = tempfile.mkdtemp(prefix="cedarpy_tools_")
    os.environ["CEDARPY_DATA_DIR"] = tmp
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    os.environ.setdefault("CEDARPY_TEST_MODE", "1")  # enable test-only endpoints
    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _cleanup_tmp(tmp_dir: str):
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def _create_project(client: TestClient, title: str) -> int:
    r = client.post("/projects/create", data={"title": title})
    assert r.status_code in (200, 303)
    home = client.get("/").text
    import re as _re
    m = _re.search(r"/project/(\d+)", home)
    assert m, "project id not found"
    return int(m.group(1))


def _upload_file(client: TestClient, pid: int, branch_id: int, name: str, content: bytes, content_type: str) -> int:
    files = {"file": (name, content, content_type)}
    r = client.post(f"/project/{pid}/files/upload?branch_id={branch_id}", files=files, follow_redirects=False)
    assert r.status_code in (200, 303)
    # Read project page and find last file id by name
    page = client.get(f"/project/{pid}?branch_id={branch_id}").text
    import re as _re
    # crude search: rely on display name present and later discover via /api/test/tool queries
    # Instead, query DB via test tool 'db'
    return _last_file_id(client, pid)


def _last_file_id(client: TestClient, pid: int) -> int:
    # Use /api/test/tool db to query latest file id
    q = "SELECT id FROM files ORDER BY id DESC LIMIT 1"
    r = client.post("/api/test/tool", json={
        "function": "db",
        "project_id": pid,
        "args": {"sql": q}
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("success") is True
    rows = data.get("rows") or []
    assert rows and rows[0]
    return int(rows[0][0])


@pytest.mark.timeout(120)
def test_tools_end_to_end():
    # Require a real OpenAI key for tabular_import (no placeholders)
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    assert api_key and api_key.strip(), "Missing OPENAI_API_KEY; set a real key to run tabular_import"

    main, tmp = _reload_app_isolated_env()
    try:
        with TestClient(main.app) as client:
            # Create project and resolve Main branch id
            pid = _create_project(client, f"Tool Suite {int(time.time())}")
            # Fetch main branch id via SQL
            r = client.post("/api/test/tool", json={
                "function": "db",
                "project_id": pid,
                "args": {"sql": "SELECT id FROM branches WHERE name='Main' LIMIT 1"}
            })
            assert r.status_code == 200
            main_bid = int((r.json().get("rows") or [[1]])[0][0])

            # 1) db
            r = client.post("/api/test/tool", json={
                "function": "db",
                "project_id": pid,
                "args": {"sql": "SELECT 1"}
            })
            assert r.status_code == 200
            assert r.json().get("success") is True

            # 2) code
            r = client.post("/api/test/tool", json={
                "function": "code",
                "project_id": pid,
                "branch_id": main_bid,
                "args": {"source": "print('ok')"}
            })
            assert r.status_code == 200
            jd = r.json()
            assert jd.get("ok") is True
            assert "ok" in (jd.get("logs") or "")

            # 3) web
            r = client.post("/api/test/tool", json={
                "function": "web",
                "project_id": pid,
                "args": {"url": "https://example.org/"}
            })
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # 4) download
            r = client.post("/api/test/tool", json={
                "function": "download",
                "project_id": pid,
                "branch_id": main_bid,
                "args": {"urls": ["https://example.org/"]}
            })
            assert r.status_code == 200
            jd = r.json()
            assert jd.get("ok") is True
            dls = jd.get("downloads") or []
            assert dls and dls[0].get("file_id")
            dl_file_id = int(dls[0]["file_id"])

            # 5) extract (use the downloaded HTML file)
            r = client.post("/api/test/tool", json={
                "function": "extract",
                "project_id": pid,
                "args": {"file_id": dl_file_id}
            })
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # 6) image (upload a tiny PNG)
            png_bytes = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01"
                b"\x0b\xe7\x02\x9a\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            _upload_file(client, pid, main_bid, "tiny.png", png_bytes, "image/png")
            img_file_id = _last_file_id(client, pid)
            r = client.post("/api/test/tool", json={
                "function": "image",
                "project_id": pid,
                "args": {"image_id": img_file_id, "purpose": "sanity"}
            })
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # 7) shell
            r = client.post("/api/test/tool", json={
                "function": "shell",
                "project_id": pid,
                "args": {"script": "echo hello"}
            })
            assert r.status_code == 200
            jd = r.json()
            assert jd.get("ok") is True
            assert "hello" in (jd.get("stdout") or "")

            # 8) notes
            r = client.post("/api/test/tool", json={
                "function": "notes",
                "project_id": pid,
                "branch_id": main_bid,
                "args": {"themes": [{"name": "T", "notes": ["n1"]}]}
            })
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # 9) compose
            r = client.post("/api/test/tool", json={
                "function": "compose",
                "project_id": pid,
                "branch_id": main_bid,
                "args": {"sections": [{"title": "Intro", "text": "..."}]}
            })
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # 10) tabular_import (upload a CSV and import)
            csv_bytes = b"a,b\n1,2\n3,4\n"
            _upload_file(client, pid, main_bid, "data.csv", csv_bytes, "text/csv")
            csv_file_id = _last_file_id(client, pid)
            r = client.post("/api/test/tool", json={
                "function": "tabular_import",
                "project_id": pid,
                "branch_id": main_bid,
                "args": {"file_id": csv_file_id, "options": {"header_skip": 0}}
            })
            assert r.status_code == 200
            jd = r.json()
            assert jd.get("ok") is True, f"tabular import failed: {jd}"
            assert isinstance(jd.get("rows_inserted"), int)

    finally:
        _cleanup_tmp(tmp)
