"""
File upload module for Cedar app.
Handles file upload endpoints and processing.
"""

import os
import json
import hashlib
import mimetypes
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session

from ..db_utils import ensure_project_initialized
from ..changelog_utils import record_changelog
from main_models import (
    Project, Branch, Thread, ThreadMessage, FileEntry
)
from main_helpers import current_branch
from ..db_utils import get_project_db


def serve_project_upload(project_id: int, file_id: int, db: Session = Depends(get_project_db)):
    """Serve uploaded file for download/viewing."""
    ensure_project_initialized(project_id)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    file_entry = db.query(FileEntry).filter(
        FileEntry.id == file_id,
        FileEntry.project_id == project_id
    ).first()
    
    if not file_entry or not file_entry.storage_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.exists(file_entry.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    # Determine content type
    content_type = file_entry.mime_type
    if not content_type:
        content_type, _ = mimetypes.guess_type(file_entry.storage_path)
        if not content_type:
            content_type = "application/octet-stream"
    
    # Return file response
    return FileResponse(
        path=file_entry.storage_path,
        media_type=content_type,
        filename=file_entry.display_name or f"file_{file_id}"
    )


def upload_file(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    branch_id: Optional[int] = Form(None),
    thread_id: Optional[int] = Form(None),
    is_ajax: Optional[str] = Form(None),
    db: Session = Depends(get_project_db)
):
    """
    Handle file upload for a project.
    Creates file entry, optionally runs post-processing.
    """
    ensure_project_initialized(project_id)
    
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        if is_ajax:
            return JSONResponse({"error": "Project not found"}, status_code=404)
        return RedirectResponse("/", status_code=303)
    
    # Determine branch
    branch = current_branch(db, project_id, branch_id)
    
    # Create storage directory
    storage_base = os.path.expanduser("~/CedarPyData/project_uploads")
    project_dir = os.path.join(storage_base, f"project_{project_id}")
    os.makedirs(project_dir, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_hash = hashlib.md5(file.filename.encode()).hexdigest()[:8]
    safe_filename = f"{timestamp}_{file_hash}_{file.filename}"
    storage_path = os.path.join(project_dir, safe_filename)
    
    # Save file
    try:
        contents = file.file.read()
        with open(storage_path, 'wb') as f:
            f.write(contents)
    except Exception as e:
        if is_ajax:
            return JSONResponse({"error": f"Failed to save file: {e}"}, status_code=500)
        return RedirectResponse(f"/project/{project_id}?msg=Upload+failed", status_code=303)
    
    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(file.filename)
    if not mime_type:
        mime_type = "application/octet-stream"
    
    # Determine file type and structure
    file_ext = Path(file.filename).suffix.lower()
    file_type = "unknown"
    structure = "unstructured"
    
    # Common file type detection
    if file_ext in ['.csv', '.tsv', '.xlsx', '.xls']:
        file_type = "spreadsheet"
        structure = "tabular"
    elif file_ext in ['.json', '.jsonl']:
        file_type = "json"
        structure = "structured"
    elif file_ext in ['.txt', '.md', '.rst']:
        file_type = "text"
        structure = "unstructured"
    elif file_ext in ['.pdf']:
        file_type = "pdf"
        structure = "document"
    elif file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        file_type = "image"
        structure = "binary"
    elif file_ext in ['.py', '.js', '.java', '.cpp', '.c', '.h']:
        file_type = "code"
        structure = "code"
    
    # Create file entry
    file_entry = FileEntry(
        project_id=project_id,
        branch_id=branch.id,
        display_name=file.filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_type=file_type,
        structure=structure,
        size_bytes=len(contents),
        hash_sha256=hashlib.sha256(contents).hexdigest()
    )
    
    db.add(file_entry)
    db.commit()
    db.refresh(file_entry)
    
    # Add version tracking
    add_version(db, "file", file_entry.id, {
        "project_id": project_id,
        "branch_id": branch.id,
        "display_name": file.filename,
        "size_bytes": len(contents)
    })
    
    # Create or update thread if provided
    if thread_id:
        thread = db.query(Thread).filter(
            Thread.id == thread_id,
            Thread.project_id == project_id
        ).first()
        
        if thread:
            # Add upload message to thread
            msg = ThreadMessage(
                project_id=project_id,
                branch_id=branch.id,
                thread_id=thread_id,
                role="system",
                content=f"File uploaded: {file.filename}",
                display_title="File Upload"
            )
            db.add(msg)
            db.commit()
    
    # Record in changelog
    try:
        input_payload = {
            "filename": file.filename,
            "size": len(contents),
            "type": file_type
        }
        output_payload = {
            "file_id": file_entry.id,
            "storage_path": storage_path
        }
        record_changelog(db, project_id, branch.id, "file.upload", input_payload, output_payload)
    except Exception:
        pass
    
    # Start background processing if configured
    # NOTE: Background processing implementation would go here
    # This is where tabular import, text extraction, etc. would be triggered
    
    # Return response
    if is_ajax:
        return JSONResponse({
            "ok": True,
            "file_id": file_entry.id,
            "redirect": f"/project/{project_id}?branch_id={branch.id}&file_id={file_entry.id}"
        })
    
    redirect_url = f"/project/{project_id}?branch_id={branch.id}&file_id={file_entry.id}"
    if thread_id:
        redirect_url += f"&thread_id={thread_id}"
    redirect_url += "&msg=File+uploaded"
    
    return RedirectResponse(redirect_url, status_code=303)


def _run_upload_postprocess_background(
    project_id: int,
    branch_id: int,
    file_id: int,
    thread_id: int,
    file_type: str,
    structure: str
):
    """
    Background worker for file post-processing.
    Handles text extraction, tabular import, etc.
    """
    # This would contain the actual implementation
    # For now, it's a placeholder
    pass