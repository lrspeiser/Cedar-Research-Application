"""
New WebSocket chat handler implementing the thinker-orchestrator flow.
Flow: user message → thinker (stream) → orchestrator → agents → results
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import asdict
import logging
from openai import AsyncOpenAI
import os

from thinker import Thinker, ThinkerContext
from orchestrator import Orchestrator
from agents.base_agent import AgentContext

logger = logging.getLogger(__name__)

class WebSocketChatHandler:
    """Handles WebSocket chat connections with new flow"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        # Initialize OpenAI client
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if api_key:
            self.openai_client = AsyncOpenAI(api_key=api_key)
        else:
            self.openai_client = None
            logger.warning("No OpenAI API key provided")
        
        # Initialize components
        self.thinker = Thinker(self.openai_client) if self.openai_client else None
        self.orchestrator = Orchestrator(self.openai_client) if self.openai_client else None
    
    async def handle_connection(self, websocket: WebSocket, project_id: int):
        """Handle a WebSocket connection for a project"""
        await websocket.accept()
        logger.info(f"WebSocket connection accepted for project {project_id}")
        
        # Send initial connection event
        await self._send_event(websocket, "info", "connected", {
            "message": "Connected to chat system",
            "project_id": project_id
        })
        
        try:
            while True:
                # Receive message from client
                data = await websocket.receive_json()
                await self._process_message(websocket, data, project_id)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for project {project_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await self._send_event(websocket, "error", "system_error", {
                "error": str(e)
            })
    
    async def _process_message(self, websocket: WebSocket, data: Dict[str, Any], project_id: int):
        """Process a message from the client"""
        
        query = data.get("query", "")
        thread_id = data.get("thread_id", 1)
        
        if not query:
            await self._send_event(websocket, "error", "invalid_query", {
                "error": "No query provided"
            })
            return
        
        # Reset orchestrator for new query
        if self.orchestrator:
            self.orchestrator.reset()
        
        try:
            # 1. Echo user message back
            await self._send_event(websocket, "user", "message", {
                "content": query,
                "thread_id": thread_id,
                "timestamp": time.time()
            })
            
            # 2. Start processing
            await self._send_event(websocket, "assistant", "processing_start", {
                "message": "Thinking about your request..."
            })
            
            # Get context (simplified for now)
            context = await self._build_context(query, project_id, thread_id)
            
            # 3. Run thinker and stream its output
            thinking_notes = ""
            await self._send_event(websocket, "assistant", "thinking_start", {})
            
            if self.thinker:
                thinker_context = ThinkerContext(
                    query=query,
                    chat_history=context.get("chat_history", []),
                    files=context.get("files", []),
                    databases=context.get("databases", []),
                    notes=context.get("notes", []),
                    code_snippets=context.get("code_snippets", []),
                    changelog=context.get("changelog", []),
                    available_agents=["plan", "code", "web", "file", "db", "notes", "images", "question", "final"]
                )
                
                # Stream thinker output
                async for chunk in self.thinker.think(thinker_context):
                    thinking_notes += chunk
                    await self._send_event(websocket, "assistant", "thinking_chunk", {
                        "chunk": chunk
                    })
                
                await self._send_event(websocket, "assistant", "thinking_complete", {
                    "full_text": thinking_notes
                })
                
                # Parse thinker output
                thinking_output = self.thinker.parse_thinking_output(thinking_notes)
                
            else:
                # Fallback if no thinker available
                thinking_notes = "Processing query directly..."
                thinking_output = None
                await self._send_event(websocket, "assistant", "thinking_complete", {
                    "full_text": thinking_notes
                })
            
            # 4. Run orchestrator
            if self.orchestrator and thinking_output:
                agent_context = AgentContext(
                    query=query,
                    thinking_notes=thinking_notes,
                    chat_history=context.get("chat_history", []),
                    files=context.get("files", []),
                    databases=context.get("databases", []),
                    notes=context.get("notes", []),
                    code_snippets=context.get("code_snippets", []),
                    changelog=context.get("changelog", []),
                    previous_results=None
                )
                
                # Orchestration loop
                max_loops = 5
                loop_count = 0
                final_result = None
                
                while loop_count < max_loops:
                    loop_count += 1
                    
                    # Execute agents
                    await self._send_event(websocket, "system", "orchestration_start", {
                        "iteration": loop_count
                    })
                    
                    results, decision = await self.orchestrator.orchestrate(
                        agent_context, 
                        thinking_output
                    )
                    
                    # Send agent results
                    for result in results:
                        await self._send_event(websocket, "system", "agent_result", {
                            "agent": result.agent_name,
                            "success": result.success,
                            "output": result.output if result.success else None,
                            "error": result.error if not result.success else None
                        })
                    
                    # Send selected result to user
                    if decision.selected_result and decision.selected_result.success:
                        await self._send_event(websocket, "assistant", "result", {
                            "content": decision.selected_result.output,
                            "agent": decision.selected_result.agent_name,
                            "metadata": decision.selected_result.metadata,
                            "display_type": decision.selected_result.display_type
                        })
                        final_result = decision.selected_result
                    
                    # Check if we should continue
                    if not decision.should_continue:
                        break
                    
                    # If we need the thinker again
                    if decision.needs_thinker:
                        # Update context with previous results
                        agent_context.previous_results = [asdict(r) for r in results]
                        
                        # Re-run thinker with updated context
                        await self._send_event(websocket, "assistant", "thinking_start", {
                            "reason": "Re-evaluating based on results"
                        })
                        
                        # Stream new thinking
                        new_thinking = ""
                        async for chunk in self.thinker.think(thinker_context):
                            new_thinking += chunk
                            await self._send_event(websocket, "assistant", "thinking_chunk", {
                                "chunk": chunk
                            })
                        
                        thinking_notes = new_thinking
                        thinking_output = self.thinker.parse_thinking_output(thinking_notes)
                        agent_context.thinking_notes = thinking_notes
                    
                    # Otherwise use next agents from decision
                    elif decision.next_agents:
                        # Update thinking output with new agents
                        thinking_output.suggested_agents = decision.next_agents
                
                # Send final status
                if final_result:
                    if final_result.display_type == "question":
                        await self._send_event(websocket, "assistant", "question", {
                            "content": final_result.output,
                            "waiting_for_response": True
                        })
                    else:
                        await self._send_event(websocket, "assistant", "final", {
                            "content": final_result.output,
                            "agent": final_result.agent_name
                        })
                else:
                    await self._send_event(websocket, "assistant", "final", {
                        "content": "I couldn't generate a response. Please try rephrasing your query.",
                        "error": True
                    })
            
            else:
                # Fallback without orchestrator - simple response
                await self._send_event(websocket, "assistant", "final", {
                    "content": "System is in limited mode. Cannot process complex queries.",
                    "limited_mode": True
                })
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._send_event(websocket, "error", "processing_error", {
                "error": str(e)
            })
            
        finally:
            # Send processing complete
            await self._send_event(websocket, "assistant", "processing_complete", {
                "timestamp": time.time()
            })
    
    async def _send_event(self, websocket: WebSocket, event_type: str, event_name: str, data: Dict[str, Any]):
        """Send an event to the WebSocket client"""
        message = {
            "type": event_type,
            "event": event_name,
            "data": data,
            "timestamp": time.time(),
            "id": str(uuid.uuid4())
        }
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send event: {e}")
    
    async def _build_context(self, query: str, project_id: int, thread_id: int) -> Dict[str, Any]:
        """Build context for processing (simplified version)"""
        # In production, this would fetch from database
        return {
            "chat_history": [],  # Would fetch from DB
            "files": [],         # Would fetch project files
            "databases": [],     # Would fetch available DBs
            "notes": [],         # Would fetch notes
            "code_snippets": [], # Would fetch code history
            "changelog": []      # Would fetch changelog
        }

# Create a singleton instance
chat_handler = WebSocketChatHandler()

# FastAPI WebSocket endpoint
async def websocket_endpoint(websocket: WebSocket, project_id: int):
    """FastAPI WebSocket endpoint"""
    await chat_handler.handle_connection(websocket, project_id)