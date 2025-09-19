import os
import re
import tempfile
import shutil
import importlib

from starlette.testclient import TestClient


def _reload_app_with_env():
    tmp = tempfile.mkdtemp(prefix="cedarpy_threads_")
    os.environ["CEDARPY_DATA_DIR"] = tmp
    # Keep shell API defaults harmless for this test
    os.environ.setdefault("CEDARPY_SHELL_API_ENABLED", "1")
    import main  # noqa: F401
    importlib.reload(main)
    return main, tmp


def _cleanup(tmp_dir: str):
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def test_threads_new_json_endpoint_returns_json_response():
    main, tmp = _reload_app_with_env()
    try:
        with TestClient(main.app) as client:
            # Create a project
            title = "Threads JSON Test"
            r = client.post("/projects/create", data={"title": title})
            assert r.status_code in (200, 303)

            # Resolve project id via home page
            home = client.get("/")
            assert home.status_code == 200
            m = re.search(r"/project/(\d+)", home.text)
            assert m, "project id not found in home page"
            pid = int(m.group(1))

            # Call the endpoint that used JSONResponse; this guards against the prior NameError regression
            resp = client.get(f"/project/{pid}/threads/new?json=1")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert isinstance(data.get("thread_id"), int) and data["thread_id"] > 0
            assert isinstance(data.get("branch_id"), int)
            assert isinstance(data.get("redirect"), str) and f"/project/{pid}" in data["redirect"]
            assert isinstance(data.get("title"), str) and data["title"]
    finally:
        _cleanup(tmp)
