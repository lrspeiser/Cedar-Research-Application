"""
Test tools module for Cedar app.
Handles API endpoints for testing tool execution.
"""

import json
import base64
import io
import sqlite3
import re
import contextlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db_utils import ensure_project_initialized, _get_project_engine
from main_models import (
    Project, Branch, FileEntry, Note
)
from main_helpers import (
    current_branch, branch_filter_ids, get_project_db
)


def api_test_tool_exec(project_id: int, request: Request, body: dict, db: Session = Depends(get_project_db)):
    """
    Test endpoint for tool execution.
    Supports: sql, grep, code, notes, img operations.
    """
    ensure_project_initialized(project_id)
    
    # Get branch context
    branch_id = body.get("branch_id")
    branch = current_branch(db, project_id, branch_id)
    
    tool = body.get("tool", "").lower()
    args = body.get("args", {})
    
    # Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return JSONResponse({"ok": False, "error": "Project not found"}, status_code=404)
    
    # Tool implementations
    if tool == "sql":
        return _exec_sql_tool(project_id, args)
    elif tool == "grep":
        return _exec_grep_tool(project_id, args, db)
    elif tool == "code":
        return _exec_code_tool(project_id, branch, args, db)
    elif tool == "notes":
        return _exec_notes_tool(project_id, branch, args, db)
    elif tool == "img":
        return _exec_img_tool(project_id, args, db)
    else:
        return JSONResponse({"ok": False, "error": f"Unknown tool: {tool}"}, status_code=400)


def _exec_sql_tool(project_id: int, args: dict) -> JSONResponse:
    """Execute SQL query against project database."""
    sql_text = args.get("sql", "").strip()
    if not sql_text:
        return JSONResponse({"ok": False, "error": "SQL is required"})
    
    try:
        eng = _get_project_engine(project_id)
        with eng.begin() as conn:
            result = conn.exec_driver_sql(sql_text)
            
            if hasattr(result, 'returns_rows') and result.returns_rows:
                cols = list(result.keys()) if hasattr(result, 'keys') else []
                rows = []
                for i, row in enumerate(result.fetchall()):
                    if i >= 200:  # Limit rows
                        break
                    rows.append(list(row))
                
                return JSONResponse({
                    "ok": True,
                    "columns": cols,
                    "rows": rows,
                    "row_count": len(rows)
                })
            else:
                rowcount = result.rowcount if hasattr(result, 'rowcount') else 0
                return JSONResponse({
                    "ok": True,
                    "rowcount": rowcount,
                    "message": f"Query executed. {rowcount} row(s) affected."
                })
    
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)}"
        })


def _exec_grep_tool(project_id: int, args: dict, db: Session) -> JSONResponse:
    """Search within a file using grep/regex."""
    file_id = args.get("file_id")
    pattern = args.get("pattern", "")
    flags = args.get("flags", "")
    
    if not file_id or not pattern:
        return JSONResponse({"ok": False, "error": "file_id and pattern are required"})
    
    try:
        # Get file
        file_entry = db.query(FileEntry).filter(
            FileEntry.id == int(file_id),
            FileEntry.project_id == project_id
        ).first()
        
        if not file_entry or not file_entry.storage_path:
            return JSONResponse({"ok": False, "error": "File not found"})
        
        # Read file
        with open(file_entry.storage_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Compile regex
        re_flags = 0
        if 'i' in flags:
            re_flags |= re.IGNORECASE
        if 'm' in flags:
            re_flags |= re.MULTILINE
        if 's' in flags:
            re_flags |= re.DOTALL
        
        regex = re.compile(pattern, re_flags)
        
        # Find matches
        matches = []
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append({
                    "line": i,
                    "text": line.rstrip()
                })
                if len(matches) >= 200:  # Limit matches
                    break
        
        return JSONResponse({
            "ok": True,
            "file_id": file_id,
            "matches": matches,
            "match_count": len(matches)
        })
    
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)}"
        })


