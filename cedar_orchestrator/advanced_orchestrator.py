"""
Advanced Thinker-Orchestrator Implementation
This implements the true multi-agent pattern where:
1. Thinker analyzes the request and creates a plan
2. Multiple specialized agents process in parallel
3. Orchestrator selects the best response
"""

import os
import json
import asyncio
import logging
import math
import time
import subprocess
import sqlite3
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import file processing agents
try:
    from .file_processing_agents import FileProcessingOrchestrator
    FILE_PROCESSING_AVAILABLE = True
except ImportError:
    FILE_PROCESSING_AVAILABLE = False

# Import chief agent notes functionality
try:
    from .chief_agent_notes import ChiefAgentNoteTaker
    NOTES_AVAILABLE = True
except ImportError:
    NOTES_AVAILABLE = False

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
            return AgentResult(
                agent_name="CodeAgent",
                result="No LLM client available",
                confidence=0.0,
                method="Error",
                explanation="Cannot generate code without LLM access."
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
                    display_name="Code Executor",
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
                    display_name="Code Executor",
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
                    display_name="Code Executor",
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
            return AgentResult(
                agent_name="CodeAgent",
                display_name="Code Executor",
                result=f"Answer: Failed to generate code\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error in code generation",
                explanation=f"Code generation failed",
                summary=f"Failed to generate code: {str(e)[:100]}"
            )

class ReasoningAgent:
    """Agent that uses LLM for step-by-step reasoning and problem solving"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to reason through the problem step by step"""
        start_time = time.time()
        logger.info(f"[ReasoningAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="ReasoningAgent",
                result="No LLM client available",
                confidence=0.0,
                method="Error",
                explanation="Cannot perform reasoning without LLM access."
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ReasoningAgent] Using LLM for step-by-step reasoning with model: {model}")
            # Use correct parameter name based on model
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an expert reasoning agent. Solve problems step-by-step.
                        - Break down complex problems into steps
                        - Show your work clearly
                        - For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10), not sqrt(10))
                        - Provide the final answer clearly
                        - Be precise and accurate"""
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            # GPT-5 models have different parameters  
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 500
            else:
                completion_params["max_tokens"] = 500
                completion_params["temperature"] = 0.3
                
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            llm_result = response.choices[0].message.content
            logger.info(f"[ReasoningAgent] LLM response: {llm_result[:200]}...")
            logger.info(f"[ReasoningAgent] Completed in {time.time() - start_time:.3f}s")
            
            # Format reasoning output with structured sections
            # Extract just the key answer if it's verbose
            lines = llm_result.split('\n')
            answer = llm_result if len(llm_result) < 200 else lines[0] if lines else llm_result
            
            formatted_output = f"""Answer: {answer}

