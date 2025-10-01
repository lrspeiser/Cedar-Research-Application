"""
StrategyAgent - Extracted from specialized_agents.py

Individual agent file created during Phase 3 refactoring.
"""

"""
Specialized Agents Module
Contains domain-specific agents for specialized tasks

These agents handle:
1. FormulaAgent - Mathematical derivations from first principles
2. ResearchAgent - Web research and citations
3. StrategyAgent - Strategic planning and coordination
4. DataAgent - Database schema analysis
5. NotesAgent - Documentation and note-taking
6. FileAgent - File downloads and management
"""

import os
import time
import json
import re
import sqlite3
import logging
import urllib.request
import tempfile
import mimetypes
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

# Import AgentResult from execution_agents
from .agent_result import AgentResult

# Configure logging
logger = logging.getLogger(__name__)

class StrategyAgent:
    """Agent that creates detailed strategic plans for addressing queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Create a detailed strategic plan for addressing the user's query"""
        start_time = time.time()
        logger.info(f"[StrategyAgent] Creating strategic plan for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: StrategyAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=f"**Agent Failure Report:**\n\nThe Strategy Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to create strategic plans. Without it, no planning is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot create strategy",
                summary="Strategy Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[StrategyAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a strategic planning expert. Create detailed action plans that include:
                        1. Breaking down the problem into manageable steps
                        2. Identifying which specialized agents should be used
                        3. Determining the sequence of operations
                        4. Specifying how to gather source material
                        5. How to analyze data and compile results
                        6. How to write the final report
                        
                        Format as a numbered step-by-step plan with:
                        - Step number and title
                        - Agent(s) to use
                        - Input/output for each step
                        - Dependencies between steps
                        
                        # AVAILABLE AGENTS AND THEIR CAPABILITIES:
                        
                        **CodeAgent** (strongest): Python execution, calculations, simulations, data analysis (pandas/NumPy/ML), charts/plots (matplotlib), document extraction (CSV/PDF/HTML/OCR), can read/write databases, create/process images.
                        
                        **FormulaAgent**: Step-by-step derivations from first principles; formal proofs with assumptions.
                        
                        **ResearchAgent**: Web research with citations; use when external/current info needed.
                        
                        **StrategyAgent**: Multi-step planning (you can recursively suggest your own use for complex orchestration).
                        
                        **SQLAgent**: Executable SQL only (SQLite-compatible); creates/updates tables, indexes, constraints, runs queries.
                        
                        **DataAgent**: Schema analysis, query guidance; reads DB metadata, proposes SQL to answer questions.
                        
                        **NotesAgent**: Organized notes/summaries; turns bullets/JSON into clean notes with headings/tags/timestamps.
                        
                        **ShellAgent**: System commands (non-interactive); file searches, grep, disk usage, package installs.
                        
                        **FileAgent**: Downloads from URLs, manages files, records metadata; makes files available to other agents.
                        
                        **ImageCreationAgent**: Text-to-image generation; creates diagrams/mockups, saves to project.
                        
                        **ImageAnalysisAgent**: Image understanding/OCR; detects objects/tags/text, updates image metadata.
                        
                        # MULTI-AGENT PATTERNS:
                        - Research-then-Analyze: ResearchAgent → CodeAgent (analyze/plot) → NotesAgent
                        - Ingest-Transform-Report: FileAgent → CodeAgent (extract/clean) → SQLAgent/DataAgent → NotesAgent
                        - Complex Orchestration: StrategyAgent (plan) → ChiefAgent (dispatch iteratively)
                        
                        # USING SUPPORTING ASSETS:
                        - If PDFs/CSVs/images in project: CodeAgent (parse/analyze), ImageAnalysisAgent (OCR), SQLAgent/DataAgent (DB), NotesAgent (document)
                        - Need new files: FileAgent (download first)
                        - CodeAgent can write outputs (CSV/plots) back to project files and DB"""
                    },
                    {"role": "user", "content": f"Create a strategic plan to address: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            strategic_plan = response.choices[0].message.content
            
            logger.info(f"[StrategyAgent] Completed strategic planning in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Strategic Action Plan

{strategic_plan}

Why: Created a comprehensive strategic plan with specific steps and agent assignments"""
            
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=formatted_output,
                confidence=0.80,
                method="Strategic planning",
                explanation="Developed detailed execution strategy"
            )
            
        except Exception as e:
            logger.error(f"[StrategyAgent] Error: {e}")
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=f"Answer: Strategic planning failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Planning error"
            )
