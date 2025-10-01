"""
FormulaAgent - Extracted from specialized_agents.py

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

class FormulaAgent:
    """Agent that derives mathematical formulas from first principles"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Derive mathematical formulas from first principles and walk through derivations"""
        start_time = time.time()
        logger.info(f"[FormulaAgent] Starting mathematical derivation for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: FormulaAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=f"**Agent Failure Report:**\n\nThe Formula Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to derive mathematical formulas from first principles. Without it, no derivation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot derive formulas",
                summary="Formula Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[FormulaAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
{
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "FormulaAgent",
                            AGENT_ROLES.get("FormulaAgent", "to derive mathematical formulas from first principles"),
                            """You are a mathematical expert who derives formulas from first principles.
You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted derivation with steps, explanations, and final formula. Use markdown with LaTeX for equations. This is displayed AS-IS.",
  "final_formula": "The derived formula in LaTeX or plaintext",
  "assumptions": ["assumption 1", "assumption 2"],
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format with markdown, show ALL steps clearly, displayed AS-IS
- Start from fundamental axioms and definitions
- Show each transformation step with explanation
- Use proper mathematical notation (LaTeX in markdown)
- 'final_formula' field: Just the result formula
- 'assumptions' field: List any assumptions or constraints
- No text outside the JSON object

Example response:
{
  "answer": "**Derivation of Quadratic Formula**\n\nStarting from ax² + bx + c = 0...\n\n**Final Formula:** x = (-b ± √(b²-4ac))/(2a)",
  "final_formula": "x = (-b ± √(b²-4ac))/(2a)",
  "assumptions": ["a ≠ 0", "coefficients are real numbers"],
  "summary": "Derived quadratic formula from first principles"
}"""
                    )
                    },
                    {"role": "user", "content": f"Derive from first principles: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            full_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                response_data = json.loads(full_response)
            except json.JSONDecodeError as e:
                logger.error(f"[FormulaAgent] Failed to parse JSON: {e}")
                return AgentResult(
                    agent_name="FormulaAgent",
                    display_name="Formula Agent",
                    result=f"**JSON Parse Error:**\n\nLLM returned invalid JSON.\n\n**Error:** {e}",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse response"
                )
            
            # Extract fields
            answer = response_data.get('answer', '').strip()
            final_formula = response_data.get('final_formula', '').strip()
            assumptions = response_data.get('assumptions', [])
            summary = response_data.get('summary', '').strip()
            
            if not answer:
                return AgentResult(
                    agent_name="FormulaAgent",
                    display_name="Formula Agent",
                    result="**Missing Answer:**\n\nLLM response missing 'answer' field.",
                    confidence=0.1,
                    method="Missing answer",
                    explanation="No derivation provided",
                    summary="No answer generated"
                )
            
            if not summary:
                summary = f"Derived formula for: {task[:100]}"
            
            logger.info(f"[FormulaAgent] Completed derivation in {time.time() - start_time:.3f}s")
            logger.info(f"[FormulaAgent] Final formula: {final_formula[:100]}")
            
            # Display LLM's answer AS-IS
            formatted_output = answer
            
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=formatted_output,
                confidence=0.85,
                method="First principles derivation",
                explanation="Mathematical derivation from axioms",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[FormulaAgent] Error: {e}")
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=f"Answer: Unable to complete derivation\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Derivation failed"
            )
