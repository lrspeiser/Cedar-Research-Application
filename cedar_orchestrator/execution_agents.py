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
from dataclasses import dataclass
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
    
class ShellAgent:
    """Agent that executes shell commands exactly as provided by the Chief Agent"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.conversation_history = []  # Store conversation context
        
    async def process(self, task: str, conversation_context: str = None) -> AgentResult:
        """Execute shell commands exactly as provided and analyze results
        
        Args:
            task: Either a shell command to execute or a request from Chief Agent with command
            conversation_context: Optional conversation history for context
        """
        start_time = time.time()
        logger.info(f"[ShellAgent] Starting shell execution for: {task[:200]}...")
        
        # The task should contain the exact shell command from the Chief Agent
        # Look for shell command in various formats
        shell_command = None
        
        # Pattern 1: Command in backticks `command`
        import re
        backtick_match = re.search(r'`([^`]+)`', task)
        
        # Pattern 2: Command after "Execute:" or "Run:" or "Command:"
        exec_match = re.search(r'(?:Execute|Run|Command):\s*(.+?)(?:\n|$)', task, re.IGNORECASE)
        
        # Pattern 3: Command in quotes after shell-related keywords
        quote_match = re.search(r'(?:run|execute|shell)\s+["\']([^"\']]+)["\']', task, re.IGNORECASE)
        
        # Pattern 4: The entire task is the command (if it starts with common shell commands)
        shell_commands = ['ls', 'cd', 'pwd', 'grep', 'find', 'cat', 'echo', 'pip', 'npm', 'brew', 'apt-get', 'chmod', 'mkdir', 'rm', 'cp', 'mv', 'curl', 'wget', 'git', 'docker', 'python', 'node']
        
        if backtick_match:
            shell_command = backtick_match.group(1).strip()
            logger.info(f"[ShellAgent] Extracted command from backticks: {shell_command}")
        elif exec_match:
            shell_command = exec_match.group(1).strip()
            logger.info(f"[ShellAgent] Extracted command after keyword: {shell_command}")
        elif quote_match:
            shell_command = quote_match.group(1).strip()
            logger.info(f"[ShellAgent] Extracted command from quotes: {shell_command}")
        elif any(task.strip().startswith(cmd) for cmd in shell_commands):
            shell_command = task.strip()
            logger.info(f"[ShellAgent] Using entire task as command: {shell_command}")
        else:
            # Last resort: if the task looks like it might be a command
            lines = task.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('//'):
                    # Check if line contains shell-like syntax
                    if any(cmd in line.lower() for cmd in shell_commands) or '|' in line or '>' in line or '&&' in line:
                        shell_command = line
                        logger.info(f"[ShellAgent] Found command-like line: {shell_command}")
                        break
        
        if not shell_command:
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result="""Answer: No executable shell command found

Error: The Shell Agent requires an exact shell command to execute. 

The Chief Agent should provide the command in one of these formats:
- In backticks: `ls -la`
- After a keyword: Execute: ls -la
- As a direct command: grep -r "pattern" /path

Suggested Next Steps: Please provide the exact shell command to execute.""",
                confidence=0.1,
                method="No command found",
                explanation="No shell command identified in the request"
            )
        
        # Store the command in history
        self.conversation_history.append({"command": shell_command, "timestamp": time.time()})
        
        # Execute the shell command
        logger.info(f"[ShellAgent] Executing command: {shell_command}")
        
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
            
            # Get output (keep more for analysis)
            output = result.stdout[:5000] if result.stdout else ""
            error = result.stderr[:2000] if result.stderr else ""
            exit_code = result.returncode
            
            # Build execution report
            execution_report = f"""Shell Command Execution Report
============================================
Command: {shell_command}
Working Directory: ~/Projects/cedarpy
Exit Code: {exit_code}
Execution Time: {time.time() - start_time:.2f}s
"""
            
            if output:
                execution_report += f"\nStandard Output:\n{'-' * 40}\n{output}\n"
            if error:
                execution_report += f"\nError Output:\n{'-' * 40}\n{error}\n"
            
            logger.info(f"[ShellAgent] Command completed with exit code: {exit_code}")
            
            # Analyze results with LLM
            analysis = ""
            suggested_followups = []
            
            if self.llm_client:
                try:
                    # Build context including conversation history if available
                    context = f"""You are analyzing shell command execution results.
                    
Conversation Context:
{conversation_context if conversation_context else 'No prior context provided'}

