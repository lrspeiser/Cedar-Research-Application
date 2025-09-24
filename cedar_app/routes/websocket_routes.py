"""
WebSocket routes for Cedar app.
Handles real-time communication.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket chat endpoint."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Simplified echo for now
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        pass

@router.websocket("/health")
async def websocket_health(websocket: WebSocket):
    """WebSocket health check."""
    await websocket.accept()
    await websocket.send_text("healthy")
    await websocket.close()
