"""
ShellAgent - Extracted from execution_agents.py

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

class ShellAgent:
    """Agent that executes shell commands exactly as provided by the Chief Agent"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.conversation_history = []  # Store conversation context
        
    async def process(self, task: str, conversation_context: str = None) -> AgentResult:
        """Use LLM to extract and confirm shell command, then execute it
        
        Args:
            task: Request from Chief Agent describing what shell command to run
            conversation_context: Optional conversation history for context
        """
        start_time = time.time()
        logger.info(f"[ShellAgent] Starting shell execution for: {task[:200]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result="**Agent Failure Report:**\n\nThe Shell Agent requires an LLM to extract and validate shell commands.\n\n**What the Chief Agent should know:**\nThis agent needs an LLM to safely parse and execute shell commands.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available",
                summary="Shell Agent failed: No LLM configured"
            )
        
        # Use LLM to extract command in JSON format
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
            logger.info(f"[ShellAgent] Requesting command extraction from LLM using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "ShellAgent",
                            AGENT_ROLES.get("ShellAgent", "to extract and execute safe, non-interactive shell commands"),
                            """You are a shell command expert.
You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted response explaining what command you'll run and why. Use markdown. This is displayed AS-IS.",
  "command": "exact_shell_command_to_execute",
  "expected_output": "Brief description of what output to expect",
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format it with markdown - explain what you're doing, displayed AS-IS
- 'command' field: Our code will EXTRACT and EXECUTE this exact shell command
- 'expected_output' field: What the user should expect to see
- 'summary' field: Brief summary for logs
- No text outside the JSON object
- The command must be a single-line shell command (can use pipes, &&, etc.)
- Use non-interactive commands only
- Working directory is ~/Projects/cedarpy

Example response:
{
  "answer": "**Finding Python files**\n\nI'll search for all .py files in the current directory.",
  "command": "find . -name '*.py' -type f",
  "expected_output": "List of Python file paths",
  "summary": "Find all Python files"
}"""
                        )
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            full_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                response_data = json.loads(full_response)
            except json.JSONDecodeError as e:
                logger.error(f"[ShellAgent] Failed to parse JSON response: {e}")
                return AgentResult(
                    agent_name="ShellAgent",
                    display_name="Shell Executor",
                    result=f"**JSON Parse Error:**\n\nThe LLM returned invalid JSON.\n\n**Error:** {e}",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse LLM response as JSON"
                )
            
            # Extract fields from JSON
            answer = response_data.get('answer', '').strip()
            shell_command = response_data.get('command', '').strip()
            expected_output = response_data.get('expected_output', '').strip()
            summary = response_data.get('summary', '').strip()
            
            if not shell_command:
                return AgentResult(
                    agent_name="ShellAgent",
                    display_name="Shell Executor",
                    result="**Missing Command:**\n\nThe LLM response did not include a shell command in the 'command' field.",
                    confidence=0.1,
                    method="Missing command field",
                    explanation="No command provided by LLM",
                    summary="No command generated"
                )
            
            if not summary:
                summary = f"Execute: {shell_command[:100]}"
            
            logger.info(f"[ShellAgent] Extracted command: {shell_command}")
            logger.info(f"[ShellAgent] Expected output: {expected_output}")
            logger.info(f"[ShellAgent] LLM-provided answer:\n{answer[:200]}...")
            
        except Exception as e:
            logger.error(f"[ShellAgent] Command extraction error: {e}")
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=f"**Command Extraction Failed:**\n\n{str(e)}",
                confidence=0.1,
                method="Extraction error",
                explanation=f"Failed to extract command: {str(e)[:100]}",
                summary="Command extraction failed"
            )
        
        # Store the command in history
        self.conversation_history.append({"command": shell_command, "timestamp": time.time()})
        
        # Execute the shell command
        logger.info(f"[ShellAgent] Executing command: {shell_command}")
        logger.info(f"[ShellAgent] Expected output: {expected_output}")
        
        try:
            # Use subprocess for actual shell execution
            result = subprocess.run(
                shell_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout for longer operations
                cwd=os.path.expanduser("~/Projects/cedarpy"),  # Set working directory
                env={**os.environ}  # Pass current environment
            )
            
            # Get output (full console logs)
            output = result.stdout if result.stdout else ""
            error = result.stderr if result.stderr else ""
            exit_code = result.returncode
            
            logger.info(f"[ShellAgent] Command completed with exit code: {exit_code}")
            logger.info(f"[ShellAgent] Stdout length: {len(output)} chars")
            logger.info(f"[ShellAgent] Stderr length: {len(error)} chars")
            
            # Build formatted output: LLM's answer + execution results
            formatted_output = answer  # Use LLM's pre-formatted answer AS-IS
            
            # Add execution status
            if exit_code == 0:
                formatted_output += f"\n\n**Status:** ✅ Success (exit code 0)"
            else:
                formatted_output += f"\n\n**Status:** ❌ Failed (exit code {exit_code})"
            
            # Add command and output
            formatted_output += f"\n\n**Command Executed:**\n```bash\n{shell_command}\n```"
            
            if output:
                # Truncate very long output
                display_output = output if len(output) < 3000 else output[:3000] + "\n... (output truncated)"
                formatted_output += f"\n\n**Output:**\n```\n{display_output}\n```"
            else:
                formatted_output += f"\n\n**Output:**\n```\n(no output)\n```"
            
            if error:
                display_error = error if len(error) < 1000 else error[:1000] + "\n... (truncated)"
                formatted_output += f"\n\n**Errors/Warnings:**\n```\n{display_error}\n```"
            
            # Determine confidence
            confidence = 0.9 if exit_code == 0 else 0.6
            
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=formatted_output,
                confidence=confidence,
                method=f"Shell execution (exit code: {exit_code})",
                explanation=f"Executed: {shell_command[:50]}{'...' if len(shell_command) > 50 else ''}",
                summary=summary
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"[ShellAgent] Command timed out: {shell_command}")
            timeout_msg = answer if answer else "**Timeout:**\n\nCommand execution timed out."
            timeout_msg += f"\n\n**Command:** `{shell_command}`\n\n**Reason:** The command took longer than 60 seconds and was terminated."
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=timeout_msg,
                confidence=0.3,
                method="Timeout",
                explanation="Command timed out",
                summary=summary if summary else f"Command '{shell_command[:50]}...' timed out"
            )
        except Exception as e:
            logger.error(f"[ShellAgent] Execution error: {e}")
            error_msg = answer if answer else "**Execution Error:**\n\nCommand failed to execute."
            error_msg += f"\n\n**Command:** `{shell_command}`\n\n**Error:** {str(e)}"
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=error_msg,
                confidence=0.2,
                method="Execution error",
                explanation=f"Error: {str(e)[:100]}",
                summary=f"Failed to execute '{shell_command[:50]}{'...' if len(shell_command) > 50 else ''}' - {str(e)[:50]}"
            )