Previous Commands in Session:
{self._format_history()}

Analyze the results and provide:
1. A brief SUMMARY of what you did and key findings (2-3 sentences)
2. Details about what happened (success/failure)
2. Extract key information from the output
3. Identify any errors or warnings
4. Recommend specific follow-up shell commands if needed
5. Note if the original goal was achieved

Format follow-up commands exactly as they should be run."""
                    
                    model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
                    completion_params = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": context},
                            {"role": "user", "content": f"Command: {shell_command}\n\nExecution Report:\n{execution_report}"}
                        ]
                    }
                    if "gpt-5" in model:
                        completion_params["max_completion_tokens"] = 800
                    else:
                        completion_params["max_tokens"] = 800
                        completion_params["temperature"] = 0.2
                    
                    response = await self.llm_client.chat.completions.create(**completion_params)
                    analysis = response.choices[0].message.content.strip()
                    
                    # Extract summary if present (look for SUMMARY: or similar)
                    summary = ""
                    summary_match = re.search(r'SUMMARY[:\s]+(.+?)(?:\n\n|\n(?:[A-Z]|\d\.)|$)', analysis, re.IGNORECASE | re.DOTALL)
                    if summary_match:
                        summary = summary_match.group(1).strip()
                    else:
                        # Fallback: use first paragraph as summary
                        first_para = analysis.split('\n\n')[0] if '\n\n' in analysis else analysis.split('\n')[0]
                        summary = first_para[:200] + "..." if len(first_para) > 200 else first_para
                    
                    # Extract follow-up commands if mentioned
                    followup_matches = re.findall(r'`([^`]+)`', analysis)
                    if followup_matches:
                        suggested_followups = followup_matches
                    
                except Exception as e:
                    logger.warning(f"[ShellAgent] Failed to analyze results: {e}")
                    analysis = self._basic_analysis(shell_command, exit_code, output, error)
                    summary = f"Executed shell command '{shell_command}' with exit code {exit_code}"
            else:
                # Provide basic analysis without LLM
                analysis = self._basic_analysis(shell_command, exit_code, output, error)
                summary = f"Executed shell command '{shell_command}' with exit code {exit_code}"
            
            # Format the final response
            if exit_code == 0:
                status = "✅ Command executed successfully"
                confidence = 0.9
            else:
                status = f"❌ Command failed with exit code {exit_code}"
                confidence = 0.6
            
            # Build formatted output
            formatted_output = f"""Answer: {status}

**Executed Command:**
```bash
{shell_command}
```

**Analysis:**
{analysis}

**Execution Details:**
- Working Directory: ~/Projects/cedarpy
- Exit Code: {exit_code}
- Execution Time: {time.time() - start_time:.2f}s
"""
            
            # Add output preview
            if output:
                preview = output[:1000] + "..." if len(output) > 1000 else output
                formatted_output += f"\n**Output Preview:**\n```\n{preview}\n```\n"
            
            if error:
                error_preview = error[:500] + "..." if len(error) > 500 else error
                formatted_output += f"\n**Error Output:**\n```\n{error_preview}\n```\n"
            
            # Add follow-up suggestions
            if suggested_followups:
                formatted_output += "\n**Suggested Follow-up Commands:**\n"
                for cmd in suggested_followups[:3]:  # Limit to 3 suggestions
                    formatted_output += f"- `{cmd}`\n"
            
            formatted_output += "\nWhy: Direct shell command execution with full system access\n"
            formatted_output += "\nSuggested Next Steps: "
            
            if exit_code == 0:
                if suggested_followups:
                    formatted_output += "Run the suggested follow-up commands to continue."
                else:
                    formatted_output += "The command succeeded. Review the output for the information you need."
            else:
                formatted_output += "Review the error message and adjust the command as needed."
            
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=formatted_output,
                confidence=confidence,
                method=f"Shell execution (exit code: {exit_code})",
                explanation=f"Executed: {shell_command[:50]}{'...' if len(shell_command) > 50 else ''}",
                summary=summary if 'summary' in locals() else f"Executed shell command '{shell_command[:50]}{'...' if len(shell_command) > 50 else ''}' with {'success' if exit_code == 0 else f'exit code {exit_code}'}"
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"[ShellAgent] Command timed out: {shell_command}")
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=f"""Answer: ⏱️ Command timed out after 60 seconds

**Command:** `{shell_command}`

**Why:** The command took too long to execute and was terminated