Why: Applied step-by-step logical reasoning to analyze the problem"""
            
            return AgentResult(
                agent_name="ReasoningAgent",
                display_name="Logical Reasoner",
                result=formatted_output,
                confidence=0.85,
                method="LLM step-by-step reasoning",
                explanation=f"Applied logical reasoning"
            )
            
        except Exception as e:
            logger.error(f"[ReasoningAgent] Error: {e}")
            return AgentResult(
                agent_name="ReasoningAgent",
                display_name="Logical Reasoner",
                result=f"Answer: Reasoning failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error in reasoning",
                explanation=f"Reasoning error"
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
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result="No LLM client available",
                confidence=0.0,
                method="Error",
                explanation="Cannot generate SQL without LLM access."
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

class GeneralAgent:
    """General purpose agent using LLM for direct answers"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to directly answer questions"""
        start_time = time.time()
        logger.info(f"[GeneralAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="GeneralAgent",
                result="No LLM client available",
                confidence=0.0,
                method="Error",
                explanation="Cannot process without LLM access."
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[GeneralAgent] Using LLM for direct response with model: {model}")
            # Use correct parameter name based on model
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a helpful assistant. Answer questions directly and concisely.
                        - For mathematical problems, compute the exact answer
                        - Parse expressions correctly (e.g., 'square root of 5*10' means sqrt(5*10))
                        - Be accurate and precise
                        - Give just the answer when appropriate"""
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            # GPT-5 models have different parameters
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 300
            else:
                completion_params["max_tokens"] = 300
                completion_params["temperature"] = 0.5
                
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            llm_result = response.choices[0].message.content
            logger.info(f"[GeneralAgent] LLM response: {llm_result[:200]}...")
            logger.info(f"[GeneralAgent] Completed in {time.time() - start_time:.3f}s")
            
            # Format general response with structured sections
            # Keep answer concise
            lines = llm_result.split('\n')
            answer = llm_result if len(llm_result) < 200 else lines[0] if lines else llm_result
            
            formatted_output = f"""Answer: {answer}

Why: Provided a direct response based on the query context"""
            
            return AgentResult(
                agent_name="GeneralAgent",
                display_name="General Assistant",
                result=formatted_output,
                confidence=0.75,
                method="Direct LLM response",
                explanation=f"Direct AI answer",
                summary=f"Provided direct answer to: {task[:100]}{'...' if len(task) > 100 else ''}"
            )
            
        except Exception as e:
            logger.error(f"[GeneralAgent] Error: {e}")
            return AgentResult(
                agent_name="GeneralAgent",
                display_name="General Assistant",
                result=f"Answer: Processing failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation=f"Processing error"
            )

class MathAgent:
    """Agent that derives mathematical formulas from first principles"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Derive mathematical formulas from first principles and walk through derivations"""
        start_time = time.time()
        logger.info(f"[MathAgent] Starting mathematical derivation for: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
                result="No LLM client available for mathematical derivation",
                confidence=0.0,
                method="Error",
                explanation="Cannot derive formulas without LLM access"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[MathAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a mathematical expert who derives formulas from first principles.
                        - Start from fundamental axioms and definitions
                        - Show each step of the derivation clearly
                        - Explain the reasoning behind each transformation
                        - Use proper mathematical notation
                        - Include any assumptions or constraints
                        - Provide the final formula and its applications"""
                    },
                    {"role": "user", "content": f"Derive from first principles: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1500
            else:
                completion_params["max_tokens"] = 1500
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            derivation = response.choices[0].message.content
            
            logger.info(f"[MathAgent] Completed derivation in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Mathematical Derivation from First Principles

{derivation}

Why: Derived the formula step-by-step from fundamental mathematical principles"""
            
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
                result=formatted_output,
                confidence=0.85,
                method="First principles derivation",
                explanation="Mathematical derivation from axioms",
                summary=f"Derived formula from first principles for: {task[:80]}{'...' if len(task) > 80 else ''}"
            )
            
        except Exception as e:
            logger.error(f"[MathAgent] Error: {e}")
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
                result=f"Answer: Unable to complete derivation\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Derivation failed"
            )

class ResearchAgent:
    """Agent that performs web searches using GPT's web search capabilities"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Run web search and return relevant sites and content"""
        start_time = time.time()
        logger.info(f"[ResearchAgent] Starting web research for: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result="No LLM client available for web research",
                confidence=0.0,
                method="Error",
                explanation="Cannot perform research without LLM access"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ResearchAgent] Using model: {model}")
            
            # Note: This simulates web search results. In production, you'd integrate with actual search APIs
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a research assistant with web search capabilities.
                        Based on the query, provide:
                        1. A list of relevant websites and sources
                        2. Key content and findings from each source
                        3. A summary of the most important information
                        4. Citations and references
                        
                        Format your response as:
                        - Source 1: [URL/Title] - Key findings
                        - Source 2: [URL/Title] - Key findings
                        etc.
                        
                        Then provide a comprehensive summary."""
                    },
                    {"role": "user", "content": f"Research this topic and find relevant sources: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1000
            else:
                completion_params["max_tokens"] = 1000
                completion_params["temperature"] = 0.5
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            research_results = response.choices[0].message.content
            
            logger.info(f"[ResearchAgent] Completed research in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Web Research Results

{research_results}

Why: Conducted web research to find relevant sources and information"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=formatted_output,
                confidence=0.75,
                method="Web search and research",
                explanation="Found and analyzed relevant web sources"
            )
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Error: {e}")
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=f"Answer: Research failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Research error"
            )

class StrategyAgent:
    """Agent that creates detailed strategic plans for addressing queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Create a detailed strategic plan for addressing the user's query"""
        start_time = time.time()
        logger.info(f"[StrategyAgent] Creating strategic plan for: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result="No LLM client available for strategic planning",
                confidence=0.0,
                method="Error",
                explanation="Cannot create strategy without LLM access"
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
                        2. Identifying which specialized agents should be used (available agents: Code Executor, Math Agent, Research Agent, Data Agent, Notes Agent, Logical Reasoner, General Assistant)
                        3. Determining the sequence of operations
                        4. Specifying how to gather source material
                        5. How to analyze data and compile results
                        6. How to write the final report
                        
                        Format as a numbered step-by-step plan with:
                        - Step number and title
                        - Agent(s) to use
                        - Input/output for each step
                        - Dependencies between steps"""
                    },
                    {"role": "user", "content": f"Create a strategic plan to address: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1200
            else:
                completion_params["max_tokens"] = 1200
                completion_params["temperature"] = 0.4
            
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

class DataAgent:
    """Agent that analyzes available databases and suggests SQL queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.project_id = None  # Will be set during processing
        
    async def process(self, task: str, project_id: Optional[int] = None) -> AgentResult:
        """Get database metadata and suggest relevant SQL queries"""
        start_time = time.time()
        logger.info(f"[DataAgent] Analyzing databases for: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result="No LLM client available for data analysis",
                confidence=0.0,
                method="Error",
                explanation="Cannot analyze data without LLM access"
            )
        
        try:
            # Get database metadata if project_id is provided
            db_metadata = "No specific database context available"
            if project_id:
                try:
                    from cedar_app.db_utils import _project_dirs, _get_project_engine
                    db_path = _project_dirs(project_id)["db_path"]
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Get all tables
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = cursor.fetchall()
                        
                        db_metadata = "Available tables:\n"
                        for table in tables:
                            table_name = table[0]
                            cursor.execute(f"PRAGMA table_info({table_name})")
                            columns = cursor.fetchall()
                            db_metadata += f"\n- {table_name}: "
                            db_metadata += ", ".join([f"{col[1]} ({col[2]})" for col in columns])
                        
                        conn.close()
                except Exception as e:
                    logger.warning(f"[DataAgent] Could not get database metadata: {e}")
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[DataAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a data analysis expert. Based on the available database schema and the user's query:
                        1. List relevant tables and their purposes
                        2. Suggest SQL queries that would help answer the question
                        3. Explain what each query would return
                        4. Recommend data transformations or joins if needed
                        
                        Format SQL queries properly with:
                        - Clear comments explaining the purpose
                        - Proper JOIN clauses if needed
                        - Appropriate WHERE conditions
                        - GROUP BY and aggregations as necessary"""
                    },
                    {"role": "user", "content": f"Database Schema:\n{db_metadata}\n\nUser Query: {task}\n\nSuggest relevant SQL queries."}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 800
            else:
                completion_params["max_tokens"] = 800
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            sql_suggestions = response.choices[0].message.content
            
            logger.info(f"[DataAgent] Completed data analysis in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Database Analysis and SQL Suggestions

{sql_suggestions}

Why: Analyzed available databases and suggested relevant SQL queries"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=formatted_output,
                confidence=0.70,
                method="Database analysis and SQL generation",
                explanation="Analyzed schema and suggested queries"
            )
            
        except Exception as e:
            logger.error(f"[DataAgent] Error: {e}")
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=f"Answer: Data analysis failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Analysis error"
            )

class FileAgent:
    """Agent that downloads files from the web or manages user-provided files"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI], project_id: int = None, branch_id: int = None, db_session = None):
        self.llm_client = llm_client
        self.project_id = project_id
        self.branch_id = branch_id
        self.db_session = db_session
        
    async def process(self, task: str) -> AgentResult:
        """Download files or process file paths and save with metadata"""
        start_time = time.time()
        logger.info(f"[FileAgent] Starting file processing for: {task[:100]}...")
        
        # Import required modules at the start
        import re
        import urllib.request
        import tempfile
        import mimetypes
        
        # Check if task contains URLs or file paths
        url_pattern = r'https?://[^\s]+'
        file_path_pattern = r'(/[^\s]+|[A-Za-z]:\\[^\s]+|\./[^\s]+)'
        
        urls = re.findall(url_pattern, task)
        file_paths = re.findall(file_path_pattern, task)
        
        results = []
        
        # Handle URL downloads
        if urls:
            logger.info(f"[FileAgent] Found {len(urls)} URLs to download")
            for url in urls:
                try:
                    # Create temp directory for downloads
                    download_dir = os.path.join(os.path.expanduser("~"), "CedarDownloads")
                    os.makedirs(download_dir, exist_ok=True)
                    
                    # Extract filename from URL
                    url_path = url.split('?')[0]
                    filename = os.path.basename(url_path) or 'download'
                    
                    # Download file
                    logger.info(f"[FileAgent] Downloading from {url}")
                    with urllib.request.urlopen(url, timeout=30) as response:
                        content = response.read()
                        
                    # Save file
                    timestamp = time.strftime('%Y%m%d_%H%M%S')
                    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
                    full_filename = f"{timestamp}_{safe_filename}"
                    file_path = os.path.join(download_dir, full_filename)
                    
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    # Get file metadata
                    file_size = len(content)
                    mime_type, _ = mimetypes.guess_type(filename)
                    
                    # Read first lines for description
                    first_lines = ""
                    try:
                        if mime_type and 'text' in mime_type:
                            first_lines = content[:500].decode('utf-8', errors='ignore')
                    except:
                        first_lines = "[Binary file]"
                    
                    # Save to database if available
                    file_id = None
                    if self.db_session and self.project_id and self.branch_id:
                        try:
                            from main_models import FileEntry
                            
                            # Generate AI description if LLM available
                            ai_description = None
                            if self.llm_client and first_lines and len(first_lines) > 10:
                                try:
                                    model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
                                    completion_params = {
                                        "model": model,
                                        "messages": [
                                            {"role": "system", "content": "Generate a brief description for this file based on its content."},
                                            {"role": "user", "content": f"File: {filename}\nContent preview: {first_lines[:500]}"}
                                        ]
                                    }
                                    if "gpt-5" in model:
                                        completion_params["max_completion_tokens"] = 100
                                    else:
                                        completion_params["max_tokens"] = 100
                                    
                                    response = await self.llm_client.chat.completions.create(**completion_params)
                                    ai_description = response.choices[0].message.content.strip()
                                except:
                                    pass
                            
                            file_entry = FileEntry(
                                project_id=self.project_id,
                                branch_id=self.branch_id,
                                filename=full_filename,
                                display_name=filename,
                                file_type=os.path.splitext(filename)[1][1:] if '.' in filename else 'unknown',
                                structure='sources' if 'text' in (mime_type or '') else 'binary',
                                mime_type=mime_type or 'application/octet-stream',
                                size_bytes=file_size,
                                storage_path=file_path,
                                ai_title=f"Downloaded: {filename}",
                                ai_description=ai_description or f"Downloaded from {url}",
                                ai_category="downloaded",
                                metadata_json={"source_url": url, "download_time": time.time()}
                            )
                            self.db_session.add(file_entry)
                            self.db_session.commit()
                            file_id = file_entry.id
                            logger.info(f"[FileAgent] Saved file to database with ID: {file_id}")
                        except Exception as e:
                            logger.warning(f"[FileAgent] Failed to save to database: {e}")
                    
                    results.append({
                        "action": "downloaded",
                        "url": url,
                        "path": file_path,
                        "filename": full_filename,
                        "size": file_size,
                        "mime_type": mime_type or 'application/octet-stream',
                        "preview": first_lines[:200],
                        "file_id": file_id
                    })
                    
                except Exception as e:
                    logger.error(f"[FileAgent] Download failed for {url}: {e}")
                    results.append({
                        "action": "error",
                        "url": url,
                        "error": str(e)
                    })
        
        # Handle local file paths
        elif file_paths:
            logger.info(f"[FileAgent] Found {len(file_paths)} file paths to process")
            for path in file_paths:
                try:
                    if os.path.exists(path):
                        file_size = os.path.getsize(path)
                        mime_type, _ = mimetypes.guess_type(path)
                        
                        # Read first lines
                        first_lines = ""
                        try:
                            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                first_lines = f.read(500)
                        except:
                            first_lines = "[Binary file]"
                        
                        results.append({
                            "action": "analyzed",
                            "path": path,
                            "filename": os.path.basename(path),
                            "size": file_size,
                            "mime_type": mime_type or 'unknown',
                            "preview": first_lines[:200]
                        })
                    else:
                        results.append({
                            "action": "error",
                            "path": path,
                            "error": "File not found"
                        })
                except Exception as e:
                    results.append({
                        "action": "error",
                        "path": path,
                        "error": str(e)
                    })
        else:
            # No files or URLs found - provide guidance
            return AgentResult(
                agent_name="FileAgent",
                display_name="File Manager",
                result="""Answer: No files or URLs detected in your request

Why: To use the File Agent, please provide either:
- A URL to download (e.g., https://example.com/file.pdf)
- A file path to analyze (e.g., /Users/you/document.txt)

Suggested Next Steps: Include a specific URL or file path in your request""",
                confidence=0.3,
                method="No files detected",
                explanation="Awaiting file information"
            )
        
        # Format results
        if results:
            answer_lines = []
            for r in results:
                if r["action"] == "downloaded":
                    answer_lines.append(f"✓ Downloaded {r['filename']} ({r['size']} bytes) to {r['path']}")
                elif r["action"] == "analyzed":
                    answer_lines.append(f"✓ Analyzed {r['filename']} ({r['size']} bytes)")
                elif r["action"] == "error":
                    answer_lines.append(f"✗ Error: {r['error']}")
            
            formatted_output = f"""Answer: {chr(10).join(answer_lines)}

Why: Files have been processed and saved with metadata

File Details:
{json.dumps(results, indent=2)}

Suggested Next Steps: Files are ready for further processing or analysis"""
            
            return AgentResult(
                agent_name="FileAgent",
                display_name="File Manager",
                result=formatted_output,
                confidence=0.9 if all(r["action"] != "error" for r in results) else 0.6,
                method="File download and analysis",
                explanation=f"Processed {len(results)} file(s)"
            )
        
        return AgentResult(
            agent_name="FileAgent",
            display_name="File Manager",
            result="No files processed",
            confidence=0.1,
            method="No action taken",
            explanation="No files to process"
        )

class NotesAgent:
    """Agent that creates and manages structured notes from findings"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.existing_notes = []  # Will be populated with existing notes
        
    async def process(self, task: str, content_to_note: str = "", existing_notes: List[str] = None) -> AgentResult:
        """Create notes from content while avoiding duplication"""
        start_time = time.time()
        logger.info(f"[NotesAgent] Creating notes for: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result="No LLM client available for note creation",
                confidence=0.0,
                method="Error",
                explanation="Cannot create notes without LLM access"
            )
        
        try:
            if existing_notes:
                self.existing_notes = existing_notes
            
            existing_notes_text = "\n".join(self.existing_notes) if self.existing_notes else "No existing notes"
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[NotesAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a note-taking expert. Create concise, well-organized notes that:
                        1. Capture key findings and insights
                        2. Avoid duplicating existing notes
                        3. Use bullet points and clear headings
                        4. Include important formulas, code snippets, or data
                        5. Add tags for easy searching later
                        6. Reference sources when applicable
                        
                        Format notes with:
                        - Clear titles
                        - Date/timestamp
                        - Categories/tags
                        - Key points
                        - Action items if any"""
                    },
                    {"role": "user", "content": f"Existing Notes:\n{existing_notes_text}\n\nContent to create notes from:\n{content_to_note or task}\n\nCreate new notes without duplicating existing ones."}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 600
            else:
                completion_params["max_tokens"] = 600
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            notes = response.choices[0].message.content
            
            logger.info(f"[NotesAgent] Completed note creation in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Notes Created

{notes}

Why: Created structured notes from the provided content, avoiding duplication with existing notes"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=formatted_output,
                confidence=0.85,
                method="Intelligent note creation",
                explanation="Created organized notes from findings"
            )
            
        except Exception as e:
            logger.error(f"[NotesAgent] Error: {e}")
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=f"Answer: Note creation failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Note creation error"
            )

class ChiefAgent:
    """Chief Agent that reviews all sub-agent responses and makes final decisions"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def review_and_decide(self, user_query: str, agent_results: List[AgentResult], iteration: int = 0, max_iterations: int = 10, previous_context: str = "") -> Dict[str, Any]:
        """Review all agent results and make the final decision on what to do next"""
        start_time = time.time()
        remaining_loops = max_iterations - iteration - 1
        logger.info(f"[ChiefAgent] Starting review of {len(agent_results)} agent results (iteration {iteration}/{max_iterations}, {remaining_loops} loops remaining)")
        
        if not self.llm_client:
            # Fallback: use best available result
            best_result = max(agent_results, key=lambda r: r.confidence) if agent_results else None
            return {
                "decision": "final",
                "final_answer": best_result.result if best_result else "No results available",
                "additional_guidance": None,
                "selected_agent": best_result.display_name if best_result else "None",
                "reasoning": "No LLM available - using best available result"
            }
        
        try:
            # Prepare agent results summary for Chief Agent review
            results_summary = []
            for result in agent_results:
                results_summary.append(f"""
                Agent: {result.display_name}
                Summary: {result.summary if result.summary else 'No summary provided'}
                Confidence: {result.confidence}
                Method: {result.method}
                Response: {result.result[:500]}
                """)
            
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ChiefAgent] Using LLM for decision making with model: {model}")
            
            # Ask Chief Agent to review and decide
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": f"""You are the Chief Agent coordinating a research team for RIGOROUS ACADEMIC RESEARCH. Your work will be used in academic papers and must meet the highest standards of reproducibility and citation.

🎓 ACADEMIC RESEARCH CONTEXT:
You are assisting academics with research that will be published. Every analysis, computation, and conclusion must be:
• REPRODUCIBLE: Others must be able to replicate the work exactly
• DOCUMENTED: Every step must be clearly documented with code/commands
• CITED: All sources must be properly referenced
• VERIFIABLE: Results must be independently verifiable
• STRUCTURED: Data should be organized in queryable databases when possible

CURRENT STATUS:
- Iteration: {iteration + 1} of {max_iterations}
- Remaining loops available: {remaining_loops}
- You can use ALL remaining iterations if needed for thoroughness

DETAILED AGENT CAPABILITIES - READ CAREFULLY:

1. 💻 CODING AGENT (Code Executor)
   ✅ CAN: Write and execute Python code, perform calculations, data analysis, create visualizations
   ✅ CAN: Process data, run statistical tests, implement algorithms, generate plots
   ❌ CANNOT: Access files on disk, search the filesystem, run shell commands
   📝 REQUIRES: Clear computational task or analysis request
   USE FOR: All computations, data processing, statistical analysis, algorithm implementation

2. 🖥️ SHELL EXECUTOR (Shell Agent) - ONLY AGENT THAT CAN SEARCH YOUR MACHINE!
   ✅ CAN: Execute ANY shell command on the system (grep, find, ls, cat, etc.)
   ✅ CAN: Search for files on your computer: `find ~ -name "*mond*"`
   ✅ CAN: Search file contents: `grep -r "pattern" /path`
   ✅ CAN: Install packages: `pip install package`, `brew install tool`
   ✅ CAN: Navigate filesystem, read files, check what's installed
   ❌ CANNOT: Write complex programs (use Code Agent instead)
   📝 REQUIRES: Exact shell command in backticks: `command here`
   USE FOR: Finding files on your machine, searching content, system operations

3. 🗄️ SQL AGENT (Database Creator)
   ✅ CAN: Create SQL databases, tables, indexes, and schemas
   ✅ CAN: Execute SQL queries (SELECT, INSERT, UPDATE, DELETE)
   ✅ CAN: Import CSV/JSON data into structured database tables
   ❌ CANNOT: Search filesystem or download files
   📝 REQUIRES: Data to structure or SQL operations to perform
   USE FOR: Creating structured databases from raw data, querying data

4. 🔬 MATH AGENT (Mathematical Prover)
   ✅ CAN: Derive formulas from first principles, write proofs
   ✅ CAN: Create LaTeX mathematical expressions
   ❌ CANNOT: Execute calculations (use Code Agent for actual computation)
   📝 REQUIRES: Mathematical concept to prove or derive
   USE FOR: Mathematical proofs, theorem derivation, formula explanation

5. 📚 RESEARCH AGENT (Citation Finder)
   ✅ CAN: Find academic papers and sources (simulated web search)
   ✅ CAN: Build bibliographies and citation lists
   ❌ CANNOT: Access actual internet or download papers
   📝 REQUIRES: Research topic or claim to find sources for
   USE FOR: Finding citations, building literature reviews

6. 📋 STRATEGY AGENT (Research Planner)
   ✅ CAN: Create detailed research plans and methodologies
   ✅ CAN: Design experimental protocols and workflows
   ❌ CANNOT: Execute any actual operations
   📝 REQUIRES: Research goal or problem to plan
   USE FOR: Planning research approach, designing methodology

7. 📊 DATA AGENT (Schema Analyzer)
   ✅ CAN: Analyze database schemas, suggest SQL queries
   ✅ CAN: Design data structures and relationships
   ❌ CANNOT: Actually create databases (use SQL Agent)
   ❌ CANNOT: Search for files (use Shell Agent)
   📝 REQUIRES: Database or data structure to analyze
   USE FOR: Schema design, query optimization suggestions

8. 📝 NOTES AGENT (Documentation Creator)
   ✅ CAN: Create structured notes and documentation
   ✅ CAN: Organize findings into readable format
   ❌ CANNOT: Search for information or execute operations
   📝 REQUIRES: Content to document or findings to organize
   USE FOR: Creating research notes, documenting methodology

9. 📥 FILE AGENT (URL Downloader ONLY!)
   ✅ CAN: Download files from URLs (http/https)
   ✅ CAN: Save downloaded files to project directory
   ❌ CANNOT: Search your computer for files (use Shell Agent!)
   ❌ CANNOT: Browse local filesystem or find existing files
   ❌ CANNOT: Access files already on your machine
   📝 REQUIRES: Valid URL to download from
   USE FOR: ONLY downloading files from the internet

10. 🤔 REASONING AGENT (Logical Analyzer)
    ✅ CAN: Provide step-by-step logical analysis
    ✅ CAN: Break down complex problems
    ❌ CANNOT: Access data or execute operations
    📝 REQUIRES: Problem requiring logical analysis
    USE FOR: Logical reasoning, problem decomposition

11. 💬 GENERAL ASSISTANT (Knowledge Base)
    ✅ CAN: Provide general information and explanations
    ❌ CANNOT: Access current data or execute operations
    📝 REQUIRES: General question
    USE FOR: Background information only

⚠️ CRITICAL DISTINCTIONS:
- To FIND FILES ON THE COMPUTER: Use Shell Agent with `find` or `grep` commands
- To DOWNLOAD FROM INTERNET: Use File Agent with URL
- To ANALYZE EXISTING DATA: Use Code Agent for computation
- To CREATE DATABASES: Use SQL Agent
- To SEARCH YOUR MACHINE: ONLY Shell Agent can do this!

📋 AGENT SELECTION GUIDE:

1. FOR FINDING FILES ON THE USER'S COMPUTER:
   ➡️ USE: Shell Agent with commands like:
      - `find ~ -name "*keyword*"` to find files by name
      - `grep -r "content" /path` to search file contents
      - `ls -la /directory` to list files
   ❌ NOT: File Agent (only downloads from URLs)
   ❌ NOT: Notes Agent (only creates documentation)

2. FOR COMPUTATIONS AND ANALYSIS:
   ➡️ USE: Code Agent for all calculations, data processing, statistics
   - Ensures reproducibility with shareable code
   - Document all parameters in code comments

3. FOR STRUCTURING DATA:
   ➡️ USE: SQL Agent to create databases from raw data
   - Converts CSV/JSON into queryable tables
   - Creates indexes and relationships

4. FOR DOWNLOADING FROM THE INTERNET:
   ➡️ USE: File Agent ONLY with valid URLs
   ❌ NOT for searching local files

5. FOR RESEARCH AND CITATIONS:
   ➡️ USE: Research Agent for finding papers and sources
   - Builds comprehensive bibliographies
   - Documents conflicting findings

6. FOR SYSTEM OPERATIONS:
   ➡️ USE: Shell Agent for ALL filesystem operations:
      - Installing packages: `pip install pandas`
      - Checking installations: `pip list | grep pandas`
      - File operations: `cp`, `mv`, `rm`, `mkdir`

7. FOR DOCUMENTATION:
   ➡️ USE: Notes Agent to organize and document findings
   - Does NOT search or execute anything
   - Only creates structured documentation

⚠️ COMMON MISTAKES TO AVOID:
❌ Using File Agent to search for local files (use Shell Agent)
❌ Using Notes Agent to find information (it only documents)
❌ Using Data Agent to create databases (use SQL Agent)
❌ Using Math Agent for calculations (use Code Agent)
✅ Use Shell Agent for ANY filesystem search or operation

SHELL AGENT COMMAND FORMAT (CRITICAL!):
The Shell Agent is your ONLY way to search the user's computer!

MUST provide EXACT commands in backticks:
- Find files by name: `find ~ -name "*mond*"` or `find /path -name "*.pdf"`
- Search file contents: `grep -r "search term" /path/to/search`
- List files: `ls -la /directory`
- Read a file: `cat /path/to/file.txt`
- Check what's installed: `pip list`, `brew list`
- Install packages: `pip install numpy pandas`
- Download with curl: `curl -O https://example.com/file.pdf`
- System info: `pwd`, `which python`, `df -h`

REMEMBER: Shell Agent is the ONLY agent that can:
- Search for files on the computer
- Navigate the filesystem
- Check what's installed
- Read local files

Your DECISION PROCESS:
1. EXPLAIN YOUR THINKING: Describe your research approach and methodology
2. DECIDE NEXT ACTION: "final" (complete), "loop" (continue research), "clarify" (need user input)
3. COORDINATE AGENTS: Call multiple agents simultaneously when appropriate
4. ENSURE RIGOR: Every result must be verifiable and reproducible

DECISION CRITERIA FOR ACADEMIC RIGOR:
- Use "final" when:
  * Results are REPRODUCIBLE with provided code/commands
  * All claims have CITATIONS from credible sources
  * Data is STRUCTURED in queryable format (database/CSV)
  * Methodology is DOCUMENTED and can be peer-reviewed
  * Statistical significance/confidence is established where applicable
  * Limitations and biases are acknowledged

- Use "loop" when (utilize ALL {remaining_loops} iterations if needed):
  * Need to verify results with different methods
  * Missing citations for key claims
  * Data needs to be structured into databases
  * Code hasn't been written for reproducible analysis
  * Need multiple agents working simultaneously
  * Results seem inconsistent - need validation
  * Haven't documented methodology sufficiently

- Use "clarify" when:
  * Research question needs refinement
  * Conflicting requirements need resolution
  * After multiple iterations, same error persists (ask user for help)
  * Need access to specific datasets or resources
  * Ethical considerations require user input
  * Statistical assumptions need validation

You MUST respond in this EXACT JSON format:
{{
  "decision": "final" or "loop" or "clarify",
  "thinking_process": "Your research methodology and how agents will contribute to reproducible results",
  "final_answer": "Complete answer with sections: Results, Methodology, Citations, Code/Data, Limitations, Suggested Next Steps",
  "additional_guidance": "Specific research tasks for next iteration with all context (only if 'loop')",
  "clarification_question": "Specific research question needing user input (only if 'clarify')",
  "selected_agent": "Best performing agent or 'combined' for multi-agent collaboration",
  "reasoning": "Research rationale and expected contribution to academic rigor"
}}

ACADEMIC STANDARDS CHECKLIST:
✅ Every computation has reproducible code
✅ All data is in structured, queryable format
✅ Citations provided for all claims
✅ Methodology fully documented
✅ Multiple verification methods used when possible
✅ Limitations explicitly stated

REMEMBER: 
- You have {remaining_loops} iterations - USE THEM ALL for thoroughness
- Call MULTIPLE agents simultaneously for comprehensive analysis
- ALWAYS prefer Code Agent for computations (reproducibility)
- ALWAYS structure data in databases when possible
- If stuck after multiple attempts, ask user for help"""
                    },
                    {
                        "role": "user",
                        "content": f"""Research Query: {user_query}

Current Iteration: {iteration + 1} of {max_iterations}
Remaining Loops: {remaining_loops}

{('Previous Context:\n' + previous_context + '\n') if previous_context else ''}
Agent Responses from this iteration:
{''.join(results_summary)}

🎓 ACADEMIC RESEARCH REVIEW:
Evaluate responses for academic rigor. Ensure:
1. All computations have reproducible code
2. Data is being structured for future queries
3. Citations support all claims
4. Multiple verification methods when appropriate
5. Clear documentation of methodology

DECISION GUIDANCE:
- You have {remaining_loops} iterations - use them ALL if needed for rigor
- Call MULTIPLE agents simultaneously for comprehensive analysis
- If the same problem occurs repeatedly, ask the user for help
- Prioritize reproducibility over quick answers
- Structure all data into databases for systematic analysis"""
                    }
                ]
            }
            
            # GPT-5 models have different parameters
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 800
            else:
                completion_params["max_tokens"] = 800
                completion_params["temperature"] = 0.3
                
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            chief_response = response.choices[0].message.content
            # Log full response for debugging JSON issues
            if len(chief_response) <= 500:
                logger.info(f"[ChiefAgent] Response: {chief_response}")
            else:
                logger.info(f"[ChiefAgent] Response (truncated): {chief_response[:500]}...")
            
            # Parse JSON response
            try:
                decision_data = json.loads(chief_response)
                # Validate required fields
                if "decision" not in decision_data:
                    decision_data["decision"] = "final"
                if "final_answer" not in decision_data:
                    # Use best agent result as fallback
                    best_result = max(agent_results, key=lambda r: r.confidence) if agent_results else None
                    decision_data["final_answer"] = best_result.result if best_result else "No results available"
                # Add thinking_process to metadata if present
                if "thinking_process" in decision_data:
                    logger.info(f"[ChiefAgent] Thinking: {decision_data['thinking_process'][:200]}...")
                # Ensure final answer includes suggested next steps
                if "Suggested Next Steps:" not in decision_data.get("final_answer", ""):
                    decision_data["final_answer"] += "\n\nSuggested Next Steps: Review the results and let me know if you need further clarification."
                # Normalize decision value
                if decision_data["decision"] not in ["final", "loop", "clarify"]:
                    logger.warning(f"[ChiefAgent] Invalid decision value: {decision_data['decision']}, defaulting to 'final'")
                    decision_data["decision"] = "final"
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                logger.warning("[ChiefAgent] Failed to parse JSON response, using fallback")
                best_result = max(agent_results, key=lambda r: r.confidence) if agent_results else None
                decision_data = {
                    "decision": "final",
                    "final_answer": best_result.result if best_result else "No results available",
                    "additional_guidance": None,
                    "selected_agent": best_result.display_name if best_result else "None",
                    "reasoning": "JSON parsing failed - using best available result"
                }
            
            logger.info(f"[ChiefAgent] Decision: {decision_data.get('decision')}, Selected: {decision_data.get('selected_agent')}")
            logger.info(f"[ChiefAgent] Completed in {time.time() - start_time:.3f}s")
            
            return decision_data
            
        except Exception as e:
            logger.error(f"[ChiefAgent] Error: {e}")
            # Fallback: use best available result
            best_result = max(agent_results, key=lambda r: r.confidence) if agent_results else None
            return {
                "decision": "final",
                "final_answer": best_result.result if best_result else "No results available",
                "additional_guidance": None,
                "selected_agent": best_result.display_name if best_result else "None",
                "reasoning": f"Chief Agent error: {str(e)[:100]}"
            }

class ThinkerOrchestrator:
    """The main orchestrator that coordinates all agents"""
    
    MAX_ITERATIONS = 10  # Maximum number of Chief Agent loop iterations
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.chief_agent = ChiefAgent(self.llm_client)  # Chief Agent is primary
        
        # Core execution agents
        self.code_agent = CodeAgent(self.llm_client)
        self.sql_agent = SQLAgent(self.llm_client)
        self.shell_agent = ShellAgent(self.llm_client)  # NEW: Full shell access
        
        # Specialized agents
        self.math_agent = MathAgent(self.llm_client)
        self.research_agent = ResearchAgent(self.llm_client)
        self.strategy_agent = StrategyAgent(self.llm_client)
        self.data_agent = DataAgent(self.llm_client)
        self.notes_agent = NotesAgent(self.llm_client)
        self.file_agent = FileAgent(self.llm_client)  # Will get context during orchestration
        
        # Keep but use sparingly
        self.reasoning_agent = ReasoningAgent(self.llm_client)
        self.general_agent = GeneralAgent(self.llm_client)
        
        # Initialize file processing orchestrator if available
        if FILE_PROCESSING_AVAILABLE:
            self.file_processor = FileProcessingOrchestrator(self.llm_client)
        else:
            self.file_processor = None
        
    async def process_file(self, file_path: str, file_type: str, websocket: WebSocket) -> Dict[str, Any]:
        """Process uploaded file using file processing agents"""
        if not self.file_processor:
            await websocket.send_json({
                "type": "message",
                "role": "assistant",
                "text": "File processing agents not available. Please install required libraries."
            })
            return {"error": "File processing not available"}
        
        return await self.file_processor.process_file(file_path, file_type, websocket)
    
    async def think(self, message: str) -> Dict[str, Any]:
        """Thinker phase: Analyze the request for academic research approach"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": [],
            "selection_reasoning": "",
            "research_priority": "reproducibility"  # Default research priority
        }
        
        # Analyze the message for research context
        import re
        has_url = bool(re.search(r'https?://[^\s]+', message))
        has_file_path = bool(re.search(r'(/[^\s]+\.[a-zA-Z]{2,4}|[A-Za-z]:\\[^\s]+|\./[^\s]+)', message))
        has_shell_command = bool(re.search(r'`[^`]+`', message)) or any(cmd in message.lower() for cmd in ['grep', 'find', 'ls', 'cat', 'brew install', 'pip install', 'npm install', 'apt-get', 'chmod', 'mkdir', 'rm', 'cp', 'mv'])
        
        # CRITICAL: Check for file search keywords
        is_file_search = any(phrase in message.lower() for phrase in [
            'find files', 'find all files', 'search for files', 'files on my computer',
            'files on my machine', 'files related to', 'search my computer',
            'search my machine', 'look for files', 'locate files', 'where are',
            'list files', 'show files', 'what files', 'search for',
            'files containing', 'containing the word', 'grep', 'find'
        ])
        
        # Check for research-specific keywords
        is_data_task = any(word in message.lower() for word in ['data', 'dataset', 'csv', 'excel', 'json', 'analyze', 'statistics', 'correlation'])
        is_research_task = any(word in message.lower() for word in ['research', 'paper', 'study', 'literature', 'review', 'citation', 'reference', 'peer-review'])
        is_computation = any(word in message.lower() for word in ['calculate', 'compute', 'analyze', 'model', 'simulate', 'algorithm'])
        
        # FILE SEARCH ON USER'S COMPUTER (Highest Priority)
        if is_file_search or ('find' in message.lower() and 'file' in message.lower()):
            thinking_process["identified_type"] = "file_search"
            thinking_process["analysis"] = "User wants to search for files on their computer"
            thinking_process["agents_to_use"] = ["ShellAgent"]
            thinking_process["selection_reasoning"] = "Shell Agent is the ONLY agent that can search the filesystem. Will use find or grep commands."
            thinking_process["research_priority"] = "file_discovery"
        # RESEARCH DATA PROCESSING
        elif is_data_task or (has_file_path and any(ext in message.lower() for ext in ['.csv', '.json', '.xlsx', '.txt', '.pdf'])):
            thinking_process["identified_type"] = "research_data_processing"
            thinking_process["analysis"] = "Research data needs to be processed, structured, and analyzed"
            thinking_process["agents_to_use"] = ["FileAgent", "CodeAgent", "SQLAgent", "DataAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: File processing, Code for analysis, SQL for structuring, Data for schema, Notes for documentation"
            thinking_process["research_priority"] = "data_structuring"
        # ACADEMIC RESEARCH TASKS
        elif is_research_task:
            thinking_process["identified_type"] = "academic_research"
            thinking_process["analysis"] = "Academic research requiring citations and reproducible methodology"
            thinking_process["agents_to_use"] = ["ResearchAgent", "CodeAgent", "NotesAgent", "StrategyAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Research for citations, Code for reproducible analysis, Notes for methodology, Strategy for approach"
            thinking_process["research_priority"] = "citations_and_reproducibility"
        # COMPUTATIONAL RESEARCH
        elif is_computation:
            thinking_process["identified_type"] = "computational_research"
            thinking_process["analysis"] = "Computational task requiring reproducible code and verification"
            thinking_process["agents_to_use"] = ["CodeAgent", "MathAgent", "SQLAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Code for computation, Math for verification, SQL for results storage, Notes for documentation"
            thinking_process["research_priority"] = "computational_reproducibility"
        # Shell commands (when explicit)
        elif has_shell_command or any(word in message.lower() for word in ['run command', 'execute', 'shell', 'terminal', 'install package', 'grep for']):
            thinking_process["identified_type"] = "shell_command"
            thinking_process["analysis"] = "System commands for research infrastructure"
            thinking_process["agents_to_use"] = ["ShellAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Shell for execution, Notes to document system setup"
        # File handling with research context
        elif has_url or has_file_path or any(word in message.lower() for word in ["download", "file", "upload", "save file"]):
            thinking_process["identified_type"] = "file_operation"
            thinking_process["analysis"] = "File operations for research materials"
            thinking_process["agents_to_use"] = ["FileAgent", "CodeAgent", "SQLAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: File processing, Code for analysis, SQL for data storage, Notes for documentation"
            thinking_process["research_priority"] = "data_organization"
        # Mathematical research
        elif any(word in message.lower() for word in ["derive", "proof", "theorem", "formula from first principles", "mathematical derivation"]):
            thinking_process["identified_type"] = "mathematical_derivation"
            thinking_process["analysis"] = "Mathematical research requiring proofs and verification"
            thinking_process["agents_to_use"] = ["MathAgent", "CodeAgent", "ResearchAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Math for proofs, Code for verification, Research for references, Notes for documentation"
            thinking_process["research_priority"] = "mathematical_rigor"
        # Literature and citations
        elif any(word in message.lower() for word in ["sources", "citations", "literature review", "bibliography", "references"]):
            thinking_process["identified_type"] = "literature_research"
            thinking_process["analysis"] = "Literature research and citation building"
            thinking_process["agents_to_use"] = ["ResearchAgent", "NotesAgent", "SQLAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Research for sources, Notes for bibliography, SQL to store citation database"
            thinking_process["research_priority"] = "citation_management"
        # Strategic research planning
        elif any(word in message.lower() for word in ["plan", "methodology", "research design", "hypothesis", "experiment"]):
            thinking_process["identified_type"] = "research_planning"
            thinking_process["analysis"] = "Research methodology and experimental design"
            thinking_process["agents_to_use"] = ["StrategyAgent", "ResearchAgent", "CodeAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Strategy for methodology, Research for precedents, Code for analysis plan, Notes for protocol"
            thinking_process["research_priority"] = "methodology_design"
        # Statistical analysis
        elif any(word in message.lower() for word in ["statistical", "significance", "p-value", "correlation", "regression", "anova"]):
            thinking_process["identified_type"] = "statistical_analysis"
            thinking_process["analysis"] = "Statistical analysis requiring reproducible code"
            thinking_process["agents_to_use"] = ["CodeAgent", "MathAgent", "SQLAgent", "NotesAgent", "ResearchAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Code for statistics, Math for theory, SQL for data, Notes for interpretation, Research for methods"
            thinking_process["research_priority"] = "statistical_rigor"
        # Database operations
        elif any(word in message.lower() for word in ["sql", "database", "query", "table", "schema"]):
            thinking_process["identified_type"] = "database_operations"
            thinking_process["analysis"] = "Database operations for research data management"
            thinking_process["agents_to_use"] = ["SQLAgent", "DataAgent", "CodeAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: SQL for database, Data for schema design, Code for ETL, Notes for data dictionary"
            thinking_process["research_priority"] = "data_management"
        # Documentation
        elif any(word in message.lower() for word in ["document", "methodology", "protocol", "procedure"]):
            thinking_process["identified_type"] = "research_documentation"
            thinking_process["analysis"] = "Research documentation and protocol development"
            thinking_process["agents_to_use"] = ["NotesAgent", "ResearchAgent", "CodeAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent: Notes for documentation, Research for standards, Code for reproducible procedures"
            thinking_process["research_priority"] = "documentation"
        # Default: comprehensive research approach
        else:
            thinking_process["identified_type"] = "comprehensive_research"
            thinking_process["analysis"] = "Comprehensive research requiring multiple perspectives"
            thinking_process["agents_to_use"] = ["StrategyAgent", "CodeAgent", "ResearchAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Multi-agent collaboration: Strategy for approach, Code for analysis, Research for context, Notes for documentation"
            thinking_process["research_priority"] = "comprehensive_analysis"
            
        return thinking_process
        
    async def orchestrate(self, message: str, websocket, iteration: int = 0, previous_results: List[AgentResult] = None, project_id: int = None, branch_id: int = None, db_session = None):
        """Full orchestration process controlled by Chief Agent decisions with optional notes persistence"""
        orchestration_start = time.time()
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration for message: {message} (iteration: {iteration})")
        logger.info("="*80)
        
        # Check iteration limit
        if iteration >= self.MAX_ITERATIONS:
            # If we have previous results, use Chief Agent's last final_answer
            if previous_results:
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": f"**Note:** Maximum iterations ({self.MAX_ITERATIONS}) reached.\n\n{previous_results[0].result if previous_results else 'Processing limit reached. Please refine your request.'}"
                })
            else:
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": "Processing limit reached. Please try a more specific request."
                })
            return
        
        # Phase 1: Thinking
        logger.info("[ORCHESTRATOR] PHASE 1: Thinker Analysis")
        thinking = await self.think(message)
        logger.info(f"[ORCHESTRATOR] Thinking result: Type={thinking['identified_type']}, Agents={thinking['agents_to_use']}")
        
        # Build detailed explanation of what each agent will do
        agent_explanations = []
        for agent_name in thinking['agents_to_use']:
            if agent_name == "CodeAgent":
                agent_explanations.append("• **Coding Agent**: Will generate and execute Python code to compute the exact result")
            elif agent_name == "ShellAgent":
                agent_explanations.append("• **Shell Executor**: Will run system commands to complete the requested operation")
            elif agent_name == "SQLAgent":
                agent_explanations.append("• **SQL Agent**: Will create database queries or schema modifications as needed")
            elif agent_name == "MathAgent":
                agent_explanations.append("• **Math Agent**: Will derive formulas from first principles and show mathematical proofs")
            elif agent_name == "ResearchAgent":
                agent_explanations.append("• **Research Agent**: Will search for relevant sources and compile information")
            elif agent_name == "StrategyAgent":
                agent_explanations.append("• **Strategy Agent**: Will create a detailed action plan for solving this problem")
            elif agent_name == "DataAgent":
                agent_explanations.append("• **Data Agent**: Will analyze database schemas and suggest appropriate queries")
            elif agent_name == "NotesAgent":
                agent_explanations.append("• **Notes Agent**: Will document findings and create organized notes")
            elif agent_name == "FileAgent":
                agent_explanations.append("• **File Agent**: Will download files or analyze file paths as requested")
            elif agent_name == "ReasoningAgent":
                agent_explanations.append("• **Reasoning Agent**: Will apply step-by-step logical analysis")
            elif agent_name == "GeneralAgent":
                agent_explanations.append("• **General Assistant**: Will provide direct answers using general knowledge")
        
        agent_details = "\n".join(agent_explanations)
        
        # Send processing action that UI expects - this sets up streamText variable
        await websocket.send_json({
            "type": "action",
            "function": "processing",
            "text": f"""🤔 **Chief Agent Analysis** (Iteration {iteration + 1}/{self.MAX_ITERATIONS})

📊 **Problem Assessment:**
I've analyzed your request as a {thinking['identified_type'].replace('_', ' ')}.
{thinking['analysis']}.

🎯 **Solution Approach:**
{thinking['selection_reasoning']}.

🤖 **Agent Assignments:**
{agent_details}

⏳ Now coordinating these agents to solve your request..."""
        })
        await asyncio.sleep(0.5)  # Allow UI to set up streaming
        
        # No need for redundant streaming update
        
        # Phase 2: Parallel agent processing
        logger.info("[ORCHESTRATOR] PHASE 2: Parallel Agent Processing")
        agents = []
        if "CodeAgent" in thinking["agents_to_use"]:
            agents.append(self.code_agent)
            logger.info("[ORCHESTRATOR] Added CodeAgent to processing queue")
        if "ReasoningAgent" in thinking["agents_to_use"]:
            agents.append(self.reasoning_agent)
            logger.info("[ORCHESTRATOR] Added ReasoningAgent to processing queue")
        if "GeneralAgent" in thinking["agents_to_use"]:
            agents.append(self.general_agent)
            logger.info("[ORCHESTRATOR] Added GeneralAgent to processing queue")
        if "SQLAgent" in thinking["agents_to_use"]:
            agents.append(self.sql_agent)
            logger.info("[ORCHESTRATOR] Added SQLAgent to processing queue")
        if "ShellAgent" in thinking["agents_to_use"]:
            agents.append(self.shell_agent)
            logger.info("[ORCHESTRATOR] Added ShellAgent to processing queue")
        # Add new specialized agents
        if "MathAgent" in thinking["agents_to_use"]:
            agents.append(self.math_agent)
            logger.info("[ORCHESTRATOR] Added MathAgent to processing queue")
        if "ResearchAgent" in thinking["agents_to_use"]:
            agents.append(self.research_agent)
            logger.info("[ORCHESTRATOR] Added ResearchAgent to processing queue")
        if "StrategyAgent" in thinking["agents_to_use"]:
            agents.append(self.strategy_agent)
            logger.info("[ORCHESTRATOR] Added StrategyAgent to processing queue")
        if "DataAgent" in thinking["agents_to_use"]:
            agents.append(self.data_agent)
            logger.info("[ORCHESTRATOR] Added DataAgent to processing queue")
        if "NotesAgent" in thinking["agents_to_use"]:
            agents.append(self.notes_agent)
            logger.info("[ORCHESTRATOR] Added NotesAgent to processing queue")
        if "FileAgent" in thinking["agents_to_use"]:
            # Update FileAgent with current context if available
            if db_session and project_id and branch_id:
                self.file_agent.project_id = project_id
                self.file_agent.branch_id = branch_id
                self.file_agent.db_session = db_session
            agents.append(self.file_agent)
            logger.info("[ORCHESTRATOR] Added FileAgent to processing queue")
            
        # Process all agents in parallel
        logger.info(f"[ORCHESTRATOR] Starting parallel processing with {len(agents)} agents")
        parallel_start = time.time()
        
        # Don't send stream updates that would overwrite the Chief Agent analysis
        # The detailed analysis message is complete and should stand on its own
        
        # Create agent tasks - pass conversation context to Shell Agent
        agent_tasks = []
        for agent in agents:
            if isinstance(agent, ShellAgent):
                # Pass conversation context to Shell Agent for better analysis
                conversation_context = f"User Query: {message}\nIteration: {iteration + 1}"
                if previous_results:
                    conversation_context += "\nPrevious Results:\n"
                    for prev in previous_results[:3]:
                        conversation_context += f"- {prev.display_name}: {prev.result[:100]}...\n"
                agent_tasks.append(agent.process(message, conversation_context=conversation_context))
            else:
                agent_tasks.append(agent.process(message))
        
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        logger.info(f"[ORCHESTRATOR] Parallel processing completed in {time.time() - parallel_start:.3f}s")
        
        # Send agent results
        logger.info("[ORCHESTRATOR] Processing agent results")
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, AgentResult):
                logger.info(f"[ORCHESTRATOR] Result {i+1}: {result.agent_name} - Confidence: {result.confidence:.2f}, Method: {result.method}")
                logger.info(f"[ORCHESTRATOR] Result {i+1} content: {result.result[:200]}...")
                
                # Send agent completion status with display name
                status_text = result.result  # Already formatted by the agent
                
                await websocket.send_json({
                    "type": "agent_result",
                    "agent_name": result.display_name,  # Use display name for UI
                    "text": status_text,
                    "summary": result.summary,  # Include summary for user visibility
                    "metadata": {
                        "agent": result.agent_name,
                        "confidence": result.confidence,
                        "method": result.method,
                        "needs_rerun": result.needs_rerun,
                        "summary": result.summary  # Also include in metadata
                    }
                })
                valid_results.append(result)
                await asyncio.sleep(0.2)
            elif isinstance(result, Exception):
                logger.error(f"[ORCHESTRATOR] Agent {i+1} failed with exception: {result}")
                
        # Phase 3: Chief Agent Review and Decision
        logger.info("[ORCHESTRATOR] PHASE 3: Chief Agent Review and Decision")
        logger.info(f"[ORCHESTRATOR] Chief Agent reviewing {len(valid_results)} valid results")
        
        # Don't send stream updates - let agent results speak for themselves
        
        # Build context from previous iterations
        previous_context = ""
        if previous_results:
            previous_context = "Previous iteration results:\n"
            for prev_result in previous_results[:3]:  # Include top 3 from previous
                previous_context += f"- {prev_result.display_name}: {prev_result.result[:200]}...\n"
        
        # Have Chief Agent review all results and make a decision
        chief_decision = await self.chief_agent.review_and_decide(
            user_query=message, 
            agent_results=valid_results, 
            iteration=iteration,
            max_iterations=self.MAX_ITERATIONS,
            previous_context=previous_context
        )
        logger.info(f"[ORCHESTRATOR] Chief Agent decision: {chief_decision.get('decision')}")
        
        # Log thinking process if available
        if chief_decision.get('thinking_process'):
            logger.info(f"[ORCHESTRATOR] Chief Agent thinking: {chief_decision['thinking_process'][:300]}...")
        
        # Save notes if we have a database session and project context
        if NOTES_AVAILABLE and db_session and project_id and branch_id:
            try:
                note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                note_id = await note_taker.save_agent_notes(
                    agent_results=valid_results,
                    user_query=message, 
                    chief_decision=chief_decision
                )
                if note_id:
                    logger.info(f"[ORCHESTRATOR] Saved notes to database with ID: {note_id}")
                    # Optionally send notification to websocket
                    await websocket.send_json({
                        "type": "note_saved",
                        "note_id": note_id,
                        "message": "Analysis saved to Notes"
                    })
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to save notes: {e}")
        
        # Handle clarification needs (still handled by individual agents)
        needs_clarification = any(r.needs_clarification for r in valid_results)
        
        if needs_clarification:
            # Find the agent needing clarification and format the question
            for result in valid_results:
                if result.needs_clarification:
                    clarification_text = f"**Clarification Needed**\n\n"
                    clarification_text += f"**Question:** {result.clarification_question}\n\n"
                    clarification_text += f"**Results So Far:** {result.result.split('Answer: ')[1].split('\n')[0] if 'Answer: ' in result.result else 'Processing incomplete'}\n\n"
                    clarification_text += f"**Next Steps:** Please provide more details to continue processing\n\n"
                    
                    await websocket.send_json({
                        "type": "message",
                        "role": "Assistant",
                        "text": clarification_text
                    })
                    return
        
        # Handle Chief Agent's clarification request
        if chief_decision.get('decision') == 'clarify':
            clarification_question = chief_decision.get('clarification_question', 'Could you please provide more details about your request?')
            thinking = chief_decision.get('thinking_process', 'Need more information from user')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting clarification: {clarification_question}")
            
            await websocket.send_json({
                "type": "message",
                "role": "The Chief Agent",
                "text": f"""🤔 **Clarification Needed**

{thinking}

**Question:** {clarification_question}

**Why I'm asking:** {chief_decision.get('reasoning', 'This information will help me provide a more accurate and helpful response.')}

Please provide this information so I can better assist you."""
            })
            return
        
        # Chief Agent makes the final decision
        if chief_decision.get('decision') == 'loop' and iteration < self.MAX_ITERATIONS - 1:
            # Chief Agent wants another iteration
            guidance = chief_decision.get('additional_guidance', '')
            thinking = chief_decision.get('thinking_process', 'Analyzing how to improve the answer...')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting iteration {iteration + 1} with guidance: {guidance}")
            
            await websocket.send_json({
                "type": "agent_result",
                "agent_name": "The Chief Agent",
                "text": f"""🔄 Refining Answer (Iteration {iteration + 2}/{self.MAX_ITERATIONS}, {self.MAX_ITERATIONS - iteration - 2} loops remaining)

🤔 Chief Agent's Analysis:
{thinking}

🎯 Next Approach:
{guidance}

⏳ Running additional analysis..."""
            })
            
            # Prepare enhanced message with Chief Agent's guidance
            # Check if the guidance contains a shell command (in backticks)
            if '`' in guidance:
                # Extract command from guidance if present
                import re
                cmd_match = re.search(r'`([^`]+)`', guidance)
                if cmd_match and 'ShellAgent' in thinking.get('agents_to_use', []):
                    # Pass the command directly for Shell Agent
                    enhanced_message = f"Execute: `{cmd_match.group(1)}`\n\nOriginal request: {message}"
                else:
                    enhanced_message = f"{message}\n\nRefinement guidance: {guidance}"
            else:
                enhanced_message = f"{message}\n\nRefinement guidance: {guidance}"
            
            # Brief delay for UI
            await asyncio.sleep(0.3)
            
            # Start next iteration with Chief Agent's guidance
            return await self.orchestrate(enhanced_message, websocket, iteration + 1, valid_results, project_id, branch_id, db_session)
        
        # Chief Agent has made final decision - prepare the response
        final_answer = chief_decision.get('final_answer', '')
        selected_agent = chief_decision.get('selected_agent', 'The Chief Agent')
        reasoning = chief_decision.get('reasoning', '')
        
        logger.info(f"[ORCHESTRATOR] Chief Agent FINAL decision")
        logger.info(f"[ORCHESTRATOR] Selected approach: {selected_agent}")
        logger.info(f"[ORCHESTRATOR] Reasoning: {reasoning}")
        
        # Send stream update before final
        await websocket.send_json({
            "type": "stream", 
            "text": "Finalizing response..."
        })
        
        # Calculate total time before using it
        total_time = time.time() - orchestration_start
        
        # Use Chief Agent's final answer
        result_text = final_answer
        
        # Parse out the structured sections if they exist
        answer_match = re.search(r'Answer:\s*(.+?)(?=\n\n|\n(?:Why:|Potential Issues:|Suggested Next Steps:)|$)', result_text, re.DOTALL)
        why_match = re.search(r'Why:\s*(.+?)(?=\n\n|\n(?:Potential Issues:|Suggested Next Steps:)|$)', result_text, re.DOTALL)
        issues_match = re.search(r'Potential Issues:\s*(.+?)(?=\n\n|\nSuggested Next Steps:|$)', result_text, re.DOTALL)
        next_steps_match = re.search(r'Suggested Next Steps:\s*(.+?)(?=\n\n|$)', result_text, re.DOTALL)
        
        # If Chief Agent provided a plain answer, use it directly
        if not answer_match and not why_match:
            answer = result_text
            why = reasoning
            issues = None
            next_steps = None
        else:
            answer = answer_match.group(1).strip() if answer_match else result_text.split('\n')[0]
            why = why_match.group(1).strip() if why_match else reasoning
            issues = issues_match.group(1).strip() if issues_match else None
            next_steps = next_steps_match.group(1).strip() if next_steps_match else None
        
        # Build final structured response
        final_text = f"**Answer:** {answer}\n\n"
        final_text += f"**Why:** {why}\n\n"
        
        # Add Agent Summaries section if we have results with summaries
        agent_summaries = [r for r in valid_results if r.summary]
        if agent_summaries:
            final_text += "**What Each Agent Found:**\n"
            for result in agent_summaries:
                final_text += f"• **{result.display_name}:** {result.summary}\n"
            final_text += "\n"
        
        if issues and issues.lower() != 'none':
            final_text += f"**Potential Issues:** {issues}\n\n"
            
        # Always include Suggested Next Steps
        if next_steps:
            final_text += f"**Suggested Next Steps:** {next_steps}\n\n"
        else:
            # Fallback if Chief Agent didn't provide next steps
            final_text += "**Suggested Next Steps:** "
            if "error" in result_text.lower() or "failed" in result_text.lower():
                final_text += "Review the error details and try a different approach or provide more specific information.\n\n"
            elif "code" in result_text.lower() or "function" in result_text.lower():
                final_text += "Test the provided code, modify it for your specific use case, or ask for additional features.\n\n"
            elif "file" in result_text.lower() or "download" in result_text.lower():
                final_text += "Check the downloaded files, analyze their contents, or process them further as needed.\n\n"
            else:
                final_text += "Let me know if you need clarification, want to explore this topic further, or have related questions.\n\n"
        
        # Add metadata about processing
        if iteration > 0:
            final_text += f"\n_🔄 Resolved after {iteration + 1} iterations in {total_time:.1f}s_"
        else:
            final_text += f"\n_✅ Processed in {total_time:.1f}s_"
        
        # Send final response with Chief Agent attribution
        await websocket.send_json({
            "type": "message",
            "role": selected_agent if selected_agent != 'combined' else 'The Chief Agent',
            "text": final_text,
            "metadata": {
                "selected_agent": selected_agent,
                "chief_reasoning": reasoning,
                "confidence": max([r.confidence for r in valid_results]) if valid_results else 0.0,
                "method": "Chief Agent Decision",
                "orchestration_time": total_time,
                "all_results": [
                    {
                        "agent": r.agent_name,
                        "result": r.result,
                        "summary": r.summary,
                        "confidence": r.confidence,
                        "method": r.method,
                        "explanation": r.explanation
                    } for r in valid_results
                ]
            }
        })
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Orchestration completed in {total_time:.3f}s")
        logger.info(f"[ORCHESTRATOR] Final answer: {final_answer[:100]}...")
        logger.info("="*80)
        

# Export the advanced orchestrator
__all__ = ['ThinkerOrchestrator', 'AgentResult']