"""
Main Orchestrator Module
Coordinates all agents through the Chief Agent decision-making system

This module contains:
1. ChiefAgent - The decision-making agent that reviews and coordinates
2. ThinkerOrchestrator - Main orchestration class that manages all agents
"""

import os
import time
import json
import re
import logging
import asyncio
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import execution agents
from .execution_agents import AgentResult, ShellAgent, CodeAgent, SQLAgent

# Import specialized agents
from .specialized_agents import MathAgent, ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FileAgent

# Import file processing agents if available
try:
    from .file_processing_agents import FileProcessingOrchestrator
    FILE_PROCESSING_AVAILABLE = True
except ImportError:
    FILE_PROCESSING_AVAILABLE = False

# Import chief agent notes functionality if available
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
            
            # Create the system prompt (shortened version for space)
            system_prompt = f"""You are the Chief Agent - an intelligent orchestrator who thinks carefully about each query before acting.

🎯 YOUR PRIMARY DIRECTIVE:
ASSESS the query complexity FIRST, then choose the MINIMAL agent strategy needed.

CURRENT ITERATION STATUS:
- Iteration: {iteration + 1} of {max_iterations}
- Remaining loops: {remaining_loops}

You MUST respond in this EXACT JSON format:
{{
  "decision": "final" or "loop" or "clarify",
  "query_assessment": "SPECIFIC assessment: Is this simple (like 2+2), moderate (like file search), or complex (like deriving equations)? WHY?",
  "thinking_process": "SPECIFIC to THIS query: 'User asks about X. This specifically requires Y because Z. I will use [specific agents] because [specific reasons].'",
  "final_answer": "The actual answer to the user's question (only if 'final')",
  "additional_guidance": "SPECIFIC next action: 'Run Coding Agent with THIS specific code' or 'Query SQL for THIS specific data' (only if 'loop')"
  "clarification_question": "SPECIFIC question about ambiguity: 'When you say X, do you mean Y or Z?' (only if 'clarify')",
  "selected_agent": "Single agent name OR 'combined' if truly needed",
  "reasoning": "SPECIFIC explanation: 'For calculating 2+2, I only need Coding Agent' NOT generic statements",
  "efficiency_note": "Why this is the MINIMAL approach needed (not maximum)"
}}"""

            # Ask Chief Agent to review and decide
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"""User Query: {user_query}

Current Iteration: {iteration + 1} of {max_iterations}
Remaining Loops: {remaining_loops}

{('Previous Context:\n' + previous_context + '\n') if previous_context else ''}
Agent Responses from this iteration:
{''.join(results_summary)}

Be SPECIFIC about THIS query, not generic!
Only loop if you have a SPECIFIC thing you need to get."""
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
                # Log the new assessment fields
                if "query_assessment" in decision_data:
                    logger.info(f"[ChiefAgent] Query Assessment: {decision_data['query_assessment'][:200]}...")
                if "thinking_process" in decision_data:
                    logger.info(f"[ChiefAgent] Thinking: {decision_data['thinking_process'][:200]}...")
                if "efficiency_note" in decision_data:
                    logger.info(f"[ChiefAgent] Efficiency: {decision_data['efficiency_note'][:100]}...")
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
                "role": "File Processing",
                "text": "File processing agents not available. Please install required libraries."
            })
            return {"error": "File processing not available"}
        
        return await self.file_processor.process_file(file_path, file_type, websocket)
    
    async def think(self, message: str) -> Dict[str, Any]:
        """Thinker phase: Intelligently assess query complexity and choose minimal agent strategy"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": [],
            "selection_reasoning": "",
            "complexity": "simple",  # simple, moderate, or complex
            "research_priority": "minimal"  # Keep this for compatibility
        }
        
        # First: Assess query complexity
        # Simple arithmetic or basic questions
        if any(pattern in message.lower() for pattern in ['2+2', '2 + 2', 'what is', 'calculate', 'compute']) and len(message) < 50:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "simple_calculation"
            thinking_process["analysis"] = f"Simple calculation: {message}"
            thinking_process["agents_to_use"] = ["CodeAgent"]
            thinking_process["selection_reasoning"] = f"User asks '{message}' - this is a simple calculation that only needs Coding Agent"
            return thinking_process
        
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
        
        # FILE SEARCH ON USER'S COMPUTER
        if is_file_search or ('find' in message.lower() and 'file' in message.lower()):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "file_search"
            thinking_process["analysis"] = f"User wants to find files related to: {message}"
            thinking_process["agents_to_use"] = ["ShellAgent"]
            thinking_process["selection_reasoning"] = f"File search query - only Shell Agent needed with find/grep commands"
            return thinking_process
        # Simple SQL query
        elif any(word in message.lower() for word in ['sql', 'select', 'create table', 'database']):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "sql_query"
            thinking_process["analysis"] = f"SQL operation requested"
            thinking_process["agents_to_use"] = ["SQLAgent"]
            thinking_process["selection_reasoning"] = f"SQL query - only SQL Agent needed"
            return thinking_process
        # Data processing - moderate complexity
        elif is_data_task or (has_file_path and any(ext in message.lower() for ext in ['.csv', '.json', '.xlsx'])):
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "data_processing"
            thinking_process["analysis"] = f"Data processing task"
            thinking_process["agents_to_use"] = ["CodeAgent", "SQLAgent"]  # Only essential agents
            thinking_process["selection_reasoning"] = f"Data task - Coding Agent for analysis, SQL Agent for storage"
        # Complex mathematical derivation
        elif any(word in message.lower() for word in ['derive', 'proof', 'theorem', 'maxwell', 'equation']):
            thinking_process["complexity"] = "complex"
            thinking_process["identified_type"] = "mathematical_derivation"
            thinking_process["analysis"] = f"Complex derivation requested"
            thinking_process["agents_to_use"] = ["MathAgent", "CodeAgent"]
            thinking_process["selection_reasoning"] = f"Mathematical derivation - Math Agent for theory, Coding Agent for verification"
        # Simple computation
        elif is_computation:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "computation"
            thinking_process["analysis"] = f"Computational task"
            thinking_process["agents_to_use"] = ["CodeAgent"]
            thinking_process["selection_reasoning"] = f"Computation - only Coding Agent needed"
        # Shell commands
        elif has_shell_command:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "shell_command"
            thinking_process["analysis"] = f"Shell command execution"
            thinking_process["agents_to_use"] = ["ShellAgent"]
            thinking_process["selection_reasoning"] = f"Shell command - only Shell Agent needed"
        # File download
        elif has_url:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "file_download"
            thinking_process["analysis"] = f"File download from URL"
            thinking_process["agents_to_use"] = ["FileAgent"]
            thinking_process["selection_reasoning"] = f"URL download - only File Agent needed"
        # Default: Use minimal agents based on keywords
        else:
            # Try to be smart about the default
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "general_query"
            thinking_process["analysis"] = f"General query: {message[:100]}"
            # Default to just Coding Agent for most things
            thinking_process["agents_to_use"] = ["CodeAgent"]
            thinking_process["selection_reasoning"] = f"General query - starting with Coding Agent, can add more if needed"
            
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
                logger.info(f"[ORCHESTRATOR] Result {i+1} UI label: {result.display_name}")
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
                
                # Determine which agent failed based on index
                agent_name = "Unknown Agent"
                display_name = "Unknown Agent"
                if i < len(agents):
                    agent = agents[i]
                    agent_name = agent.__class__.__name__
                    # Map agent to display name
                    agent_display_names = {
                        "CodeAgent": "Coding Agent",
                        "ShellAgent": "Shell Executor",
                        "SQLAgent": "SQL Agent",
                        "MathAgent": "Math Agent",
                        "ResearchAgent": "Research Agent",
                        "StrategyAgent": "Strategy Agent",
                        "DataAgent": "Data Agent",
                        "NotesAgent": "Notes Agent",
                        "FileAgent": "File Manager"
                    }
                    display_name = agent_display_names.get(agent_name, agent_name)
                
                # Create error report with detailed information
                error_type = type(result).__name__
                error_msg = str(result)
                
                # Check for common error patterns and provide specific guidance
                error_details = f"""Exception Type: {error_type}
