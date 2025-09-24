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

class ThinkerOrchestrator:
    """The main orchestrator that coordinates all agents"""
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.code_agent = CodeAgent(self.llm_client)
        self.reasoning_agent = ReasoningAgent(self.llm_client)
        self.general_agent = GeneralAgent(self.llm_client)
        self.sql_agent = SQLAgent(self.llm_client)
        
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
            "agents_to_use": []
        }
        
        # Analyze the message
        if any(word in message.lower() for word in ["calculate", "compute", "square root", "sqrt", "multiply", "divide", "add", "subtract", "sum", "product"]):
            thinking_process["identified_type"] = "mathematical_computation"
            thinking_process["analysis"] = "This is a mathematical computation requiring precise calculation"
            thinking_process["agents_to_use"] = ["CodeAgent", "ReasoningAgent", "GeneralAgent"]
        elif any(word in message.lower() for word in ["code", "program", "function", "script", "algorithm"]):
            thinking_process["identified_type"] = "coding_task"
            thinking_process["analysis"] = "This requires code generation or programming"
            thinking_process["agents_to_use"] = ["CodeAgent", "GeneralAgent"]
        elif any(word in message.lower() for word in ["sql", "database", "query", "table", "select from"]):
            thinking_process["identified_type"] = "database_query"
            thinking_process["analysis"] = "This requires SQL query generation and execution"
            thinking_process["agents_to_use"] = ["SQLAgent", "GeneralAgent"]
        elif any(word in message.lower() for word in ["explain", "why", "how", "what is", "define"]):
            thinking_process["identified_type"] = "explanation_query"
            thinking_process["analysis"] = "This requires detailed explanation or reasoning"
            thinking_process["agents_to_use"] = ["ReasoningAgent", "GeneralAgent"]
        else:
            thinking_process["identified_type"] = "general_query"
            thinking_process["analysis"] = "This is a general query"
            thinking_process["agents_to_use"] = ["GeneralAgent", "ReasoningAgent"]
            
        return thinking_process
        
    async def orchestrate(self, message: str, websocket: WebSocket, rerun_count: int = 0, previous_results: List[AgentResult] = None):
        """Full orchestration process with rerun capability"""
        orchestration_start = time.time()
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration for message: {message} (rerun: {rerun_count})")
        logger.info("="*80)
        
        # Check rerun limit
        if rerun_count >= 30:
            await websocket.send_json({
                "type": "message",
                "role": "Orchestrator",
                "text": "Answer: Maximum retry limit (30) reached. Please refine your request or try a different approach.\n\nPotential issues: Multiple agent failures"
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
            "text": f"Analyzing request...\nType: {thinking['identified_type']}\nEngaging {len(thinking['agents_to_use'])} agents"
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
                
        # Phase 3: Select best result and check for reruns
        logger.info("[ORCHESTRATOR] PHASE 3: Result Selection and Rerun Check")
        logger.info(f"[ORCHESTRATOR] Comparing {len(valid_results)} valid results")
        
        # Check if any agent needs clarification
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
        
        # Check if any agent needs rerun
        needs_rerun = any(r.needs_rerun for r in valid_results if r.confidence < 0.5)
        
        if needs_rerun and rerun_count < 30:
            # Prepare context for rerun
            context = f"{message}\n\nPrevious attempts had issues:\n"
            for r in valid_results:
                if r.needs_rerun:
                    context += f"- {r.display_name}: {r.rerun_reason}\n"
            
            await websocket.send_json({
                "type": "agent_result",
                "agent_name": "Orchestrator",
                "text": f"Status: Retrying with improved context (attempt {rerun_count + 2}/30)\n\nReason: {valid_results[0].rerun_reason if valid_results else 'Error in processing'}"
            })
            
            # Rerun with context
            await asyncio.sleep(0.5)
            return await self.orchestrate(context, websocket, rerun_count + 1, valid_results)
        
        best_result = await self.select_best_result(valid_results, thinking)
        logger.info(f"[ORCHESTRATOR] Selected best result: {best_result.agent_name} with confidence {best_result.confidence}")
        logger.info(f"[ORCHESTRATOR] Selection reasoning: Method={best_result.method}")
        
        # Send stream update before final
        await websocket.send_json({
            "type": "stream", 
            "text": "Finalizing response..."
        })
        
        # Calculate total time before using it
        total_time = time.time() - orchestration_start
        
        # Extract the structured parts from the best result
        result_text = best_result.result
        
        # Parse out the structured sections
        answer_match = re.search(r'Answer:\s*(.+?)(?=\n\n|\n(?:Why:|Potential Issues:|Suggested Next Steps:)|$)', result_text, re.DOTALL)
        why_match = re.search(r'Why:\s*(.+?)(?=\n\n|\n(?:Potential Issues:|Suggested Next Steps:)|$)', result_text, re.DOTALL)
        issues_match = re.search(r'Potential Issues:\s*(.+?)(?=\n\n|\nSuggested Next Steps:|$)', result_text, re.DOTALL)
        next_steps_match = re.search(r'Suggested Next Steps:\s*(.+?)(?=\n\n|$)', result_text, re.DOTALL)
        
        answer = answer_match.group(1).strip() if answer_match else result_text.split('\n')[0]
        why = why_match.group(1).strip() if why_match else f"Processed using {best_result.display_name}"
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
        if rerun_count > 0:
            final_text += f"\n_Resolved after {rerun_count + 1} attempts in {total_time:.1f}s_"
        else:
            final_text += f"\n_Processed in {total_time:.1f}s_"
        
        # Send final response with proper agent attribution
        await websocket.send_json({
            "type": "message",
            "role": best_result.display_name,  # Show which agent provided the answer
            "text": final_text,
            "metadata": {
                "selected_agent": best_result.agent_name,
                "confidence": best_result.confidence,
                "method": best_result.method,
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
        logger.info(f"[ORCHESTRATOR] Final answer: {best_result.result[:100]}...")
        logger.info("="*80)
        
    async def select_best_result(self, results: List[AgentResult], thinking: Dict) -> AgentResult:
        """Orchestrator logic to select the best result"""
        if not results:
            return AgentResult("Orchestrator", "No valid results from agents", 0.0, "Fallback")
            
        # For mathematical computations, prefer highest confidence
        if thinking["identified_type"] == "mathematical_computation":
            # Prefer exact computation methods
            for result in results:
                if result.confidence == 1.0:  # Perfect confidence from mathematical calculation
                    return result
                    
        # Otherwise, select by highest confidence
        return max(results, key=lambda r: r.confidence)

# Export the advanced orchestrator
__all__ = ['ThinkerOrchestrator', 'AgentResult']