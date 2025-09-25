"""
Changelog and Version Utilities for Cedar
==========================================

This module contains utilities for:
- Recording changelog entries
- Managing version tracking
- Summarizing actions via LLM
"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session


def record_changelog(db: Session, project_id: int, branch_id: int, action: str, 
                     input_payload: Dict[str, Any], output_payload: Dict[str, Any],
                     ChangelogEntry, llm_summarize_action_fn=None):
    """
    Persist a changelog entry and try to LLM-summarize it. Best-effort; stores even if summary fails.
    Prefers a model-provided run_summary (string or list of strings) when present in output_payload.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        action: Action name
        input_payload: Input data for the action
        output_payload: Output data from the action
        ChangelogEntry: SQLAlchemy model class for changelog entries
        llm_summarize_action_fn: Optional function to generate LLM summary
    """
    # Prefer explicit run_summary if provided; else generate via LLM
    summary: Optional[str] = None
    try:
        rs = (output_payload or {}).get("run_summary") if isinstance(output_payload, dict) else None
        if isinstance(rs, list):
            summary = " • ".join([str(x) for x in rs])
        elif isinstance(rs, str):
            summary = rs.strip()
    except Exception:
        summary = None
    
    if not summary and llm_summarize_action_fn:
        summary = llm_summarize_action_fn(action, input_payload, output_payload)
    
    try:
        entry = ChangelogEntry(
            project_id=project_id,
            branch_id=branch_id,
            action=action,
            input_json=input_payload,
            output_json=output_payload,
            summary_text=summary,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        try:
            print(f"[changelog-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        db.rollback()


def add_version(db: Session, project_id: int, branch_id: int, table_name: str,
                row_id: int, column_name: str, old_value: Any, new_value: Any,
                Version):
    """
    Record a version entry for tracking changes to data.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        table_name: Name of the table being modified
        row_id: ID of the row being modified
        column_name: Name of the column being modified
        old_value: Previous value
        new_value: New value
        Version: SQLAlchemy model class for version entries
    """
    try:
        version_entry = Version(
            project_id=project_id,
            branch_id=branch_id,
            table_name=table_name,
            row_id=row_id,
            column_name=column_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            created_at=datetime.utcnow()
        )
        db.add(version_entry)
        db.commit()
    except Exception as e:
        try:
            print(f"[version-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        db.rollback()