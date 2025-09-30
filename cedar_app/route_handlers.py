"""
Route handler functions extracted from main.py to reduce file size.

This module contains large route handler functions that were previously inline
in main.py. These are extracted to keep main.py under 1000 lines as per project rules.

Functions can be imported and called directly from route definitions in main.py.
"""

from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import html

# Import models and helpers (will be available when called from main.py context)
from main_models import Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Note, SQLUndoLog
from cedar_app.ui_utils import layout
from main_helpers import escape, ensure_main_branch, current_branch

__all__ = [
    'execute_sql_handler',
    'create_thread_handler', 
    'merge_index_html_handler',
    'get_or_create_project_registry',
]


def execute_sql_handler(
    project_id: int,
    request: Request,
    sql: str,
    db: Session
) -> RedirectResponse:
    """
    Handler for SQL execution endpoint.
    Extracted from main.py line 1208.
    """
    from cedar_app.db_utils import _get_project_engine, record_changelog, add_version
    from main_helpers import _snake_case
    
    sql = sql.strip()
    if not sql:
        return RedirectResponse(f\"/project/{project_id}\", status_code=303)

    # Get branch context
    try:
        branch_id = request.query_params.get(\"branch_id\")
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(\"/\", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Parse SQL to detect operation type
    sql_lower = sql.lower().strip()
    is_select = sql_lower.startswith(\"select\")
    is_create = sql_lower.startswith(\"create table\")
    is_insert = sql_lower.startswith(\"insert\")
    is_update = sql_lower.startswith(\"update\")
    is_delete = sql_lower.startswith(\"delete\")
    is_drop = sql_lower.startswith(\"drop table\")

    # Branch-awareness check for mutations
    if not is_select:
        # For mutations, ensure the table is branch-aware
        # Extract table name
        table_name = None
        if is_insert or is_update or is_delete:
            try:
                import re
                if is_insert:
                    match = re.search(r'insert\\s+into\\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql_lower)
                elif is_update:
                    match = re.search(r'update\\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql_lower)
                elif is_delete:
                    match = re.search(r'delete\\s+from\\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql_lower)
                else:
                    match = None
                if match:
                    table_name = match.group(1)
            except Exception:
                pass

    # Execute SQL
    eng = _get_project_engine(project_id)
    undo_log = None

    try:
        with eng.begin() as conn:
            # Before mutation, store undo snapshot
            if not is_select and table_name:
                try:
                    snapshot = conn.execute(sql_text(f\"SELECT * FROM {table_name}\")).fetchall()
                    undo_log = SQLUndoLog(
                        project_id=project_id,
                        branch_id=branch.id,
                        operation_type=\"mutation\",
                        table_name=table_name,
                        snapshot_data=[dict(row._mapping) for row in snapshot]
                    )
                    db.add(undo_log)
                    db.commit()
                except Exception:
                    pass

            result = conn.execute(sql_text(sql))

            # For SELECT, fetch results
            if is_select:
                rows = result.fetchall()
                keys = result.keys()
                # Store in changelog as a query action
                try:
                    record_changelog(
                        db,
                        project_id,
                        branch.id,
                        \"sql_query\",
                        {\"sql\": sql},
                        {\"row_count\": len(rows)}
                    )
                except Exception:
                    pass

            # For mutations, record changelog
            else:
                try:
                    record_changelog(
                        db,
                        project_id,
                        branch.id,
                        \"sql_mutation\",
                        {\"sql\": sql},
                        {\"affected\": result.rowcount if hasattr(result, 'rowcount') else None}
                    )
                except Exception:
                    pass

    except Exception as e:
        # SQL error - return with error message
        error_msg = str(e)
        return RedirectResponse(
            f\"/project/{project_id}?branch_id={branch.id}&msg=SQL+error:+{html.escape(error_msg)}\",
            status_code=303
        )

    return RedirectResponse(
        f\"/project/{project_id}?branch_id={branch.id}&msg=SQL+executed+successfully\",
        status_code=303
    )


def create_thread_handler(
    project_id: int,
    request: Request,
    title: Optional[str] = None,
) -> RedirectResponse | JSONResponse:
    \"\"\"
    Handler for thread creation endpoint.
    Extracted from main.py line 1773.
    \"\"\"
    from cedar_app.db_utils import _get_project_engine, ensure_project_initialized
    from sqlalchemy.orm import sessionmaker
    
    ensure_project_initialized(project_id)
    
    # Get project database session
    eng = _get_project_engine(project_id)
    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    
    try:
        # branch selected via query parameter
        try:
            branch_id = request.query_params.get(\"branch_id\")
            branch_id = int(branch_id) if branch_id is not None else None
        except Exception:
            branch_id = None

        file_q = request.query_params.get(\"file_id\")
        dataset_q = request.query_params.get(\"dataset_id\")
        json_q = request.query_params.get(\"json\")

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return RedirectResponse(\"/\", status_code=303)

        branch = current_branch(db, project.id, branch_id)

        # Derive a default title from file/dataset context when GET and no explicit title
        file_obj = None
        dataset_obj = None
        try:
            if file_q is not None:
                file_obj = db.query(FileEntry).filter(FileEntry.id == int(file_q), FileEntry.project_id == project.id).first()
        except Exception:
            file_obj = None
        try:
            if dataset_q is not None:
                dataset_obj = db.query(Dataset).filter(Dataset.id == int(dataset_q), Dataset.project_id == project.id).first()
        except Exception:
            dataset_obj = None

        if request.method.upper() == 'GET' and (title is None or not str(title).strip()):
            if file_obj:
                label = (file_obj.ai_title or file_obj.display_name or '').strip() or f\"File {file_obj.id}\"
                title = f\"File: {label}\"
            elif dataset_obj:
                title = f\"DB: {dataset_obj.name}\"
            else:
                title = \"New Thread\"
        title = (title or \"New Thread\").strip()

        t = Thread(project_id=project.id, branch_id=branch.id, title=title)
        db.add(t)
        db.commit()
        db.refresh(t)

        redirect_url = f\"/project/{project.id}?branch_id={branch.id}&thread_id={t.id}\" + (f\"&file_id={file_obj.id}\" if file_obj else \"\") + (f\"&dataset_id={dataset_obj.id}\" if dataset_obj else \"\") + \"&msg=Thread+created\"

        # Optional JSON response for client-side creation
        if json_q is not None and str(json_q).strip() not in {\"\", \"0\", \"false\", \"False\", \"no\"}:
            return JSONResponse({\"thread_id\": t.id, \"branch_id\": branch.id, \"redirect\": redirect_url, \"title\": t.title})

        # Redirect to focus the newly created thread
        return RedirectResponse(redirect_url, status_code=303)
    finally:
        db.close()


def merge_index_html_handler(projects: List[Project]) -> str:
    \"\"\"
    Generate HTML for merge index page.
    Extracted from main.py line 1360.
    \"\"\"
    rows = []
    for p in projects:
        rows.append(f\"<tr><td>{escape(p.title)}</td><td><a class='pill' href='/merge/{p.id}'>Open</a></td></tr>\")
    body = f\"\"\"
      <h1>Merge</h1>
      <div class='card' style='max-width:720px'>
        <h3>Projects</h3>
        <table class='table'>
          <thead><tr><th>Title</th><th>Actions</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan=\"2\" class=\"muted\">No projects yet.</td></tr>'}</tbody>
        </table>
      </div>
    \"\"\"
    return body


def get_or_create_project_registry(db: Session, title: str) -> Project:
    \"\"\"
    Idempotent create by title.
    Extracted from main.py line 1484.
    
    - SQLite: use INSERT .. ON CONFLICT DO NOTHING, then SELECT
    - Fallback: SELECT first, else create
    \"\"\"
    from cedar_app.db_utils import registry_engine
    
    t = (title or \"\").strip()
    if not t:
        raise ValueError(\"empty title\")
    
    # Try SQLite upsert
    try:
        if registry_engine.dialect.name == \"sqlite\":
            try:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            except Exception:
                sqlite_insert = None
            if sqlite_insert is not None:
                stmt = sqlite_insert(Project).values(title=t)
                stmt = stmt.on_conflict_do_nothing(index_elements=[Project.title])
                db.execute(stmt)
                db.commit()
                existing = db.query(Project).filter(Project.title == t).first()
                if existing:
                    return existing
    except Exception:
        pass
    
    # Generic fallback (race-safe enough for CI; on conflict we query after rollback)
    existing = db.query(Project).filter(Project.title == t).first()
    if existing:
        return existing
    p = Project(title=t)
    db.add(p)
    try:
        db.commit()
        db.refresh(p)
        return p
    except Exception:
        db.rollback()
        existing = db.query(Project).filter(Project.title == t).first()
        if existing:
            return existing
        raise