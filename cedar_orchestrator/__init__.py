"""
Cedar Orchestrator module - Advanced Thinker-Orchestrator Implementation

This module provides the production WebSocket chat implementation with:
- Thinker that analyzes requests and creates execution plans
- Multiple specialized agents (Code, Math, General) running in parallel
- Orchestrator that selects the best result based on confidence
- Full streaming of reasoning and agent processing
"""

from cedar_orchestrator.ws_chat import register_ws_chat, WSDeps
from cedar_orchestrator.orchestrator import ThinkerOrchestrator, ChiefAgent
from cedar_orchestrator.execution_agents import AgentResult

__all__ = [
    "register_ws_chat",
    "WSDeps",
    "ThinkerOrchestrator",
    "ChiefAgent",
    "AgentResult",
]

# Version info
__version__ = "3.0.0"  # Advanced orchestrator version
