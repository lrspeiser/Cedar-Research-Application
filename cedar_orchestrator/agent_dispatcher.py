"""
Agent Dispatcher Module

Handles creation and parallel dispatch of agent tasks based on Chief Agent decisions.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentDispatcher:
    """Handles agent task creation and parallel execution"""
    
    @staticmethod
    def select_agents(
        agent_tasks_list: List[Dict[str, Any]],
        orchestrator
    ) -> tuple[List[Any], Dict[str, Dict[str, Any]]]:
        """
        Select and prepare agents based on Chief Agent's task list.
        
        Args:
            agent_tasks_list: List of task dicts from Chief Agent (agent, task, context)
            orchestrator: ThinkerOrchestrator instance with agent references
            
        Returns:
            (agents, agent_task_map): List of agent objects and task mapping
        """
        agents = []
        agent_task_map = {}
        
        # Extract unique agent names and their tasks
        for task_entry in agent_tasks_list:
            try:
                agent_name = str(task_entry.get('agent', '')).strip()
                task_str = str(task_entry.get('task', '')).strip()
                context = task_entry.get('context', {})
                
                if agent_name and task_str:
                    if agent_name not in [a.__class__.__name__ for a in agents]:
                        agent_obj = AgentDispatcher._get_agent_by_name(
                            agent_name, orchestrator
                        )
                        if agent_obj:
                            agents.append(agent_obj)
                            agent_task_map[agent_name] = {
                                'task': task_str,
                                'context': context
                            }
                            logger.info(f"[AgentDispatcher] Added {agent_name} to queue")
            except Exception as e:
                logger.warning(f"[AgentDispatcher] Failed to parse task entry: {e}")
        
        logger.info(f"[AgentDispatcher] Selected {len(agents)} agents")
        return agents, agent_task_map
    
    @staticmethod
    def _get_agent_by_name(agent_name: str, orchestrator) -> Optional[Any]:
        """Get agent instance by name from orchestrator"""
        agent_map = {
            "CodeAgent": orchestrator.code_agent,
            "SQLAgent": orchestrator.sql_agent,
            "ShellAgent": orchestrator.shell_agent,
            "FormulaAgent": orchestrator.formula_agent,
            "ResearchAgent": orchestrator.research_agent,
            "StrategyAgent": orchestrator.strategy_agent,
            "DataAgent": orchestrator.data_agent,
            "NotesAgent": orchestrator.notes_agent,
            "FileAgent": orchestrator.file_agent,
            "ImageCreationAgent": orchestrator.image_creation_agent,
            "ImageAnalysisAgent": orchestrator.image_analysis_agent
        }
        return agent_map.get(agent_name)
    
    @staticmethod
    async def dispatch_agents(
        agents: List[Any],
        agent_task_map: Dict[str, Dict[str, Any]],
        message: str,
        iteration: int,
        project_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        file_id: Optional[int] = None,
        db_session = None
    ) -> List[Any]:
        """
        Dispatch agents in parallel and return their results.
        
        Returns:
            List of results (AgentResult or Exception instances)
        """
        logger.info(f"[AgentDispatcher] Starting parallel dispatch of {len(agents)} agents")
        
        agent_tasks = []
        for agent in agents:
            agent_class_name = agent.__class__.__name__
            
            # Get specific task for this agent
            task_info = agent_task_map.get(agent_class_name, {'task': message, 'context': {}})
            task_str = task_info.get('task', message)
            task_context = task_info.get('context', {})
            
            logger.info(f"[AgentDispatcher] Dispatching {agent_class_name} with task: {task_str[:100]}...")
            
            # Create task with agent-specific parameters
            task = AgentDispatcher._create_agent_task(
                agent, agent_class_name, task_str, task_context,
                message, iteration, project_id, branch_id, file_id, db_session
            )
            agent_tasks.append(task)
        
        # Execute all agents in parallel
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        logger.info(f"[AgentDispatcher] All {len(results)} agents completed")
        
        return results
    
    @staticmethod
    def _create_agent_task(
        agent: Any,
        agent_class_name: str,
        task_str: str,
        task_context: Dict[str, Any],
        message: str,
        iteration: int,
        project_id: Optional[int],
        branch_id: Optional[int],
        file_id: Optional[int],
        db_session
    ):
        """Create async task for specific agent type"""
        
        # ShellAgent: Add conversation context
        if agent_class_name == "ShellAgent":
            conversation_context = (
                f"User Query: {message}\n"
                f"Iteration: {iteration + 1}\n"
                f"Specific Task: {task_str}"
            )
            return agent.process(task_str, conversation_context=conversation_context)
        
        # ImageCreationAgent: Needs project/branch/db
        elif agent_class_name == "ImageCreationAgent":
            return agent.process(
                task_str,
                project_id=project_id,
                branch_id=branch_id,
                db_session=db_session
            )
        
        # ImageAnalysisAgent: May need file_id from context
        elif agent_class_name == "ImageAnalysisAgent":
            file_id_for_analysis = task_context.get('file_id', file_id)
            return agent.process(
                task_str,
                project_id=project_id,
                branch_id=branch_id,
                db_session=db_session,
                file_id=file_id_for_analysis
            )
        
        # DataAgent: May use project_id from context
        elif agent_class_name == "DataAgent":
            project_id_for_data = task_context.get('project_id', project_id)
            return agent.process(task_str, project_id=project_id_for_data)
        
        # NotesAgent: May have content_to_note in context
        elif agent_class_name == "NotesAgent":
            content_to_note = task_context.get('content_to_note', '')
            existing_notes = task_context.get('existing_notes', [])
            return agent.process(
                task_str,
                content_to_note=content_to_note,
                existing_notes=existing_notes
            )
        
        # FileAgent: Set db context
        elif agent_class_name == "FileAgent":
            if db_session and project_id and branch_id:
                agent.project_id = project_id
                agent.branch_id = branch_id
                agent.db_session = db_session
            return agent.process(task_str)
        
        # Default: Just pass task string
        else:
            return agent.process(task_str)
