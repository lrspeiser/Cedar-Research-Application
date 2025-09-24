"""
Base agent class that all specific agents inherit from.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

@dataclass
class AgentContext:
    """Context passed to agents for execution"""
    query: str
    thinking_notes: str
    chat_history: List[Dict[str, Any]]
    files: List[Dict[str, Any]]
    databases: List[Dict[str, Any]]
    notes: List[Dict[str, Any]]
    code_snippets: List[Dict[str, Any]]
    changelog: List[Dict[str, Any]]
    previous_results: List[Dict[str, Any]] = None

@dataclass
class AgentResult:
    """Result from agent execution"""
    success: bool
    agent_name: str
    output: Any
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    display_type: str = "text"  # text, code, table, image, etc.

class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str, openai_client=None):
        self.name = name
        self.openai_client = openai_client
        
    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's main functionality"""
        pass
    
    async def validate_context(self, context: AgentContext) -> bool:
        """Validate that the context has required information"""
        if not context.query:
            logger.error(f"{self.name}: Missing query in context")
            return False
        return True
    
    def create_success_result(self, output: Any, metadata: Dict[str, Any] = None, display_type: str = "text") -> AgentResult:
        """Helper to create a successful result"""
        return AgentResult(
            success=True,
            agent_name=self.name,
            output=output,
            metadata=metadata,
            display_type=display_type
        )
    
    def create_error_result(self, error: str) -> AgentResult:
        """Helper to create an error result"""
        return AgentResult(
            success=False,
            agent_name=self.name,
            output=None,
            error=error
        )