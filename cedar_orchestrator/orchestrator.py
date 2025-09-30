"""
Main Orchestrator Module (Refactored)

Simplified coordinator that delegates responsibilities to specialized modules:
- agent_dispatcher: Agent selection and parallel execution
- agent_result_processor: Result processing and error handling
- resource_indexer: Building project resource indexes
- chief_agent: Decision-making and synthesis
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import all agents from the agents package
from .agents import (
    AgentResult, ShellAgent, CodeAgent, SQLAgent, FormulaAgent,
    ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FileAgent,
    ImageCreationAgent, ImageAnalysisAgent, FileReaderAgent,
    LangExtractAgent, OCRAgent, PDFExtractionAgent, SQLMetadataAgent
)

# Import modular components
from .chief_agent import ChiefAgent
from .agent_dispatcher import AgentDispatcher
from .agent_result_processor import AgentResultProcessor
from .resource_indexer import ResourceIndexer
from .notes_persistence import NotesPersistence

# File processing orchestrator
try:
    from .file_processing_agents import FileProcessingOrchestrator
    FILE_PROCESSING_AVAILABLE = True
except ImportError:
    FILE_PROCESSING_AVAILABLE = False

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
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
    
    MAX_ITERATIONS = 10
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.chief_agent = ChiefAgent(self.llm_client)
        
        # Initialize all agents
        self.code_agent = CodeAgent(self.llm_client)
        self.sql_agent = SQLAgent(self.llm_client)
        self.shell_agent = ShellAgent(self.llm_client)
        self.formula_agent = FormulaAgent(self.llm_client)
        self.research_agent = ResearchAgent(self.llm_client)
        self.strategy_agent = StrategyAgent(self.llm_client)
        self.data_agent = DataAgent(self.llm_client)
        self.notes_agent = NotesAgent(self.llm_client)
        self.file_agent = FileAgent(self.llm_client)
        self.image_creation_agent = ImageCreationAgent(self.llm_client)
        self.image_analysis_agent = ImageAnalysisAgent(self.llm_client)
        
        # File processor
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
    
    async def orchestrate(
        self,
        message: str,
        websocket: WebSocket,
        iteration: int = 0,
        previous_results: List[AgentResult] = None,
        project_id: int = None,
        branch_id: int = None,
        thread_id: int = None,
        db_session = None,
        conversation_history: Optional[str] = None,
        file_id: int = None,
        dataset_id: int = None
    ):
        """Main orchestration flow"""
        orchestration_start = time.time()
        run_logs: List[str] = []
        
        logger.info("=" * 80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration (iteration: {iteration})")
        logger.info(f"[ORCHESTRATOR] Message: {message[:200]}...")
        logger.info("=" * 80)
        
        # Check iteration limit
        if iteration >= self.MAX_ITERATIONS:
            await self._send_max_iterations_message(websocket, previous_results)
            return
        
        # Phase 1: Chief Agent Planning (iteration 0 only)
        planning_decision = None
        if iteration == 0:
            logger.info("[ORCHESTRATOR] PHASE 1: Chief Agent Planning")
            planning_decision = await self.chief_agent.review_and_decide(
                user_query=message,
                agent_results=[],
                iteration=iteration,
                max_iterations=self.MAX_ITERATIONS,
                previous_context="",
                resources=None,
                conversation_history=conversation_history,
                ws=websocket,
                run_logs=run_logs,
                thread_id=thread_id
            )
            
            # Handle clarification request
            if planning_decision.get('decision') == 'clarify':
                await self._send_clarification(websocket, planning_decision)
                return
        
        # Phase 2: Agent Execution (iteration 0) or use previous results (iteration 1+)
        valid_results = []
        had_errors = False
        
        if iteration == 0:
            logger.info("[ORCHESTRATOR] PHASE 2: Agent Execution")
            
            # Parse agent tasks from Chief Agent
            agent_tasks_list = planning_decision.get('agent_tasks', []) if isinstance(planning_decision.get('agent_tasks'), list) else []
            
            if agent_tasks_list:
                # Select and dispatch agents
                agents, agent_task_map = AgentDispatcher.select_agents(agent_tasks_list, self)
                
                if agents:
                    results = await AgentDispatcher.dispatch_agents(
                        agents, agent_task_map, message, iteration,
                        project_id, branch_id, file_id, db_session
                    )
                    
                    # Process results
                    valid_results, had_errors = await AgentResultProcessor.process_results(
                        results, agents, message, websocket, run_logs,
                        db_session, project_id, branch_id
                    )
        else:
            logger.info(f"[ORCHESTRATOR] PHASE 2 SKIPPED: Using previous results (iteration {iteration})")
            valid_results = previous_results or []
        
        # Phase 3: Chief Agent Synthesis
        logger.info("[ORCHESTRATOR] PHASE 3: Chief Agent Synthesis")
        
        # Build resource index
        resources_index = ResourceIndexer.build_resource_index(db_session, project_id, branch_id)
        
        # Get Chief Agent's final decision
        chief_decision = await self.chief_agent.review_and_decide(
            user_query=message,
            agent_results=valid_results,
            iteration=iteration,
            max_iterations=self.MAX_ITERATIONS,
            previous_context="",
            resources=resources_index,
            conversation_history=conversation_history,
            ws=websocket,
            run_logs=run_logs,
            thread_id=thread_id
        )
        
        # Handle clarification request
        if chief_decision.get('decision') == 'clarify':
            await self._send_clarification(websocket, chief_decision)
            return
        
        # Save notes after every Chief Agent decision (doesn't show in UI bubbles)
        await NotesPersistence.save_orchestration_notes(
            agent_results=valid_results,
            user_query=message,
            chief_decision=chief_decision,
            iteration=iteration,
            project_id=project_id,
            branch_id=branch_id,
            db_session=db_session,
            websocket=websocket
        )
        
        # Handle iteration request
        allowed_loops = 3 if had_errors else self.MAX_ITERATIONS
        if chief_decision.get('decision') == 'loop' and iteration < allowed_loops - 1:
            await self._handle_iteration(
                websocket, chief_decision, iteration, message,
                valid_results, project_id, branch_id, thread_id,
                db_session, conversation_history, file_id, dataset_id
            )
            return
        
        # Send final answer
        await self._send_final_answer(
            websocket, chief_decision, valid_results,
            iteration, orchestration_start
        )
    
    async def _send_max_iterations_message(self, websocket: WebSocket, previous_results: List[AgentResult]):
        """Send message when max iterations reached"""
        text = f"**Note:** Maximum iterations ({self.MAX_ITERATIONS}) reached.\n\n"
        if previous_results:
            text += previous_results[0].result if previous_results else 'Processing limit reached.'
        else:
            text += 'Processing limit reached. Please try a more specific request.'
        
        await websocket.send_json({
            "type": "message",
            "role": "The Chief Agent",
            "text": text
        })
    
    async def _send_clarification(self, websocket: WebSocket, decision: Dict[str, Any]):
        """Send clarification request to user"""
        clarification_question = decision.get('clarification_question', 'Could you please provide more details?')
        thinking = decision.get('thinking_process', 'Need more information from user')
        reasoning = decision.get('reasoning', 'This will help me provide a better response.')
        
        await websocket.send_json({
            "type": "message",
            "role": "The Chief Agent",
            "text": f"""🤔 **Clarification Needed**

