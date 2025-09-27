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

from ..db_utils import ensure_project_initialized, _project_dirs
from ..changelog_utils import record_changelog
from main_models import (
    Project, Branch, Thread, ThreadMessage, FileEntry
)
from main_helpers import current_branch
from ..db_utils import get_project_db


def serve_project_upload(project_id: int, file_id: int, db: Session = Depends(get_project_db)):
    """Deprecated wrapper: use cedar_app.api_routes.serve_project_upload via path.
    This wrapper resolves file_id to a path and delegates to the canonical server.
    """
    ensure_project_initialized(project_id)
    file_entry = db.query(FileEntry).filter(
        FileEntry.id == file_id,
        FileEntry.project_id == project_id
    ).first()
    if not file_entry or not file_entry.storage_path:
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(file_entry.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    # Compute relative path under project files root and delegate
    base = _project_dirs(project_id)["files_root"]
    rel_path = os.path.relpath(os.path.abspath(file_entry.storage_path), start=os.path.abspath(base))
    from ..api_routes import serve_project_upload as _serve
    return _serve(project_id=project_id, path=rel_path, project_dirs_fn=_project_dirs)


def upload_file(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    branch_id: Optional[int] = Form(None),
    thread_id: Optional[int] = Form(None),
    is_ajax: Optional[str] = Form(None),
    db: Session = Depends(get_project_db)
):
    """Deprecated wrapper: delegate to utils.file_operations.upload_file (canonical).
    Note: branch_id/thread_id/is_ajax are ignored by the canonical handler.
    """
    from .file_operations import upload_file as _upload
    return _upload(project_id, request, file, db)


