"""
WebSocket Chat with Advanced Thinker-Orchestrator Implementation
This module provides the real multi-agent orchestration system.
"""

import os
import logging
import json
import time
import asyncio
import traceback
from typing import Optional, Dict, Tuple
from fastapi import WebSocket, FastAPI, WebSocketDisconnect
from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Track running orchestration tasks by (project_id, branch_id, chat_number)
RUN_TASKS: Dict[Tuple[Optional[int], Optional[int], Optional[int]], asyncio.Task] = {}

class WSDeps:
    """Dependencies container for WebSocket chat"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def register_ws_chat(app: FastAPI, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    """
    Register WebSocket chat routes with advanced orchestrator.
    
    Args:
        app: FastAPI application instance
        deps: Dependencies container
        route_path: WebSocket route path pattern
    """
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY") or ""
    
    if not api_key:
        logger.warning("No OpenAI API key found. Some features will be limited.")
        print("[startup] WARNING: No OpenAI API key configured. LLM features will be limited.")
    else:
        print("[startup] OpenAI API key configured. Full orchestration enabled.")
    
    # Create the advanced orchestrator
    orchestrator = ThinkerOrchestrator(api_key)
    
    # Register route WITH project_id for compatibility
    if "{project_id}" in route_path:
        @app.websocket(route_path)
        async def ws_chat_with_project(websocket: WebSocket, project_id: int):
            """WebSocket endpoint with project context"""
            await handle_ws_chat(websocket, orchestrator, project_id, deps)
    
    # Also register a simple route WITHOUT project_id
    simple_path = "/ws/chat"
    @app.websocket(simple_path)
    async def ws_chat_simple(websocket: WebSocket):
        """WebSocket endpoint without project context"""
        await handle_ws_chat(websocket, orchestrator, None, deps)
    
    logger.info(f"Registered advanced WebSocket routes: {route_path} and {simple_path}")
    print(f"[startup] Advanced thinker-orchestrator WebSocket routes registered")
    print(f"[startup]   - {route_path} (with project context)")
    print(f"[startup]   - {simple_path} (general chat)")

async def handle_ws_chat(
    websocket: WebSocket, 
    orchestrator: ThinkerOrchestrator, 
    project_id: Optional[int],
    deps: WSDeps
):
    """
    Handle WebSocket chat connection with advanced orchestration.
    
    Args:
        websocket: WebSocket connection
        orchestrator: ThinkerOrchestrator instance
        project_id: Optional project ID for context
        deps: Dependencies container
    """
    try:
        await websocket.accept()
        
        # Import chat manager for persistence
        from cedar_app.utils.chat_persistence import get_chat_manager
        chat_manager = get_chat_manager()
        current_chat_number = None
        
        logger.info(f"WebSocket connected: project_id={project_id}")
        
        # Main message loop - supports multiple runs per connection
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")
                action = data.get("action")

                if message_type == "message" or action == "chat":
                    # New orchestration request
                    content = data.get("content", "").strip()
                    branch_id = data.get("branch_id", 1)
                    chat_number = data.get("chat_number", current_chat_number)

                    # Create or get chat
                    if not chat_number and project_id:
                        chat_data = chat_manager.create_chat(
                            project_id=project_id,
                            branch_id=branch_id,
                            title=f"Chat {content[:30]}..." if content else "New Chat"
                        )
                        chat_number = chat_data['chat_number']
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Created new chat #{chat_number}")
                        await websocket.send_json({
                            "type": "chat_created",
                            "chat_number": chat_number,
                            "title": chat_data['title']
                        })
                    elif chat_number and project_id:
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Using existing chat #{chat_number}")

                    if not content:
                        await websocket.send_json({
                            "type": "error",
                            "error": "Empty message received",
                            "content": "Empty message received"
                        })
                        continue

                    # Save user message to chat
                    if project_id and chat_number:
                        chat_manager.add_message(project_id, branch_id, chat_number, role="user", content=content)
                        chat_manager.set_chat_status(project_id, branch_id, chat_number, "processing")

                    logger.info(f"[WebSocket] Initiating orchestration for chat #{chat_number}")

                    # Wrapper to persist regardless of WebSocket availability
                    class PersistentWebSocket:
                        def __init__(self, ws, chat_mgr, proj_id, br_id, chat_num):
                            self.ws = ws
                            self.chat_mgr = chat_mgr
                            self.proj_id = proj_id
                            self.br_id = br_id
                            self.chat_num = chat_num
                        async def send_json(self, payload):
                            try:
                                # Persist first
                                if self.proj_id and self.chat_num:
                                    msg_type = payload.get('type', '')
                                    if msg_type == 'message':
                                        self.chat_mgr.add_message(self.proj_id, self.br_id, self.chat_num,
                                                                  role=payload.get('role', 'assistant'),
                                                                  content=payload.get('text', ''),
                                                                  metadata={'type': 'agent_response'})
                                    elif msg_type == 'agent_result':
                                        # Store as assistant message too for visibility
                                        self.chat_mgr.add_message(self.proj_id, self.br_id, self.chat_num,
                                                                  role='assistant',
                                                                  content=payload.get('text', ''),
                                                                  metadata={'type': 'agent_result'})
                                    elif msg_type == 'final':
                                        self.chat_mgr.add_message(self.proj_id, self.br_id, self.chat_num,
                                                                  role='assistant',
                                                                  content=payload.get('text', ''),
                                                                  metadata={'type': 'final_answer'})
                                        self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "complete")
                                    elif msg_type == 'error':
                                        self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "error")
                                # Best-effort send to client
                                try:
                                    await self.ws.send_json(payload)
                                except Exception:
                                    # Ignore send errors (e.g. client disconnected)
                                    pass
                            except Exception:
                                # Never raise from persistence
                                pass

                    ws_to_use = websocket if not (project_id and chat_number) else PersistentWebSocket(websocket, chat_manager, project_id, branch_id, chat_number)

                    # Optional DB session for notes
                    db_session = None
                    if project_id and hasattr(deps, 'RegistrySessionLocal'):
                        try:
                            db_session = deps.RegistrySessionLocal()
                        except Exception as e:
                            logger.warning(f"Could not get database session for notes: {e}")

                    # Launch orchestration as a detached task
                    async def run_orchestration():
                        try:
                            await orchestrator.orchestrate(
                                content,
                                ws_to_use,
                                project_id=project_id,
                                branch_id=branch_id,
                                db_session=db_session
                            )
                        except asyncio.CancelledError:
                            logger.info(f"[WebSocket] Orchestration task cancelled for chat #{chat_number}")
                            raise
                        except Exception as e:
                            logger.error(f"[WebSocket] Orchestration error: {e}")
                            try:
                                await ws_to_use.send_json({"type":"error","error":str(e),"content":str(e)})
                            except Exception:
                                pass
                        finally:
                            if db_session:
                                try:
                                    db_session.close()
                                except Exception:
                                    pass

                    key = (project_id, branch_id, chat_number)
                    # If an existing task is running for this chat, cancel it
                    old = RUN_TASKS.get(key)
                    if old and not old.done():
                        try:
                            old.cancel()
                        except Exception:
                            pass
                    task = asyncio.create_task(run_orchestration())
                    RUN_TASKS[key] = task

                    # Control loop: watch for cancel/close while orchestration runs
                    while True:
                        if task.done():
                            # Finished normally or cancelled
                            try:
                                RUN_TASKS.pop(key, None)
                            except Exception:
                                pass
                            break
                        # Wait for a control message or task completion
                        try:
                            recv_task = asyncio.create_task(websocket.receive_json())
                            done, pending = await asyncio.wait({recv_task, task}, return_when=asyncio.FIRST_COMPLETED)
                            if recv_task in done:
                                try:
                                    ctrl = recv_task.result()
                                except WebSocketDisconnect:
                                    # Client disconnected: leave task running in background
                                    logger.info(f"[WebSocket] Client disconnected during orchestration chat #{chat_number}; task continues")
                                    break
                                except Exception:
                                    break
                                t = ctrl.get('type') or ctrl.get('action')
                                if t == 'cancel':
                                    # Cancel orchestration
                                    try:
                                        task.cancel()
                                    except Exception:
                                        pass
                                    try:
                                        await websocket.send_json({"type":"info","message":"cancelled"})
                                    except Exception:
                                        pass
                                    break
                                elif t == 'ping':
                                    try:
                                        await websocket.send_json({"type":"pong"})
                                    except Exception:
                                        pass
                                    continue
                                elif t == 'close':
                                    # Close requested by client
                                    try:
                                        task.cancel()
                                    except Exception:
                                        pass
                                    break
                                else:
                                    # Ignore any other incoming messages while a run is active
                                    continue
                            else:
                                # Task completed
                                try:
                                    RUN_TASKS.pop(key, None)
                                except Exception:
                                    pass
                                break
                        finally:
                            try:
                                if not recv_task.done():
                                    recv_task.cancel()
                            except Exception:
                                pass

                    # Proceed to next loop to wait for a new chat message

                elif data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "close":
                    break
                else:
                    msg_info = f"type={data.get('type')}, action={data.get('action')}"
                    logger.warning(f"Unknown message format: {msg_info}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Unknown message format: {msg_info}",
                        "content": f"Unknown message format: {msg_info}"
                    })
            except WebSocketDisconnect:
                # Client disconnected; keep any running task alive
                logger.info(f"[WebSocket] Disconnected client for project_id={project_id}")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Error processing message: {str(e)}",
                        "content": f"Error processing message: {str(e)}",
                        "details": str(e),
                        "stack": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
                    })
                except Exception:
                    pass
                break
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        try:
            await websocket.close()
            logger.info(f"WebSocket disconnected: project_id={project_id}")
        except Exception:
            pass

# Export public interface
__all__ = ['register_ws_chat', 'WSDeps']