"""
SQL utilities for Cedar app.
Handles SQL execution, WebSocket operations, undo functionality, and result formatting.
"""

import re
import os
import json
import html
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import RedirectResponse

from ..db_utils import (_get_project_engine, SQLUndoLog, ensure_project_initialized, 
                       current_branch, record_changelog, get_project_db)
from ..database import registry_engine
from ..models import Project, Branch
from ..auth import require_shell_enabled_and_auth
from ..ui_utils import layout, escape

# Configuration
SHELL_API_ENABLED = os.getenv("CEDARPY_SHELL_API_TOKEN") is not None
SHELL_API_TOKEN = os.getenv("CEDARPY_SHELL_API_TOKEN")

# SQL Helper Functions
def _dialect(engine_obj=None) -> str:
    """Get the database dialect name."""
    eng = engine_obj or registry_engine
    return eng.dialect.name

def _safe_identifier(name: str) -> str:
    """Sanitize SQL identifier by removing non-alphanumeric characters."""
    return re.sub(r"[^a-zA-Z0-9_]+", "", name)

def _sql_quote(val: Any) -> str:
    """Quote SQL values safely."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return "'" + s + "'"

def _table_has_branch_columns(conn, table: str) -> bool:
    """Check if table has project_id and branch_id columns."""
    try:
        if _dialect() == "sqlite":
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            cols = {r[1] for r in rows}
            return "project_id" in cols and "branch_id" in cols
        elif _dialect() == "mysql":
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            ).fetchall()
            cols = {r[0] for r in rows}
            return "project_id" in cols and "branch_id" in cols
    except Exception:
        return False
    return False

def _get_pk_columns(conn, table: str) -> List[str]:
    """Get primary key column names for a table."""
    try:
        if _dialect() == "sqlite":
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            return [r[1] for r in rows if r[5]]  # r[5] is pk flag
        elif _dialect() == "mysql":
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_KEY='PRI'",
                (table,),
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []
    return []

def _extract_where_clause(sql_text: str) -> Optional[str]:
    """Extract WHERE clause from SQL statement."""
    s = sql_text
    low = s.lower()
    i = low.find(" where ")
    if i == -1:
        return None
    return s[i+7:].strip()

def _preprocess_sql_branch_aware(conn, sql_text: str, project_id: int, branch_id: int, main_id: int) -> Tuple[str, bool]:
    """
    STRICT EXPLICIT-ONLY MODE:
    - No automatic SQL rewriting or injection is performed.
    - SELECT/INSERT/UPDATE/DELETE/CREATE are executed exactly as provided.
    - See BRANCH_SQL_POLICY.md for required patterns when operating on branch-aware tables.
    Returns (sql_as_is, False)
    """
    s = (sql_text or "").strip()
    return (s, False)

# SQL Execution Functions
def _execute_sql(sql_text: str, project_id: int, max_rows: int = 200) -> dict:
    """Execute SQL against the per-project database."""
    sql_text = (sql_text or "").strip()
    if not sql_text:
        return {"success": False, "error": "Empty SQL"}
    first = sql_text.split()[0].lower() if sql_text.split() else ""
    stype = first
    result: dict = {"success": False, "statement_type": stype}
    try:
        with _get_project_engine(project_id).begin() as conn:
            if first in ("select", "pragma", "show"):
                res = conn.exec_driver_sql(sql_text)
                cols = list(res.keys()) if res.returns_rows else []
                rows = []
                count = 0
                if res.returns_rows:
                    for r in res:
                        rows.append([r[c] if isinstance(r, dict) else r[idx] for idx, c in enumerate(cols)])
                        count += 1
                        if count >= max_rows:
                            break
                result.update({
                    "success": True,
                    "columns": cols,
                    "rows": rows,
                    "rowcount": None,
                    "truncated": res.returns_rows and (count >= max_rows),
                })
            else:
                res = conn.exec_driver_sql(sql_text)
                result.update({
                    "success": True,
                    "rowcount": res.rowcount,
                })
    except Exception as e:
        result.update({"success": False, "error": str(e)})
    return result

def _execute_sql_with_undo(db: Session, sql_text: str, project_id: int, branch_id: int, max_rows: int = 200) -> dict:
    """Execute SQL with undo logging for mutations."""
    s = (sql_text or "").strip()
    if not s:
        return {"success": False, "error": "Empty SQL"}
    first = s.split()[0].lower() if s.split() else ""
    if first in ("select", "pragma", "show", "create"):
        return _execute_sql(s, project_id, max_rows=max_rows)

    # Simple parse
    m_ins = re.match(r"insert\s+into\s+([a-zA-Z0-9_]+)\s*\(([^\)]+)\)\s*values\s*\((.+)\)\s*;?$", s, flags=re.IGNORECASE | re.DOTALL)
    m_upd = re.match(r"update\s+([a-zA-Z0-9_]+)\s+set\s+(.+?)\s*(where\s+(.+))?;?$", s, flags=re.IGNORECASE | re.DOTALL)
    m_del = re.match(r"delete\s+from\s+([a-zA-Z0-9_]+)\s*(where\s+(.+))?;?$", s, flags=re.IGNORECASE | re.DOTALL)

    op = None
    table = None
    where_sql = None
    cols_list = []
    vals_list = []

    if m_ins:
        op = "insert"; table = _safe_identifier(m_ins.group(1))
        cols_list = [c.strip() for c in m_ins.group(2).split(",")]
        vals_list = [v.strip() for v in m_ins.group(3).split(",")]
    elif m_upd:
        op = "update"; table = _safe_identifier(m_upd.group(1))
        where_sql = m_upd.group(4)
    elif m_del:
        op = "delete"; table = _safe_identifier(m_del.group(1))
        where_sql = m_del.group(3)

    if not op or not table:
        # Fallback
        return _execute_sql(s, project_id, max_rows=max_rows)

    # Only capture for manageable row counts
    try:
        undo_cap = int(os.getenv("CEDARPY_SQL_UNDO_MAX_ROWS", "1000"))
    except Exception:
        undo_cap = 1000

    with _get_project_engine(project_id).begin() as conn:
        # Strict explicit-only enforcement for branch-aware tables
        try:
            table_for_check = None
            if m_ins:
                table_for_check = _safe_identifier(m_ins.group(1))
            elif m_upd:
                table_for_check = _safe_identifier(m_upd.group(1))
            elif m_del:
                table_for_check = _safe_identifier(m_del.group(1))
            if table_for_check:
                if _table_has_branch_columns(conn, table_for_check):
                    # INSERT must list both project_id and branch_id columns explicitly
                    if m_ins:
                        cols_ci = [c.strip().lower() for c in cols_list]
                        missing = [c for c in ("project_id","branch_id") if c not in cols_ci]
                        if missing:
                            return {"success": False, "error": f"Strict branch policy: INSERT into '{table_for_check}' must explicitly include columns: {', '.join(missing)}. See BRANCH_SQL_POLICY.md"}
                    # UPDATE/DELETE must have WHERE that references both project_id and branch_id
                    if m_upd or m_del:
                        where_lc = (where_sql or "").lower()
                        if ("project_id" not in where_lc) or ("branch_id" not in where_lc):
                            return {"success": False, "error": f"Strict branch policy: {op.upper()} on '{table_for_check}' must include WHERE with both project_id and branch_id. See BRANCH_SQL_POLICY.md"}
        except Exception as _enf_err:
            # Be safe: if enforcement itself errors, block the write
            return {"success": False, "error": f"Strict branch policy check failed: {_enf_err}"}

        # Determine PK columns if any
        pk_cols = _get_pk_columns(conn, table)
        rows_before = []
        rows_after = []
        created_log_id = None

        if op in ("update", "delete"):
            w = _extract_where_clause(s)
            if w:
                sel_sql = f"SELECT * FROM {table} WHERE {w}"
                res = conn.exec_driver_sql(sel_sql)
                cols = list(res.keys()) if res.returns_rows else []
                count = 0
                for r in res:
                    row = {cols[i]: r[i] for i in range(len(cols))}
                    rows_before.append(row)
                    count += 1
                    if count >= undo_cap: break

        # Execute original statement
        conn.exec_driver_sql(s)

        if op == "insert":
            # Try to identify inserted row
            if pk_cols:
                # Construct a WHERE from provided PK values if present
                provided = {c.lower(): vals_list[i] for i, c in enumerate(cols_list)} if cols_list and vals_list else {}
                have_pk_vals = all(pc.lower() in provided for pc in pk_cols)
                if have_pk_vals:
                    conds = []
                    for pc in pk_cols:
                        raw = provided[pc.lower()]
                        conds.append(f"{pc} = {raw}")
                    conds.append(f"project_id = {project_id}")
                    conds.append(f"branch_id = {branch_id}")
                    sel = f"SELECT * FROM {table} WHERE " + " AND ".join(conds)
                    res2 = conn.exec_driver_sql(sel)
                    cols2 = list(res2.keys()) if res2.returns_rows else []
                    for r in res2:
                        rows_after.append({cols2[i]: r[i] for i in range(len(cols2))})
                else:
                    # SQLite last_insert_rowid for single integer PK
                    if _dialect(_get_project_engine(project_id)) == "sqlite" and len(pk_cols) == 1:
                        pk = pk_cols[0]
                        rid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
                        res2 = conn.exec_driver_sql(f"SELECT * FROM {table} WHERE {pk} = {rid}")
                        cols2 = list(res2.keys()) if res2.returns_rows else []
                        for r in res2:
                            rows_after.append({cols2[i]: r[i] for i in range(len(cols2))})
        elif op == "update":
            if where_sql:
                res3 = conn.exec_driver_sql(f"SELECT * FROM {table} WHERE {where_sql}")
                cols3 = list(res3.keys()) if res3.returns_rows else []
                count = 0
                for r in res3:
                    rows_after.append({cols3[i]: r[i] for i in range(len(cols3))})
                    count += 1
                    if count >= undo_cap: break

        # Done with data mutations; log insertion happens outside this transaction to avoid SQLite locking

    # Store undo log using the ORM session (separate transaction)
    try:
        log = SQLUndoLog(
            project_id=project_id,
            branch_id=branch_id,
            table_name=table,
            op=op,
            sql_text=s,
            pk_columns=pk_cols,
            rows_before=rows_before,
            rows_after=rows_after,
        )
        db.add(log)
        # Ensure PK is assigned before commit even if expire_on_commit=True
        db.flush()
        try:
            created_log_id = log.id
        except Exception:
            created_log_id = None
        db.commit()
    except Exception as e:
        try:
            print(f"[undo-log-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        db.rollback()

    # Best-effort fallback: if we did not capture an explicit created_log_id, query the latest log for this project+branch
    if created_log_id is None:
        try:
            _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id, SQLUndoLog.branch_id==branch_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
            if not _last:
                _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
            if _last:
                created_log_id = _last.id
        except Exception:
            created_log_id = None

    # Return a generic result (we can run a SELECT for UPDATE/DELETE to show rowcount)
    _res = _execute_sql(
        f"SELECT changes() as affected" if _dialect(_get_project_engine(project_id)) == "sqlite" else s,
        project_id,
        max_rows=max_rows,
    )
    # Include undo_log_id when we created one
    if created_log_id is not None:
        try:
            _res["undo_log_id"] = created_log_id
        except Exception:
            pass
    return _res

# Result rendering
def _render_sql_result_html(result: dict) -> str:
    """Render SQL execution result as HTML."""
    if not result:
        return ""
    if not result.get("success"):
        return f"<div class='muted' style='color:#b91c1c'>Error: {escape(str(result.get('error') or 'unknown error'))}</div>"
    info = []
    if result.get("statement_type"):
        info.append(f"<span class='pill'>{escape(result['statement_type'].upper())}</span>")
    if "rowcount" in result and result["rowcount"] is not None:
        info.append(f"<span class='small muted'>rowcount: {result['rowcount']}</span>")
    if result.get("truncated"):
        info.append("<span class='small muted'>truncated</span>")
    info_html = " ".join(info)

    # Table for rows
    rows_html = ""
    if result.get("columns") and result.get("rows") is not None:
        # Deduplicate headers to avoid showing duplicate column names (observed in some drivers)
        cols_unique = []
        for c in (result["columns"] or []):
            if c not in cols_unique:
                cols_unique.append(c)
        headers = ''.join(f"<th>{escape(str(c))}</th>" for c in cols_unique)
        body_rows = []
        for row in result["rows"]:
            tds = []
            for val in row:
                s = str(val)
                if len(s) > 400:
                    s = s[:400] + "…"
                tds.append(f"<td class='small'>{escape(s)}</td>")
            body_rows.append(f"<tr>{''.join(tds)}</tr>")
        body_rows_html = ''.join(body_rows) or '<tr><td class="muted">(no rows)</td></tr>'
        rows_html = f"<table class='table'><thead><tr>{headers}</tr></thead><tbody>{body_rows_html}</tbody></table>"

    return f"""
      <div style='margin-top:10px'>
        <div>{info_html}</div>
        {rows_html}
      </div>
    """

# WebSocket handlers
async def handle_sql_websocket(websocket: WebSocket, project_id: int):
    """Handle basic SQL WebSocket connections."""
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
    # Ensure per-project database exists
    try:
        ensure_project_initialized(project_id)
    except Exception:
        pass
    # Process messages
    while True:
        try:
            msg = await websocket.receive_text()
        except WebSocketDisconnect:
            break
        except Exception:
            break
        if not msg:
            continue
        if msg.strip() == "__CLOSE__":
            break
        payload = None
        try:
            payload = json.loads(msg)
        except Exception:
            payload = {"sql": msg}
        sql_text = (payload.get("sql") if isinstance(payload, dict) else msg) or ""
        try:
            try:
                max_rows = int(payload.get("max_rows", int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200")))) if isinstance(payload, dict) else int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200"))
            except Exception:
                max_rows = 200
            result = _execute_sql(sql_text, project_id, max_rows=max_rows)
            out = {
                "ok": bool(result.get("success")),
                "statement_type": result.get("statement_type"),
                "columns": result.get("columns"),
                "rows": result.get("rows"),
                "rowcount": result.get("rowcount"),
                "truncated": result.get("truncated"),
                "error": None if result.get("success") else result.get("error"),
            }
        except Exception as e:
            out = {"ok": False, "error": str(e)}
        try:
            await websocket.send_text(json.dumps(out))
        except Exception:
            break
    try:
        await websocket.close()
    except Exception:
        pass
