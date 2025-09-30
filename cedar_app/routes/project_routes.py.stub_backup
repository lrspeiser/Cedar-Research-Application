"""
Project routes for Cedar app.
Handles project-specific pages and operations.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from cedar_app.database import get_project_db, ensure_project_initialized
from cedar_app.utils.html import layout

router = APIRouter()

@router.get("/{project_id}", response_class=HTMLResponse)
def view_project(project_id: int, branch_id: int = None, request: Request = None):
    """View a specific project."""
    ensure_project_initialized(project_id)
    
    # For now, return a simple page
    # The full project_page_html is too large (1562 lines) and needs to be broken down
    body = f"""
    <h1>Project {project_id}</h1>
    <div class='card'>
        <p>Branch: {branch_id or 'Main'}</p>
        <p>This is a simplified project view.</p>
        <p>Full functionality to be restored after refactoring.</p>
    </div>
    """
    return layout(f"Project {project_id}", body)

@router.post("/{project_id}/branch")
def create_branch(project_id: int, name: str, db=Depends(lambda: get_project_db(project_id))):
    """Create a new branch in the project."""
    from main_models import Branch
    branch = Branch(project_id=project_id, name=name)
    db.add(branch)
    db.commit()
    return {"ok": True, "branch_id": branch.id}
