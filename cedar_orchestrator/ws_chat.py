"""
WebSocket Chat with Advanced Thinker-Orchestrator Implementation
This module provides the real multi-agent orchestration system.
"""

import os
import logging
import json
import time
from typing import Optional
from fastapi import WebSocket, FastAPI
from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                
                # Support both formats: {"type": "message"} and {"action": "chat"}
                message_type = data.get("type")
                action = data.get("action")
                
                if message_type == "message" or action == "chat":
                    content = data.get("content", "").strip()
                    branch_id = data.get("branch_id", 1)  # Default to branch 1
                    chat_number = data.get("chat_number", current_chat_number)
                    
                    # Create or get chat
                    if not chat_number and project_id:
                        # Create a new chat if none specified
                        chat_data = chat_manager.create_chat(
                            project_id=project_id,
                            branch_id=branch_id,
                            title=f"Chat {content[:30]}..." if content else "New Chat"
                        )
                        chat_number = chat_data['chat_number']
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Created new chat #{chat_number}")
                        
                        # Notify client about new chat
                        await websocket.send_json({
                            "type": "chat_created",
                            "chat_number": chat_number,
                            "title": chat_data['title']
                        })
                    elif chat_number and project_id:
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Using existing chat #{chat_number}")
                    
                    logger.info("*"*80)
                    logger.info(f"[WebSocket] New message received from client")
                    logger.info(f"[WebSocket] Project ID: {project_id}, Chat #{chat_number}")
                    logger.info(f"[WebSocket] Message content: {content}")
                    logger.info(f"[WebSocket] Message length: {len(content)} characters")
                    logger.info("*"*80)
                    
                    if not content:
                        logger.warning("[WebSocket] Empty message received, sending error")
                        await websocket.send_json({
                            "type": "error",
                            "content": "Empty message received"
                        })
                        continue
                    
                    # Save user message to chat
                    if project_id and chat_number:
                        chat_manager.add_message(
                            project_id=project_id,
                            branch_id=branch_id,
                            chat_number=chat_number,
                            role="user",
                            content=content
                        )
                        chat_manager.set_chat_status(project_id, branch_id, chat_number, "processing")
                    
                    logger.info(f"[WebSocket] Initiating orchestration for: {content[:100]}...")
                    orchestration_start = time.time()
                    
                    # Create a wrapper to capture messages sent to WebSocket
                    class PersistentWebSocket:
                        def __init__(self, ws, chat_mgr, proj_id, br_id, chat_num):
                            self.ws = ws
                            self.chat_mgr = chat_mgr
                            self.proj_id = proj_id
                            self.br_id = br_id
                            self.chat_num = chat_num
                        
                        async def send_json(self, data):
                            # Send to client
                            await self.ws.send_json(data)
                            
                            # Persist certain message types
                            if self.proj_id and self.chat_num:
                                msg_type = data.get('type', '')
                                if msg_type == 'message':
                                    self.chat_mgr.add_message(
                                        self.proj_id, self.br_id, self.chat_num,
                                        role=data.get('role', 'assistant'),
                                        content=data.get('text', ''),
                                        metadata={'type': 'agent_response'}
                                    )
                                elif msg_type == 'final':
                                    self.chat_mgr.add_message(
                                        self.proj_id, self.br_id, self.chat_num,
                                        role='assistant',
                                        content=data.get('text', ''),
                                        metadata={'type': 'final_answer'}
                                    )
                                    self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "complete")
                                elif msg_type == 'error':
                                    self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "error")
                    
                    # Use wrapper if we have persistence context
                    ws_to_use = websocket
                    if project_id and chat_number:
                        ws_to_use = PersistentWebSocket(websocket, chat_manager, project_id, branch_id, chat_number)
                    
                    # Process with advanced orchestrator
                    await orchestrator.orchestrate(content, ws_to_use)
                    
                    orchestration_time = time.time() - orchestration_start
                    logger.info("*"*80)
                    logger.info(f"[WebSocket] Orchestration completed in {orchestration_time:.3f}s")
                    logger.info("*"*80)
                    
                    # Log to changelog if we have the necessary deps
                    if project_id and hasattr(deps, 'record_changelog'):
                        try:
                            # Get a database session
                            if hasattr(deps, 'RegistrySessionLocal'):
                                db = deps.RegistrySessionLocal()
                                try:
                                    branch_id = 1  # Default branch
                                    deps.record_changelog(
                                        db=db,
                                        project_id=project_id,
                                        branch_id=branch_id,
                                        action="ws_chat",
                                        input_payload={"message": content},
                                        output_payload={"processed": True}
                                    )
                                finally:
                                    db.close()
                        except Exception as e:
                            logger.error(f"Failed to record changelog: {e}")
                    
                elif data.get("type") == "ping":
                    # Handle ping/pong for connection keepalive
                    await websocket.send_json({"type": "pong"})
                    
                elif data.get("type") == "close":
                    # Clean close requested
                    break
                    
                else:
                    # Unknown message type
                    msg_info = f"type={data.get('type')}, action={data.get('action')}"
                    logger.warning(f"Unknown message format: {msg_info}")
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Unknown message format: {msg_info}"
                    })
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "content": f"Error processing message: {str(e)}"
                })
                
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        try:
            await websocket.close()
            logger.info(f"WebSocket disconnected: project_id={project_id}")
        except:
            pass

# Export public interface
__all__ = ['register_ws_chat', 'WSDeps']