"""
Patched WebSocket chat orchestrator that uses the new thinker-orchestrator flow.
This replaces the old ws_chat.py module's functionality.
"""

import os
import sys
import json
import asyncio
import logging
from fastapi import WebSocket, FastAPI
from typing import Any, Dict

# Add parent directory to path to import our new modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class WSDeps:
    """Compatibility wrapper for dependencies container"""
    def __init__(self, **kwargs):
        # Store all the dependencies for compatibility
        for k, v in kwargs.items():
            setattr(self, k, v)

# Import the new WebSocket handler
try:
    from ws_chat import WebSocketChatHandler
    NEW_FLOW_AVAILABLE = True
    logger.info("New thinker-orchestrator flow loaded successfully")
except ImportError as e:
    logger.error(f"Failed to import new flow: {e}")
    NEW_FLOW_AVAILABLE = False
    # Fall back to old implementation
    from cedar_orchestrator.ws_chat import register_ws_chat as register_ws_chat_old, WSDeps as WSDeps_old

def register_ws_chat(app: FastAPI, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    """
    Register the WebSocket chat orchestrator with the new thinker-orchestrator flow.
    Falls back to the old implementation if the new modules aren't available.
    """
    
    if NEW_FLOW_AVAILABLE:
        # Use the new thinker-orchestrator flow
        api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        chat_handler = WebSocketChatHandler(api_key)
        
        @app.websocket(route_path)
        async def ws_chat_new(websocket: WebSocket, project_id: int):
            """WebSocket endpoint using new thinker-orchestrator flow"""
            try:
                await chat_handler.handle_connection(websocket, project_id)
            except Exception as e:
                logger.error(f"Error in new WebSocket handler: {e}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "event": "system_error", 
                        "data": {"error": str(e)}
                    })
                    await websocket.close()
                except:
                    pass
        
        logger.info(f"Registered new thinker-orchestrator WebSocket handler at {route_path}")
        print(f"[startup] New thinker-orchestrator flow registered at {route_path}")
        
    else:
        # Fall back to old implementation
        logger.warning("New flow not available, falling back to old implementation")
        print("[startup] WARNING: New thinker-orchestrator flow not available, using old implementation")
        
        # Import and use the old implementation
        from cedar_orchestrator import ws_chat as old_module
        old_deps = old_module.WSDeps(**{k: getattr(deps, k) for k in dir(deps) if not k.startswith('_')})
        old_module.register_ws_chat(app, old_deps, route_path)