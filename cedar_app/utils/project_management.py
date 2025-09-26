"""
Project management utilities for Cedar app.
Handles project operations like merge, delete, and branch management.
"""

import os
import shutil
import html
import hashlib
import threading
from typing import Optional, Dict, Any
from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db_utils import (
    get_project_db, RegistrySessionLocal, _project_dirs, _get_project_engine,
    ensure_project_initialized
)
from main_models import Project, Branch, FileEntry, Thread, Dataset, ChangelogEntry, SQLUndoLog, Note
from main_helpers import current_branch, ensure_main_branch

# Import these at the module level to avoid circular imports
_project_engines_lock = threading.Lock()
_project_engines: Dict[int, Any] = {}


def _hash_payload(payload) -> str:
    """Hash a payload for comparison."""
    try:
        import json
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    except Exception:
        return ""


def merge_to_main(app, project_id: int, request: Request, db: Session):
    """Merge current branch to Main branch."""
    from ..changelog_utils import record_changelog as _record_changelog_base
    from ..llm_utils import llm_summarize_action as _llm_summarize_action
    
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    
    current_b = current_branch(db, project.id, branch_id)
    main_b = ensure_main_branch(db, project.id)
    if current_b.id == main_b.id:
        return RedirectResponse(f"/project/{project.id}?branch_id={main_b.id}&msg=Already+in+Main", status_code=303)

    merged_counts = {"files": 0, "threads": 0, "datasets": 0, "tables": 0}

    # Merge Files: copy physical files and create Main records
    paths_files = _project_dirs(project.id)["files_root"]
    src_dir = os.path.join(paths_files, f"branch_{current_b.name}")
    dst_dir = os.path.join(paths_files, f"branch_{main_b.name}")
    os.makedirs(dst_dir, exist_ok=True)
    
    files = db.query(FileEntry).filter(FileEntry.project_id == project.id, FileEntry.branch_id == current_b.id).all()
    for f in files:
        try:
            src_path = f.storage_path
            base_name = os.path.basename(f.filename)
            target_name = base_name
            target_path = os.path.join(dst_dir, target_name)
            # Avoid collision
            i = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(base_name)
                target_name = f"{name}__m{i}{ext}"
                target_path = os.path.join(dst_dir, target_name)
                i += 1
            # Copy file
            if src_path and os.path.exists(src_path):
                shutil.copy2(src_path, target_path)
            # Create Main record
            existing = db.query(FileEntry).filter(
                FileEntry.project_id == project.id,
                FileEntry.branch_id == main_b.id,
                FileEntry.filename == f.filename
            ).first()
            if not existing:
                new_f = FileEntry(
                    project_id=project.id,
                    branch_id=main_b.id,
                    filename=f.filename,
                    display_name=f.display_name,
                    file_type=f.file_type,
                    file_key=f.file_key,
                    size_bytes=f.size_bytes,
                    storage_path=target_path,
                    metadata_json=f.metadata_json,
                    structure=f.structure,
                    ai_title=f.ai_title,
                    ai_description=f.ai_description,
                    ai_category=f.ai_category,
                )
                db.add(new_f)
                merged_counts["files"] += 1
        except Exception:
            pass
    db.commit()

    # Merge Threads
    threads = db.query(Thread).filter(Thread.project_id == project.id, Thread.branch_id == current_b.id).all()
    for t in threads:
        existing = db.query(Thread).filter(
            Thread.project_id == project.id,
            Thread.branch_id == main_b.id,
            Thread.title == t.title
        ).first()
        if not existing:
            new_t = Thread(project_id=project.id, branch_id=main_b.id, title=t.title)
            db.add(new_t)
            merged_counts["threads"] += 1
    db.commit()

    # Merge Datasets
    datasets = db.query(Dataset).filter(Dataset.project_id == project.id, Dataset.branch_id == current_b.id).all()
    for d in datasets:
        existing = db.query(Dataset).filter(
            Dataset.project_id == project.id,
            Dataset.branch_id == main_b.id,
            Dataset.name == d.name
        ).first()
        if not existing:
            new_d = Dataset(project_id=project.id, branch_id=main_b.id, name=d.name)
            db.add(new_d)
            merged_counts["datasets"] += 1
    db.commit()

    # Merge Notes
    try:
        notes = db.query(Note).filter(Note.project_id == project.id, Note.branch_id == current_b.id).all()
        for n in notes:
            main_note = db.query(Note).filter(
                Note.project_id == project.id,
                Note.branch_id == main_b.id,
                Note.title == n.title
            ).first()
            if main_note:
                main_note.content = n.content
                main_note.updated_at = func.now()
            else:
                new_n = Note(
                    project_id=project.id,
                    branch_id=main_b.id,
                    title=n.title,
                    content=n.content
                )
                db.add(new_n)
        db.commit()
    except Exception:
        pass

    # Migrate data rows from branch-aware tables
    try:
        with _get_project_engine(project.id).begin() as conn:
            tables_res = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            for (table_name,) in tables_res:
                if table_name in {"files", "threads", "thread_messages", "datasets", "branches", "versions", "changelog", "sql_undo_log", "notes"}:
                    continue
                try:
                    pragma_res = conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
                    cols = {r[1] for r in pragma_res}
                    if "project_id" in cols and "branch_id" in cols:
                        conn.exec_driver_sql(
                            f"INSERT OR IGNORE INTO {table_name} SELECT * FROM {table_name} WHERE project_id={project.id} AND branch_id={current_b.id}"
                        )
                        conn.exec_driver_sql(
                            f"UPDATE {table_name} SET branch_id={main_b.id} WHERE project_id={project.id} AND branch_id={current_b.id}"
                        )
                        merged_counts["tables"] += 1
                except Exception:
                    pass
    except Exception:
        pass

    # After merging data rows, also adopt unique changelog entries from the branch into Main
    try:
        main_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==main_b.id).order_by(ChangelogEntry.created_at.desc()).limit(500).all()
        seen = set((ce.action, _hash_payload(ce.input_json)) for ce in main_entries)
        branch_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==current_b.id).order_by(ChangelogEntry.created_at.asc()).all()
        adopted = 0
        for ce in branch_entries:
            key = (ce.action, _hash_payload(ce.input_json))
            if key in seen:
                continue
            ne = ChangelogEntry(
                project_id=project.id,
                branch_id=main_b.id,
                action=ce.action,
                input_json=ce.input_json,
                output_json={"merged_from_branch_id": current_b.id, "merged_from_branch": current_b.name, "original_output": ce.output_json},
                summary_text=(ce.summary_text or f"Adopted from {current_b.name}: {ce.action}"),
            )
            db.add(ne)
            adopted += 1
        if adopted:
            db.commit()
    except Exception:
        db.rollback()

    msg = f"Merged files={merged_counts['files']}, threads={merged_counts['threads']}, datasets={merged_counts['datasets']}, tables={merged_counts['tables']}"
    
    try:
        _record_changelog_base(db, project.id, main_b.id, "branch.merge_to_main", 
                               {"from_branch": current_b.name}, {"merged_counts": merged_counts},
                               ChangelogEntry=ChangelogEntry, llm_summarize_action_fn=_llm_summarize_action)
    except Exception:
        pass
        
    return RedirectResponse(f"/project/{project.id}?branch_id={main_b.id}&msg=" + html.escape(msg), status_code=303)


