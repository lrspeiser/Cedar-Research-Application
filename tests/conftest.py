import os
import pytest

autouse = True

@pytest.fixture(autouse=True)
def _isolate_db(monkeypatch, tmp_path):
    data_dir = tmp_path / "CedarPyData"
    dbfile = data_dir / "cedarpy-registry.db"
    os.makedirs(data_dir, exist_ok=True)
    monkeypatch.setenv("CEDARPY_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CEDARPY_DATABASE_URL", f"sqlite:///{dbfile}")
    yield

import os
from pathlib import Path

# Load OpenAI API key from .env for the test session without printing any secrets.
# We mirror the key into both CEDARPY_OPENAI_API_KEY and OPENAI_API_KEY to satisfy
# whichever location the app/tests expect. See README for secure key setup.

def _parse_dotenv(path: Path) -> dict:
    vals = {}
    try:
        if not path.is_file():
            return vals
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            vals[k] = v
    except Exception:
        # Best effort; do not surface parse details in test output
        return vals
    return vals

def pytest_sessionstart(session):
    # Candidate .env locations (aligned with the app's loader order):
    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / ".env",
        Path(os.path.expanduser("~")) / "CedarPyData" / ".env",
    ]
    merged = {}
    for p in candidates:
        merged.update(_parse_dotenv(p))

    # If keys are not already in the environment, set them from .env
    key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or merged.get("CEDARPY_OPENAI_API_KEY") or merged.get("OPENAI_API_KEY")
    if key:
        # Only set if missing to avoid overriding CI-provided secrets
        if os.getenv("CEDARPY_OPENAI_API_KEY") is None:
            os.environ["CEDARPY_OPENAI_API_KEY"] = key
        if os.getenv("OPENAI_API_KEY") is None:
            os.environ["OPENAI_API_KEY"] = key

    # Determine whether LLM tests can run by verifying access to the configured model.
    # We do a cheap retrieve call rather than a completion to avoid extra cost.
    ready = False
    try:
        from openai import OpenAI  # type: ignore
        model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
        api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            try:
                client.models.retrieve(model)
                ready = True
            except Exception:
                ready = False
    except Exception:
        ready = False
    os.environ["CEDARPY_TEST_LLM_READY"] = "1" if ready else "0"


# Register custom marks (no-op) so @pytest.mark.e2e / @pytest.mark.timeout don't warn
try:
    import pytest  # type: ignore
    def pytest_configure(config):  # type: ignore
        try:
            config.addinivalue_line("markers", "e2e: end-to-end tests against embedded UI")
            config.addinivalue_line("markers", "timeout(x): per-test timeout")
        except Exception:
            pass
except Exception:
    pass
