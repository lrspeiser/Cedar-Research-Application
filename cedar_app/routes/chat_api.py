"""
Chat API endpoints for managing numbered chats.
"""

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse
from typing import Dict, Any
from cedar_app.utils.chat_persistence import get_chat_manager

def register_chat_api_routes(app: FastAPI):
    """Register the chat API routes on the FastAPI app"""
    
    @app.post("/api/chat/new")
    def create_new_chat(payload: Dict[str, Any] = Body(...)):
        """Create a new numbered chat."""
        project_id = payload.get('project_id')
        branch_id = payload.get('branch_id')
        
        if not project_id or not branch_id:
            raise HTTPException(status_code=400, detail="project_id and branch_id required")
        
        chat_manager = get_chat_manager()
        chat_data = chat_manager.create_chat(
            project_id=project_id,
            branch_id=branch_id,
            title=payload.get('title', None)
        )
        
        return JSONResponse({
            'chat_number': chat_data['chat_number'],
            'title': chat_data['title'],
            'created_at': chat_data['created_at']
        })
    
    @app.post("/api/chat/load")
    def load_chat(payload: Dict[str, Any] = Body(...)):
        """Load a specific chat's history."""
        project_id = payload.get('project_id')
        branch_id = payload.get('branch_id')
        chat_number = payload.get('chat_number')
        
        if not all([project_id, branch_id, chat_number]):
            raise HTTPException(status_code=400, detail="project_id, branch_id, and chat_number required")
        
        chat_manager = get_chat_manager()
        chat_data = chat_manager.get_chat(project_id, branch_id, chat_number)
        
        if not chat_data:
            raise HTTPException(status_code=404, detail=f"Chat {chat_number} not found")
        
        return JSONResponse({
            'chat_number': chat_data['chat_number'],
            'title': chat_data['title'],
            'status': chat_data['status'],
            'messages': chat_data.get('messages', []),
            'agent_results': chat_data.get('agent_results', [])
        })
    
    @app.post("/api/chat/update")
    def update_chat(payload: Dict[str, Any] = Body(...)):
        """Update a chat with new messages or status."""
        project_id = payload.get('project_id')
        branch_id = payload.get('branch_id')
        chat_number = payload.get('chat_number')
        updates = payload.get('updates', {})
        
        if not all([project_id, branch_id, chat_number]):
            raise HTTPException(status_code=400, detail="project_id, branch_id, and chat_number required")
        
        chat_manager = get_chat_manager()
        success = chat_manager.update_chat(project_id, branch_id, chat_number, updates)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Chat {chat_number} not found")
        
        return JSONResponse({'success': True})
    
    @app.get("/api/chat/list")
    def list_chats(project_id: int, branch_id: int, limit: int = 20):
        """List chats for a project/branch."""
        chat_manager = get_chat_manager()
        chats = chat_manager.list_chats(project_id, branch_id, limit)
        
        return JSONResponse({'chats': chats})
    
    @app.get("/api/chat/active")
    def get_active_chat(project_id: int, branch_id: int):
        """Get the currently active chat for a project/branch."""
        chat_manager = get_chat_manager()
        chat_number = chat_manager.get_active_chat(project_id, branch_id)
        
        return JSONResponse({'active_chat_number': chat_number})