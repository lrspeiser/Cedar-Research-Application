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
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from openai import AsyncOpenAI
from fastapi import WebSocket

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
    result: Any
    confidence: float
    method: str
    explanation: str = ""  # User-facing explanation of what the agent did
    
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
                
                return AgentResult(
                    agent_name="CodeAgent",
                    result=output.strip() if output else "Code executed successfully but produced no output",
                    confidence=0.95 if output else 0.5,
                    method="LLM-generated and executed Python code",
                    explanation=f"I generated Python code to solve this problem and executed it. The code computed: {output.strip()[:200] if output else 'No output'}."
                )
                
            except Exception as exec_error:
                logger.error(f"[CodeAgent] Code execution error: {exec_error}")
                return AgentResult(
                    agent_name="CodeAgent",
                    result=f"Code execution failed: {str(exec_error)}",
                    confidence=0.3,
                    method="LLM code generation with execution error",
                    explanation=f"I generated code but encountered an error during execution: {str(exec_error)[:200]}"
                )
                
        except Exception as e:
            logger.error(f"[CodeAgent] Error: {e}")
            return AgentResult(
                agent_name="CodeAgent",
                result=f"Failed to generate code: {str(e)}",
                confidence=0.1,
                method="Error in code generation",
                explanation=f"I encountered an error while generating code: {str(e)[:200]}"
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
            
            return AgentResult(
                agent_name="ReasoningAgent",
                result=llm_result,
                confidence=0.85,
                method="LLM step-by-step reasoning",
                explanation=f"I used step-by-step reasoning to solve this problem."
            )
            
        except Exception as e:
            logger.error(f"[ReasoningAgent] Error: {e}")
            return AgentResult(
                agent_name="ReasoningAgent",
                result=f"Failed to reason: {str(e)}",
                confidence=0.1,
                method="Error in reasoning",
                explanation=f"I encountered an error during reasoning: {str(e)[:200]}"
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
            return AgentResult(
                agent_name="SQLAgent",
                result=f"Generated SQL query: {generated_sql}",
                confidence=0.8,
                method="LLM-generated SQL",
                explanation=f"I generated a SQL query to solve this problem. In a production environment, this would be executed against your database."
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
            
            return AgentResult(
                agent_name="GeneralAgent",
                result=llm_result,
                confidence=0.75,
                method="Direct LLM response",
                explanation=f"I provided a direct answer using AI reasoning."
            )
            
        except Exception as e:
            logger.error(f"[GeneralAgent] Error: {e}")
            return AgentResult(
                agent_name="GeneralAgent",
                result=f"Failed to process: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation=f"I encountered an error: {str(e)[:200]}"
            )

class ThinkerOrchestrator:
    """The main orchestrator that coordinates all agents"""
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.code_agent = CodeAgent(self.llm_client)
        self.reasoning_agent = ReasoningAgent(self.llm_client)
        self.general_agent = GeneralAgent(self.llm_client)
        self.sql_agent = SQLAgent(self.llm_client)
        
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
        
    async def orchestrate(self, message: str, websocket: WebSocket):
        """Full orchestration process"""
        orchestration_start = time.time()
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration for message: {message}")
        logger.info("="*80)
        
        # Phase 1: Thinking
        logger.info("[ORCHESTRATOR] PHASE 1: Thinker Analysis")
        thinking = await self.think(message)
        logger.info(f"[ORCHESTRATOR] Thinking result: Type={thinking['identified_type']}, Agents={thinking['agents_to_use']}")
        
        # Send processing action that UI expects
        await websocket.send_json({
            "type": "action",
            "function": "processing",
            "text": f"Analyzing request...\nType: {thinking['identified_type']}\nEngaging {len(thinking['agents_to_use'])} agents"
        })
        await asyncio.sleep(0.5)  # Simulate thinking time
        
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
                
                # Send agent completion status
                status_text = f"{result.agent_name}: Completed\nMethod: {result.method}\nResult: {result.result[:100]}{'...' if len(result.result) > 100 else ''}"
                
                await websocket.send_json({
                    "type": "action",
                    "function": "status",
                    "text": status_text,
                    "metadata": {
                        "agent": result.agent_name,
                        "confidence": result.confidence,
                        "method": result.method
                    }
                })
                valid_results.append(result)
                await asyncio.sleep(0.2)
            elif isinstance(result, Exception):
                logger.error(f"[ORCHESTRATOR] Agent {i+1} failed with exception: {result}")
                
        # Phase 3: Select best result
        logger.info("[ORCHESTRATOR] PHASE 3: Result Selection")
        logger.info(f"[ORCHESTRATOR] Comparing {len(valid_results)} valid results")
        best_result = await self.select_best_result(valid_results, thinking)
        logger.info(f"[ORCHESTRATOR] Selected best result: {best_result.agent_name} with confidence {best_result.confidence}")
        logger.info(f"[ORCHESTRATOR] Selection reasoning: Method={best_result.method}")
        
        # Calculate total time before using it
        total_time = time.time() - orchestration_start
        
        # Create clean final response - always start with TLDR/Answer
        if "code" in thinking['identified_type'].lower() or best_result.agent_name == "CodeAgent":
            # For code results, format as: Answer, Code, Errors
            final_text = f"**Answer:** {best_result.result}\n\n"
            
            # Check if there was generated code in the metadata
            if "generated_code" in str(best_result.explanation):
                final_text += f"**Code:** See execution output above\n\n"
            
            # Check for errors
            if "error" in best_result.result.lower() or "failed" in best_result.result.lower():
                final_text += f"**Errors:** {best_result.result}\n\n"
            else:
                final_text += "**Errors:** None\n\n"
        else:
            # For non-code results, just start with the answer
            final_text = f"**Answer:** {best_result.result}\n\n"
        
        # Add minimal context about what happened
        final_text += "---\n\n"
        final_text += f"**Process:** Analyzed as {thinking['identified_type']}, ran {len(valid_results)} agents\n\n"
        
        # Brief summary of agent results (no percentages)
        final_text += "**Agent Results:**\n"
        for result in valid_results:
            final_text += f"- {result.agent_name}: {result.result[:60]}{'...' if len(result.result) > 60 else ''}\n"
        
        final_text += f"\n**Selected:** {best_result.agent_name} using {best_result.method}\n"
        final_text += f"**Time:** {total_time:.2f}s"
        
        # Send final response in format expected by UI
        await websocket.send_json({
            "type": "message",
            "role": "assistant",
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