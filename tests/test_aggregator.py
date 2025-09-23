import json
from typing import Any

# Ensure repo root importable
import sys, pathlib
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from cedar_orchestrator import aggregate as agg

class _FakeResp:
    class _Choice:
        class _Msg:
            def __init__(self, content: str):
                self.content = content
        def __init__(self, content: str):
            self.message = _FakeResp._Choice._Msg(content)
    def __init__(self, content: str):
        self.choices = [self._Choice(content)]

class _FakeClient:
    class chat:
        class completions:
            @staticmethod
            def create(model: str, messages: Any):
                # Return a deterministic final JSON
                return _FakeResp(json.dumps({"function": "final", "args": {"text": "OK", "title": "Agg OK"}}))


def test_aggregator_builds_prompt_and_parses_final():
    candidates = [
        {"name": "example.summarize", "ok": True, "status": "ok", "content": {"summary": "Summary: hi"}},
        {"name": "retrieval.retrieve_docs", "ok": True, "status": "ok", "content": {"results": []}},
    ]
    res = agg.aggregate("hello", candidates, client=_FakeClient, model="gpt-5")
    assert res.get("ok") is True
    fj = res.get("final_json")
    assert isinstance(fj, dict) and fj.get("function") == "final"
    dp = res.get("debug_prompt")
    assert isinstance(dp, list) and any(isinstance(m, dict) and m.get("role") == "system" for m in dp)
