"""
Notes Persistence Module

Handles automatic saving of Chief Agent decisions and agent results to the database
as structured notes after every orchestration cycle.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Try to import notes functionality
try:
    from .chief_agent_notes import ChiefAgentNoteTaker
    NOTES_AVAILABLE = True
except ImportError:
    NOTES_AVAILABLE = False
    logger.warning("[NotesPersistence] ChiefAgentNoteTaker not available")


class NotesPersistence:
    """Handles automatic persistence of Chief Agent decisions and agent results"""
    
    @staticmethod
    async def save_orchestration_notes(
        agent_results: List[Any],
        user_query: str,
        chief_decision: Dict[str, Any],
        iteration: int,
        project_id: Optional[int],
        branch_id: Optional[int],
        db_session,
        websocket: Optional[WebSocket] = None
    ) -> Optional[int]:
        """
        Save notes for the current orchestration cycle.
        
        Args:
            agent_results: List of AgentResult objects
            user_query: Original user query
            chief_decision: Chief Agent's decision dictionary
            iteration: Current iteration number
            project_id: Project ID
            branch_id: Branch ID
            db_session: Database session
            websocket: Optional WebSocket for notifications
            
        Returns:
            Note ID if saved successfully, None otherwise
        """
        logger.info(f"[NotesPersistence] ={'='*50}")
        logger.info(f"[NotesPersistence] NOTES SAVE - ITERATION {iteration + 1}")
        logger.info(f"[NotesPersistence] ={'='*50}")
        
        # Check requirements
        if not NOTES_AVAILABLE:
            logger.warning("[NotesPersistence] ⚠️ SKIPPED: ChiefAgentNoteTaker not available")
            return None
        
        if not db_session:
            logger.warning("[NotesPersistence] ⚠️ SKIPPED: db_session is None")
            return None
        
        if not project_id:
            logger.warning(f"[NotesPersistence] ⚠️ SKIPPED: project_id is None/False: {project_id}")
            return None
        
        if not branch_id:
            logger.warning(f"[NotesPersistence] ⚠️ SKIPPED: branch_id is None/False: {branch_id}")
            return None
        
        logger.info(f"[NotesPersistence] ✓ All conditions met")
        logger.info(f"[NotesPersistence] project_id: {project_id}")
        logger.info(f"[NotesPersistence] branch_id: {branch_id}")
        logger.info(f"[NotesPersistence] iteration: {iteration}")
        logger.info(f"[NotesPersistence] decision: {chief_decision.get('decision')}")
        logger.info(f"[NotesPersistence] agent_results count: {len(agent_results)}")
        
        try:
            # Create note taker
            logger.info("[NotesPersistence] Creating ChiefAgentNoteTaker...")
            note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
            logger.info("[NotesPersistence] ChiefAgentNoteTaker created successfully")
            
            # Enhance decision with iteration metadata
            enhanced_decision = dict(chief_decision)
            enhanced_decision['iteration'] = iteration
            enhanced_decision['is_final'] = chief_decision.get('decision') != 'loop'
            enhanced_decision['total_iterations'] = iteration + 1
            
            logger.info(f"[NotesPersistence] Enhanced decision:")
            logger.info(f"[NotesPersistence]   iteration: {iteration}")
            logger.info(f"[NotesPersistence]   is_final: {enhanced_decision['is_final']}")
            logger.info(f"[NotesPersistence]   total_iterations: {enhanced_decision['total_iterations']}")
            
            # Save notes
            logger.info("[NotesPersistence] Calling save_agent_notes...")
            note_id = await note_taker.save_agent_notes(
                agent_results=agent_results,
                user_query=user_query,
                chief_decision=enhanced_decision
            )
            
            logger.info(f"[NotesPersistence] save_agent_notes returned: {note_id}")
            
            if note_id:
                logger.info(f"[NotesPersistence] ✅ SUCCESS: Saved iteration {iteration + 1} notes")
                logger.info(f"[NotesPersistence] Note ID: {note_id}")
                
                # Send WebSocket notification
                if websocket:
                    try:
                        await websocket.send_json({
                            "type": "note_saved",
                            "note_id": note_id,
                            "iteration": iteration + 1,
                            "is_final": enhanced_decision['is_final'],
                            "message": f"Iteration {iteration + 1} analysis saved to Notes"
                        })
                        logger.info("[NotesPersistence] WebSocket notification sent")
                    except Exception as e:
                        logger.warning(f"[NotesPersistence] Failed to send WebSocket notification: {e}")
                
                return note_id
            else:
                logger.warning(f"[NotesPersistence] ⚠️ No note ID returned")
                return None
                
        except Exception as e:
            logger.error(f"[NotesPersistence] ❌ ERROR: Failed to save notes")
            logger.error(f"[NotesPersistence] Exception: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[NotesPersistence] Traceback:\n{traceback.format_exc()}")
            return None
    
    @staticmethod
    async def run_notes_agent_on_decision(
        notes_agent,
        user_query: str,
        chief_decision: Dict[str, Any],
        project_id: Optional[int],
        branch_id: Optional[int],
        db_session,
        websocket: Optional[WebSocket] = None,
        thread_summary: Optional[str] = None
    ) -> Optional[int]:
        """
        Run NotesAgent to create a summary note of the Chief Agent decision and persist it.
        
        Behavior:
        - Reads existing notes for deduplication context
        - Builds content from the Chief decision and (optionally) a thread summary
        - Calls NotesAgent to produce a user-friendly note
        - Saves the generated note into the project's notes table
        
        Returns:
            Note ID if saved successfully, None otherwise
        """
        if not notes_agent:
            return None
        
        logger.info("[NotesPersistence] Running NotesAgent on Chief decision...")
        
        try:
            # Get existing notes for deduplication
            existing_notes_list = []
            if db_session and project_id and branch_id and NOTES_AVAILABLE:
                try:
                    note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                    existing_notes_list = await note_taker.get_existing_notes()
                except Exception as e:
                    logger.warning(f"[NotesPersistence] Could not fetch existing notes: {e}")
            
            # Build content to note
            decision = chief_decision or {}
            lines = []
            
            lines.append(f"Decision: {decision.get('decision', '')}")
            
            if tp := (decision.get('thinking_process') or '').strip():
                lines.append(f"Thinking Process:\n{tp}")
            
            if fa := (decision.get('final_answer') or '').strip():
                lines.append(f"Final Answer:\n{fa}")
            
            if ag := (decision.get('additional_guidance') or '').strip():
                lines.append(f"Additional Guidance:\n{ag}")
            
            if sel := (decision.get('selected_agent') or '').strip():
                lines.append(f"Selected Agent: {sel}")
            
            if atu := decision.get('agent_tasks'):
                try:
                    agent_names = [t.get('agent','') for t in atu if isinstance(t, dict)]
                    lines.append(f"Agents To Use: {', '.join([a for a in agent_names if a])}")
                except Exception:
                    pass
            
            if rsn := (decision.get('reasoning') or '').strip():
                lines.append(f"Reasoning:\n{rsn}")
            
            # Include thread summary (conversation history) if provided
            if thread_summary:
                short_hist = thread_summary if len(thread_summary) <= 2000 else (thread_summary[:2000] + "\n... (truncated)")
                lines.append(f"Thread Summary:\n{short_hist}")
            
            content_to_note = "\n\n".join(lines) if lines else "Chief Agent summary"
            
            # Run NotesAgent
            notes_result = await notes_agent.process(
                task=user_query,
                content_to_note=content_to_note,
                existing_notes=existing_notes_list
            )
            
            # Persist the generated note
            note_id = None
            try:
                from main_models import Note
                note = Note(
                    project_id=int(project_id) if project_id is not None else None,
                    branch_id=int(branch_id) if branch_id is not None else None,
                    content=getattr(notes_result, 'result', '') or content_to_note,
                    tags=["NotesAgent"],
                    agent_name="NotesAgent",
                    user_query=user_query,
                    note_type="agent_finding",
                    title=None
                )
                db_session.add(note)
                db_session.commit()
                db_session.refresh(note)
                note_id = note.id
                logger.info(f"[NotesPersistence] ✅ Saved NotesAgent note ID {note_id}")
            except Exception as e:
                logger.error(f"[NotesPersistence] Failed to save NotesAgent note: {e}")
                try:
                    db_session.rollback()
                except Exception:
                    pass
                note_id = None
            
            # Send to WebSocket if available
            if websocket and hasattr(notes_result, 'display_name'):
                try:
                    await websocket.send_json({
                        "type": "agent_result",
                        "agent_name": notes_result.display_name,
                        "text": notes_result.result,
                        "summary": getattr(notes_result, 'summary', None),
                        "metadata": {
                            "agent": "NotesAgent",
                            "confidence": getattr(notes_result, 'confidence', None),
                            "method": getattr(notes_result, 'method', None)
                        }
                    })
                except Exception as e:
                    logger.warning(f"[NotesPersistence] Failed to send NotesAgent result: {e}")
            
            # Notify UI about saved note
            if websocket and note_id:
                try:
                    await websocket.send_json({
                        "type": "note_saved",
                        "note_id": note_id,
                        "iteration": decision.get('iteration') or None,
                        "is_final": decision.get('decision') != 'loop',
                        "message": "NotesAgent summary saved to Notes"
                    })
                except Exception:
                    pass
            
            logger.info("[NotesPersistence] NotesAgent completed successfully")
            return note_id
            
        except Exception as e:
            logger.error(f"[NotesPersistence] NotesAgent processing failed: {e}")
            return None
