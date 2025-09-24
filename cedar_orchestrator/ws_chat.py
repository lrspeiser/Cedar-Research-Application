"""
WebSocket Chat with Advanced Thinker-Orchestrator Implementation
This module provides the real multi-agent orchestration system.
"""

import os
import logging
from typing import Optional
from fastapi import WebSocket, FastAPI
from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator

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
        
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to Cedar Advanced Orchestrator" + 
                      (f" (Project {project_id})" if project_id else ""),
            "features": {
                "thinker": True,
                "code_agent": True,
                "math_agent": True,
                "general_agent": True,
                "parallel_processing": True
            }
        })
        
        logger.info(f"WebSocket connected: project_id={project_id}")
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                
                if data.get("type") == "message":
                    content = data.get("content", "").strip()
                    
                    if not content:
                        await websocket.send_json({
                            "type": "error",
                            "content": "Empty message received"
                        })
                        continue
                    
                    logger.info(f"Processing message: {content[:50]}...")
                    
                    # Process with advanced orchestrator
                    await orchestrator.orchestrate(content, websocket)
                    
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
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Unknown message type: {data.get('type')}"
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