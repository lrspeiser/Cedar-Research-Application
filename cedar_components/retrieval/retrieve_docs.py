# Retrieval component placeholder (LangExtract integration later)
# Keys: see README "Keys & Env" (not used here). Prompts emitted to debug for visibility.
from __future__ import annotations

import time
from typing import Any, Dict

from cedar_orchestrator.ctx import OrchestratorCtx, ComponentResult
from cedar_components.registry import register


@register("retrieval.retrieve_docs")
async def retrieve_docs_run(payload: Dict[str, Any], ctx: OrchestratorCtx) -> ComponentResult:
    t0 = time.time()
    query = str((payload or {}).get("query") or "").strip()
    prompt = [
        {"role": "system", "content": "Retrieve relevant documents from the project's index (placeholder)."},
        {"role": "user", "content": query or "(empty query)"},
        {"role": "user", "content": "Component: retrieval.retrieve_docs"},
    ]
    # Placeholder: return empty results; integration with LangExtract/SQLite will follow in M8
    results = []
    dt = int((time.time() - t0) * 1000)
    return ComponentResult(
        ok=True,
        status="ok",
        component="retrieval.retrieve_docs",
        content={"results": results},
        debug={"prompt": prompt},
        duration_ms=dt,
    )
