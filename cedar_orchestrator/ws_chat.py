"""
Simple WebSocket chat orchestrator with thinker-orchestrator flow.
"""

import os
import json
import asyncio
import logging
from fastapi import WebSocket, FastAPI
from typing import Any, Dict, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class WSDeps:
    """Compatibility wrapper for dependencies container"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class SimpleThinkerOrchestrator:
    """Simple thinker-orchestrator implementation for testing"""
    
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
    
    async def process_message(self, websocket: WebSocket, message: str):
        """Process a message with thinker reasoning and parallel agents"""
        
        # Stream thinker reasoning
        await websocket.send_json({
            "type": "thinker_reasoning",
            "content": f"Thinking about: {message}"
        })
        
        # Simulate parallel agent work
        agents = ["Agent1", "Agent2", "Agent3"]
        for agent in agents:
            await websocket.send_json({
                "type": "agent_result",
                "agent_name": agent,
                "content": f"{agent} processed: {message}"
            })
            await asyncio.sleep(0.1)
        
        # Final response
        final_response = f"Processed your message: {message}"
        
        if self.client:
            try:
                # Get actual LLM response
                completion = await self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": message}],
                    max_tokens=150
                )
                final_response = completion.choices[0].message.content or final_response
            except Exception as e:
                logger.error(f"LLM error: {e}")
        
        await websocket.send_json({
            "type": "final_response",
            "content": final_response
        })

def register_ws_chat(app: FastAPI, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    """
    Register WebSocket chat routes.
    """
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    orchestrator = SimpleThinkerOrchestrator(api_key)
    
    # Register route WITH project_id for compatibility
    if "{project_id}" in route_path:
        @app.websocket(route_path)
        async def ws_chat_with_project(websocket: WebSocket, project_id: int):
            await handle_ws_chat(websocket, orchestrator, project_id)
    
    # Also register a simple route WITHOUT project_id for testing
    simple_path = "/ws/chat"
    @app.websocket(simple_path)
    async def ws_chat_simple(websocket: WebSocket):
        await handle_ws_chat(websocket, orchestrator, None)
    
    logger.info(f"Registered WebSocket routes: {route_path} and {simple_path}")
    print(f"[startup] WebSocket routes registered: {route_path} and {simple_path}")

async def handle_ws_chat(websocket: WebSocket, orchestrator: SimpleThinkerOrchestrator, project_id: Optional[int]):
    """Handle WebSocket chat connection"""
    try:
        await websocket.accept()
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to Cedar WebSocket chat" + (f" (project {project_id})" if project_id else "")
        })
        
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("type") == "message":
                    content = data.get("content", "")
                    await orchestrator.process_message(websocket, content)
            except Exception as e:
                logger.error(f"Message processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "content": str(e)
                })
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass
