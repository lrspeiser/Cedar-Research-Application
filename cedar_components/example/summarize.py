# Simple summarization component (no external calls)
# Keys: see README "Keys & Env" (not used here). Prompts emitted to debug for visibility.
from __future__ import annotations

import time
from typing import Any, Dict

from cedar_orchestrator.ctx import OrchestratorCtx, ComponentResult
from cedar_components.registry import register


@register("example.summarize")
async def summarize_run(payload: Dict[str, Any], ctx: OrchestratorCtx) -> ComponentResult:
    t0 = time.time()
    text = str((payload or {}).get("text") or "").strip()
    # Build a "prompt" for debug visibility (system + user)
    prompt = [
        {"role": "system", "content": "You are a concise summarizer. Return a short summary (<= 200 chars)."},
        {"role": "user", "content": text or "(empty)"},
        {"role": "user", "content": "Component: example.summarize"},
    ]
    # Trivial summary logic, deterministic and safe for unit tests
    summary = (text or "").strip().replace("\n", " ")[:200]
    if summary:
        summary = f"Summary: {summary}"
    else:
        summary = "Summary: (no content)"
    dt = int((time.time() - t0) * 1000)
    return ComponentResult(
        ok=True,
        status="ok",
        component="example.summarize",
        content={"summary": summary},
        debug={"prompt": prompt},
        duration_ms=dt,
    )
