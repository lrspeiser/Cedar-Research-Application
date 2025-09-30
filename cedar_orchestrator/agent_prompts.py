"""
Dynamic prompt extraction - reads actual prompts directly from agent implementation files.
NO DUPLICATES. NO BACKUPS. NO MANUAL COPIES.
This file ONLY contains extraction logic to read prompts from the source code.
"""

import re
import os
from pathlib import Path

# Base directory for agent implementations
ORCHESTRATOR_DIR = Path(__file__).parent


def extract_prompt_from_agent(file_path: str, class_name: str, method_name: str = "process") -> str:
    """
    Extract the actual system prompt from an agent class by reading the source file.
    Looks for the 'content': '''...''' or 'content': \"\"\"...\"\"\" in the system message.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the class definition (with or without parentheses)
        class_pattern = rf'class {class_name}[:\(]'
        class_match = re.search(class_pattern, content)
        if not class_match:
            return f"[Could not find class {class_name}]"
        
        # Find the process method within the class
        class_start = class_match.start()
        
        # Look for the system prompt in the completion_params or messages
        # Pattern: "role": "system", "content": """...""" or '''...'''
        system_prompt_pattern = r'"role"\s*:\s*"system"\s*,\s*"content"\s*:\s*(""".*?"""|\'\'\'.*?\'\'\')'
        
        # Search from class start onwards
        matches = list(re.finditer(system_prompt_pattern, content[class_start:], re.DOTALL))
        
        if matches:
            # Get the first system prompt found in this class
            prompt_with_quotes = matches[0].group(1)
            # Remove the triple quotes
            prompt = prompt_with_quotes.strip('"""').strip("'''").strip()
            return prompt
        
        return f"[No system prompt found in {class_name}]"
        
    except Exception as e:
        return f"[Error extracting prompt: {e}]"


def get_chief_agent_prompt() -> str:
    """Extract Chief Agent prompt from orchestrator.py"""
    file_path = ORCHESTRATOR_DIR / "orchestrator.py"
    return extract_prompt_from_agent(str(file_path), "ChiefAgent", "process")


def get_code_agent_prompt() -> str:
    """Extract CodeAgent prompt from execution_agents.py"""
    file_path = ORCHESTRATOR_DIR / "execution_agents.py"
    return extract_prompt_from_agent(str(file_path), "CodeAgent", "process")


def get_shell_agent_prompt() -> str:
    """Extract ShellAgent prompt from execution_agents.py"""
    file_path = ORCHESTRATOR_DIR / "execution_agents.py"
    return extract_prompt_from_agent(str(file_path), "ShellAgent", "process")


def get_sql_agent_prompt() -> str:
    """Extract SQLAgent prompt from execution_agents.py"""
    file_path = ORCHESTRATOR_DIR / "execution_agents.py"
    return extract_prompt_from_agent(str(file_path), "SQLAgent", "process")


def get_formula_agent_prompt() -> str:
    """Extract FormulaAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "FormulaAgent", "process")


def get_research_agent_prompt() -> str:
    """Extract ResearchAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "ResearchAgent", "process")


def get_strategy_agent_prompt() -> str:
    """Extract StrategyAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "StrategyAgent", "process")


def get_data_agent_prompt() -> str:
    """Extract DataAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "DataAgent", "process")


def get_notes_agent_prompt() -> str:
    """Extract NotesAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "NotesAgent", "process")


def get_file_agent_prompt() -> str:
    """Extract FileAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    # FileAgent doesn't use LLM prompts for main logic, but may use for descriptions
    return "[FileAgent uses direct file operations without LLM prompts for main tasks. May use LLM for generating file descriptions.]"


def get_image_creation_agent_prompt() -> str:
    """Extract ImageCreationAgent prompt"""
    # This agent uses DALL-E API directly, no system prompt
    return "[ImageCreationAgent uses DALL-E API directly for image generation. No system prompt - user's description is passed directly to the image generation API.]"


def get_image_analysis_agent_prompt() -> str:
    """Extract ImageAnalysisAgent prompt"""
    # This agent uses Vision API directly
    return "[ImageAnalysisAgent uses OpenAI Vision API to analyze images. The user's task is passed directly to the vision model along with the image.]"


# Agent metadata for the /agents page
# This defines WHAT to extract, not the actual prompts (which are extracted dynamically)
AGENTS_METADATA = [
    {
        "name": "The Chief Agent",
        "internal_name": "ChiefAgent",
        "description": "Primary orchestrator that reviews all sub-agent responses and makes final decisions. ALWAYS delegates to specialized agents.",
        "is_primary": True,
        "get_prompt": get_chief_agent_prompt
    },
    {
        "name": "Coding Agent",
        "internal_name": "CodeAgent",
        "description": "Python coding & execution: simple calculations (2+2, sums, etc), data analytics, plotting/graphs, and document data extraction.",
        "is_primary": False,
        "get_prompt": get_code_agent_prompt
    },
    {
        "name": "Shell Executor",
        "internal_name": "ShellAgent",
        "description": "Executes shell commands with full system access. Can install packages, grep files, and run system commands.",
        "is_primary": False,
        "get_prompt": get_shell_agent_prompt
    },
    {
        "name": "SQL Agent",
        "internal_name": "SQLAgent",
        "description": "Creates databases, tables, and executes SQL queries for comprehensive database management",
        "is_primary": False,
        "get_prompt": get_sql_agent_prompt
    },
    {
        "name": "Formula Agent",
        "internal_name": "FormulaAgent",
        "description": "Derives mathematical formulas from first principles and walks through detailed proofs. NOT for simple arithmetic - use CodeAgent for calculations.",
        "is_primary": False,
        "get_prompt": get_formula_agent_prompt
    },
    {
        "name": "Research Agent",
        "internal_name": "ResearchAgent",
        "description": "Performs web searches to find relevant sources, citations, and information",
        "is_primary": False,
        "get_prompt": get_research_agent_prompt
    },
    {
        "name": "Strategy Agent",
        "internal_name": "StrategyAgent",
        "description": "Creates detailed strategic plans for addressing complex queries with multi-step orchestration",
        "is_primary": False,
        "get_prompt": get_strategy_agent_prompt
    },
    {
        "name": "Data Agent",
        "internal_name": "DataAgent",
        "description": "Analyzes database schemas and suggests relevant SQL queries",
        "is_primary": False,
        "get_prompt": get_data_agent_prompt
    },
    {
        "name": "Notes Agent",
        "internal_name": "NotesAgent",
        "description": "Creates and manages organized notes from important findings",
        "is_primary": False,
        "get_prompt": get_notes_agent_prompt
    },
    {
        "name": "File Agent",
        "internal_name": "FileAgent",
        "description": "Downloads files from URLs and manages local files. Saves metadata to database.",
        "is_primary": False,
        "get_prompt": get_file_agent_prompt
    },
    {
        "name": "Image Creation Agent",
        "internal_name": "ImageCreationAgent",
        "description": "Creates images using OpenAI's DALL-E and saves them to the project files store",
        "is_primary": False,
        "get_prompt": get_image_creation_agent_prompt
    },
    {
        "name": "Image Analysis Agent",
        "internal_name": "ImageAnalysisAgent",
        "description": "Analyzes images using OpenAI Vision and updates metadata in the database",
        "is_primary": False,
        "get_prompt": get_image_analysis_agent_prompt
    }
]