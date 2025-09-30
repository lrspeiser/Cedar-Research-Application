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
    Handles multiple prompt patterns:
    1. "role": "system", "content": '''...'''
    2. sys_prompt = '''...'''
    3. system_header = f'''...'''
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the class definition (with or without parentheses)
        class_pattern = rf'class {class_name}[:\(]'
        class_match = re.search(class_pattern, content)
        if not class_match:
            return f"[Could not find class {class_name}]"
        
        class_start = class_match.start()
        
        # Find the next class definition to limit our search scope
        next_class_pattern = r'\nclass \w+[:\(]'
        next_class_match = re.search(next_class_pattern, content[class_start + 10:])
        if next_class_match:
            class_end = class_start + 10 + next_class_match.start()
            class_content = content[class_start:class_end]
        else:
            class_content = content[class_start:]
        
        # Try pattern 1: "role": "system", "content": """...""" or '''...'''
        system_prompt_pattern = r'"role"\s*:\s*"system"\s*,\s*"content"\s*:\s*(""".*?"""|\'\'\' .*?\'\'\')'
        matches = list(re.finditer(system_prompt_pattern, class_content, re.DOTALL))
        if matches:
            prompt_with_quotes = matches[0].group(1)
            prompt = prompt_with_quotes.strip('"""').strip("'''").strip()
            return prompt
        
        # Try pattern 2: sys_prompt = """...""" or sys_prompt = '''...'''
        sys_prompt_pattern = r'sys_prompt\s*=\s*(""".*?"""|\'\'\' .*?\'\'\')'
        matches = list(re.finditer(sys_prompt_pattern, class_content, re.DOTALL))
        if matches:
            prompt_with_quotes = matches[0].group(1)
            prompt = prompt_with_quotes.strip('"""').strip("'''").strip()
            return prompt
        
        # Try pattern 3: system_header = f"""...""" (for ChiefAgent)
        system_header_pattern = r'system_header\s*=\s*f?(""".*?"""|\'\'\' .*?\'\'\')'
        matches = list(re.finditer(system_header_pattern, class_content, re.DOTALL))
        if matches:
            prompt_with_quotes = matches[0].group(1)
            # Remove f-string formatting and quotes
            prompt = prompt_with_quotes.strip('"""').strip("'''").strip()
            # Note: f-strings with variables won't render, but schema will be visible
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
    # FileAgent uses LLM for optional description generation
    prompt = extract_prompt_from_agent(str(file_path), "FileAgent", "process")
    if "[No system prompt found" in prompt:
        return "[FileAgent uses direct file operations without LLM prompts for main tasks. Optional LLM-based file description generation uses JSON schema: {'description': 'brief 1-2 sentence description'}]"
    return prompt


def get_image_creation_agent_prompt() -> str:
    """Extract ImageCreationAgent prompt"""
    # This agent uses DALL-E API directly, no system prompt
    return "[ImageCreationAgent uses DALL-E API directly for image generation. No system prompt - user's description is passed directly to the image generation API.]"


def get_image_analysis_agent_prompt() -> str:
    """Extract ImageAnalysisAgent prompt from specialized_agents.py"""
    file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
    return extract_prompt_from_agent(str(file_path), "ImageAnalysisAgent", "process")


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