**Suggested Next Steps:**
- Try adding output redirection or limiting the scope (e.g., `grep -r "pattern" . --include="*.py"`)
- Use `head` or `tail` to limit output (e.g., `command | head -100`)
- Run the command with `&` to run in background if it's a long process""",
                confidence=0.3,
                method="Timeout",
                explanation="Command timed out",
                summary=f"Command '{shell_command[:50]}{'...' if len(shell_command) > 50 else ''}' timed out after 60 seconds"
            )
        except Exception as e:
            logger.error(f"[ShellAgent] Execution error: {e}")
            return AgentResult(
                agent_name="ShellAgent",
                display_name="Shell Executor",
                result=f"""Answer: ❌ Failed to execute command

**Command:** `{shell_command}`

**Error:** {str(e)}

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
    
    def _format_history(self) -> str:
        """Format command history for context"""
        if not self.conversation_history:
            return "No previous commands in this session"
        
        history_lines = []
        for i, entry in enumerate(self.conversation_history[-5:], 1):  # Last 5 commands
            cmd = entry.get('command', 'Unknown')
            history_lines.append(f"{i}. {cmd}")
        
        return "\n".join(history_lines)
    
    def _basic_analysis(self, command: str, exit_code: int, output: str, error: str) -> str:
        """Provide basic analysis without LLM"""
        analysis = []
        
        if exit_code == 0:
            analysis.append("The command completed successfully.")
            if output:
                lines = output.strip().split('\n')
                analysis.append(f"Generated {len(lines)} lines of output.")
                # Try to identify common patterns
                if 'successfully installed' in output.lower():
                    analysis.append("Package installation completed.")
                elif re.search(r'\d+ files?', output):
                    match = re.search(r'(\d+) files?', output)
                    analysis.append(f"Found or processed {match.group(1)} file(s).")
        else:
            analysis.append(f"The command failed with exit code {exit_code}.")
            if 'command not found' in error.lower():
                analysis.append("The command or program is not installed or not in PATH.")
            elif 'permission denied' in error.lower():
                analysis.append("Permission denied. You may need elevated privileges.")
            elif 'no such file or directory' in error.lower():
                analysis.append("File or directory not found. Check the path.")
            
        return " ".join(analysis)

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
            # Use correct parameter name based on model
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system", 
                        "content": """You are a Python code generator. Your response should have two parts:
                        
                        1. SUMMARY: A brief 2-3 sentence description of what the code does and key computations/operations
                        
                        2. CODE: The executable Python code (no markdown, just raw Python)
                        
                        Requirements for the code:
                        - The code should print the final result
                        - Use proper error handling
                        - For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10))
                        - The code must be complete and runnable as-is
                        
                        Format:
                        SUMMARY: [Your summary here]
                        
                        [Your Python code here]"""
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            # GPT-5 models have different parameters
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 500
                # GPT-5 doesn't support custom temperature
            else:
                completion_params["max_tokens"] = 500
                completion_params["temperature"] = 0.1
            
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
            
            # Extract summary and code
            summary = ""
            generated_code = full_response
            
            # Look for SUMMARY section
            if "SUMMARY:" in full_response:
                parts = full_response.split("SUMMARY:", 1)[1]
                if "\n\n" in parts:
                    summary_part, code_part = parts.split("\n\n", 1)
                    summary = summary_part.strip()
                    generated_code = code_part.strip()
                elif "\n" in parts:
                    lines = parts.split("\n")
                    # Find where code starts (non-empty line after summary)
                    for i, line in enumerate(lines):
                        if i > 0 and line.strip() and not line.startswith("SUMMARY"):
                            summary = lines[0].strip()
                            generated_code = "\n".join(lines[i:]).strip()
                            break
            
            # Remove markdown code blocks if present in code
            if generated_code.startswith("```"):
                generated_code = generated_code.split("\n", 1)[1]
                if generated_code.endswith("```"):
                    generated_code = generated_code.rsplit("```", 1)[0]
            
            # Fallback summary if not extracted
            if not summary:
                summary = f"Generated and executed Python code to solve: {task[:100]}"
            
            logger.info(f"[CodeAgent] Generated code:\n{generated_code}")
            
            # Show the code that will be executed
            code_preview = f"**Code to execute:**\n```python\n{generated_code}\n```\n\n"
            
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
                
                # Format output for user with structured sections
                answer = output.strip() if output else 'Code executed successfully'
                formatted_output = f"""{code_preview}Answer: {answer}

