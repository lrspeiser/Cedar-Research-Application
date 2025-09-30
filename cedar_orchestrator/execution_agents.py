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

# Remove file processing and notes imports - not needed for execution agents

# Configure detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Also log to file for persistence
try:
    import sys
    log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")
    os.makedirs(log_dir, exist_ok=True)
    from datetime import datetime
    log_file = os.path.join(log_dir, f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.info(f"Orchestrator logging initialized to {log_file}")
except Exception as e:
    logger.warning(f"Could not set up file logging: {e}")

@dataclass
class AgentResult:
    agent_name: str
    display_name: str  # User-friendly name for the UI
    result: Any
    confidence: float
    method: str
    explanation: str = ""  # User-facing explanation of what the agent did
    summary: str = ""  # User-facing summary of what the agent did and key findings
    needs_rerun: bool = False  # Whether this agent needs to be rerun
    rerun_reason: str = ""  # Why a rerun is needed
    needs_clarification: bool = False  # Whether the agent needs user clarification
    clarification_question: str = ""  # Question to ask the user
    artifacts: dict = field(default_factory=dict)  # Optional artifacts produced by the agent (e.g., generated code)
    
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
                        "content": """You are a shell command expert.

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
            error_msg += f"\n\n**Command:** `{shell_command}`\n\n**Error:** {str(e)}

**Common Issues:**
- Command not found: Install the tool or check the PATH
- Permission denied: Try with sudo if appropriate
- Syntax error: Check quotes and special characters

**Suggested Next Steps:** 
- Verify the command syntax
- Check if required tools are installed
- Try a simpler version of the command first""",
                confidence=0.2,
                method="Execution error",
                explanation=f"Error: {str(e)[:100]}",
                summary=f"Failed to execute '{shell_command[:50]}{'...' if len(shell_command) > 50 else ''}' - {str(e)[:50]}"
            )

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
                        "content": """You are a Python code generator.

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

class SQLAgent:
    """Agent that uses LLM to write and execute SQL queries, create databases, and manage schemas"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to generate SQL for database creation, updates, and queries"""
        start_time = time.time()
        logger.info(f"[SQLAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: SQLAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=f"**Agent Failure Report:**\n\nThe SQL Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to generate SQL queries. Without it, no SQL generation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot generate SQL",
                summary="SQL Agent failed: No LLM configured"
            )
        
        # Check if this is actually a SQL/database task
        if not any(word in task.lower() for word in ["sql", "database", "table", "select", "query", "create", "insert", "update", "delete", "alter", "index"]):
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result="Not a database query task",
                confidence=0.1,
                method="Task mismatch",
                explanation="This doesn't appear to be a database-related task."
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            # Ask LLM to write SQL query
            logger.info(f"[SQLAgent] Requesting SQL generation from LLM using model: {model}")
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a SQL expert.

You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted response explaining the SQL and what it does. Use markdown. This is displayed AS-IS.",
  "sql": "executable_sql_statements_here",
  "operation_type": "CREATE_TABLE | SELECT | INSERT | UPDATE | DELETE | ALTER_TABLE | CREATE_INDEX | CREATE_DATABASE",
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format it with markdown - explain what the SQL does, displayed AS-IS
- 'sql' field: Our code will EXTRACT and EXECUTE this SQL (no markdown fences, just SQL)
- 'operation_type' field: Type of SQL operation
- 'summary' field: Brief summary for logs
- No text outside the JSON object

SQL CAPABILITIES:
- CREATE DATABASE statements for new databases
- CREATE TABLE with proper schemas and constraints
- INSERT, UPDATE, DELETE for data manipulation
- SELECT queries with JOINs, aggregations, subqueries
- ALTER TABLE for schema modifications
- CREATE INDEX for performance optimization

AVAILABLE TABLES:
The project database includes a 'notes' table:
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  branch_id INTEGER NOT NULL,
  content TEXT NOT NULL,
  tags JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

REQUIREMENTS:
- Use SQLite/PostgreSQL compatible syntax
- Include proper constraints (PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE)
- For queries on notes table, you can search content, filter by tags, etc.

Example response:
{
  "answer": "**Query to find recent notes**\n\nThis SELECT query retrieves the 10 most recent notes, ordered by creation date.",
  "sql": "SELECT * FROM notes ORDER BY created_at DESC LIMIT 10;",
  "operation_type": "SELECT",
  "summary": "Query for 10 most recent notes"
}"""
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
                logger.error(f"[SQLAgent] Failed to parse JSON response: {e}")
                logger.error(f"[SQLAgent] Raw response: {full_response[:500]}")
                return AgentResult(
                    agent_name="SQLAgent",
                    display_name="SQL Agent",
                    result=f"**JSON Parse Error:**\n\nThe LLM returned invalid JSON.\n\n**Error:** {e}\n\n**Raw Response (truncated):**\n```\n{full_response[:500]}\n```",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse LLM response as JSON"
                )
            
            # Extract fields from JSON
            answer = response_data.get('answer', '').strip()
            generated_sql = response_data.get('sql', '').strip()
            operation_type = response_data.get('operation_type', 'SQL Operation').strip()
            summary = response_data.get('summary', '').strip()
            
            if not generated_sql:
                return AgentResult(
                    agent_name="SQLAgent",
                    display_name="SQL Agent",
                    result="**Missing SQL:**\n\nThe LLM response did not include executable SQL in the 'sql' field.",
                    confidence=0.1,
                    method="Missing sql field",
                    explanation="No SQL provided by LLM",
                    summary="No SQL generated"
                )
            
            if not summary:
                summary = f"Generated {operation_type} SQL for: {task[:100]}"
            
            logger.info(f"[SQLAgent] Generated SQL: {generated_sql}")
            logger.info(f"[SQLAgent] Operation type: {operation_type}")
            logger.info(f"[SQLAgent] LLM-provided answer:\n{answer[:200]}...")
            
            # Build formatted output: LLM's answer + SQL code block
            formatted_output = answer  # Use LLM's pre-formatted answer AS-IS
            formatted_output += f"\n\n**Generated SQL:**\n```sql\n{generated_sql}\n```"
            
            # Determine confidence based on operation type
            if operation_type in ['CREATE_TABLE', 'CREATE_DATABASE', 'CREATE_INDEX']:
                confidence = 0.9
            else:
                confidence = 0.85
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=formatted_output,
                confidence=confidence,
                method=f"LLM-generated {operation_type}",
                explanation=f"Generated {operation_type} SQL",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[SQLAgent] Error: {e}")
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=f"Answer: Failed to generate SQL\n\nError: {str(e)}\n\nSuggested Next Steps: Check your query syntax and try again",
                confidence=0.1,
                method="Error",
                explanation=f"SQL generation error: {str(e)[:100]}"
            )

# Export the execution agents
__all__ = ['AgentResult', 'ShellAgent', 'CodeAgent', 'SQLAgent']
