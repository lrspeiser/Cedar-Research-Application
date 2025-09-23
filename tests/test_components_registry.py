import asyncio
import os
from typing import Any, Dict

import pytest

# Ensure repo root importable
import sys
import pathlib
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from cedar_orchestrator.ctx import OrchestratorCtx
from cedar_components import registry as reg
# Ensure components register themselves by importing their modules
import cedar_components.example.summarize  # noqa: F401
import cedar_components.retrieval.retrieve_docs  # noqa: F401


def test_registry_lists_components():
    names = reg.list_components()
    # Expect at least our example and retrieval components
    assert "example.summarize" in names
    assert "retrieval.retrieve_docs" in names


def test_example_summarize_component_debug_prompt_and_output():
    ctx = OrchestratorCtx(project_id=1, thread_id=1, branch_id=1)
    payload: Dict[str, Any] = {"text": "CedarPy components test."}
    res = asyncio.run(reg.invoke("example.summarize", payload, ctx))
    assert res.ok is True
    assert isinstance(res.content, dict) and "summary" in res.content
    # Debug prompt includes a system role entry
    debug = res.debug or {}
    prompt = debug.get("prompt")
    assert isinstance(prompt, list) and len(prompt) >= 1
    assert any(isinstance(m, dict) and m.get("role") == "system" for m in prompt)
