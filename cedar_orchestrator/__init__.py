"""
Cedar Orchestrator module - New thinker-orchestrator implementation.

This module provides the new WebSocket chat implementation with:
- Thinker that streams its reasoning process
- Parallel agent execution
- Smart result selection
"""

from cedar_orchestrator.ws_chat import register_ws_chat, WSDeps

__all__ = [
    "register_ws_chat",
    "WSDeps",
]

# Version info
__version__ = "2.0.0"