def _exec_code_tool(project_id: int, branch: Any, args: dict, db: Session) -> JSONResponse:
    """Execute Python code in sandboxed environment."""
    source = args.get("source", "")
    language = args.get("language", "python").lower()
    
    if language != "python":
        return JSONResponse({"ok": False, "error": f"Unsupported language: {language}"})
    
    if not source:
        return JSONResponse({"ok": False, "error": "Source code is required"})
    
    # Create cedar helper object
    class CedarHelper:
        def query(self, sql: str):
            """Execute SQL query."""
            try:
                eng = _get_project_engine(project_id)
                with eng.begin() as conn:
                    result = conn.exec_driver_sql(sql)
                    if hasattr(result, 'returns_rows') and result.returns_rows:
                        cols = list(result.keys())
                        rows = [dict(zip(cols, row)) for row in result.fetchall()[:200]]
                        return {"ok": True, "columns": cols, "rows": rows}
                    else:
                        return {"ok": True, "rowcount": result.rowcount}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        
        def list_files(self):
            """List project files."""
            ids = branch_filter_ids(db, project_id, branch.id)
            files = db.query(FileEntry).filter(
                FileEntry.project_id == project_id,
                FileEntry.branch_id.in_(ids)
            ).limit(100).all()
            
            return [
                {
                    "id": f.id,
                    "name": f.display_name,
                    "type": f.file_type,
                    "size": f.size_bytes
                }
                for f in files
            ]
        
        def read(self, file_id: int):
            """Read file contents."""
            f = db.query(FileEntry).filter(
                FileEntry.id == int(file_id),
                FileEntry.project_id == project_id
            ).first()
            
            if not f or not f.storage_path:
                return None
            
            try:
                with open(f.storage_path, 'rb') as fh:
                    data = fh.read(500000)  # Limit to 500KB
                    try:
                        return data.decode('utf-8', errors='replace')
                    except:
                        return f"base64:{base64.b64encode(data).decode('ascii')}"
            except:
                return None
    
    # Execute code
    cedar = CedarHelper()
    output_buffer = io.StringIO()
    
    # Restricted globals
    safe_globals = {
        "__builtins__": {
            "print": lambda *args, **kwargs: print(*args, file=output_buffer, **kwargs),
            "len": len,
            "range": range,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
        },
        "cedar": cedar,
        "json": json,
        "re": re,
        "io": io,
    }
    
    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(compile(source, "<test_code>", "exec"), safe_globals, safe_globals)
        
        output = output_buffer.getvalue()
        return JSONResponse({
            "ok": True,
            "output": output,
            "language": language
        })
    
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "output": output_buffer.getvalue()
        })


def _exec_notes_tool(project_id: int, branch: Any, args: dict, db: Session) -> JSONResponse:
    """Create notes in the project."""
    content = args.get("content", "")
    tags = args.get("tags", [])
    
    if not content:
        return JSONResponse({"ok": False, "error": "Content is required"})
    
    try:
        note = Note(
            project_id=project_id,
            branch_id=branch.id,
            content=str(content),
            tags=tags if isinstance(tags, list) else None
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        
        return JSONResponse({
            "ok": True,
            "note_id": note.id,
            "created_at": note.created_at.isoformat() if note.created_at else None
        })
    
    except Exception as e:
        db.rollback()
        return JSONResponse({
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)}"
        })


def _exec_img_tool(project_id: int, args: dict, db: Session) -> JSONResponse:
    """Get image data for analysis."""
    image_id = args.get("image_id")
    purpose = args.get("purpose", "")
    
    if not image_id:
        return JSONResponse({"ok": False, "error": "image_id is required"})
    
    try:
        # Get image file
        f = db.query(FileEntry).filter(
            FileEntry.id == int(image_id),
            FileEntry.project_id == project_id
        ).first()
        
        if not f or not f.storage_path:
            return JSONResponse({"ok": False, "error": "Image not found"})
        
        # Read image and convert to data URL
        with open(f.storage_path, 'rb') as fh:
            data = fh.read()
        
        mime = f.mime_type or "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        
        # Truncate for response (first 120KB of data URL)
        data_url_truncated = data_url[:120000] if len(data_url) > 120000 else data_url
        
        return JSONResponse({
            "ok": True,
            "image_id": f.id,
            "purpose": purpose,
            "mime_type": mime,
            "size_bytes": len(data),
            "data_url_head": data_url_truncated
        })
    
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)}"
        })