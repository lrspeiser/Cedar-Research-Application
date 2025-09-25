"""
SQL route handlers for Cedar app.
Handles SQL execution endpoints, WebSocket SQL interface, undo functionality, and branch-aware operations.
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any
from fastapi import Request, Form, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketState

from ..db_utils import (
    ensure_project_initialized,
    get_project_db,
    _get_project_engine
)
from ..utils.sql_utils import (
    _table_has_branch_columns,
    _execute_sql,
    _execute_sql_with_undo,
    _render_sql_result_html,
    _safe_identifier,
    handle_sql_websocket
)
from ..changelog_utils import record_changelog
from ..ui_utils import escape, layout
from main_models import Project, Branch, SQLUndoLog
from main_helpers import current_branch, ensure_main_branch


async def ws_sqlx(websocket: WebSocket, project_id: int):
    """
    Enhanced WebSocket SQL endpoint with branch-aware execution.
    Strict explicit mode: requires project_id and branch_id to be specified in SQL.
    """
    await websocket.accept()
    
    try:
        while True:
            # Receive request
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"sql": raw}
            
            sql_text = msg.get("sql", "").strip()
            branch_id = msg.get("branch_id")
            
            if not sql_text:
                await websocket.send_json({"success": False, "error": "No SQL provided"})
                continue
            
            # Get branch info
            SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False)
            db = SessionLocal()
            try:
                ensure_project_initialized(project_id)
                branch = current_branch(db, project_id, int(branch_id) if branch_id else None)
                main_branch = ensure_main_branch(db, project_id)
                
                # Execute with undo support
                result = _execute_sql_with_undo(db, sql_text, project_id, branch.id)
                
                # Add branch info to result
                result["branch"] = {"id": branch.id, "name": branch.name}
                result["main_branch"] = {"id": main_branch.id, "name": main_branch.name}
                
                # Send result
                await websocket.send_json(result)
                
                # Log to changelog if mutation
                if result.get("success") and result.get("statement_type") not in ("select", "pragma", "show"):
                    try:
                        record_changelog(
                            db, project_id, branch.id, 
                            f"sql.{result.get('statement_type', 'unknown')}",
                            {"sql": sql_text},
                            {"rowcount": result.get("rowcount")}
                        )
                    except Exception:
                        pass
                        
            except Exception as e:
                await websocket.send_json({"success": False, "error": str(e)})
            finally:
                db.close()
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"success": False, "error": f"WebSocket error: {str(e)}"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def make_table_branch_aware(project_id: int, request: Request, table: str = Form(...), db: Session = Depends(get_project_db)):
    """
    Add project_id and branch_id columns to an existing table for branch isolation.
    Only works if table doesn't already have these columns.
    """
    ensure_project_initialized(project_id)
    
    # Get current branch
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id else None
    except Exception:
        branch_id = None
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    
    branch = current_branch(db, project.id, branch_id)
    table_safe = _safe_identifier(table)
    
    # Check if table exists and columns don't exist yet
    try:
        with _get_project_engine(project_id).begin() as conn:
            # Check if table has the columns
            if _table_has_branch_columns(conn, table_safe):
                msg = f"Table {table_safe} already has branch columns"
            else:
                # Add columns
                conn.exec_driver_sql(f"ALTER TABLE {table_safe} ADD COLUMN project_id INTEGER DEFAULT {project_id}")
                conn.exec_driver_sql(f"ALTER TABLE {table_safe} ADD COLUMN branch_id INTEGER DEFAULT {branch.id}")
                
                # Update existing rows
                conn.exec_driver_sql(f"UPDATE {table_safe} SET project_id = {project_id}, branch_id = {branch.id} WHERE project_id IS NULL")
                
                msg = f"Table {table_safe} is now branch-aware"
                
                # Log to changelog
                try:
                    record_changelog(
                        db, project_id, branch.id, 
                        "sql.make_branch_aware",
                        {"table": table_safe},
                        {"success": True}
                    )
                except Exception:
                    pass
    except Exception as e:
        msg = f"Error: {str(e)}"
    
    return RedirectResponse(f"/project/{project_id}?branch_id={branch.id}&msg={escape(msg)}", status_code=303)


def undo_last_sql(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    """
    Undo the last SQL mutation operation using the undo log.
    Only affects operations that were logged with undo support.
    """
    ensure_project_initialized(project_id)
    
    # Get current branch
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id else None
    except Exception:
        branch_id = None
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    
    branch = current_branch(db, project.id, branch_id)
    
    # Find the most recent undo log entry
    last_undo = db.query(SQLUndoLog).filter(
        SQLUndoLog.project_id == project_id,
        SQLUndoLog.branch_id == branch.id,
        SQLUndoLog.applied == False
    ).order_by(SQLUndoLog.created_at.desc()).first()
    
    if not last_undo:
        msg = "No operations to undo"
        return RedirectResponse(f"/project/{project_id}?branch_id={branch.id}&msg={msg}", status_code=303)
    
    # Execute the undo SQL
    try:
        undo_sql = last_undo.undo_sql
        result = _execute_sql(undo_sql, project_id)
        
        if result.get("success"):
            # Mark as applied
            last_undo.applied = True
            db.commit()
            
            msg = f"Undone: {last_undo.operation} on {last_undo.table_name}"
            
            # Log to changelog
            try:
                record_changelog(
                    db, project_id, branch.id, 
                    "sql.undo",
                    {"operation": last_undo.operation, "table": last_undo.table_name},
                    {"success": True, "undo_sql": undo_sql}
                )
            except Exception:
                pass
        else:
            msg = f"Undo failed: {result.get('error', 'Unknown error')}"
            
    except Exception as e:
        msg = f"Undo error: {str(e)}"
    
    return RedirectResponse(f"/project/{project_id}?branch_id={branch.id}&msg={escape(msg)}", status_code=303)


def execute_sql(project_id: int, request: Request, sql: str = Form(...), db: Session = Depends(get_project_db)):
    """
    Execute SQL query via form submission.
    Returns results as HTML table for display.
    """
    ensure_project_initialized(project_id)
    
    # Get current branch
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id else None
    except Exception:
        branch_id = None
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    
    branch = current_branch(db, project.id, branch_id)
    
    # Execute SQL with undo support
    result = _execute_sql_with_undo(db, sql, project_id, branch.id)
    
    # Log to changelog if mutation
    if result.get("success") and result.get("statement_type") not in ("select", "pragma", "show", "create"):
        try:
            record_changelog(
                db, project_id, branch.id, 
                f"sql.{result.get('statement_type', 'unknown')}",
                {"sql": sql},
                {"rowcount": result.get("rowcount")}
            )
        except Exception:
            pass
    
    # Render result as HTML
    html_content = _render_sql_result_html(
        result, project, branch, sql,
        layout_fn=layout
    )
    
    return HTMLResponse(html_content)