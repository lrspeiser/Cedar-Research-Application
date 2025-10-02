"""
Agent Result Processor Module

Handles processing of agent execution results, including:
- Result validation and error handling
- WebSocket streaming of agent outputs
- Code artifact persistence
- Error report generation
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import WebSocket

from .agents import AgentResult

logger = logging.getLogger(__name__)


class AgentResultProcessor:
    """Processes agent results and handles WebSocket communication"""
    
    AGENT_DISPLAY_NAMES = {
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
    
    @staticmethod
    async def process_results(
        results: List[Any],
        agents: List[Any],
        message: str,
        websocket: WebSocket,
        run_logs: List[str],
        db_session = None,
        project_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        file_id: Optional[int] = None
    ) -> tuple[List[AgentResult], bool]:
        """
        Process agent execution results and stream to WebSocket.
        
        Returns:
            (valid_results, had_errors): Tuple of valid results list and error flag
        """
        logger.info("[AgentResultProcessor] Processing agent results")
        valid_results = []
        had_errors = False
        
        for i, result in enumerate(results):
            if isinstance(result, AgentResult):
                await AgentResultProcessor._process_valid_result(
                    result, i, websocket, run_logs, 
                    db_session, project_id, branch_id, thread_id, file_id
                )
                valid_results.append(result)
                await asyncio.sleep(0.2)
                
            elif isinstance(result, Exception):
                error_result = await AgentResultProcessor._process_error(
                    result, i, agents, message, websocket, run_logs
                )
                valid_results.append(error_result)
                had_errors = True
                await asyncio.sleep(0.2)
        
        return valid_results, had_errors
    
    @staticmethod
    async def _process_valid_result(
        result: AgentResult,
        index: int,
        websocket: WebSocket,
        run_logs: List[str],
        db_session,
        project_id: Optional[int],
        branch_id: Optional[int],
        thread_id: Optional[int],
        file_id: Optional[int]
    ):
        """Process a successful agent result"""
        logger.info(f"[AgentResultProcessor] Result {index+1}: {result.agent_name} - "
                   f"Confidence: {result.confidence:.2f}, Method: {result.method}")
        logger.info(f"[AgentResultProcessor] Result {index+1} UI label: {result.display_name}")
        logger.info(f"[AgentResultProcessor] Result {index+1} content: {result.result[:200]}...")
        
        # Persist code artifacts
        await AgentResultProcessor._persist_code_artifact(
            result, db_session, project_id, branch_id
        )

        # Apply optional DB update (agent-provided SQL)
        await AgentResultProcessor._apply_db_update(
            result, db_session, project_id, branch_id, thread_id, file_id, websocket, run_logs
        )
        
        # Send to WebSocket
        await websocket.send_json({
            "type": "agent_result",
            "agent_name": result.display_name,
            "text": result.result,
            "summary": result.summary,
            "metadata": {
                "agent": result.agent_name,
                "confidence": result.confidence,
                "method": result.method,
                "needs_rerun": result.needs_rerun,
                "summary": result.summary
            }
        })
        
        # Update run logs
        try:
            short = (result.summary or (result.result or '').split('\n', 1)[0] or '').strip()
            if len(short) > 160:
                short = short[:160]
            run_logs.append(f"AgentOK: {result.display_name} conf={result.confidence:.2f} sum={short}")
        except Exception:
            pass
    
    @staticmethod
    async def _apply_db_update(
        result: AgentResult,
        db_session,
        project_id: Optional[int],
        branch_id: Optional[int],
        thread_id: Optional[int],
        file_id: Optional[int],
        websocket: Optional[WebSocket],
        run_logs: List[str]
    ):
        """Execute agent-provided db_update.sql (via SQLRunner) and attach results.
        The agent should include artifacts['db_update'] = { description, sql, idempotency_key?, run_mode }.
        """
        try:
            if not db_session or not project_id or not branch_id:
                return
            dbu = None
            try:
                dbu = (result.artifacts or {}).get('db_update') if isinstance(result.artifacts, dict) else None
            except Exception:
                dbu = None
            if not dbu:
                return
            sql_text = str(dbu.get('sql') or '').strip()
            if not sql_text:
                return
            # Render placeholders
            def _sub(s: str) -> str:
                repl = s.replace('{{project_id}}', str(int(project_id)))
                repl = repl.replace('{{branch_id}}', str(int(branch_id)))
                repl = repl.replace('{{thread_id}}', str(int(thread_id)) if thread_id is not None else 'NULL')
                repl = repl.replace('{{file_id}}', str(int(file_id)) if file_id is not None else 'NULL')
                return repl
            sql_exec = _sub(sql_text)
            # Execute with SQLRunner for consistent reporting
            try:
                from cedar_orchestrator.agents.sql_runner import SQLRunner
            except Exception:
                from .agents.sql_runner import SQLRunner  # fallback relative import
            runner = SQLRunner(llm_client=None)
            exec_result = await runner.process(sql_exec, db_session=db_session, project_id=int(project_id), branch_id=int(branch_id))
            # Attach result
            result.artifacts = result.artifacts or {}
            result.artifacts['db_update_result'] = {
                'status': 'ok' if exec_result and exec_result.confidence >= 0.6 else 'error',
                'report': getattr(exec_result, 'result', ''),
                'summary': getattr(exec_result, 'summary', ''),
            }
            # Append a short note to the visible text so Chief Agent sees it
            try:
                short_line = "\n\nDB Update: " + (result.artifacts['db_update_result']['summary'] or 'executed')
                result.result = (result.result or '') + short_line
            except Exception:
                pass
            # Stream a secondary bubble for transparency
            try:
                if websocket:
                    await websocket.send_json({
                        'type': 'agent_result',
                        'agent_name': 'SQLRunner (auto)',
                        'text': result.artifacts['db_update_result']['report'] or result.artifacts['db_update_result']['summary'],
                        'summary': result.artifacts['db_update_result']['summary']
                    })
            except Exception:
                pass
            # Log
            try:
                run_logs.append(f"DBUpdateOK: {result.display_name} -> {len(sql_exec)} chars SQL")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[AgentResultProcessor] DB update failed: {type(e).__name__}: {e}")
            try:
                result.artifacts = result.artifacts or {}
                result.artifacts['db_update_result'] = {'status': 'error', 'error': str(e)}
                result.result = (result.result or '') + f"\n\nDB Update: error {type(e).__name__}: {e}"
                run_logs.append(f"DBUpdateERR: {result.display_name}: {type(e).__name__}: {e}")
            except Exception:
                pass

    @staticmethod
    async def _persist_code_artifact(
        result: AgentResult,
        db_session,
        project_id: Optional[int],
        branch_id: Optional[int]
    ):
        """Persist code artifacts to database"""
        try:
            if not (db_session and project_id and branch_id):
                return
            
            artifacts = getattr(result, 'artifacts', None)
            if not artifacts:
                return
            
            art = artifacts or {}
            if str(art.get('type', '')).lower() != 'code':
                return
            if not str(art.get('source', '')).strip():
                return
            
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
            logger.info(f"[AgentResultProcessor] Saved code snippet id={getattr(sc, 'id', None)} "
                       f"lang={lang} name={name[:40]}")
        except Exception as e:
            logger.warning(f"[AgentResultProcessor] Failed to persist code artifact: "
                         f"{type(e).__name__}: {e}")
    
    @staticmethod
    async def _process_error(
        exception: Exception,
        index: int,
        agents: List[Any],
        message: str,
        websocket: WebSocket,
        run_logs: List[str]
    ) -> AgentResult:
        """Process an agent execution error"""
        logger.error(f"[AgentResultProcessor] Agent {index+1} failed with exception: {exception}")
        
        # Determine which agent failed
        agent_name = "Unknown Agent"
        display_name = "Unknown Agent"
        if index < len(agents):
            agent = agents[index]
            agent_name = agent.__class__.__name__
            display_name = AgentResultProcessor.AGENT_DISPLAY_NAMES.get(agent_name, agent_name)
        
        # Create error report
        error_type = type(exception).__name__
        error_msg = str(exception)
        
        error_details = f"""Exception Type: {error_type}
Error Message: {error_msg}
Agent: {agent_name}
Task: {message[:200]}{'...' if len(message) > 200 else ''}"""
        
        suggested_fix = AgentResultProcessor._get_error_suggestions(error_msg)
        
        # Create error result
        error_result = AgentResult(
            agent_name=agent_name,
            display_name=display_name,
            result=f"""**Agent Failure Report:**

{display_name} encountered an unexpected error and could not complete the task.

**Error Details:**
```
{error_details}
```

**Suggested Fix:**
{suggested_fix}

**What the Chief Agent should know:**
This agent crashed during execution. The error has been logged and detailed information is provided above for troubleshooting.""",
            confidence=0.0,
            method="Agent Exception",
            explanation=f"Agent crashed: {error_type}",
            summary=f"{display_name} failed with {error_type}: {error_msg[:100]}{'...' if len(error_msg) > 100 else ''}"
        )
        
        # Send error to WebSocket
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
        
        # Update run logs
        try:
            run_logs.append(f"AgentERR: {display_name} type={error_type} msg={error_msg[:160]}")
        except Exception:
            pass
        
        return error_result
    
    @staticmethod
    def _get_error_suggestions(error_msg: str) -> str:
        """Generate context-specific error suggestions"""
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
        
        return suggested_fix
