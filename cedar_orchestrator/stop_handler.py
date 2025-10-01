"""
Stop Handler Module

Handles user-initiated stop requests for graceful termination of orchestration.
Allows the Chief Agent to generate a final answer based on work completed so far.
"""

import logging
import asyncio
from typing import Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class StopHandler:
    """Manages stop requests and graceful termination"""
    
    # Thread-safe stop flags keyed by thread_id
    _stop_flags: Dict[int, bool] = {}
    
    @classmethod
    def request_stop(cls, thread_id: int) -> None:
        """Request orchestration to stop gracefully for a specific thread"""
        cls._stop_flags[thread_id] = True
        logger.info(f"[StopHandler] Stop requested for thread {thread_id}")
    
    @classmethod
    def clear_stop(cls, thread_id: int) -> None:
        """Clear stop flag for a thread (call when orchestration completes)"""
        if thread_id in cls._stop_flags:
            del cls._stop_flags[thread_id]
            logger.info(f"[StopHandler] Stop flag cleared for thread {thread_id}")
    
    @classmethod
    def should_stop(cls, thread_id: int) -> bool:
        """Check if stop was requested for this thread"""
        return cls._stop_flags.get(thread_id, False)
    
    @classmethod
    async def handle_user_stop(
        cls,
        thread_id: int,
        message: str,
        valid_results: list,
        run_logs: list,
        websocket: Optional[WebSocket] = None
    ) -> Dict[str, any]:
        """
        Handle user-initiated stop by creating a summary of work completed.
        
        Returns a chief_decision dict that can be passed to _send_final_answer.
        """
        logger.info(f"[StopHandler] Handling user stop for thread {thread_id}")
        
        # Build summary of what was accomplished
        summary_parts = ["**Processing stopped by user**\n\n"]
        
        if valid_results:
            summary_parts.append(f"**Completed Work ({len(valid_results)} agents ran):**\n")
            for i, result in enumerate(valid_results, 1):
                agent_name = getattr(result, 'display_name', 'Unknown Agent')
                confidence = getattr(result, 'confidence', 0.0)
                summary = getattr(result, 'summary', 'No summary')
                summary_parts.append(f"{i}. **{agent_name}** (confidence: {confidence:.2f})")
                summary_parts.append(f"   {summary}\n")
        else:
            summary_parts.append("No agents had completed when stop was requested.\n")
        
        # Add run logs context
        if run_logs and len(run_logs) > 0:
            summary_parts.append("\n**Processing Timeline:**\n")
            for log in run_logs[-10:]:  # Last 10 log entries
                summary_parts.append(f"- {log}")
        
        summary_parts.append("\n\n_The Chief Agent can provide a partial answer based on the work completed._")
        
        final_text = "\n".join(summary_parts)
        
        # Send stop notification
        if websocket:
            try:
                await websocket.send_json({
                    "type": "user_stopped",
                    "message": "Processing stopped by user",
                    "partial_results_count": len(valid_results)
                })
            except Exception as e:
                logger.warning(f"[StopHandler] Failed to send stop notification: {e}")
        
        # Return a decision dict compatible with _send_final_answer
        return {
            "decision": "final",
            "final_answer": final_text,
            "selected_agent": "User Stop",
            "reasoning": f"User requested stop after {len(valid_results)} agents completed",
            "was_stopped": True
        }
    
    @classmethod
    async def send_stop_signals(cls, websocket: Optional[WebSocket]) -> None:
        """Send signals to stop all UI spinners"""
        if not websocket:
            return
        
        try:
            # Stop any thinking/synthesis spinners
            await websocket.send_json({"type": "thinking_complete"})
            await websocket.send_json({"type": "synthesis_complete"})
            
            # Stop general spinner
            await websocket.send_json({"type": "processing_stopped"})
            
            logger.info("[StopHandler] Stop signals sent to UI")
        except Exception as e:
            logger.warning(f"[StopHandler] Failed to send stop signals: {e}")
