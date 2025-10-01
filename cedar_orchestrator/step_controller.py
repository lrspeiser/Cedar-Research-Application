"""
StepController - per-thread step-through control for preview streaming.

Allows enabling a step mode that pauses at named checkpoints, advancing
one step at a time with "next" or unblocking all future waits with
"continue". Also supports cancellation and cleanup.

Notes:
- This is an in-memory controller; it resets on process restart.
- Keys are thread_id (string). Upstream callers should pass the WebSocket
  thread_id for correlation.

See STEPPING_DEBUG_README.md for usage.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class _StepState:
    enabled: bool = False
    continue_mode: bool = False
    cancelled: bool = False
    tokens: int = 0
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)


class StepController:
    _states: Dict[str, _StepState] = {}

    @classmethod
    def _get(cls, thread_id: Optional[str]) -> _StepState:
        key = str(thread_id) if thread_id is not None else "default"
        if key not in cls._states:
            cls._states[key] = _StepState()
        return cls._states[key]

    @classmethod
    async def wait_next(cls, thread_id: Optional[str], step_name: str) -> None:
        state = cls._get(thread_id)
        # Fast-path: not enabled or already in continue mode or cancelled
        if not state.enabled or state.continue_mode or state.cancelled:
            return
        async with state.cond:
            # Consume an available token immediately
            if state.tokens > 0:
                state.tokens -= 1
                return
            # Otherwise wait until next() or continue()/cancel()
            while state.enabled and not state.continue_mode and not state.cancelled and state.tokens <= 0:
                await state.cond.wait()
            # If a token is available, consume it
            if state.tokens > 0:
                state.tokens -= 1

    @classmethod
    def enable(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        state.enabled = True
        state.continue_mode = False
        state.cancelled = False
        state.tokens = 0
        # Do not notify here; waits will start after enable

    @classmethod
    def disable(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        state.enabled = False
        state.continue_mode = False
        state.cancelled = False
        state.tokens = 0
        # Wake any waiters so they can exit
        asyncio.create_task(cls._notify_all(thread_id))

    @classmethod
    def next(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        # Issue exactly one token
        state.tokens += 1
        asyncio.create_task(cls._notify_all(thread_id))

    @classmethod
    def cont(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        state.continue_mode = True
        state.tokens = 0
        asyncio.create_task(cls._notify_all(thread_id))

    @classmethod
    def cancel(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        state.cancelled = True
        asyncio.create_task(cls._notify_all(thread_id))

    @classmethod
    def cleanup(cls, thread_id: Optional[str]) -> None:
        key = str(thread_id) if thread_id is not None else "default"
        if key in cls._states:
            del cls._states[key]

    @classmethod
    async def _notify_all(cls, thread_id: Optional[str]) -> None:
        state = cls._get(thread_id)
        async with state.cond:
            state.cond.notify_all()