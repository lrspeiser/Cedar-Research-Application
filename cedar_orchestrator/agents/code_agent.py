"""
CodeAgent - Extracted from execution_agents.py

Individual agent file created during Phase 3 refactoring.
"""

"""
Execution Agents Module
Contains core agents that execute concrete actions: shell commands, code, and SQL queries

These agents handle:
1. ShellAgent - Executes shell commands on the system
2. CodeAgent - Generates and executes Python code
3. SQLAgent - Creates and executes SQL queries
"""

import os
import time
import json
import math
import re
import sqlite3
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import AgentResult
from .agent_result import AgentResult
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

# Configure detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CodeAgent:
    """Agent that uses LLM to write code, then executes it"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to generate Python code, execute it, and return results"""
        start_time = time.time()
        logger.info(f"[CodeAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: CodeAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="CodeAgent",
                display_name="Coding Agent",
                result=f"**Agent Failure Report:**\n\nThe Coding Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to generate and execute code. Without it, no code generation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot generate code",
                summary="Coding Agent failed: No LLM configured"
            )
        
        try:
            # Get model from environment, defaulting to gpt-5
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            
            # Ask LLM to write Python code to solve the problem
            logger.info(f"[CodeAgent] Requesting code generation from LLM using model: {model}")
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "CodeAgent",
                            AGENT_ROLES.get("CodeAgent", "to write and execute Python code"),
                            """You are a Python code generator.

You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted response explaining what you're doing and the result. Use markdown formatting (bold, code blocks, etc). Include the computed result clearly. This is displayed to the user AS-IS.",
  "code": "executable_python_code_here_without_markdown_fences",
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format it with markdown, explanation, result - displayed AS-IS
- 'code' field: Our code will EXTRACT and EXECUTE this Python (no ``` fences, just raw Python)
- 'summary' field: Brief summary for logs
- The code must print its result to stdout
- Use proper error handling in the code
- For math expressions, parse correctly (e.g., 'square root of 5*10' = sqrt(5*10))
- No text outside the JSON object

Example response:
{
  "answer": "**Result: 4**\n\nCalculated 2+2 using Python addition.",
  "code": "result = 2 + 2\nprint(f'Result: {result}')",
  "summary": "Calculated 2+2"
}"""
                        )
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            # GPT-5 models have different parameters
            # Add check for ambiguous queries that might need clarification
            if "unclear" in task.lower() or "ambiguous" in task.lower() or task.count('?') > 2:
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result="Results So Far: Unable to generate code due to unclear requirements\n\nNext Steps: Clarify the specific calculation or operation needed",
                    confidence=0.2,
                    method="Needs clarification",
                    explanation="Query is ambiguous",
                    needs_clarification=True,
                    clarification_question="Could you please specify exactly what calculation or operation you'd like me to perform?"
                )
                
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            full_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                response_data = json.loads(full_response)
            except json.JSONDecodeError as e:
                logger.error(f"[CodeAgent] Failed to parse JSON response: {e}")
                logger.error(f"[CodeAgent] Raw response: {full_response[:500]}")
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result=f"**JSON Parse Error:**\n\nThe LLM returned invalid JSON.\n\n**Error:** {e}\n\n**Raw Response (truncated):**\n```\n{full_response[:500]}\n```",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse LLM response as JSON"
                )
            
            # Extract fields from JSON
            answer = response_data.get('answer', '').strip()
            generated_code = response_data.get('code', '').strip()
            summary = response_data.get('summary', '').strip()
            
            if not generated_code:
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result="**Missing Code:**\n\nThe LLM response did not include executable code in the 'code' field.",
                    confidence=0.1,
                    method="Missing code field",
                    explanation="No code provided by LLM",
                    summary="No code generated"
                )
            
            if not summary:
                summary = f"Generated Python code for: {task[:100]}"
            
            logger.info(f"[CodeAgent] Generated code:\n{generated_code}")
            logger.info(f"[CodeAgent] LLM-provided answer:\n{answer[:200]}...")
            
            # Execute the generated code
            import io
            import contextlib
            
            output_buffer = io.StringIO()
            error_buffer = io.StringIO()
            
            try:
                # Create a safe execution environment with common libraries
                exec_globals = {
                    "__builtins__": __builtins__,
                    "math": math,
                    "json": json,
                    "time": time,
                    "os": os,
                }
                
                with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                    exec(generated_code, exec_globals)
                
                output = output_buffer.getvalue()
                errors = error_buffer.getvalue()
                
                if errors:
                    logger.warning(f"[CodeAgent] Code execution had warnings: {errors}")
                
                logger.info(f"[CodeAgent] Execution output: {output}")
                logger.info(f"[CodeAgent] Completed in {time.time() - start_time:.3f}s")
                
                # Build final output: LLM's answer + execution results + code block
                formatted_output = answer  # Use LLM's pre-formatted answer AS-IS
                
                # Append execution results
                formatted_output += f"\n\n**Execution Output:**\n```\n{output if output else '(no output)'}\n```"
                
                # Append the code that was executed
                formatted_output += f"\n\n**Code Executed:**\n```python\n{generated_code}\n```"
                
                if errors:
                    formatted_output += f"\n\n**Warnings:**\n```\n{errors}\n```"

                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result=formatted_output,
                    confidence=0.95 if output else 0.5,
                    method="LLM-generated and executed Python code",
                    explanation=f"Generated and executed Python code",
                    summary=summary,
                    artifacts={
                        "type": "code",
                        "language": "python",
                        "name": (summary[:80] if summary else "Generated Code"),
                        "description": summary or "",
                        "source": generated_code,
                    }
                )
                
            except Exception as exec_error:
                logger.error(f"[CodeAgent] Code execution error: {exec_error}")
                # Use LLM's answer if available, otherwise create error message
                if answer:
                    formatted_output = answer
                    formatted_output += f"\n\n**Execution Failed:**\n```\n{str(exec_error)}\n```"
                else:
                    formatted_output = f"**Execution Error:**\n\nThe generated code failed to execute.\n\n**Error:** {str(exec_error)}"
                
                formatted_output += f"\n\n**Code That Failed:**\n```python\n{generated_code}\n```"

                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result=formatted_output,
                    confidence=0.3,
                    method="LLM code generation with execution error",
                    explanation=f"Code execution error",
                    summary=summary if 'summary' in locals() else f"Failed to execute generated code: {str(exec_error)[:100]}",
                    needs_rerun=True,
                    rerun_reason=f"Execution error: {str(exec_error)[:100]}",
                    artifacts={
                        "type": "code",
                        "language": "python",
                        "name": (summary[:80] if 'summary' in locals() and summary else "Generated Code (error)"),
                        "description": (summary if 'summary' in locals() else "") or "",
                        "source": generated_code,
                    }
                )
                
        except Exception as e:
            logger.error(f"[CodeAgent] Error: {e}")
            error_type = type(e).__name__
            error_details = f"""Exception Type: {error_type}
Error Message: {str(e)}
Task: {task[:200]}{'...' if len(task) > 200 else ''}
Model: {model if 'model' in locals() else 'Not determined'}"""
            
            return AgentResult(
                agent_name="CodeAgent",
                display_name="Coding Agent",
                result=f"**Code Generation Failed:**\n\nThe Coding Agent encountered an error while generating code.\n\n**Error Details:**\n```\n{error_details}\n```\n\n**Common Causes:**\n- OpenAI API rate limit or timeout\n- Invalid API key or permissions\n- Network connectivity issues\n- Model-specific parameter errors\n\n**Suggested Fix:**\nCheck the error message above and ensure your API configuration is correct.",
                confidence=0.1,
                method=f"Error: {error_type}",
                explanation=f"Code generation failed: {error_type}",
                summary=f"Failed to generate code - {error_type}: {str(e)[:100]}"
            )
