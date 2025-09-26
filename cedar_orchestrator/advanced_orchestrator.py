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

QUALITY CHECKS:
- For mathematical problems: Verify calculations are correct
- For coding tasks: Ensure code is syntactically correct and solves the problem
- For explanations: Ensure clarity and completeness
- For SQL queries: Verify syntax and logic

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
        
    async def orchestrate(self, message: str, websocket: WebSocket, iteration: int = 0, previous_results: List[AgentResult] = None):
        """Full orchestration process controlled by Chief Agent decisions"""
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
                    "role": "Chief Agent",
                    "text": f"**Note:** Maximum iterations ({self.MAX_ITERATIONS}) reached.\n\n{previous_results[0].result if previous_results else 'Processing limit reached. Please refine your request.'}"
                })
            else:
                await websocket.send_json({
                    "type": "message",
                    "role": "Chief Agent",
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
                "agent_name": "Chief Agent",
                "text": f"Status: Refining answer (iteration {iteration + 2}/{self.MAX_ITERATIONS})\n\nApproach: {guidance}"
            })
            
            # Prepare enhanced message with Chief Agent's guidance
            enhanced_message = f"{message}\n\nRefinement guidance: {guidance}"
            
            # Brief delay for UI
            await asyncio.sleep(0.3)
            
            # Start next iteration with Chief Agent's guidance
            return await self.orchestrate(enhanced_message, websocket, iteration + 1, valid_results)
        
        # Chief Agent has made final decision - prepare the response
        final_answer = chief_decision.get('final_answer', '')
        selected_agent = chief_decision.get('selected_agent', 'Chief Agent')
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
            "role": selected_agent if selected_agent != 'combined' else 'Chief Agent',
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