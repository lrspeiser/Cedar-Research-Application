"""
Project and thread management routes for Cedar app.
Handles creation and management of projects and threads.
"""

from typing import Optional
from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ..db_utils import (
    ensure_project_initialized,
    get_project_db,
    get_registry_db,
    _ensure_project_storage
)
from main_models import Project, Branch, Thread, ThreadMessage
from main_helpers import current_branch, add_version


def create_project(title: str = Form(...), db: Session = Depends(get_registry_db)):
    """
    Create a new project in the registry.
    Initializes storage directories and creates main branch.
    """
    # Create project record
    project = Project(title=title.strip()[:100])
    db.add(project)
    db.commit()
    db.refresh(project)
    
    # Initialize project storage and database
    try:
        _ensure_project_storage(project.id)
        ensure_project_initialized(project.id)
    except Exception as e:
        # Rollback on failure
        db.delete(project)
        db.commit()
        raise e
    
    # Redirect to the new project
    return RedirectResponse(f"/project/{project.id}?msg=Project+created", status_code=303)


def create_thread(project_id: int, request: Request, title: Optional[str] = Form(None), db: Session = Depends(get_project_db)):
    """
    Create a new thread in the project.
    
    If no title is provided, derives one from context (file/dataset) or uses default.
    Supports both form submission and JSON response for API usage.
    """
    ensure_project_initialized(project_id)
    
    # Get branch from query params
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    # Get context from query params
    file_q = request.query_params.get("file_id")
    dataset_q = request.query_params.get("dataset_id")
    json_q = request.query_params.get("json")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Derive a default title from file/dataset context when GET and no explicit title
    from main_models import FileEntry, Dataset
    
    file_obj = None
    dataset_obj = None
    
    try:
        if file_q is not None:
            file_obj = db.query(FileEntry).filter(
                FileEntry.id == int(file_q), 
                FileEntry.project_id == project.id
            ).first()
    except Exception:
        file_obj = None
        
    try:
        if dataset_q is not None:
            dataset_obj = db.query(Dataset).filter(
                Dataset.id == int(dataset_q), 
                Dataset.project_id == project.id
            ).first()
    except Exception:
        dataset_obj = None

    # Determine title
    if request.method.upper() == 'GET' and (title is None or not str(title).strip()):
        if file_obj:
            label = (file_obj.ai_title or file_obj.display_name or '').strip() or f"File {file_obj.id}"
            title = f"File: {label}"
        elif dataset_obj:
            title = f"DB: {dataset_obj.name}"
        else:
            title = "New Thread"
    title = (title or "New Thread").strip()

    # Create thread
    thread = Thread(project_id=project.id, branch_id=branch.id, title=title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    
    # Add version tracking
    add_version(db, "thread", thread.id, {
        "project_id": project.id, 
        "branch_id": branch.id, 
        "title": thread.title
    })

    redirect_url = f"/project/{project.id}?branch_id={branch.id}&thread_id={thread.id}"
    if file_obj:
        redirect_url += f"&file_id={file_obj.id}"
    if dataset_obj:
        redirect_url += f"&dataset_id={dataset_obj.id}"
    redirect_url += "&msg=Thread+created"

    # Optional JSON response for client-side creation
    if json_q is not None and str(json_q).strip() not in {"", "0", "false", "False", "no"}:
        return JSONResponse({
            "thread_id": thread.id, 
            "branch_id": branch.id, 
            "redirect": redirect_url, 
            "title": thread.title
        })

    # Redirect to focus the newly created thread
    return RedirectResponse(redirect_url, status_code=303)