Why: Generated and executed Python code to compute the exact result"""
                
                if errors:
                    formatted_output += f"\n\nPotential Issues: {errors}"
                    formatted_output += f"\n\nSuggested Next Steps: Review the error messages and adjust the query if needed"
                
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result=formatted_output,
                    confidence=0.95 if output else 0.5,
                    method="LLM-generated and executed Python code",
                    explanation=f"Generated and executed Python code",
                    summary=summary
                )
                
            except Exception as exec_error:
                logger.error(f"[CodeAgent] Code execution error: {exec_error}")
                formatted_output = f"""{code_preview}Answer: Unable to complete the calculation due to an error

**Execution Error:** {str(exec_error)}

Why: The generated code encountered an execution error

Potential Issues: The code failed during execution - see error above

Suggested Next Steps: Review the code and error, then provide a more specific query"""
                
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Coding Agent",
                    result=formatted_output,
                    confidence=0.3,
                    method="LLM code generation with execution error",
                    explanation=f"Code execution error",
                    summary=summary if 'summary' in locals() else f"Failed to execute generated code: {str(exec_error)[:100]}",
                    needs_rerun=True,
                    rerun_reason=f"Execution error: {str(exec_error)[:100]}"
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
            # Use correct parameter name based on model
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a SQL expert. Generate SQL for database operations including:
                        - CREATE DATABASE statements for new databases
                        - CREATE TABLE statements with proper schemas and constraints
                        - INSERT, UPDATE, DELETE operations for data manipulation
                        - SELECT queries with JOINs, aggregations, and subqueries
                        - ALTER TABLE for schema modifications
                        - CREATE INDEX for performance optimization
                        
                        IMPORTANT: The project database includes a 'notes' table with the following schema:
                        CREATE TABLE notes (
                          id INTEGER PRIMARY KEY,
                          project_id INTEGER NOT NULL,
                          branch_id INTEGER NOT NULL,
                          content TEXT NOT NULL,
                          tags JSON,  -- list of strings
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        
                        You can query the notes table to search for saved notes, agent findings, and research results.
                        Example: SELECT * FROM notes WHERE content LIKE '%keyword%' ORDER BY created_at DESC;
                        
                        - Output ONLY the SQL statements, no explanations
                        - Use standard SQL syntax (SQLite/PostgreSQL compatible)
                        - Include proper constraints (PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE)
                        - For CREATE TABLE, include appropriate data types and relationships"""
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            # GPT-5 models have different parameters
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 300
            else:
                completion_params["max_tokens"] = 300
                completion_params["temperature"] = 0.1
                
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            generated_sql = response.choices[0].message.content.strip()
            # Remove markdown if present
            if generated_sql.startswith("```"):
                generated_sql = generated_sql.split("\n", 1)[1]
                if generated_sql.endswith("```"):
                    generated_sql = generated_sql.rsplit("```", 1)[0]
            
            logger.info(f"[SQLAgent] Generated SQL: {generated_sql}")
            
            # Determine the type of SQL operation
            sql_upper = generated_sql.upper()
            if "CREATE DATABASE" in sql_upper:
                operation_type = "Database Creation"
            elif "CREATE TABLE" in sql_upper:
                operation_type = "Table Creation"
            elif "INSERT" in sql_upper:
                operation_type = "Data Insertion"
            elif "UPDATE" in sql_upper:
                operation_type = "Data Update"
            elif "DELETE" in sql_upper:
                operation_type = "Data Deletion"
            elif "ALTER TABLE" in sql_upper:
                operation_type = "Schema Modification"
            elif "CREATE INDEX" in sql_upper:
                operation_type = "Index Creation"
            elif "SELECT" in sql_upper:
                operation_type = "Data Query"
            else:
                operation_type = "SQL Operation"
            
            # Show the SQL that was generated
            sql_preview = f"**SQL Generated:**\n```sql\n{generated_sql}\n```\n\n"
            
            formatted_output = f"""{sql_preview}Answer: Generated {operation_type} SQL for your request

Why: Translated your request into executable SQL statements

Suggested Next Steps: 
- Review the SQL for correctness
- Execute in your database environment
- For CREATE operations, ensure database permissions
- For data modifications, consider using transactions"""
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=formatted_output,
                confidence=0.9 if "CREATE" in sql_upper else 0.85,
                method=f"LLM-generated {operation_type}",
                explanation=f"Generated {operation_type} SQL",
                summary=f"Generated {operation_type} SQL for {task[:50]}{'...' if len(task) > 50 else ''}"
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
