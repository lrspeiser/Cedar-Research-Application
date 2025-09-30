"""
Agent Result Data Class
Defines the standard result structure returned by all agents
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Standard result structure returned by all agents"""
    agent_name: str
    display_name: str  # User-friendly name for the UI
    result: Any
    confidence: float
    method: str
    explanation: str = ""  # User-facing explanation of what the agent did
    summary: str = ""  # User-facing summary of what the agent did and key findings
    needs_rerun: bool = False  # Whether this agent needs to be rerun
    rerun_reason: str = ""  # Why a rerun is needed
    needs_clarification: bool = False  # Whether the agent needs user clarification
    clarification_question: str = ""  # Question to ask the user
    artifacts: dict = field(default_factory=dict)  # Optional artifacts produced by the agent (e.g., generated code)