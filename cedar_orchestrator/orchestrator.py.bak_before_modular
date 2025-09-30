"""
Main Orchestrator Module
Coordinates all agents through the Chief Agent decision-making system

This module contains the ThinkerOrchestrator class which:
- Manages all specialized agents (Code, SQL, Shell, Research, etc.)
- Delegates decision-making to ChiefAgent (imported from chief_agent module)
- Handles agent coordination, iteration management, and result processing
- Provides WebSocket-based real-time communication for agent activities
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

# Import all agents from the agents package
from .agents import (
    AgentResult,
    ShellAgent,
    CodeAgent,
    SQLAgent,
    FormulaAgent,
    ResearchAgent,
    StrategyAgent,
    DataAgent,
    NotesAgent,
    FileAgent,
    ImageCreationAgent,
    ImageAnalysisAgent,
    FileReaderAgent,
    LangExtractAgent,
    OCRAgent,
    PDFExtractionAgent,
    SQLMetadataAgent
)

# Import ChiefAgent from separate module
from .chief_agent import ChiefAgent

# File processing orchestrator is still in the parent module
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
        self.formula_agent = FormulaAgent(self.llm_client)
        self.research_agent = ResearchAgent(self.llm_client)
        self.strategy_agent = StrategyAgent(self.llm_client)
        self.data_agent = DataAgent(self.llm_client)
        self.notes_agent = NotesAgent(self.llm_client)
        self.file_agent = FileAgent(self.llm_client)  # Will get context during orchestration
        # Images
        self.image_creation_agent = ImageCreationAgent(self.llm_client)
        self.image_analysis_agent = ImageAnalysisAgent(self.llm_client)
        
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
    
        """Thinker phase: Assess query complexity and choose agents for confident answers"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": [],
            "selection_reasoning": "",
            "complexity": "simple",  # simple, moderate, or complex
            "confidence_strategy": "appropriate"  # appropriate, comprehensive, or exhaustive
        }
        
        # First: Assess query complexity
        # Simple arithmetic or basic questions - but still might benefit from multiple agents
        if any(pattern in message.lower() for pattern in ['2+2', '2 + 2', 'what is', 'calculate', 'compute']) and len(message) < 50:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "simple_calculation"
            thinking_process["analysis"] = f"Calculation query: {message}"
            thinking_process["agents_to_use"] = ["CodeAgent", "FormulaAgent"]  # Use both for validation
            thinking_process["selection_reasoning"] = f"User asks '{message}' - using Code and Formula agents for confident verification"
            thinking_process["confidence_strategy"] = "appropriate"
            return thinking_process
        
        # Analyze the message for research context
        import re
        has_url = bool(re.search(r'https?://[^\s]+', message))
        has_file_path = bool(re.search(r'(/[^\s]+\.[a-zA-Z]{2,4}|[A-Za-z]:\\[^\s]+|\./[^\s]+)', message))
        has_shell_command = bool(re.search(r'`[^`]+`', message)) or any(cmd in message.lower() for cmd in ['grep', 'find', 'ls', 'cat', 'brew install', 'pip install', 'npm install', 'apt-get', 'chmod', 'mkdir', 'rm', 'cp', 'mv'])
        # Image-related heuristics
        msg_lower = message.lower()
        has_image_word = any(w in msg_lower for w in ['image','images','picture','photo','plot','chart','visualize','render','thumbnail'])
        wants_create = any(w in msg_lower for w in ['create','generate','draw','render','visualize','plot','chart'])
        wants_analyze = any(w in msg_lower for w in ['analyz','describe','what\'s in','what is in'])
        file_ctx_present = bool((context or {}).get('file_id'))
        
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
            thinking_process["agents_to_use"] = ["FormulaAgent", "CodeAgent"]
            thinking_process["selection_reasoning"] = f"Mathematical derivation - Formula Agent for theory, Coding Agent for verification"
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
        # Image creation / visualization
        elif has_image_word and wants_create:
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "image_creation"
            thinking_process["analysis"] = "Image generation or visualization requested"
            thinking_process["agents_to_use"] = ["ImageCreationAgent"]
            thinking_process["selection_reasoning"] = "Use Image Creation to generate an image and save it to Files/Images"
        # Image analysis
        elif (has_image_word and wants_analyze) or (file_ctx_present and has_image_word):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "image_analysis"
            thinking_process["analysis"] = "Analyze an image and update metadata"
            thinking_process["agents_to_use"] = ["ImageAnalysisAgent"]
            thinking_process["selection_reasoning"] = "Use Image Analysis to describe and tag the image"
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
        
    async def orchestrate(self, message: str, websocket, iteration: int = 0, previous_results: List[AgentResult] = None, project_id: int = None, branch_id: int = None, thread_id: int = None, db_session = None, conversation_history: Optional[str] = None, file_id: int = None, dataset_id: int = None):
        """Full orchestration process controlled by Chief Agent decisions with optional notes persistence
        
        Args:
            file_id: File ID for file upload context (preserved across iterations)
            dataset_id: Dataset ID for data processing context (preserved across iterations)
        """
        orchestration_start = time.time()
        # file_id and dataset_id are now parameters, not local vars
        # Structured run logs (always passed to the Chief Agent)
        run_logs: List[str] = []
        try:
            run_logs.append(f"Start: t={orchestration_start:.3f}s message={message[:120]}")
        except Exception:
            pass
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration (iteration: {iteration})")
        logger.info(f"[ORCHESTRATOR] Context: project_id={project_id}, branch_id={branch_id}, file_id={file_id}, dataset_id={dataset_id}")
        logger.info(f"[ORCHESTRATOR] Message: {message[:200]}...")
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
        
        # Phase 1: Chief Agent planning (stream analysis before sub-agents) and selection
        # ONLY RUN THIS ON ITERATION 0 - subsequent iterations have previous_results and should skip to Phase 3
        planning_decision = None
        
        if iteration == 0:
            logger.info("[ORCHESTRATOR] PHASE 1: Chief Agent Planning (iteration 0 only)")
            try:
                run_logs.append("Phase: planning.start")
            except Exception:
                pass
            try:
                planning_decision = await self.chief_agent.review_and_decide(
                    user_query=message,
                    agent_results=[],  # no agent results yet in iteration 0
                    iteration=iteration,
                    max_iterations=self.MAX_ITERATIONS,
                    previous_context="",
                    resources=None,
                    conversation_history=conversation_history,
                    ws=websocket,  # emit thinking_start + prompt + thinking
                    run_logs=run_logs,
                    thread_id=thread_id  # pass thread_id for WebSocket event correlation
                )
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Pre-analysis planning emit failed: {e}")
                try:
                    run_logs.append(f"Error: planning.emit_failed: {type(e).__name__}: {e}")
                except Exception:
                    pass
                planning_decision = {"decision": "loop", "agent_tasks": []}
        else:
            logger.info(f"[ORCHESTRATOR] SKIP PHASE 1: Iteration {iteration} has previous_results={len(previous_results or [])} results, going straight to Phase 3 synthesis")
            # Skip to Phase 3 with previous results - no need to plan again
            pass

        # Short-circuit only for clarifications - Chief Agent must NOT answer directly without agents
        try:
            if planning_decision and planning_decision.get('decision') == 'clarify':
                clarification_question = planning_decision.get('clarification_question', 'Could you please provide more details about your request?')
                thinking = planning_decision.get('thinking_process', 'Need more information from user')
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": f"""🤔 **Clarification Needed**\n\n{thinking}\n\n**Question:** {clarification_question}\n\nPlease provide this information so I can better assist you."""
                })
                return
            # REMOVED: Chief Agent should NEVER finalize without running agents first
            # All work must be delegated to specialized agents
        except Exception:
            pass

        # Phase 2: Only run if we're in iteration 0 (planning phase)
        # For iteration 1+, skip to Phase 3 with previous_results
        valid_results = []
        
        if iteration == 0:
            # Parse agent_tasks from planning_decision
            agent_tasks_list = []
            try:
                if isinstance(planning_decision.get('agent_tasks'), list):
                    agent_tasks_list = planning_decision.get('agent_tasks', [])
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to parse agent_tasks: {e}")
                agent_tasks_list = []
        
            # Extract unique agent names from tasks
            agents_to_use = []
            agent_task_map = {}  # Map agent name to task string
            for task_entry in agent_tasks_list:
                try:
                    agent_name = str(task_entry.get('agent', '')).strip()
                    task_str = str(task_entry.get('task', '')).strip()
                    context = task_entry.get('context', {})
                    if agent_name and task_str:
                        if agent_name not in agents_to_use:
                            agents_to_use.append(agent_name)
                        # Store task and context for this agent
                        agent_task_map[agent_name] = {
                            'task': task_str,
                            'context': context
                        }
                except Exception as e:
                    logger.warning(f"[ORCHESTRATOR] Failed to parse task entry: {e}")
            
            logger.info(f"[ORCHESTRATOR] Agents selected by Chief Agent: {agents_to_use}")
            logger.info(f"[ORCHESTRATOR] Agent tasks: {agent_task_map}")
            try:
                run_logs.append("Planning: agents=" + ",".join(agents_to_use))
            except Exception:
                pass

            # Phase 2: Parallel agent processing based on Chief Agent selection
            logger.info("[ORCHESTRATOR] PHASE 2: Parallel Agent Processing (from Chief selection)")
            agents = []
            # Helper to add agent if requested
            def _add(agent_name: str, agent_obj):
                nonlocal agents
                if agent_name in agents_to_use:
                    agents.append(agent_obj)
                    logger.info(f"[ORCHESTRATOR] Added {agent_name} to processing queue")
                    try:
                        run_logs.append(f"Queue: {agent_name}")
                    except Exception:
                        pass
            _add("CodeAgent", self.code_agent)
            _add("SQLAgent", self.sql_agent)
            _add("ShellAgent", self.shell_agent)
            _add("FormulaAgent", self.formula_agent)
            _add("ResearchAgent", self.research_agent)
            _add("StrategyAgent", self.strategy_agent)
            _add("DataAgent", self.data_agent)
            _add("NotesAgent", self.notes_agent)
            _add("ImageCreationAgent", self.image_creation_agent)
            _add("ImageAnalysisAgent", self.image_analysis_agent)
            if "FileAgent" in agents_to_use:
                if db_session and project_id and branch_id:
                    self.file_agent.project_id = project_id
                    self.file_agent.branch_id = branch_id
                    self.file_agent.db_session = db_session
                agents.append(self.file_agent)
                logger.info("[ORCHESTRATOR] Added FileAgent to processing queue")

            # Process all agents in parallel
            logger.info(f"[ORCHESTRATOR] Starting parallel processing with {len(agents)} agents")
            parallel_start = time.time()
            
            # Track whether any agent error occurred
            had_errors = False
            
            # Don't send stream updates that would overwrite the Chief Agent analysis
            # The detailed analysis message is complete and should stand on its own
            
            # Create agent tasks - use specific task strings from agent_task_map
            agent_tasks = []
            for agent in agents:
                agent_class_name = agent.__class__.__name__
                
                # Get the specific task for this agent, fallback to user message
                task_info = agent_task_map.get(agent_class_name, {'task': message, 'context': {}})
                task_str = task_info.get('task', message)
                task_context = task_info.get('context', {})
                
                logger.info(f"[ORCHESTRATOR] Dispatching to {agent_class_name} with task: {task_str[:100]}...")
                
                if isinstance(agent, ShellAgent):
                    conversation_context = f"User Query: {message}\nIteration: {iteration + 1}\nSpecific Task: {task_str}"
                    agent_tasks.append(agent.process(task_str, conversation_context=conversation_context))
                elif agent is self.image_creation_agent:
                    agent_tasks.append(agent.process(task_str, project_id=project_id, branch_id=branch_id, db_session=db_session))
                elif agent is self.image_analysis_agent:
                    # ImageAnalysisAgent may need file_id from context
                    file_id_for_analysis = task_context.get('file_id', file_id)
                    agent_tasks.append(agent.process(task_str, project_id=project_id, branch_id=branch_id, db_session=db_session, file_id=file_id_for_analysis))
                elif agent is self.data_agent:
                    # DataAgent may use project_id from context
                    project_id_for_data = task_context.get('project_id', project_id)
                    agent_tasks.append(agent.process(task_str, project_id=project_id_for_data))
                elif agent is self.notes_agent:
                    # NotesAgent may have content_to_note in context
                    content_to_note = task_context.get('content_to_note', '')
                    existing_notes = task_context.get('existing_notes', [])
                    agent_tasks.append(agent.process(task_str, content_to_note=content_to_note, existing_notes=existing_notes))
                else:
                    # Default: just pass the task string
                    agent_tasks.append(agent.process(task_str))
            
            results = await asyncio.gather(*agent_tasks, return_exceptions=True)
            logger.info(f"[ORCHESTRATOR] Parallel processing completed in {time.time() - parallel_start:.3f}s")
            try:
                run_logs.append(f"Phase: agents.done dt={time.time() - parallel_start:.3f}s count={len(agents)}")
            except Exception:
                pass
            
            # Send agent results
            logger.info("[ORCHESTRATOR] Processing agent results")
            valid_results = []
            for i, result in enumerate(results):
                if isinstance(result, AgentResult):
                    logger.info(f"[ORCHESTRATOR] Result {i+1}: {result.agent_name} - Confidence: {result.confidence:.2f}, Method: {result.method}")
                    logger.info(f"[ORCHESTRATOR] Result {i+1} UI label: {result.display_name}")
                    logger.info(f"[ORCHESTRATOR] Result {i+1} content: {result.result[:200]}...")
                    
                    # Persist code artifacts even if not selected by Chief Agent
                    try:
                        if db_session and project_id and branch_id and getattr(result, 'artifacts', None):
                            art = result.artifacts or {}
                            if str(art.get('type', '')).lower() == 'code' and str(art.get('source', '')).strip():
                                from main_models import SavedCode
                                name = (str(art.get('name') or '') or 'Generated Code')[:255]
                                desc = str(art.get('description') or '')
                                lang = str(art.get('language') or 'python')[:50]
                                src = str(art.get('source') or '')
                                sc = SavedCode(
                                    project_id=int(project_id),
                                    branch_id=int(branch_id),
                                    name=name,
                                    description=desc,
                                    language=lang,
                                    code=src,
                                    agent_name=(result.display_name or result.agent_name)[:100]
                                )
                                db_session.add(sc)
                                db_session.commit()
                                logger.info(f"[ORCHESTRATOR] Saved code snippet id={getattr(sc, 'id', None)} lang={lang} name={name[:40]}")
                    except Exception as e:
                        logger.warning(f"[ORCHESTRATOR] Failed to persist code artifact: {type(e).__name__}: {e}")
                    
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
                    try:
                        short = (result.summary or (result.result or '').split('\n',1)[0] or '').strip()
                        if len(short) > 160: short = short[:160]
                        run_logs.append(f"AgentOK: {result.display_name} conf={result.confidence:.2f} sum={short}")
                    except Exception:
                        pass
                    valid_results.append(result)
                    await asyncio.sleep(0.2)
                elif isinstance(result, Exception):
                    logger.error(f"[ORCHESTRATOR] Agent {i+1} failed with exception: {result}")
                    had_errors = True
                    
                    # Determine which agent failed based on index
                    agent_name = "Unknown Agent"
                    display_name = "Unknown Agent"
                    if i < len(agents):
                        agent = agents[i]
                        agent_name = agent.__class__.__name__
                        # Map agent to display name
                        agent_display_names = {
                            "CodeAgent": "Coding Agent",
                            "ShellAgent": "Desktop Agent",
                            "SQLAgent": "SQL Agent",
                            "FormulaAgent": "Formula Agent",
                            "ResearchAgent": "Research Agent",
                            "StrategyAgent": "Strategy Agent",
                            "DataAgent": "Data Agent",
                            "NotesAgent": "Notes Agent",
                            "FileAgent": "File Manager",
                            "ImageCreationAgent": "Image Creation",
                            "ImageAnalysisAgent": "Image Analysis"
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
                try:
                    run_logs.append(f"AgentERR: {display_name} type={error_type} msg={error_msg[:160]}")
                except Exception:
                    pass
                valid_results.append(error_result)
                await asyncio.sleep(0.2)
            else:
                # Iteration 1+: Use previous_results instead of running agents again
                logger.info(f"[ORCHESTRATOR] PHASE 2 SKIPPED: Using previous_results from iteration {iteration - 1}")
                valid_results = previous_results or []
                logger.info(f"[ORCHESTRATOR] Loaded {len(valid_results)} results from previous iteration")
                
        # Phase 3: Chief Agent Review and Decision
        logger.info("[ORCHESTRATOR] PHASE 3: Chief Agent Review and Decision")
        logger.info(f"[ORCHESTRATOR] Chief Agent reviewing {len(valid_results)} valid results")
        
        # Don't send stream updates - let agent results speak for themselves
        
        # Do not pass previous iterations context to Chief Agent; keep input minimal
        previous_context = ""
        
        # Have Chief Agent review all results and make a decision
        # Build resource index for the Chief Agent (names + official IDs)
        resources_index: Optional[Dict[str, Any]] = None
        try:
            if db_session and project_id and branch_id:
                resources_index = {"files": [], "code": [], "databases": [], "notes": [], "images": []}
                # Files and Images from FileEntry
                try:
                    from main_models import FileEntry
                    files = db_session.query(FileEntry).filter(
                        FileEntry.project_id == int(project_id),
                        FileEntry.branch_id == int(branch_id)
                    ).order_by(FileEntry.created_at.desc()).limit(1000).all()
                    for f in files:
                        title = (getattr(f, 'ai_title', None) or f.display_name or '').strip() or f.filename
                        rec = {"id": f.id, "name": title, "structure": f.structure, "file_type": f.file_type}
                        resources_index["files"].append(rec)
                        # Basic image heuristic
                        ft = (f.file_type or '').lower()
                        if (f.structure or '').lower() == 'images' or ft in {"jpg","jpeg","png","gif","webp","bmp","tiff"}:
                            resources_index["images"].append({"id": f.id, "name": title})
                except Exception:
                    pass
                # Saved code snippets
                try:
                    from main_models import SavedCode
                    codes = db_session.query(SavedCode).filter(
                        SavedCode.project_id == int(project_id),
                        SavedCode.branch_id == int(branch_id)
                    ).order_by(SavedCode.created_at.desc()).limit(1000).all()
                    for sc in codes:
                        resources_index["code"].append({"id": sc.id, "name": (sc.name or '').strip() or f"Code {sc.id}"})
                except Exception:
                    pass
                # Databases
                try:
                    from main_models import Dataset
                    datasets = db_session.query(Dataset).filter(
                        Dataset.project_id == int(project_id),
                        Dataset.branch_id == int(branch_id)
                    ).order_by(Dataset.created_at.desc()).limit(1000).all()
                    for d in datasets:
                        resources_index["databases"].append({"id": d.id, "name": d.name})
                except Exception:
                    pass
                # Notes (include content)
                try:
                    from main_models import Note
                    notes = db_session.query(Note).filter(
                        Note.project_id == int(project_id),
                        Note.branch_id == int(branch_id)
                    ).order_by(Note.created_at.desc()).limit(1000).all()
                    for n in notes:
                        resources_index["notes"].append({
                            "id": n.id,
                            "title": (getattr(n, 'title', None) or '').strip() or f"Note {n.id}",
                            "content": n.content or ""
                        })
                except Exception:
                    pass
        except Exception:
            resources_index = None

        chief_decision = await self.chief_agent.review_and_decide(
            user_query=message,
            agent_results=valid_results,
            iteration=iteration,
            max_iterations=self.MAX_ITERATIONS,
            previous_context=previous_context,
            resources=None,
            conversation_history=conversation_history,
            ws=None,  # Do not emit thinking during the final review to avoid duplicate planning bubble
            run_logs=run_logs,
            thread_id=thread_id  # pass thread_id for WebSocket event correlation
        )
        logger.info(f"[ORCHESTRATOR] Chief Agent decision: {chief_decision.get('decision')}")
        
        # Log thinking process if available
        if chief_decision.get('thinking_process'):
            logger.info(f"[ORCHESTRATOR] Chief Agent thinking: {chief_decision['thinking_process'][:300]}...")
        
        # Chief Agent analysis is streamed from review_and_decide via 'thinking' event.
        # Always run Notes Agent to create structured notes for every Chief Agent processing step
        try:
            if self.notes_agent is not None:
                existing_notes_list = []
                # If DB session and context are available, fetch recent notes for de-duplication
                if db_session and project_id and branch_id and NOTES_AVAILABLE:
                    try:
                        note_taker_preview = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                        existing_notes_list = await note_taker_preview.get_existing_notes()
                    except Exception as e:
                        logger.warning(f"[ORCHESTRATOR-NOTES] Could not fetch existing notes for NotesAgent: {e}")
                # Prepare concise content for the notes agent: summarize Chief Agent decision only
                try:
                    decision = chief_decision or {}
                except Exception:
                    decision = {}
                try:
                    lines = []
                    lines.append(f"Decision: {decision.get('decision','')}")
                    tp = (decision.get('thinking_process') or '').strip()
                    if tp:
                        lines.append("Thinking Process:\n" + tp)
                    fa = (decision.get('final_answer') or '').strip()
                    if fa:
                        lines.append("Final Answer:\n" + fa)
                    ag = (decision.get('additional_guidance') or '').strip()
                    if ag:
                        lines.append("Additional Guidance:\n" + ag)
                    sel = (decision.get('selected_agent') or '').strip()
                    atu = decision.get('agents_to_use') or []
                    if atu:
                        lines.append("Agents To Use: " + ", ".join(atu))
                    elif sel:
                        lines.append("Selected Agent: " + sel)
                    rsn = (decision.get('reasoning') or '').strip()
                    if rsn:
                        lines.append("Reasoning:\n" + rsn)
                    content_to_note = "\n\n".join(lines)
                except Exception:
                    content_to_note = (chief_decision.get('final_answer') or '').strip() or 'Chief Agent summary'
                try:
                    notes_agent_result = await self.notes_agent.process(
                        task=message,
                        content_to_note=content_to_note,
                        existing_notes=existing_notes_list
                    )
                    if isinstance(notes_agent_result, AgentResult):
                        # Include in results for persistence and UI
                        valid_results.append(notes_agent_result)
                        try:
                            await websocket.send_json({
                                "type": "agent_result",
                                "agent_name": notes_agent_result.display_name,
                                "text": notes_agent_result.result,
                                "summary": getattr(notes_agent_result, 'summary', None),
                                "metadata": {
                                    "agent": "NotesAgent",
                                    "confidence": notes_agent_result.confidence,
                                    "method": notes_agent_result.method,
                                }
                            })
                        except Exception as e:
                            logger.warning(f"[ORCHESTRATOR-NOTES] Failed to send NotesAgent result to WS: {e}")
                except Exception as e:
                    logger.error(f"[ORCHESTRATOR-NOTES] NotesAgent processing failed: {e}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR-NOTES] Unexpected error in NotesAgent always-run block: {e}")
        
        # ALWAYS save notes after every agent response cycle (whether loop or final)
        # This ensures all intermediate findings are captured in the database
        logger.info(f"[ORCHESTRATOR-NOTES] " + "="*50)
        logger.info(f"[ORCHESTRATOR-NOTES] NOTES SAVE CHECK - ITERATION {iteration + 1}")
        logger.info(f"[ORCHESTRATOR-NOTES] " + "="*50)
        logger.info(f"[ORCHESTRATOR-NOTES] NOTES_AVAILABLE: {NOTES_AVAILABLE}")
        logger.info(f"[ORCHESTRATOR-NOTES] db_session exists: {db_session is not None}")
        logger.info(f"[ORCHESTRATOR-NOTES] db_session type: {type(db_session).__name__ if db_session else 'None'}")
        logger.info(f"[ORCHESTRATOR-NOTES] project_id: {project_id}")
        logger.info(f"[ORCHESTRATOR-NOTES] branch_id: {branch_id}")
        logger.info(f"[ORCHESTRATOR-NOTES] iteration: {iteration}")
        logger.info(f"[ORCHESTRATOR-NOTES] chief_decision type: {chief_decision.get('decision')}")
        logger.info(f"[ORCHESTRATOR-NOTES] valid_results count: {len(valid_results)}")
        for i, r in enumerate(valid_results):
            logger.info(f"[ORCHESTRATOR-NOTES]   Result {i}: {r.agent_name} - confidence: {r.confidence}")
        
        if NOTES_AVAILABLE and db_session and project_id and branch_id:
            logger.info(f"[ORCHESTRATOR-NOTES] ✓ All conditions met, attempting to save notes...")
            logger.info(f"[ORCHESTRATOR-NOTES] Using db_session of type: {type(db_session).__name__}")
            logger.info(f"[ORCHESTRATOR-NOTES] db_session bind: {db_session.bind if hasattr(db_session, 'bind') else 'No bind attribute'}")
            try:
                logger.info(f"[ORCHESTRATOR-NOTES] Creating ChiefAgentNoteTaker instance...")
                note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                logger.info(f"[ORCHESTRATOR-NOTES] ChiefAgentNoteTaker created successfully")
                
                # Include iteration info in the notes
                enhanced_decision = dict(chief_decision)
                enhanced_decision['iteration'] = iteration
                enhanced_decision['is_final'] = chief_decision.get('decision') != 'loop'
                enhanced_decision['total_iterations'] = iteration + 1
                
                logger.info(f"[ORCHESTRATOR-NOTES] Enhanced decision prepared:")
                logger.info(f"[ORCHESTRATOR-NOTES]   iteration: {iteration}")
                logger.info(f"[ORCHESTRATOR-NOTES]   is_final: {enhanced_decision['is_final']}")
                logger.info(f"[ORCHESTRATOR-NOTES]   total_iterations: {enhanced_decision['total_iterations']}")
                
                logger.info(f"[ORCHESTRATOR-NOTES] Calling save_agent_notes...")
                logger.info(f"[ORCHESTRATOR-NOTES]   agent_results: {len(valid_results)} results")
                logger.info(f"[ORCHESTRATOR-NOTES]   user_query: {message[:100]}...")
                
                note_id = await note_taker.save_agent_notes(
                    agent_results=valid_results,
                    user_query=message, 
                    chief_decision=enhanced_decision
                )
                
                logger.info(f"[ORCHESTRATOR-NOTES] save_agent_notes returned: {note_id}")
                logger.info(f"[ORCHESTRATOR-NOTES] note_id type: {type(note_id).__name__}")
                
                if note_id:
                    logger.info(f"[ORCHESTRATOR-NOTES] ✅ SUCCESS: Saved iteration {iteration + 1} notes to database")
                    logger.info(f"[ORCHESTRATOR-NOTES] Note ID: {note_id}")
                    
                    # Send notification to websocket about note save
                    logger.info(f"[ORCHESTRATOR-NOTES] Sending note_saved notification to WebSocket...")
                    note_saved_msg = {
                        "type": "note_saved",
                        "note_id": note_id,
                        "iteration": iteration + 1,
                        "is_final": chief_decision.get('decision') != 'loop',
                        "message": f"Iteration {iteration + 1} analysis saved to Notes"
                    }
                    logger.info(f"[ORCHESTRATOR-NOTES] WebSocket message: {note_saved_msg}")
                    await websocket.send_json(note_saved_msg)
                    logger.info(f"[ORCHESTRATOR-NOTES] WebSocket notification sent successfully")
                else:
                    logger.warning(f"[ORCHESTRATOR-NOTES] ⚠️ WARNING: No note ID returned for iteration {iteration + 1}")
                    logger.warning(f"[ORCHESTRATOR-NOTES] save_agent_notes returned: {note_id}")
                    logger.warning(f"[ORCHESTRATOR-NOTES] This likely means the note was not saved")
            except Exception as e:
                logger.error(f"[ORCHESTRATOR-NOTES] ❌ ERROR: Failed to save notes for iteration {iteration + 1}")
                logger.error(f"[ORCHESTRATOR-NOTES] Exception type: {type(e).__name__}")
                logger.error(f"[ORCHESTRATOR-NOTES] Exception message: {str(e)}")
                import traceback
                logger.error(f"[ORCHESTRATOR-NOTES] Full traceback:\n{traceback.format_exc()}")
                # Don't fail the whole orchestration if notes fail to save
                # But make sure we log it prominently
        else:
            logger.warning(f"[ORCHESTRATOR-NOTES] ⚠️ SKIPPING NOTES SAVE - Missing requirements:")
            if not NOTES_AVAILABLE:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ NOTES_AVAILABLE is False")
            if not db_session:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ db_session is None")
            if not project_id:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ project_id is None or False: {project_id}")
            if not branch_id:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ branch_id is None or False: {branch_id}")
        
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
        # Limit looping to 3 iterations if errors occurred; otherwise use MAX_ITERATIONS
        allowed_loops = 3 if 'had_errors' in locals() and had_errors else self.MAX_ITERATIONS
        if chief_decision.get('decision') == 'loop' and iteration < allowed_loops - 1:
            # Chief Agent wants another iteration
            guidance = (chief_decision.get('additional_guidance', '') or '').strip()
            thinking = chief_decision.get('thinking_process', 'Analyzing how to improve the answer...')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting iteration {iteration + 1} with guidance: {guidance}")

            # Do not synthesize guidance locally; keep decisions LLM-driven. If missing, proceed without guidance.
            if not guidance:
                logger.info("[ORCHESTRATOR] No additional_guidance provided by Chief Agent; proceeding without local synthesis.")

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
            if guidance and '`' in guidance:
                # Extract command from guidance if present
                cmd_match = re.search(r'`([^`]+)`', guidance)
                if cmd_match:
                    # Pass the command directly for Shell Agent
                    enhanced_message = f"Execute: `{cmd_match.group(1)}`\n\nOriginal request: {message}"
                else:
                    enhanced_message = f"{message}\n\nRefinement guidance: {guidance}"
            else:
                enhanced_message = f"{message}"

            # Brief delay for UI
            await asyncio.sleep(0.3)

            # Start next iteration with Chief Agent's guidance - preserve all context
            return await self.orchestrate(
                enhanced_message, 
                websocket, 
                iteration + 1, 
                valid_results, 
                project_id, 
                branch_id, 
                thread_id,  # Preserve thread_id across iterations
                db_session, 
                conversation_history,  # Preserve conversation history
                file_id,  # CRITICAL: Preserve file_id for ImageAnalysisAgent in subsequent iterations
                dataset_id  # Preserve dataset_id if present
            )
        
        # Chief Agent has made final decision - extract JSON fields only
        final_answer = chief_decision.get('final_answer', '')
        selected_agent = chief_decision.get('selected_agent', 'The Chief Agent')
        reasoning = chief_decision.get('reasoning', '')
        
        logger.info(f"[ORCHESTRATOR] Chief Agent FINAL decision")
        logger.info(f"[ORCHESTRATOR] Selected approach: {selected_agent}")
        logger.info(f"[ORCHESTRATOR] Final answer: {final_answer[:200]}...")
        
        # Calculate total time
        total_time = time.time() - orchestration_start
        
        # Use the LLM's formatted answer directly - no parsing, no manipulation
        final_text = final_answer
        
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