# Orchestrator context and result models
# Keys: see README "Keys & Env" for how LLM keys are loaded from env or ~/CedarPyData/.env
# Troubleshooting: see README "Troubleshooting LLM failures" for guidance; do not fabricate results
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Union, Awaitable
from pydantic import BaseModel, Field

# Type alias for event publisher
PublishEvent = Callable[[Dict[str, Any]], None]

class OrchestratorCtx(BaseModel):
    project_id: int
    branch_id: Optional[int] = None
    thread_id: Optional[int] = None
    user_id: Optional[int] = None

    # LLM config (optional here; orchestrator wires this up)
    llm_client: Optional[Any] = None
    llm_model: Optional[str] = None

    # Logging and event streaming
    logger: Optional[Callable[[str], None]] = None
    publish_event: Optional[PublishEvent] = None

    # Deadlines/timeouts and timing
    start_ts: float = Field(default_factory=lambda: time.time())
    timeouts: Dict[str, Any] = Field(default_factory=dict)

    # Extra context
    extra: Dict[str, Any] = Field(default_factory=dict)


class ComponentResult(BaseModel):
    ok: bool
    status: str = "ok"  # ok | error | timeout
    component: str
    content: Optional[Union[Dict[str, Any], str, list]] = None
    debug: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


# Component function signature
# async def run(payload: dict, ctx: OrchestratorCtx) -> ComponentResult
ComponentFn = Callable[[Dict[str, Any], OrchestratorCtx], Union[Awaitable[ComponentResult], ComponentResult]]
