"""
Prompts Package

Contains all prompt templates used by the orchestrator agents.
"""

from .chief_prompts import (
    get_system_prompt,
    get_validation_schema,
    get_system_header,
    get_synthesis_schema,
    get_planning_schema,
    get_routing_examples,
    get_agent_capabilities
)

__all__ = [
    'get_system_prompt',
    'get_validation_schema',
    'get_system_header',
    'get_synthesis_schema',
    'get_planning_schema',
    'get_routing_examples',
    'get_agent_capabilities'
]
