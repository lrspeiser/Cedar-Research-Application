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
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

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
                        "content": build_agent_system_prompt(
                            "StrategyAgent",
                            AGENT_ROLES.get("StrategyAgent", "to create strategic plans and orchestrate agents"),
                            """You are a strategic planning expert.
Respond ONLY with valid JSON in this exact schema:
{
  "plan": [
    {
      "step": 1,
      "title": "short step title",
      "agent": "CodeAgent|SQLAgent|ImageAnalysisAgent|ResearchAgent|DataAgent|ShellAgent|NotesAgent|FileAgent|StrategyAgent",
      "task": "exact task string to pass to that agent",
      "inputs": ["input 1", "input 2"],
      "outputs": ["output 1", "output 2"],
      "dependencies": [1, 2]
    }
  ],
  "summary": "brief one-line summary"
}

Notes:
- The 'plan' array must be ordered by execution sequence (step numbers ascending).
- 'agent' must name exactly one agent per step.
- 'task' must be a single, self-contained instruction string we can pass directly to the agent.
- Keep it concise; do not include prose outside the JSON object.
"""
                        )
                    },
                    {"role": "user", "content": f"Create a strategic plan to address: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw = response.choices[0].message.content.strip()

            # Parse JSON response - fail fast if invalid
            try:
                plan_data = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.error(f"[StrategyAgent] Failed to parse JSON: {e}")
                return AgentResult(
                    agent_name="StrategyAgent",
                    display_name="Strategy Agent",
                    result=f"**JSON Parse Error:**\n\nStrategyAgent returned invalid JSON.\n\n**Error:** {e}\n\n**Raw Response (truncated):**\n```\n{raw[:800]}\n```",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="StrategyAgent did not return valid JSON",
                    summary="Failed to parse StrategyAgent JSON"
                )

            logger.info(f"[StrategyAgent] Completed plan in {time.time() - start_time:.3f}s")

            # Build a readable summary for the bubble, but keep JSON in artifacts
            steps = plan_data.get("plan", [])
            lines = ["## Strategy Plan (summary)"]
            for s in steps:
                try:
                    lines.append(f"{s.get('step')}. {s.get('title')} — {s.get('agent')}")
                except Exception:
                    pass
            formatted_output = "\n".join(lines)

            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=formatted_output,
                confidence=0.80,
                method="Strategic planning",
                explanation="Developed detailed execution strategy",
                summary=plan_data.get("summary", "Strategy plan created"),
                artifacts={"type": "json", "name": "strategy_plan", "source": plan_data}
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