Error Message: {error_msg}
Agent: {agent_name}
Task: {message[:200]}{'...' if len(message) > 200 else ''}"""
                
                suggested_fix = "Review the error details and check:"
                if "OPENAI_API_KEY" in error_msg or "api_key" in error_msg.lower():
                    suggested_fix += "\n- Ensure OPENAI_API_KEY is set in environment"
                    suggested_fix += "\n- Check the API key is valid and has proper permissions"
                elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                    suggested_fix += "\n- Check network connectivity"
                    suggested_fix += "\n- Verify firewall settings allow API access"
                elif "timeout" in error_msg.lower():
                    suggested_fix += "\n- The operation took too long to complete"
                    suggested_fix += "\n- Try a simpler query or break it into smaller parts"
                elif "module" in error_msg.lower() or "import" in error_msg.lower():
                    suggested_fix += "\n- Required Python modules may not be installed"
                    suggested_fix += "\n- Check if all dependencies are properly installed"
                else:
                    suggested_fix += "\n- Check the agent's configuration"
                    suggested_fix += "\n- Review the error message for specific issues"
                
                # Create an AgentResult for the exception
                error_result = AgentResult(
                    agent_name=agent_name,
                    display_name=display_name,
                    result=f"""**Agent Failure Report:**\n\n{display_name} encountered an unexpected error and could not complete the task.\n\n**Error Details:**\n```\n{error_details}\n```\n\n**Suggested Fix:**\n{suggested_fix}\n\n**What the Chief Agent should know:**\nThis agent crashed during execution. The error has been logged and detailed information is provided above for troubleshooting.""",
                    confidence=0.0,
                    method="Agent Exception",
                    explanation=f"Agent crashed: {error_type}",
                    summary=f"{display_name} failed with {error_type}: {error_msg[:100]}{'...' if len(error_msg) > 100 else ''}"
                )
                
                # Send the error as an agent result
                await websocket.send_json({
                    "type": "agent_result",
                    "agent_name": display_name,
                    "text": error_result.result,
                    "summary": error_result.summary,
                    "metadata": {
                        "agent": agent_name,
                        "confidence": 0.0,
                        "method": "Agent Exception",
                        "error": True,
                        "error_type": error_type,
                        "summary": error_result.summary
                    }
                })
                valid_results.append(error_result)
                await asyncio.sleep(0.2)
                
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
        
        # ALWAYS save notes after every agent response cycle (whether loop or final)
        # This ensures all intermediate findings are captured in the database
        if NOTES_AVAILABLE and db_session and project_id and branch_id:
            try:
                note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                
                # Include iteration info in the notes
                enhanced_decision = dict(chief_decision)
                enhanced_decision['iteration'] = iteration
                enhanced_decision['is_final'] = chief_decision.get('decision') != 'loop'
                enhanced_decision['total_iterations'] = iteration + 1
                
                note_id = await note_taker.save_agent_notes(
                    agent_results=valid_results,
                    user_query=message, 
                    chief_decision=enhanced_decision
                )
                if note_id:
                    logger.info(f"[ORCHESTRATOR] Saved iteration {iteration + 1} notes to database with ID: {note_id}")
                    # Send notification to websocket about note save
                    await websocket.send_json({
                        "type": "note_saved",
                        "note_id": note_id,
                        "iteration": iteration + 1,
                        "is_final": chief_decision.get('decision') != 'loop',
                        "message": f"Iteration {iteration + 1} analysis saved to Notes"
                    })
                else:
                    logger.warning(f"[ORCHESTRATOR] No note ID returned for iteration {iteration + 1}")
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Failed to save notes for iteration {iteration + 1}: {e}")
                # Don't fail the whole orchestration if notes fail to save
                # But make sure we log it prominently
        
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
                        "role": result.display_name or "Agent",
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
        
        # Don't send stream update that would overwrite the bubble
        # Just proceed directly to the final message
        
        # Calculate total time before using it
        total_time = time.time() - orchestration_start
        
        # Use Chief Agent's final answer
        result_text = final_answer
        
        # Check if the Chief Agent already provided a fully formatted response
        # Look for the key structural elements that indicate it's already formatted
        has_answer_section = '**Answer:**' in result_text or 'Answer:' in result_text
        has_why_section = '**Why:**' in result_text or 'Why:' in result_text
        has_agent_section = '**What Each Agent Found:**' in result_text or 'What Each Agent Found:' in result_text
        has_next_steps = '**Suggested Next Steps:**' in result_text or 'Suggested Next Steps:' in result_text
        
        # If the Chief Agent already formatted the response completely, use it as-is
        if has_answer_section and (has_why_section or has_agent_section or has_next_steps):
            # The Chief Agent has already provided a fully formatted response
            final_text = result_text
            logger.info("[ORCHESTRATOR] Using Chief Agent's pre-formatted response")
        else:
            # The Chief Agent provided an unformatted response, so format it
            logger.info("[ORCHESTRATOR] Formatting Chief Agent's raw response")
            
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
        # Send as 'final' type to stop the frontend timer
        logger.info("[ORCHESTRATOR] Sending final message with type='final'")
        await websocket.send_json({
            "type": "final",
            "text": final_text,
            "json": {
                "role": 'The Chief Agent',
                "selected_agent": selected_agent,
                "chief_reasoning": reasoning,
                "confidence": max([r.confidence for r in valid_results]) if valid_results else 0.0,
                "method": "Chief Agent Decision",
                "orchestration_time": total_time,
                "metadata": {
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
            }
        })
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Orchestration completed in {total_time:.3f}s")
        logger.info(f"[ORCHESTRATOR] Final answer: {final_answer[:100]}...")
        logger.info(f"[ORCHESTRATOR] Notes saved for all {iteration + 1} iteration(s)")
        logger.info("="*80)
        

# Export the advanced orchestrator
__all__ = ['ThinkerOrchestrator', 'ChiefAgent']