{thinking}

**Question:** {clarification_question}

**Why I'm asking:** {reasoning}

Please provide this information so I can better assist you."""
        })
    
    async def _handle_iteration(
        self, websocket: WebSocket, decision: Dict[str, Any],
        iteration: int, message: str, valid_results: List[AgentResult],
        project_id: int, branch_id: int, thread_id: int, db_session,
        conversation_history: str, file_id: int, dataset_id: int
    ):
        """Handle iteration loop request"""
        guidance = decision.get('additional_guidance', '').strip()
        thinking = decision.get('thinking_process', 'Analyzing how to improve...')
        
        logger.info(f"[ORCHESTRATOR] Chief Agent requesting iteration {iteration + 1}")
        
        await websocket.send_json({
            "type": "agent_result",
            "agent_name": "The Chief Agent",
            "text": f"""🔄 Refining Answer (Iteration {iteration + 2}/{self.MAX_ITERATIONS})

🤔 Chief Agent's Analysis:
{thinking}

🎯 Next Approach:
{guidance}

⏳ Running additional analysis..."""
        })
        
        await asyncio.sleep(0.3)
        
        # Recurse with guidance
        await self.orchestrate(
            message, websocket, iteration + 1, valid_results,
            project_id, branch_id, thread_id, db_session,
            conversation_history, file_id, dataset_id
        )
    
    async def _send_final_answer(
        self, websocket: WebSocket, decision: Dict[str, Any],
        valid_results: List[AgentResult], iteration: int, start_time: float
    ):
        """Send final synthesized answer"""
        final_answer = decision.get('final_answer', '')
        selected_agent = decision.get('selected_agent', 'The Chief Agent')
        reasoning = decision.get('reasoning', '')
        
        total_time = time.time() - start_time
        
        # Add metadata
        final_text = final_answer
        if iteration > 0:
            final_text += f"\n_🔄 Resolved after {iteration + 1} iterations in {total_time:.1f}s_"
        else:
            final_text += f"\n_✅ Processed in {total_time:.1f}s_"
        
        await websocket.send_json({
            "type": "final",
            "text": final_text,
            "json": {
                "role": 'The Chief Agent',
                "selected_agent": selected_agent,
                "chief_reasoning": reasoning,
                "confidence": max([r.confidence for r in valid_results]) if valid_results else 0.0,
                "method": "Chief Agent Decision",
                "orchestration_time": total_time
            }
        })
        
        logger.info("=" * 80)
        logger.info(f"[ORCHESTRATOR] Orchestration completed in {total_time:.3f}s")
        logger.info("=" * 80)


__all__ = ['ThinkerOrchestrator', 'ChiefAgent']
