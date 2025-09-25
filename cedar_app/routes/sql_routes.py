"""
SQL-related route handlers (stub implementation).

This module provides stub implementations for SQL route handlers that were
referenced in main_impl_full.py but not properly extracted.
"""

from fastapi import Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session


def make_table_branch_aware_impl(project_id: int, request: Request, table: str, db: Session):
    """Stub implementation for making a table branch-aware."""
    return JSONResponse({
        "ok": False,
        "error": "make_table_branch_aware not implemented"
    })


def undo_last_sql_impl(project_id: int, request: Request, db: Session):
    """Stub implementation for undoing the last SQL operation."""
    return JSONResponse({
        "ok": False, 
        "error": "undo_last_sql not implemented"
    })


def execute_sql_impl(project_id: int, request: Request, sql: str, db: Session):
    """Stub implementation for executing SQL."""
    return JSONResponse({
        "ok": False,
        "error": "execute_sql not implemented"  
    })