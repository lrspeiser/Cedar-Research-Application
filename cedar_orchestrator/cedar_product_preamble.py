"""
Cedar Product Preamble - Standard Introduction for All Agent Prompts

This module provides the standard Cedar product introduction that should be included
in every LLM prompt across all agents to ensure consistent context.
"""

def get_cedar_product_preamble() -> str:
    """
    Get the standard Cedar product introduction preamble.
    
    This should be included at the start of every agent's system prompt
    to provide consistent context about what Cedar is and what it can do.
    
    Returns:
        Standard Cedar product introduction text
    """
    return """You are using a research tool called Cedar. Cedar provides a framework that allows the LLM to collect data from the web, analyze documents and images, store data in databases and flat files, write and run code, and ultimately generate academic level papers that bring all of this together."""


def get_agent_specific_intro(agent_name: str, agent_role: str) -> str:
    """
    Get agent-specific introduction that follows the Cedar preamble.
    
    Args:
        agent_name: Name of the agent (e.g., "CodeAgent", "ResearchAgent")
        agent_role: Brief description of what this agent does
        
    Returns:
        Agent-specific introduction text
    """
    return f"""

Specifically, you are the {agent_name}. Your job is {agent_role}."""


def build_agent_system_prompt(agent_name: str, agent_role: str, specific_instructions: str) -> str:
    """
    Build a complete system prompt with Cedar preamble + agent-specific intro + instructions.
    
    Args:
        agent_name: Name of the agent (e.g., "CodeAgent")
        agent_role: Brief description of agent's role
        specific_instructions: Detailed agent-specific instructions
        
    Returns:
        Complete system prompt starting with Cedar preamble
    """
    cedar_preamble = get_cedar_product_preamble()
    agent_intro = get_agent_specific_intro(agent_name, agent_role)
    
    return cedar_preamble + agent_intro + "\n\n" + specific_instructions


# Common agent role descriptions for consistency
AGENT_ROLES = {
    "CodeAgent": "to tackle programming tasks by writing and executing Python code, performing calculations, data analysis, and generating visualizations",
    "SQLAgent": "to handle database operations by creating tables, writing queries, and managing data storage",
    "ShellAgent": "to execute system commands, search files, and perform system-level operations",
    "ResearchAgent": "to conduct web research, find authoritative sources, and compile information with proper citations", 
    "FormulaAgent": "to derive mathematical formulas from first principles and provide step-by-step mathematical proofs",
    "StrategyAgent": "to create comprehensive strategic plans and coordinate multi-step workflows across different agents",
    "DataAgent": "to analyze database schemas, understand data relationships, and suggest appropriate queries",
    "FileAgent": "to download files from URLs, manage local files, and save metadata to the project database",
    "ImageAnalysisAgent": "to analyze images using computer vision, extract text and data, and interpret visual content",
    "ImageCreationAgent": "to generate images based on text descriptions using AI image generation tools",
    "NotesAgent": "to create organized, structured notes and documentation from research findings and analysis results"
}