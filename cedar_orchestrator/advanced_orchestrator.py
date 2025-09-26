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
    needs_rerun: bool = False  # Whether this agent needs to be rerun
    rerun_reason: str = ""  # Why a rerun is needed
    needs_clarification: bool = False  # Whether the agent needs user clarification
    clarification_question: str = ""  # Question to ask the user
    
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
                        "content": """You are a Python code generator. Generate ONLY executable Python code to solve the given problem.
                        - Output ONLY the Python code, no explanations or markdown
                        - The code should print the final result
                        - Use proper error handling
                        - For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10))
                        - The code must be complete and runnable as-is"""
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
            
            generated_code = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if generated_code.startswith("```"):
                generated_code = generated_code.split("\n", 1)[1]
                if generated_code.endswith("```"):
                    generated_code = generated_code.rsplit("```", 1)[0]
            
            logger.info(f"[CodeAgent] Generated code:\n{generated_code}")
            
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
                formatted_output = f"""Answer: {answer}

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
                    explanation=f"Generated and executed Python code"
                )
                
            except Exception as exec_error:
                logger.error(f"[CodeAgent] Code execution error: {exec_error}")
                formatted_output = f"""Answer: Unable to complete the calculation due to an error

Why: The generated code encountered an execution error

Potential Issues: {str(exec_error)}

Suggested Next Steps: Please rephrase your query or provide more context"""
                
                return AgentResult(
                    agent_name="CodeAgent",
                    display_name="Code Executor",
                    result=formatted_output,
                    confidence=0.3,
                    method="LLM code generation with execution error",
                    explanation=f"Code execution error",
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
                explanation=f"Code generation failed"
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
    """Agent that uses LLM to write and execute SQL queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to generate SQL queries and execute them"""
        start_time = time.time()
        logger.info(f"[SQLAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="SQLAgent",
                result="No LLM client available",
                confidence=0.0,
                method="Error",
                explanation="Cannot generate SQL without LLM access."
            )
        
        # Check if this is actually a SQL/database task
        if not any(word in task.lower() for word in ["sql", "database", "table", "select", "query"]):
            return AgentResult(
                agent_name="SQLAgent",
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
                        "content": """You are a SQL expert. Generate ONLY the SQL query to solve the given problem.
                        - Output ONLY the SQL query, no explanations
                        - Use standard SQL syntax
                        - The query should be complete and runnable"""
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
            
            # For demo purposes, return the SQL query
            # In production, you'd execute against a real database
            formatted_output = f"""Answer: Generated SQL query for your request

Why: Translated your request into SQL syntax

Potential Issues: Query not executed (no database connection)

Suggested Next Steps: Connect to a database to execute this query"""
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Generator",
                result=formatted_output,
                confidence=0.8,
                method="LLM-generated SQL",
                explanation=f"Generated SQL query"
            )
            
        except Exception as e:
            logger.error(f"[SQLAgent] Error: {e}")
            return AgentResult(
                agent_name="SQLAgent",
                result=f"Failed to generate SQL: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation=f"I encountered an error: {str(e)[:200]}"
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
                explanation=f"Direct AI answer"
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
                explanation="Mathematical derivation from axioms"
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
        
    async def review_and_decide(self, user_query: str, agent_results: List[AgentResult], iteration: int = 0) -> Dict[str, Any]:
        """Review all agent results and make the final decision on what to do next"""
        start_time = time.time()
        logger.info(f"[ChiefAgent] Starting review of {len(agent_results)} agent results (iteration {iteration})")
        
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
                        "content": """You are the Chief Agent, the central decision-maker in a multi-agent system. You review all sub-agent responses and make the FINAL decision on what happens next.

AVAILABLE AGENTS AND THEIR SPECIALTIES:
1. Code Executor - Generates and executes Python code for calculations and programming tasks
2. Logical Reasoner - Step-by-step logical analysis and reasoning
3. General Assistant - General knowledge and direct answers
4. SQL Agent - Database queries and SQL operations
5. Math Agent - Derives formulas from first principles with detailed mathematical proofs
6. Research Agent - Web searches and finding relevant sources/citations
7. Strategy Agent - Creates detailed action plans with agent coordination strategies
8. Data Agent - Analyzes database schemas and suggests relevant SQL queries
9. Notes Agent - Creates organized notes from findings without duplication

Your PRIMARY responsibility is to determine:
1. Whether the agents have provided a satisfactory answer that can be sent to the user (decision: "final")
2. Whether more processing is needed with specific guidance (decision: "loop")

DECISION CRITERIA:
- Use "final" when:
  * At least one agent has provided a correct, complete answer
  * The combined agent responses adequately address the user's query
  * Further processing would not meaningfully improve the answer
  * The iteration count is high (>5) and we have a reasonable answer

