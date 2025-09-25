"""
File management utilities for Cedar app.
Handles file upload, download, deletion, and file operations.
"""

import os
import shutil
import json
import mimetypes
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session, sessionmaker

from ..db_utils import _get_project_engine, ensure_project_initialized, _project_dirs
from main_models import FileEntry, Project, Branch, Thread, ThreadMessage, Dataset
from main_helpers import current_branch, add_version, ensure_main_branch, branch_filter_ids, escape
from ..changelog_utils import record_changelog
from ..llm_utils import llm_classify_file as _llm_classify_file


def file_extension_to_type(filename: str) -> str:
    """Determine file type from extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.py', '.js', '.java', '.cpp', '.c', '.cs', '.go', '.rs', '.rb', '.php', '.swift']:
        return 'code'
    elif ext in ['.txt', '.md', '.log', '.csv', '.tsv']:
        return 'text'
    elif ext in ['.pdf']:
        return 'document'
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']:
        return 'image'
    elif ext in ['.json', '.jsonl', '.geojson']:
        return 'data'
    elif ext in ['.xls', '.xlsx', '.xlsm']:
        return 'spreadsheet'
    elif ext in ['.zip', '.tar', '.gz', '.7z', '.rar']:
        return 'archive'
    elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
        return 'video'
    elif ext in ['.mp3', '.wav', '.ogg', '.flac']:
        return 'audio'
    else:
        return 'unknown'


def interpret_file(file_path: str, original_name: str) -> Dict[str, Any]:
    """Interpret file metadata."""
    meta = {}
    try:
        meta['size_bytes'] = os.path.getsize(file_path)
        meta['extension'] = os.path.splitext(original_name)[1].lower()
        meta['mime_guess'] = mimetypes.guess_type(original_name)[0]
        
        # Try to detect if it's text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(8192)
                meta['is_text'] = True
                meta['line_count'] = len(open(file_path).readlines())
                
                # Check if JSON
                if meta['extension'] in ['.json', '.jsonl']:
                    try:
                        import json
                        data = json.loads(sample if len(sample) < 8192 else open(file_path).read())
                        meta['json_valid'] = True
                        if isinstance(data, dict):
                            meta['json_top_level_keys'] = list(data.keys())[:10]
                    except:
                        meta['json_valid'] = False
                
                # Check if CSV
                if meta['extension'] in ['.csv', '.tsv']:
                    try:
                        import csv
                        dialect = csv.Sniffer().sniff(sample[:1024])
                        meta['csv_dialect'] = dialect.delimiter
                    except:
                        pass
                        
        except:
            meta['is_text'] = False
            
        # Detect format
        if meta['extension'] == '.pdf':
            meta['format'] = 'pdf'
        elif meta['extension'] in ['.jpg', '.jpeg', '.png', '.gif']:
            meta['format'] = 'image'
        elif meta.get('is_text'):
            meta['format'] = 'text'
        else:
            meta['format'] = 'binary'
            
        # Detect language for code files
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.cs': 'csharp',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.r': 'r',
            '.sql': 'sql',
            '.sh': 'bash',
            '.yml': 'yaml',
            '.yaml': 'yaml',
            '.json': 'json',
            '.xml': 'xml',
            '.html': 'html',
            '.css': 'css',
        }
        if meta['extension'] in ext_to_lang:
            meta['language'] = ext_to_lang[meta['extension']]
            
    except Exception as e:
        meta['error'] = str(e)
        
    return meta


def upload_file(app, project_id: int, request: Request, file: UploadFile, db: Session):
    """Handle file upload with LLM classification."""
    ensure_project_initialized(project_id)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Determine path: per-project files root
    paths = _project_dirs(project.id)
    branch_dir_name = f"branch_{branch.name}"
    project_dir = os.path.join(paths["files_root"], branch_dir_name)
    os.makedirs(project_dir, exist_ok=True)

    original_name = file.filename or "upload.bin"
    # Verbose request logging for uploads
    try:
        host = request.client.host if request and request.client else "?"
        print(f"[upload-api] from={host} project_id={project.id} branch={branch.name} filename={original_name} ctype={getattr(file, 'content_type', '')}")
    except Exception:
        pass
    
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_base = os.path.basename(original_name)
    storage_name = f"{ts}__{safe_base}"
    disk_path = os.path.join(project_dir, storage_name)

    with open(disk_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)

    size = os.path.getsize(disk_path)
    mime, _ = mimetypes.guess_type(original_name)
    ftype = file_extension_to_type(original_name)

    try:
        print(f"[upload-api] saved project_id={project.id} branch={branch.name} path={disk_path} size={size} mime={mime or file.content_type or ''} ftype={ftype}")
    except Exception:
        pass

    meta = interpret_file(disk_path, original_name)

    record = FileEntry(
        project_id=project.id,
        branch_id=branch.id,
        filename=storage_name,
        display_name=original_name,
        file_type=ftype,
        structure=None,
        mime_type=mime or file.content_type or "",
        size_bytes=size,
        storage_path=os.path.abspath(disk_path),
        metadata_json=meta,
        ai_processing=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Create a processing thread entry so the user can see steps
    thr_title = (f"File: {original_name}")[:100]
    thr = Thread(project_id=project.id, branch_id=branch.id, title=thr_title)
    db.add(thr)
    db.commit()
    db.refresh(thr)
    
    # Add a 'system' message with the planned classification prompt payload
    try:
        payload = {
            "action": "classify_file",
            "metadata_sample": {
                k: meta.get(k) for k in [
                    "extension", "mime_guess", "format", "language", "is_text", 
                    "size_bytes", "line_count", "json_valid", "json_top_level_keys", "csv_dialect"
                ] if k in meta
            },
            "display_name": original_name
        }
        tm = ThreadMessage(
            project_id=project.id, 
            branch_id=branch.id, 
            thread_id=thr.id, 
            role="system", 
            display_title="Submitting file to LLM to analyze...", 
            content=json.dumps(payload, ensure_ascii=False), 
            payload_json=payload
        )
        db.add(tm)
        db.commit()
    except Exception:
        db.rollback()

    # LLM classification (best-effort, no fallbacks)
    ai_result = None
    try:
        meta_for_llm = dict(meta)
        meta_for_llm["display_name"] = original_name
        ai = _llm_classify_file(meta_for_llm)
        ai_result = ai
        if ai:
            struct = ai.get("structure") if isinstance(ai, dict) else None
            record.structure = struct
            record.ai_title = ai.get("ai_title")
            record.ai_description = ai.get("ai_description")
            record.ai_category = ai.get("ai_category")
            record.ai_processing = False
            db.commit()
            db.refresh(record)
            try:
                print(f"[upload-api] classified structure={record.structure or ''} ai_title={(record.ai_title or '')[:80]}")
            except Exception:
                pass
        else:
            record.ai_processing = False
            db.commit()
            try:
                print("[upload-api] classification skipped (disabled or missing key)")
            except Exception:
                pass
            tm2 = ThreadMessage(
                project_id=project.id, 
                branch_id=branch.id, 
                thread_id=thr.id, 
                role="assistant", 
                display_title="File analysis skipped", 
                content="LLM classification disabled or missing key"
            )
            db.add(tm2)
            db.commit()
    except Exception as e:
        try:
            print(f"[llm-exec-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            record.ai_processing = False
            db.commit()
        except Exception:
            db.rollback()

    add_version(db, "file", record.id, {
        "project_id": project.id, "branch_id": branch.id,
        "filename": record.filename, "display_name": record.display_name,
        "file_type": record.file_type, "structure": record.structure,
        "mime_type": record.mime_type, "size_bytes": record.size_bytes,
        "metadata": meta,
    })

    # Changelog for file upload + classification
    try:
        input_payload = {"action": "classify_file", "metadata_for_llm": meta_for_llm}
        output_payload = {"ai": ai_result, "thread_id": thr.id}
        record_changelog(db, project.id, branch.id, "file.upload+classify", input_payload, output_payload)
    except Exception:
        pass

    # Return file and thread info for further processing
    return {
        "file_id": record.id,
        "thread_id": thr.id,
        "branch_id": branch.id,
        "redirect": f"/project/{project.id}?branch_id={branch.id}&file_id={record.id}&thread_id={thr.id}&msg=File+uploaded"
    }


def delete_file(app, project_id: int, file_id: int, db: Session):
    """Delete a single file."""
    ensure_project_initialized(project_id)
    
    file_entry = db.query(FileEntry).filter(
        FileEntry.id == file_id,
        FileEntry.project_id == project_id
    ).first()
    
    if not file_entry:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete physical file
    try:
        if file_entry.storage_path and os.path.exists(file_entry.storage_path):
            os.remove(file_entry.storage_path)
    except Exception as e:
        print(f"[delete-file-error] Failed to delete physical file: {e}")
    
    # Delete database record
    display_name = file_entry.display_name
    branch_id = file_entry.branch_id
    db.delete(file_entry)
    db.commit()
    
    # Record in changelog
    try:
        record_changelog(
            db, project_id, branch_id, "file.delete",
            {"file_id": file_id, "display_name": display_name},
            {}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "message": f"File '{display_name}' deleted",
        "redirect": f"/project/{project_id}?branch_id={branch_id}&msg=File+deleted"
    }


def download_file(app, project_id: int, file_id: int, db: Session):
    """Download a file."""
    ensure_project_initialized(project_id)
    
    file_entry = db.query(FileEntry).filter(
        FileEntry.id == file_id,
        FileEntry.project_id == project_id
    ).first()
    
    if not file_entry:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not file_entry.storage_path or not os.path.exists(file_entry.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    # Record download in changelog
    try:
        record_changelog(
            db, project_id, file_entry.branch_id, "file.download",
            {"file_id": file_id, "display_name": file_entry.display_name},
            {}
        )
    except Exception:
        pass
    
    return FileResponse(
        path=file_entry.storage_path,
        media_type=file_entry.mime_type or 'application/octet-stream',
        filename=file_entry.display_name
    )


def list_files(app, project_id: int, branch_id: Optional[int], db: Session) -> List[Dict[str, Any]]:
    """List files for a project/branch."""
    ensure_project_initialized(project_id)
    
    # Get branch filter IDs (roll-up logic)
    if branch_id:
        show_branch_ids = branch_filter_ids(db, project_id, branch_id)
    else:
        # Default to main branch if not specified
        main_b = ensure_main_branch(db, project_id)
        show_branch_ids = branch_filter_ids(db, project_id, main_b.id)
    
    files = db.query(FileEntry).filter(
        FileEntry.project_id == project_id,
        FileEntry.branch_id.in_(show_branch_ids)
    ).order_by(FileEntry.created_at.desc()).all()
    
    result = []
    for f in files:
        result.append({
            "id": f.id,
            "display_name": f.display_name,
            "filename": f.filename,
            "file_type": f.file_type,
            "structure": f.structure,
            "mime_type": f.mime_type,
            "size_bytes": f.size_bytes,
            "ai_title": f.ai_title,
            "ai_description": f.ai_description,
            "ai_category": f.ai_category,
            "branch_id": f.branch_id,
            "created_at": f.created_at.isoformat() + "Z" if f.created_at else None
        })
    
    return result


def get_file_info(app, project_id: int, file_id: int, db: Session) -> Dict[str, Any]:
    """Get detailed information about a file."""
    ensure_project_initialized(project_id)
    
    file_entry = db.query(FileEntry).filter(
        FileEntry.id == file_id,
        FileEntry.project_id == project_id
    ).first()
    
    if not file_entry:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "id": file_entry.id,
        "display_name": file_entry.display_name,
        "filename": file_entry.filename,
        "file_type": file_entry.file_type,
        "structure": file_entry.structure,
        "mime_type": file_entry.mime_type,
        "size_bytes": file_entry.size_bytes,
        "storage_path": file_entry.storage_path,
        "metadata_json": file_entry.metadata_json,
        "ai_title": file_entry.ai_title,
        "ai_description": file_entry.ai_description,
        "ai_category": file_entry.ai_category,
        "ai_processing": file_entry.ai_processing,
        "branch_id": file_entry.branch_id,
        "created_at": file_entry.created_at.isoformat() + "Z" if file_entry.created_at else None,
        "updated_at": file_entry.updated_at.isoformat() + "Z" if file_entry.updated_at else None
    }