def delete_all_files(app, project_id: int, request: Request, db: Session):
    """Delete all files in current branch."""
    from ..changelog_utils import record_changelog as _record_changelog_base
    from ..llm_utils import llm_summarize_action as _llm_summarize_action
    
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current_b = current_branch(db, project.id, branch_id)
    
    # Delete records and physical files
    files = db.query(FileEntry).filter(FileEntry.project_id == project.id, FileEntry.branch_id == current_b.id).all()
    for f in files:
        try:
            if f.storage_path and os.path.exists(f.storage_path):
                os.remove(f.storage_path)
        except Exception:
            pass
        db.delete(f)
    db.commit()
    
    try:
        _record_changelog_base(db, project.id, current_b.id, "files.delete_all", {}, {"deleted_count": len(files)},
                               ChangelogEntry=ChangelogEntry, llm_summarize_action_fn=_llm_summarize_action)
    except Exception:
        pass
        
    return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Files+deleted", status_code=303)


def delete_project(app, project_id: int):
    """Delete a project from registry and remove all its files and data."""
    global _project_engines, _project_engines_lock
    
    import logging
    logger = logging.getLogger(__name__)
    
    deleted_items = {
        "branches": 0,
        "files": 0,
        "threads": 0,
        "datasets": 0,
        "notes": 0,
        "chats": 0
    }
    
    # First, close any active database connections
    try:
        with _project_engines_lock:
            eng = _project_engines.pop(project_id, None)
        if eng is not None:
            try:
                eng.dispose()
                logger.info(f"Disposed database engine for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to dispose engine for project {project_id}: {e}")
    except Exception as e:
        logger.error(f"Error accessing engine for project {project_id}: {e}")
    
    # Get project details before deletion for logging
    project_name = f"Project {project_id}"
    try:
        with RegistrySessionLocal() as reg:
            proj = reg.query(Project).filter(Project.id == project_id).first()
            if proj:
                project_name = proj.title
                
                # Count and delete related items
                branches = reg.query(Branch).filter(Branch.project_id == project_id).all()
                deleted_items["branches"] = len(branches)
                for b in branches:
                    reg.delete(b)
                
                # Delete from registry
                reg.delete(proj)
                reg.commit()
                logger.info(f"Deleted project '{project_name}' (ID: {project_id}) from registry")
    except Exception as e:
        logger.error(f"Failed to delete project from registry: {e}")
    
    # Remove chat history
    try:
        from cedar_app.utils.chat_persistence import get_chat_manager
        chat_manager = get_chat_manager()
        deleted_items["chats"] = chat_manager.delete_project_chats(project_id)
        logger.info(f"Deleted {deleted_items['chats']} chats for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to delete chat history: {e}")
    
    # Remove project storage directory (DB + files)
    try:
        dirs = _project_dirs(project_id)
        base = dirs["base"]
        
        # Count files before deletion
        if os.path.isdir(dirs["files_root"]):
            for root, dirs, files in os.walk(dirs["files_root"]):
                deleted_items["files"] += len(files)
        
        # Remove entire project directory
        if os.path.isdir(base):
            shutil.rmtree(base, ignore_errors=False)
            logger.info(f"Removed project directory: {base}")
    except Exception as e:
        logger.error(f"Failed to remove project directory: {e}")
        # Try with ignore_errors=True as fallback
        try:
            base = _project_dirs(project_id)["base"]
            if os.path.isdir(base):
                shutil.rmtree(base, ignore_errors=True)
        except:
            pass
    
    # Log summary
    logger.info(f"Project deletion complete - {project_name} (ID: {project_id})")
    logger.info(f"Deleted: {deleted_items}")
    
    # Redirect to projects list with success message
    from fastapi import status
    from fastapi.responses import RedirectResponse
    import urllib.parse
    
    msg = f"Successfully deleted project '{project_name}' and all associated data"
    return RedirectResponse(
        f"/?msg={urllib.parse.quote(msg)}", 
        status_code=status.HTTP_303_SEE_OTHER
    )
