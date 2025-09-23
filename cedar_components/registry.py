# Component registry with registration decorator
from __future__ import annotations

import asyncio
from typing import Any, Dict, Callable, List, Optional

from cedar_orchestrator.ctx import OrchestratorCtx, ComponentResult, ComponentFn

_REGISTRY: Dict[str, ComponentFn] = {}


def register(name: str) -> Callable[[ComponentFn], ComponentFn]:
    def _decorator(fn: ComponentFn) -> ComponentFn:
        _REGISTRY[name] = fn
        return fn
    return _decorator


def list_components() -> List[str]:
    return sorted(_REGISTRY.keys())


def get_component(name: str) -> Optional[ComponentFn]:
    return _REGISTRY.get(name)


async def invoke(name: str, payload: Dict[str, Any], ctx: OrchestratorCtx) -> ComponentResult:
    fn = get_component(name)
    if not fn:
        return ComponentResult(ok=False, status="error", component=name, error=f"unknown component: {name}")
    try:
        res = fn(payload, ctx)
        if asyncio.iscoroutine(res):
            return await res  # type: ignore[return-value]
        return res  # type: ignore[return-value]
    except Exception as e:
        return ComponentResult(ok=False, status="error", component=name, error=f"{type(e).__name__}: {e}")
