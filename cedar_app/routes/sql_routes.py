"""
SQL-related route handlers for Cedar application.

This module provides WebSocket and HTTP endpoints for SQL operations including:
- Real-time SQL execution via WebSocket with streaming results
- Branch-aware table modifications (add/remove branch_id columns)
- SQL undo functionality with operation tracking
- Direct SQL execution via HTTP POST
"""

import json
import asyncio
from typing import Optional, Dict, Any

from fastapi import WebSocket, Request, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

# These will be imported from the calling context
# from cedar_app.db_utils import ensure_project_initialized, _get_project_engine, get_project_db
# from cedar_app.utils.sql_utils import handle_sql_websocket
# from main_models import SQLUndoLog, ChangelogEntry


def make_table_branch_aware_impl(project_id: int, request: Request, table: str, db: Session):
    """Make a table branch-aware by adding branch_id column and updating constraints."""
    from cedar_app.db_utils import ensure_project_initialized, _get_project_engine
    from main_helpers import record_changelog
    
    try:
        ensure_project_initialized(project_id)
        engine = _get_project_engine(project_id)
        
        with engine.begin() as conn:
            # Check if table exists
            if engine.dialect.name == "sqlite":
                result = conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                )
            else:
                result = conn.exec_driver_sql(
                    "SELECT table_name FROM information_schema.tables WHERE table_name=%s", (table,)
                )
            
            if not result.fetchone():
                return JSONResponse({"ok": False, "error": f"Table '{table}' not found"})
            
            # Check if branch_id column already exists
            if engine.dialect.name == "sqlite":
                cols_result = conn.exec_driver_sql(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cols_result.fetchall()]
            else:
                cols_result = conn.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,)
                )
                columns = [row[0] for row in cols_result.fetchall()]
            
            if "branch_id" in columns:
                return JSONResponse({"ok": False, "error": f"Table '{table}' already has branch_id column"})
            
            # Add branch_id column
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN branch_id INTEGER DEFAULT 1")
            
            # Update existing rows to reference Main branch (ID=1)
            conn.exec_driver_sql(f"UPDATE {table} SET branch_id = 1 WHERE branch_id IS NULL")
        
        # Record in changelog
        record_changelog(
            db, project_id, 1, "make_branch_aware",
            {"table": table},
            f"Made table '{table}' branch-aware"
        )
        
        return JSONResponse({"ok": True, "message": f"Table '{table}' is now branch-aware"})
        
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def undo_last_sql_impl(project_id: int, request: Request, db: Session):
    """Undo the last SQL operation for the project."""
    from cedar_app.db_utils import ensure_project_initialized, _get_project_engine
    from main_models import SQLUndoLog
    from main_helpers import record_changelog
    
    try:
        ensure_project_initialized(project_id)
        
        # Get the most recent undo log entry
        last_log = db.query(SQLUndoLog).filter(
            SQLUndoLog.project_id == project_id
        ).order_by(SQLUndoLog.created_at.desc()).first()
        
        if not last_log:
            return JSONResponse({"ok": False, "error": "No operations to undo"})
        
        engine = _get_project_engine(project_id)
        
        # Execute undo operation based on the original operation type
        with engine.begin() as conn:
            if last_log.op == "insert" and last_log.rows_after:
                # Delete the inserted rows
                for row in last_log.rows_after:
                    if last_log.pk_columns:
                        where_clauses = []
                        for pk_col in last_log.pk_columns:
                            if pk_col in row:
                                where_clauses.append(f"{pk_col} = {row[pk_col]}")
                        if where_clauses:
                            undo_sql = f"DELETE FROM {last_log.table_name} WHERE {' AND '.join(where_clauses)}"
                            conn.exec_driver_sql(undo_sql)
            
            elif last_log.op == "delete" and last_log.rows_before:
                # Re-insert the deleted rows
                for row in last_log.rows_before:
                    columns = list(row.keys())
                    values = list(row.values())
                    placeholders = ",".join(["?" for _ in values])
                    undo_sql = f"INSERT INTO {last_log.table_name} ({','.join(columns)}) VALUES ({placeholders})"
                    conn.exec_driver_sql(undo_sql, values)
            
            elif last_log.op == "update" and last_log.rows_before:
                # Restore the original values
                for row in last_log.rows_before:
                    if last_log.pk_columns:
                        where_clauses = []
                        set_clauses = []
                        for pk_col in last_log.pk_columns:
                            if pk_col in row:
                                where_clauses.append(f"{pk_col} = {row[pk_col]}")
                        for col, val in row.items():
                            if col not in last_log.pk_columns:
                                set_clauses.append(f"{col} = {repr(val)}")
                        if where_clauses and set_clauses:
                            undo_sql = f"UPDATE {last_log.table_name} SET {','.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
                            conn.exec_driver_sql(undo_sql)
        
        # Mark the log entry as undone
        db.delete(last_log)
        db.commit()
        
        # Record the undo operation
        record_changelog(
            db, project_id, last_log.branch_id or 1, "sql_undo",
            {"original_op": last_log.op, "table": last_log.table_name},
            f"Undid {last_log.op} operation on {last_log.table_name}"
        )
        
        return JSONResponse({"ok": True, "message": f"Undid {last_log.op} operation on {last_log.table_name}"})
        
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def execute_sql_impl(project_id: int, request: Request, sql: str, db: Session):
    """Execute SQL query and return results."""
    from cedar_app.db_utils import ensure_project_initialized, _get_project_engine
    from main_helpers import record_changelog
    
    try:
        ensure_project_initialized(project_id)
        
        if not sql or not sql.strip():
            return JSONResponse({"ok": False, "error": "SQL query is required"})
        
        engine = _get_project_engine(project_id)
        
        with engine.begin() as conn:
            result = conn.exec_driver_sql(text(sql))
            
            # Handle SELECT queries
            if sql.strip().upper().startswith('SELECT'):
                columns = list(result.keys()) if hasattr(result, 'keys') else []
                rows = []
                for i, row in enumerate(result.fetchall()):
                    if i >= 200:  # Limit rows
                        break
                    rows.append(dict(zip(columns, row)))
                
                # Record in changelog
                record_changelog(
                    db, project_id, 1, "sql_select",
                    {"sql": sql[:200], "row_count": len(rows)},
                    f"Executed SELECT query: {len(rows)} rows returned"
                )
                
                return JSONResponse({
                    "ok": True,
                    "type": "select",
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                })
            
            # Handle INSERT/UPDATE/DELETE queries
            else:
                rowcount = result.rowcount if hasattr(result, 'rowcount') else 0
                
                # Record in changelog
                record_changelog(
                    db, project_id, 1, "sql_execute",
                    {"sql": sql[:200], "rowcount": rowcount},
                    f"Executed SQL: {rowcount} rows affected"
                )
                
                return JSONResponse({
                    "ok": True,
                    "type": "execute",
                    "rowcount": rowcount,
                    "message": f"Query executed. {rowcount} row(s) affected."
                })
        
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
