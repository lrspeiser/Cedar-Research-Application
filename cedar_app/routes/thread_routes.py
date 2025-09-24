"""
Thread/chat routes for Cedar app.
Handles conversation threads and messages.
"""

from fastapi import APIRouter, Depends
from typing import Optional

from cedar_app.database import get_project_db

router = APIRouter()

@router.get("/list")
def list_threads(project_id: int, branch_id: Optional[int] = None):
    """List all threads for a project."""
    # Simplified implementation
    return {"ok": True, "threads": []}

@router.get("/session/{thread_id}")
def get_thread_session(thread_id: int, project_id: int):
    """Get a thread session."""
    # Simplified implementation
    return {
        "project_id": project_id,
        "thread_id": thread_id,
        "messages": []
    }
