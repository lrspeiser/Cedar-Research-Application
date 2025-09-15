import os
import sys
import importlib

from starlette.testclient import TestClient

def _prep_env():
    # Isolate and enable shell API
    tmp_dir = os.environ.setdefault("CEDARPY_DATA_DIR", os.path.abspath("./.testdata_shell"))
    os.makedirs(tmp_dir, exist_ok=True)
    os.environ["CEDARPY_SHELL_API_ENABLED"] = "1"
    os.environ["CEDARPY_SHELL_API_TOKEN"] = "testtoken"
    # import main from repo root
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import main  # noqa: F401
    importlib.reload(main)
    return main


def test_shell_grep_demo():
    main = _prep_env()
    with TestClient(main.app) as client:
        # Start a shell job that runs grep over inline text
        script = "printf 'alpha\nbeta\nalpha\n' | grep '^alpha$'"
        r = client.post(
            "/api/shell/run",
            headers={"X-API-Token": "testtoken"},
            json={"script": script},
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert job_id

        grep_matches = []
        with client.websocket_connect(f"/ws/shell/{job_id}?token=testtoken") as ws:
            while True:
                line = ws.receive_text()
                if line == "__CEDARPY_EOF__":
                    break
                # Capture only exact matches
                if line.strip() == "alpha":
                    grep_matches.append("alpha")
        # Print the actual matches so CI output shows real content (not just pass/fail)
        print("GREP_MATCHES:", grep_matches)
        assert grep_matches == ["alpha", "alpha"]