"""
SQL WebSocket module for Cedar app.
Handles WebSocket connections for SQL execution.
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import WebSocket
from sqlalchemy.orm import sessionmaker, Session

from ..db_utils import ensure_project_initialized, _get_project_engine
from ..changelog_utils import record_changelog
from main_models import Branch
from main_helpers import add_version


async def ws_sqlx(websocket: WebSocket, project_id: int):
    """
    WebSocket SQL with undo and branch context.
    Message format:
     - { "action": "exec", "sql": "...", "branch_id": 2 | null, "branch_name": "Main" | null, "max_rows": 200 }
     - { "action": "undo_last", "branch_id": 2 | null, "branch_name": "Main" | null }
    """
    # Check if shell API is enabled (security check)
    SHELL_API_ENABLED = os.getenv("CEDARPY_SHELL_API_ENABLED", "").strip() == "1"
    SHELL_API_TOKEN = os.getenv("CEDARPY_SHELL_API_TOKEN", "").strip() or None
    
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    
    if not SHELL_API_ENABLED:
        await websocket.close(code=4403)
        return
    
    if SHELL_API_TOKEN:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        if (token_q or cookie_tok) != SHELL_API_TOKEN:
            await websocket.close(code=4401)
            return
    else:
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            await websocket.close(code=4401)
            return

    await websocket.accept()

    # Ensure per-project database schema and storage are initialized
    try:
        ensure_project_initialized(project_id)
    except Exception:
        pass

    # Per-project session
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)

    def _resolve_branch_id(db: Session, branch_id: Optional[int], branch_name: Optional[str]) -> int:
        if branch_id:
            b = db.query(Branch).filter(Branch.id == branch_id, Branch.project_id == project_id).first()
            if b:
                return b.id
        if branch_name:
            b = db.query(Branch).filter(Branch.name == branch_name, Branch.project_id == project_id).first()
            if b:
                return b.id
        # Default to main branch
        main = db.query(Branch).filter(Branch.project_id == project_id, Branch.is_default == True).first()
        if main:
            return main.id
        # Create main if missing
        main = Branch(project_id=project_id, name="Main", is_default=True)
        db.add(main)
        db.commit()
        db.refresh(main)
        add_version(db, "branch", main.id, {"project_id": project_id, "name": "Main", "is_default": True})
        return main.id

    # Track undo stack
    undo_stack = []

    while True:
        try:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            action = msg.get("action", "exec")
            
            if action == "exec":
                sql_text = msg.get("sql", "").strip()
                if not sql_text:
                    await websocket.send_text(json.dumps({"error": "SQL is required"}))
                    continue

                max_rows = msg.get("max_rows", 200)
                branch_id_input = msg.get("branch_id")
                branch_name_input = msg.get("branch_name")

                db = SessionLocal()
                try:
                    branch_id = _resolve_branch_id(db, branch_id_input, branch_name_input)
                    
                    # Execute SQL
                    eng = _get_project_engine(project_id)
                    with eng.begin() as conn:
                        result = conn.exec_driver_sql(sql_text)
                        
                        # Check if this is a query that returns rows
                        if hasattr(result, 'returns_rows') and result.returns_rows:
                            cols = list(result.keys()) if hasattr(result, 'keys') else []
                            rows = []
                            for i, row in enumerate(result.fetchall()):
                                if i >= max_rows:
                                    break
                                rows.append(list(row))
                            
                            response = {
                                "ok": True,
                                "columns": cols,
                                "rows": rows,
                                "row_count": len(rows),
                                "truncated": len(rows) >= max_rows
                            }
                        else:
                            # For non-SELECT queries
                            rowcount = result.rowcount if hasattr(result, 'rowcount') else 0
                            response = {
                                "ok": True,
                                "rowcount": rowcount,
                                "message": f"Query executed successfully. {rowcount} row(s) affected."
                            }
                    
                    # Track for undo if it's a modifying statement
                    if sql_text.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER')):
                        undo_stack.append({
                            "sql": sql_text,
                            "branch_id": branch_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        # Keep only last 20 operations
                        if len(undo_stack) > 20:
                            undo_stack.pop(0)
                    
                    # Record in changelog
                    try:
                        record_changelog(db, project_id, branch_id, "sql.exec", {"sql": sql_text}, response)
                    except Exception:
                        pass
                    
                    await websocket.send_text(json.dumps(response))
                
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "ok": False,
                        "error": f"{type(e).__name__}: {str(e)}"
                    }))
                
                finally:
                    db.close()
            
            elif action == "undo_last":
                if not undo_stack:
                    await websocket.send_text(json.dumps({
                        "ok": False,
                        "error": "No operations to undo"
                    }))
                    continue
                
                # Pop the last operation
                last_op = undo_stack.pop()
                
                # For now, just acknowledge the undo
                # A real implementation would need to track inverse operations
                await websocket.send_text(json.dumps({
                    "ok": True,
                    "message": f"Undo not implemented. Would undo: {last_op['sql'][:50]}...",
                    "undone_operation": last_op
                }))
            
            else:
                await websocket.send_text(json.dumps({
                    "ok": False,
                    "error": f"Unknown action: {action}"
                }))
        
        except Exception as e:
            # Connection closed or other error
            break
    
    try:
        await websocket.close()
    except Exception:
        pass