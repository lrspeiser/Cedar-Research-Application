"""
Note management utilities for Cedar app.
Handles note operations including creation, updates, and deletions.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session, sessionmaker

from ..db_utils import _get_project_engine, ensure_project_initialized
from main_models import Note, Project, Branch, ChangelogEntry
from main_helpers import escape, branch_filter_ids
from ..changelog_utils import record_changelog as _record_changelog_base
from ..llm_utils import llm_summarize_action as _llm_summarize_action


def api_notes_save(app, payload: Dict[str, Any]):
    """Save or update a note."""
    project_id = int(payload.get("project_id"))
    branch_id = int(payload.get("branch_id"))
    note_id = payload.get("note_id")
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        if note_id:
            # Update existing note
            note = db.query(Note).filter(
                Note.id == int(note_id),
                Note.project_id == project_id,
                Note.branch_id == branch_id
            ).first()
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")
            note.title = title
            note.content = content
            note.updated_at = datetime.utcnow()
            action = "note.update"
        else:
            # Create new note
            note = Note(
                project_id=project_id,
                branch_id=branch_id,
                title=title,
                content=content,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(note)
            action = "note.create"
        
        db.commit()
        db.refresh(note)
        
        # Record in changelog
        try:
            _record_changelog_base(
                db, project_id, branch_id, action,
                {"note_id": note.id, "title": title},
                {"content": content[:500]},  # Truncate for changelog
                ChangelogEntry=ChangelogEntry,
                llm_summarize_action_fn=_llm_summarize_action
            )
        except Exception:
            pass
        
        return {
            "ok": True,
            "note": {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "created_at": note.created_at.isoformat() + "Z" if note.created_at else None,
                "updated_at": note.updated_at.isoformat() + "Z" if note.updated_at else None
            }
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_notes_list(app, project_id: int, branch_id: Optional[int] = None):
    """List all notes for a project/branch."""
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        q = db.query(Note).filter(Note.project_id == project_id)
        if branch_id is not None:
            q = q.filter(Note.branch_id == int(branch_id))
        
        notes = q.order_by(Note.updated_at.desc()).limit(200).all()
        
        return {
            "ok": True,
            "notes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "branch_id": n.branch_id,
                    "created_at": n.created_at.isoformat() + "Z" if n.created_at else None,
                    "updated_at": n.updated_at.isoformat() + "Z" if n.updated_at else None
                }
                for n in notes
            ]
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_notes_get(app, project_id: int, note_id: int):
    """Get a specific note."""
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        note = db.query(Note).filter(
            Note.id == int(note_id),
            Note.project_id == project_id
        ).first()
        
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        return {
            "ok": True,
            "note": {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "branch_id": note.branch_id,
                "created_at": note.created_at.isoformat() + "Z" if note.created_at else None,
                "updated_at": note.updated_at.isoformat() + "Z" if note.updated_at else None
            }
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_notes_delete(app, payload: Dict[str, Any]):
    """Delete a note."""
    project_id = int(payload.get("project_id"))
    branch_id = int(payload.get("branch_id"))
    note_id = int(payload.get("note_id"))
    
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        note = db.query(Note).filter(
            Note.id == note_id,
            Note.project_id == project_id,
            Note.branch_id == branch_id
        ).first()
        
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        note_title = note.title
        db.delete(note)
        db.commit()
        
        # Record deletion in changelog
        try:
            _record_changelog_base(
                db, project_id, branch_id, "note.delete",
                {"note_id": note_id, "title": note_title},
                {},
                ChangelogEntry=ChangelogEntry,
                llm_summarize_action_fn=_llm_summarize_action
            )
        except Exception:
            pass
        
        return {"ok": True, "message": f"Note '{note_title}' deleted"}
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_notes_search(app, project_id: int, query: str, branch_id: Optional[int] = None):
    """Search notes by title or content."""
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        q = db.query(Note).filter(Note.project_id == project_id)
        if branch_id is not None:
            q = q.filter(Note.branch_id == int(branch_id))
        
        # Search in both title and content
        search_pattern = f"%{query}%"
        q = q.filter(
            db.or_(
                Note.title.ilike(search_pattern),
                Note.content.ilike(search_pattern)
            )
        )
        
        notes = q.order_by(Note.updated_at.desc()).limit(50).all()
        
        return {
            "ok": True,
            "query": query,
            "notes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "content_preview": n.content[:200] + "..." if len(n.content) > 200 else n.content,
                    "branch_id": n.branch_id,
                    "updated_at": n.updated_at.isoformat() + "Z" if n.updated_at else None
                }
                for n in notes
            ]
        }
    finally:
        try:
            db.close()
        except Exception:
            pass