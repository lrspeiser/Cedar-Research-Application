"""
Cedar Orchestrator module for LLM chat and component management.

This module provides:
- WebSocket chat orchestration with fan-out/fan-in pattern
- Component-based architecture for concurrent LLM operations
- Aggregator LLM for result reconciliation
- Full event streaming via WebSocket and Redis/SSE relay
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type imports for IDE support without circular dependencies
    from .ws_chat import register_ws_chat, WSDeps
    from .ctx import OrchestratorCtx, ComponentResult

__all__ = [
    "register_ws_chat",
    "WSDeps",
    "OrchestratorCtx", 
    "ComponentResult",
]

# Version info
__version__ = "0.1.0"