"""
Integration module to replace the old WebSocket chat handler with the new thinker-orchestrator flow.
This replaces the cedar_orchestrator.ws_chat imports with our new implementation.
"""

from fastapi import FastAPI, WebSocket
from ws_chat import WebSocketChatHandler
import os
import logging

logger = logging.getLogger(__name__)

def register_new_ws_chat(app: FastAPI):
    """Register the new WebSocket chat handler with the existing FastAPI app"""
    
    # Initialize the new chat handler
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    chat_handler = WebSocketChatHandler(api_key)
    
    # Register the new WebSocket endpoint
    @app.websocket("/ws/chat/{project_id}")
    async def new_websocket_chat_endpoint(websocket: WebSocket, project_id: int):
        """New WebSocket endpoint using thinker-orchestrator flow"""
        await chat_handler.handle_connection(websocket, project_id)
    
    # Also register on the secondary route for compatibility
    @app.websocket("/ws/chat2/{project_id}")
    async def new_websocket_chat2_endpoint(websocket: WebSocket, project_id: int):
        """Secondary WebSocket endpoint using thinker-orchestrator flow"""
        await chat_handler.handle_connection(websocket, project_id)
    
    logger.info("Registered new thinker-orchestrator WebSocket chat handlers")
    print("[startup] New thinker-orchestrator WebSocket handlers registered")

def replace_ws_chat_handlers():
    """
    This function patches the imports to replace the old WebSocket handlers.
    Call this before the FastAPI app is fully initialized.
    """
    try:
        # Import the main module
        import cedar_app.main_impl_full as main_module
        
        # Get the existing app
        app = getattr(main_module, 'app', None)
        if app:
            # Clear existing WebSocket routes for /ws/chat/*
            new_routes = []
            for route in app.routes:
                # Keep all routes except WebSocket routes that match our patterns
                if hasattr(route, 'path'):
                    if route.path.startswith('/ws/chat/') and hasattr(route, 'endpoint'):
                        logger.info(f"Removing old WebSocket route: {route.path}")
                        continue
                new_routes.append(route)
            
            # Replace the routes list
            app.router.routes = new_routes
            
            # Register our new handlers
            register_new_ws_chat(app)
            
            return True
            
    except Exception as e:
        logger.error(f"Failed to replace WebSocket handlers: {e}")
        print(f"[startup] Failed to replace WebSocket handlers: {e}")
        return False
    
    return False