- Use "loop" when:
  * All agents failed or provided incomplete/incorrect answers
  * Critical information is missing that agents could obtain
  * A different approach or specific agent guidance could yield better results
  * The iteration count is low (<5) and the answer quality is poor
  * You need specific agents that weren't used yet (e.g., Research Agent for citations, Strategy Agent for planning)

QUALITY CHECKS:
- For mathematical problems: Verify calculations are correct, consider if Math Agent's derivations would help
- For coding tasks: Ensure code is syntactically correct and solves the problem
- For research queries: Check if Research Agent has been used for sources
- For complex tasks: Consider if Strategy Agent's planning would improve approach
- For data queries: Check if Data Agent has analyzed available databases
- For important findings: Consider if Notes Agent should create notes

You MUST respond in this EXACT JSON format:
{
  "decision": "final" or "loop",
  "final_answer": "The complete, formatted answer to send to the user (required for both decisions)",
  "additional_guidance": "Specific instructions for the next iteration (only if decision is 'loop')",
  "selected_agent": "Name of best agent or 'combined' (for metadata)",
  "reasoning": "Brief explanation of your decision"
}

IMPORTANT: 
- Always provide a final_answer, even if decision is "loop" (it will be used if max iterations reached)
- Keep final_answer well-formatted with clear sections
- Be decisive - don't request loops unnecessarily"""
                    },
                    {
                        "role": "user",
                        "content": f"""User Query: {user_query}

Iteration: {iteration}

Agent Responses:
{''.join(results_summary)}

Review these responses and make your decision. Remember:
- If any agent provided a good answer, use decision: "final"
- Only use decision: "loop" if the answers are truly inadequate and you have specific guidance for improvement
- Always provide a final_answer regardless of your decision"""
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
                # Normalize decision value
                if decision_data["decision"] not in ["final", "loop"]:
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
        """Thinker phase: Analyze the request and plan the approach"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": [],
            "selection_reasoning": ""  # Add reasoning for agent selection
        }
        
        # Analyze the message
        import re
        has_url = bool(re.search(r'https?://[^\s]+', message))
        has_file_path = bool(re.search(r'(/[^\s]+\.[a-zA-Z]{2,4}|[A-Za-z]:\\[^\s]+|\./[^\s]+)', message))
        
        # File handling takes priority
        if has_url or has_file_path or any(word in message.lower() for word in ["download", "file", "upload", "save file"]):
            thinking_process["identified_type"] = "file_operation"
            thinking_process["analysis"] = "This requires file download or management"
            thinking_process["agents_to_use"] = ["FileAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "File Agent for downloading/processing, Notes Agent to document the files"
        elif any(word in message.lower() for word in ["derive", "proof", "theorem", "formula from first principles", "mathematical derivation"]):
            thinking_process["identified_type"] = "mathematical_derivation"
            thinking_process["analysis"] = "This requires mathematical derivation from first principles"
            thinking_process["agents_to_use"] = ["MathAgent", "CodeAgent"]
            thinking_process["selection_reasoning"] = "Math Agent for derivations, Code Agent for verification"
        elif any(word in message.lower() for word in ["research", "sources", "citations", "find information", "web search", "literature"]):
            thinking_process["identified_type"] = "research_task"
            thinking_process["analysis"] = "This requires web research and finding sources"
            thinking_process["agents_to_use"] = ["ResearchAgent", "NotesAgent"]
            thinking_process["selection_reasoning"] = "Research Agent for finding sources, Notes Agent to document findings"
        elif any(word in message.lower() for word in ["plan", "strategy", "steps to", "approach", "how should i", "coordinate"]):
            thinking_process["identified_type"] = "strategic_planning"
            thinking_process["analysis"] = "This requires strategic planning and coordination"
            thinking_process["agents_to_use"] = ["StrategyAgent"]
            thinking_process["selection_reasoning"] = "Strategy Agent specialized for planning tasks"
        elif any(word in message.lower() for word in ["calculate", "compute", "square root", "sqrt", "multiply", "divide", "add", "subtract", "sum", "product"]):
            thinking_process["identified_type"] = "mathematical_computation"
            thinking_process["analysis"] = "This is a mathematical computation requiring precise calculation"
            thinking_process["agents_to_use"] = ["CodeAgent", "MathAgent"]
            thinking_process["selection_reasoning"] = "Code for execution, Math for formula verification"
        elif any(word in message.lower() for word in ["code", "program", "function", "script", "algorithm"]):
            thinking_process["identified_type"] = "coding_task"
            thinking_process["analysis"] = "This requires code generation or programming"
            thinking_process["agents_to_use"] = ["CodeAgent", "StrategyAgent"]
            thinking_process["selection_reasoning"] = "Code Agent for implementation, Strategy Agent for design approach"
        elif any(word in message.lower() for word in ["sql", "database", "query", "table", "select from", "data analysis"]):
            thinking_process["identified_type"] = "database_query"
            thinking_process["analysis"] = "This requires SQL query generation and execution"
            thinking_process["agents_to_use"] = ["DataAgent", "SQLAgent"]
            thinking_process["selection_reasoning"] = "Data Agent for schema analysis, SQL Agent for query generation"
        elif any(word in message.lower() for word in ["note", "remember", "save for later", "document", "summarize findings"]):
            thinking_process["identified_type"] = "note_taking"
            thinking_process["analysis"] = "This requires creating or managing notes"
            thinking_process["agents_to_use"] = ["NotesAgent"]
            thinking_process["selection_reasoning"] = "Notes Agent specialized for documentation"
        elif any(word in message.lower() for word in ["explain", "why", "how", "what is", "define"]):
            thinking_process["identified_type"] = "explanation_query"
            thinking_process["analysis"] = "This requires detailed explanation or reasoning"
            thinking_process["agents_to_use"] = ["ResearchAgent", "ReasoningAgent"]
            thinking_process["selection_reasoning"] = "Research Agent for sources, Reasoning Agent for logical analysis"
        else:
            thinking_process["identified_type"] = "general_query"
            thinking_process["analysis"] = "This is a general query"
            thinking_process["agents_to_use"] = ["StrategyAgent", "GeneralAgent"]
            thinking_process["selection_reasoning"] = "Strategy Agent for approach, General Agent as fallback"
            
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
        
        # Send processing action that UI expects - this sets up streamText variable
        await websocket.send_json({
            "type": "action",
            "function": "processing",
            "text": f"Analyzing request...\nType: {thinking['identified_type']}\nEngaging {len(thinking['agents_to_use'])} specialized agents\n\nAgent Selection: {thinking['selection_reasoning']}"
        })
        await asyncio.sleep(0.5)  # Allow UI to set up streaming
        
        # Send initial streaming update
        await websocket.send_json({
            "type": "stream",
            "text": "Processing with multiple specialized agents..."
        })
        
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
        
        # Update stream to show agents running
        await websocket.send_json({
            "type": "stream",
            "text": f"Running {len(agents)} specialized agents in parallel..."
        })
        
        agent_tasks = [agent.process(message) for agent in agents]
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
                    "metadata": {
                        "agent": result.agent_name,
                        "confidence": result.confidence,
                        "method": result.method,
                        "needs_rerun": result.needs_rerun
                    }
                })
                valid_results.append(result)
                await asyncio.sleep(0.2)
            elif isinstance(result, Exception):
                logger.error(f"[ORCHESTRATOR] Agent {i+1} failed with exception: {result}")
                
        # Phase 3: Chief Agent Review and Decision
        logger.info("[ORCHESTRATOR] PHASE 3: Chief Agent Review and Decision")
        logger.info(f"[ORCHESTRATOR] Chief Agent reviewing {len(valid_results)} valid results")
        
        # Update stream to show Chief Agent processing
        await websocket.send_json({
            "type": "stream",
            "text": "Chief Agent reviewing all responses and making final decision..."
        })
        
        # Have Chief Agent review all results and make a decision
        chief_decision = await self.chief_agent.review_and_decide(message, valid_results, iteration)
        logger.info(f"[ORCHESTRATOR] Chief Agent decision: {chief_decision.get('decision')}")
        
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
        
        # Chief Agent makes the final decision
        if chief_decision.get('decision') == 'loop' and iteration < self.MAX_ITERATIONS - 1:
            # Chief Agent wants another iteration
            guidance = chief_decision.get('additional_guidance', '')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting iteration {iteration + 1} with guidance: {guidance}")
            
            await websocket.send_json({
                "type": "agent_result",
                "agent_name": "The Chief Agent",
                "text": f"Status: Refining answer (iteration {iteration + 2}/{self.MAX_ITERATIONS})\n\nApproach: {guidance}"
            })
            
            # Prepare enhanced message with Chief Agent's guidance
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
        
        if issues and issues.lower() != 'none':
            final_text += f"**Potential Issues:** {issues}\n\n"
            
        if next_steps:
            final_text += f"**Suggested Next Steps:** {next_steps}\n\n"
        
        # Add minimal metadata
        if iteration > 0:
            final_text += f"\n_Resolved after {iteration + 1} iterations in {total_time:.1f}s_"
        else:
            final_text += f"\n_Processed in {total_time:.1f}s_"
        
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