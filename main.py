
import os
import html
import shutil
import mimetypes
import json
import csv
import io
import contextlib
import sqlite3
import math
import builtins
import hashlib
import subprocess
import threading
import asyncio
import uuid
import queue
import signal
import time
import platform
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
from contextvars import ContextVar
import logging as _logging
import time as _time
import builtins as _bi

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, Header, HTTPException, Body, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean,
    UniqueConstraint, JSON, Index, func, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import re

# ----------------------------------------------------------------------------------
# Configuration - Import from cedar_app.config module
# ----------------------------------------------------------------------------------

from cedar_app.config import (
    DATA_DIR,
    DEFAULT_SQLITE_PATH,
    PROJECTS_ROOT,
    REGISTRY_DATABASE_URL,
    LEGACY_UPLOAD_DIR,
    _default_legacy_dir,
    SHELL_API_ENABLED,
    SHELL_API_TOKEN,
    LOGS_DIR,
    SHELL_DEFAULT_WORKDIR,
    UPLOAD_AUTOCHAT_ENABLED,
    HOME_DIR,
)

from main_helpers import _get_redis, _publish_relay_event

# ----------------------------------------------------------------------------------
# Database setup
# - Central registry: global engine
# - Per-project: dynamic engine selected per request/project
# ----------------------------------------------------------------------------------

from cedar_app.db_utils import (
    registry_engine,
    RegistrySessionLocal,
    _project_dirs,
    _ensure_project_storage,
    _get_project_engine,
    get_registry_db,
    get_project_db,
    save_thread_snapshot,
    ensure_project_initialized,
    _migrate_project_files_ai_columns,
    _migrate_thread_messages_columns,
    _migrate_project_langextract_tables,
)
from main_models import Base, Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Setting, Version, ChangelogEntry, SQLUndoLog, Note













# ----------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------

from main_helpers import _ack_store, _register_ack



Base.metadata.create_all(registry_engine)

# Attempt a lightweight migration for existing DBs: add metadata_json if missing (registry only)
# Also add AI columns for LLM classification (ai_title, ai_description, ai_category) on the registry DB.
try:
    with registry_engine.begin() as conn:
        dialect = registry_engine.dialect.name
        has_col = False
        if dialect == "mysql":
            res = conn.exec_driver_sql("SHOW COLUMNS FROM files LIKE 'metadata_json'")
            has_col = res.fetchone() is not None
            if not has_col:
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON NULL")
        elif dialect == "sqlite":
            res = conn.exec_driver_sql("PRAGMA table_info(files)")
            cols = [row[1] for row in res.fetchall()]
            has_col = "metadata_json" in cols
            if not has_col:
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON")
        else:
            # best effort: try adding a JSON column with generic SQL
            conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON")
        # Add AI columns if missing
        try:
            if dialect == "sqlite":
                res2 = conn.exec_driver_sql("PRAGMA table_info(files)")
                cols2 = [row[1] for row in res2.fetchall()]
                if "ai_title" not in cols2:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                if "ai_description" not in cols2:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                if "ai_category" not in cols2:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
                if "ai_processing" not in cols2:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing INTEGER DEFAULT 0")
            elif dialect == "mysql":
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_title VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_category VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_processing TINYINT(1) DEFAULT 0")
            else:
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
                try:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing BOOLEAN DEFAULT 0")
                except Exception:
                    pass
        except Exception:
            pass
except Exception:
    # Ignore migration issues in prototype mode
    pass

# ----------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------

# Import LLM utilities from the dedicated module
from cedar_app.llm_utils import (
    llm_client_config as _llm_client_config,
    llm_classify_file as _llm_classify_file,
    llm_summarize_action as _llm_summarize_action,
    llm_dataset_friendly_name as _llm_dataset_friendly_name,
    snake_case as _snake_case,
    suggest_table_name as _suggest_table_name,
    extract_code_from_markdown as _extract_code_from_markdown,
    tabular_import_via_llm as _tabular_import_via_llm_base,
)

# Import file processing utilities
from cedar_app.file_utils import (
    is_probably_text as _is_probably_text,
    interpret_file,
)

# Import UI utilities
from cedar_app.ui_utils import (
    env_get as _env_get,
    env_set_many as _env_set_many,
    llm_reachability as _llm_reachability,
    llm_reach_ok as _llm_reach_ok,
    llm_reach_reason as _llm_reach_reason,
    is_trivial_math as _is_trivial_math,
    get_client_log_js as _get_client_log_js,
    layout,
)

# Import changelog utilities from the dedicated module
from cedar_app.changelog_utils import (
    record_changelog as _record_changelog_base,
    add_version as _add_version_base
)

# Import route handlers
from cedar_app.api_routes import (
    settings_page as _settings_page,
    settings_save as _settings_save,
    api_model_change as _api_model_change,
    api_chat_ack as _api_chat_ack,
    serve_project_upload as _serve_project_upload,
)

# Import shell utilities
from cedar_app.shell_utils import (
    ShellJob,
    ShellJobManager,
    ShellRunRequest,
    is_local_request as _is_local_request,
    require_shell_enabled_and_auth as _require_shell_enabled_and_auth_base,
    handle_shell_websocket,
    handle_health_websocket,
)

# Import SQL utilities
from cedar_app.utils.sql_utils import (
    _dialect, _safe_identifier, _sql_quote, _table_has_branch_columns,
    _get_pk_columns, _extract_where_clause, _preprocess_sql_branch_aware,
    _execute_sql, _execute_sql_with_undo, _render_sql_result_html,
    handle_sql_websocket
)

# Create shell job manager instance
_shell_job_manager = ShellJobManager(logs_dir=LOGS_DIR, default_workdir=SHELL_DEFAULT_WORKDIR)

# Wrapper for tabular_import_via_llm to pass our local dependencies
def _tabular_import_via_llm(project_id: int, branch_id: int, file_rec: FileEntry, db: Session, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Wrapper to pass our local dependencies to the LLM tabular import function."""
    return _tabular_import_via_llm_base(
        project_id, branch_id, file_rec, db,
        project_dirs_fn=_project_dirs,
        get_project_engine_fn=_get_project_engine,
        Dataset=Dataset,
        options=options
    )


# File utilities are now imported from cedar_app.file_utils

def get_db() -> Session:
    # Backward-compat shim: default DB equals central registry
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


from main_helpers import escape, ensure_main_branch, file_extension_to_type, branch_filter_ids, current_branch
try:
    import cedar_tools as ct
except Exception as e:
    # Allow server to start even if optional cedar_tools modules are not installed
    try:
        print(f"[startup] cedar_tools unavailable: {type(e).__name__}: {e}")
    except Exception:
        pass
    ct = None  # type: ignore


def record_changelog(db: Session, project_id: int, branch_id: int, action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]):
    """Wrapper for record_changelog that passes our local dependencies."""
    return _record_changelog_base(
        db, project_id, branch_id, action, input_payload, output_payload,
        ChangelogEntry=ChangelogEntry,
        llm_summarize_action_fn=_llm_summarize_action
    )

def add_version(db: Session, project_id: int, branch_id: int, table_name: str,
                row_id: int, column_name: str, old_value, new_value):
    """Wrapper for add_version that passes our local dependencies."""
    return _add_version_base(
        db, project_id, branch_id, table_name, row_id, column_name, old_value, new_value,
        Version=Version
    )

# Shell wrapper functions for backwards compatibility
def start_shell_job(script: str, shell_path: Optional[str] = None, trace_x: bool = False, workdir: Optional[str] = None) -> ShellJob:
    """Start a shell job using the job manager."""
    return _shell_job_manager.start_job(script=script, shell_path=shell_path, trace_x=trace_x, workdir=workdir)

def get_shell_job(job_id: str) -> Optional[ShellJob]:
    """Get a shell job by ID."""
    return _shell_job_manager.get_job(job_id)

def require_shell_enabled_and_auth(request: Request, x_api_token: Optional[str] = Header(default=None)):
    """Wrapper for shell auth check with our config."""
    return _require_shell_enabled_and_auth_base(
        request=request, 
        x_api_token=x_api_token,
        shell_enabled=SHELL_API_ENABLED,
        shell_token=SHELL_API_TOKEN
    )











# ----------------------------------------------------------------------------------
# Unified Logging System
# ----------------------------------------------------------------------------------

# Global logging buffers and context
_LOG_BUFFER = deque(maxlen=1000)
_SERVER_LOG_BUFFER = deque(maxlen=1000)
_current_path: ContextVar[str] = ContextVar('current_path', default='')

class CedarBufferHandler(_logging.Handler):
    def emit(self, record: _logging.LogRecord) -> None:  # type: ignore[name-defined]
        try:
            ts = datetime.utcnow().isoformat() + "Z"
            lvl = record.levelname.upper()
            msg = record.getMessage()
            url = ""  # HTTP middleware sets current path for logs during requests
            try:
                url = _current_path.get() or ""
            except Exception:
                url = ""
            loc = f"{record.module}:{record.lineno}"
            origin = f"server:{record.name}"
            _SERVER_LOG_BUFFER.append({
                "ts": ts,
                "level": lvl,
                "host": "127.0.0.1",  # local app
                "origin": origin,
                "url": url,
                "loc": loc,
                "ua": None,
                "message": msg,
                "stack": None,
            })
        except Exception:
            # Never raise from handler
            pass

def _install_unified_logging() -> None:
    try:
        # Attach handler to root and common app servers
        h = CedarBufferHandler()
        h.setLevel(_logging.DEBUG)
        root = _logging.getLogger()
        root.addHandler(h)
        root.setLevel(_logging.DEBUG)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "starlette"):
            lg = _logging.getLogger(name)
            lg.addHandler(h)
            lg.setLevel(_logging.DEBUG)
        # Optionally patch print to also append to buffer (enabled by default; set CEDARPY_PATCH_PRINT=0 to disable)
        if str(os.getenv("CEDARPY_PATCH_PRINT", "1")).strip().lower() not in {"0", "false", "no"}:
            try:
                _orig_print = _bi.print
                def _cedar_print(*args, **kwargs):  # type: ignore[override]
                    try:
                        _orig_print(*args, **kwargs)
                    finally:
                        try:
                            msg = " ".join([str(a) for a in args])
                            loc = None
                            # Best-effort caller info
                            try:
                                import inspect as _inspect
                                fr = _inspect.currentframe()
                                if fr and fr.f_back and fr.f_back.f_back:
                                    co = fr.f_back.f_back.f_code
                                    loc = f"{os.path.basename(co.co_filename)}:{co.co_firstlineno}"
                            except Exception:
                                loc = None
                            _SERVER_LOG_BUFFER.append({
                                "ts": datetime.utcnow().isoformat()+"Z",
                                "level": "INFO",
                                "host": "127.0.0.1",
                                "origin": "server:print",
                                "url": _current_path.get() if _current_path else "",
                                "loc": loc or "print",
                                "ua": None,
                                "message": msg,
                                "stack": None,
                            })
                        except Exception:
                            pass
                _bi.print = _cedar_print  # type: ignore[assignment]
            except Exception:
                pass
    except Exception:
        pass

# Install unified logging immediately
_install_unified_logging()

# ----------------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------------

app = FastAPI(title="Cedar")

# Include route modules extracted under cedar_app/routes
try:
    from cedar_app.routes.main_routes import router as _main_routes
    app.include_router(_main_routes)
    print("[startup] main_routes mounted: '/' and '/projects'")
except Exception as e:
    print(f"[startup] Could not mount main_routes: {type(e).__name__}: {e}")

# Removed: cedar_app.routes.project_routes (stub) - real project routes are in routes/app_routes.py
# This stub was shadowing the full implementation

try:
    from cedar_app.routes.log_routes import router as _log_routes
    app.include_router(_log_routes, prefix="/log")
    print("[startup] log_routes mounted at '/log'")
except Exception as e:
    print(f"[startup] Could not mount log_routes: {type(e).__name__}: {e}")

try:
    from cedar_app.routes.shell_routes import router as _shell_routes
    app.include_router(_shell_routes, prefix="/shell")
    print("[startup] shell_routes mounted at '/shell'")
except Exception as e:
    print(f"[startup] Could not mount shell_routes: {type(e).__name__}: {e}")

# Mount the main app_routes router (contains /api/client-log, /projects/create, /project/{id}, etc.)
try:
    from routes.app_routes import router as _app_routes
    app.include_router(_app_routes)
    print("[startup] app_routes mounted (includes /api/client-log, /projects/create, /project, /merge)")
except Exception as e:
    print(f"[startup] Could not mount app_routes: {type(e).__name__}: {e}")

# Mount legacy uploads directory (static files)
try:
    from fastapi.staticfiles import StaticFiles
    from cedar_app.config import LEGACY_UPLOAD_DIR, _default_legacy_dir
    if os.path.isdir(LEGACY_UPLOAD_DIR):
        app.mount("/uploads-legacy", StaticFiles(directory=LEGACY_UPLOAD_DIR), name="uploads_legacy")
        print(f"[cedarpy] Mounted /uploads-legacy from {LEGACY_UPLOAD_DIR}")
    else:
        if LEGACY_UPLOAD_DIR == _default_legacy_dir:
            os.makedirs(LEGACY_UPLOAD_DIR, exist_ok=True)
            app.mount("/uploads-legacy", StaticFiles(directory=LEGACY_UPLOAD_DIR), name="uploads_legacy")
            print(f"[cedarpy] Created and mounted /uploads-legacy at {LEGACY_UPLOAD_DIR}")
        else:
            print(f"[cedarpy] Skipping /uploads-legacy mount; directory does not exist: {LEGACY_UPLOAD_DIR}")
except Exception as e:
    print(f"[cedarpy] Skipping /uploads-legacy mount due to error: {e}")

# Add error logging middleware
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        import traceback
        print(f"[ERROR-MIDDLEWARE] Unhandled exception on {request.method} {request.url.path}")
        print(f"[ERROR-MIDDLEWARE] Exception: {e}")
        traceback.print_exc()
        # Re-raise to let FastAPI handle it
        raise

# Register HTTP middleware for request logs
@app.middleware("http")
async def _cedar_logging_mw(request: Request, call_next):
    path = str(getattr(request, "url", "") or "")
    token = None
    try:
        token = _current_path.set(path)
    except Exception:
        token = None
    start = _time.time()
    try:
        _logging.getLogger("cedarpy").debug(f"request.start {request.method} {request.url.path}")
        resp = await call_next(request)
        dur_ms = int((_time.time() - start) * 1000)
        _logging.getLogger("cedarpy").debug(f"request.end {request.method} {request.url.path} status={getattr(resp,'status_code',None)} dur_ms={dur_ms}")
        return resp
    except Exception as e:
        dur_ms = int((_time.time() - start) * 1000)
        _logging.getLogger("cedarpy").exception(f"request.error {request.method} {request.url.path} dur_ms={dur_ms} error={type(e).__name__}: {e}")
        raise
    finally:
        try:
            if token is not None:
                _current_path.reset(token)
        except Exception:
            pass

# Register file upload routes
try:
    from cedar_app.file_upload_handler import register_file_upload_routes
    register_file_upload_routes(app)
    print("[startup] File upload routes registered")
except Exception as e:
    print(f"[startup] Could not register file upload routes: {e}")

# Register WebSocket routes using new thinker-orchestrator flow
try:
    from cedar_orchestrator.ws_chat import register_ws_chat, WSDeps
    print("[startup] Using new thinker-orchestrator WebSocket flow")
    from main_helpers import _publish_relay_event as __pub, _register_ack as __ack
    deps = WSDeps(
        get_project_engine=_get_project_engine,
        ensure_project_initialized=ensure_project_initialized,
        record_changelog=record_changelog,
        llm_client_config=_llm_client_config,
        tabular_import_via_llm=_tabular_import_via_llm,
        # Optional deps (execute_sql, exec_img, llm_summarize_action) are intentionally omitted here
        # because they may not be defined at import time. The WS orchestrator handles their absence.
        RegistrySessionLocal=RegistrySessionLocal,
        FileEntry=FileEntry,
        Dataset=Dataset,
        Thread=Thread,
        ThreadMessage=ThreadMessage,
        Note=Note,
        Branch=Branch,
        ChangelogEntry=ChangelogEntry,
        branch_filter_ids=branch_filter_ids,
        current_branch=current_branch,
        file_extension_to_type=file_extension_to_type,
        publish_relay_event=__pub,
        register_ack=__ack,
        project_dirs=_project_dirs,
        save_thread_snapshot=save_thread_snapshot,
    )
    # Register canonical route using extracted orchestrator
    register_ws_chat(app, deps, route_path="/ws/chat/{project_id}")
    print("[startup] Registered /ws/chat from cedar_orchestrator module")
except Exception as e:
    print(f"[startup] Could not register /ws/chat: {type(e).__name__}: {e}")
    pass

# Legacy stub registration removed - using new thinker-orchestrator flow only

# WS ack handshake endpoint (must be defined after `app` is created)
# See README: "WebSocket handshake and client acks"

# Import SQL routes
from cedar_app.routes import sql_routes

# Register Agents route (dynamically pulls actual prompts from agent implementations)
try:
    from cedar_app.routes.agents_route import register_agents_route as _register_agents_route
    _register_agents_route(app)
    print("[startup] Agents route registered")
except Exception as e:
    print(f"[startup] FATAL: Could not register agents route: {e}")
    import traceback
    traceback.print_exc()
    raise RuntimeError(f"Agents route registration failed: {e}") from e

# Register Chat API routes
try:
    from cedar_app.routes.chat_api import register_chat_api_routes
    register_chat_api_routes(app)
    print("[startup] Chat API routes registered")
except Exception as e:
    print(f"[startup] Could not register chat API routes: {e}")

@app.on_event("startup")
def _cedarpy_startup_llm_probe():
    try:
        ok, reason, model = _llm_reachability(ttl_seconds=0, llm_client_config_fn=_llm_client_config)
        if ok:
            print(f"[startup] LLM ready (model={model})")
        else:
            print(f"[startup] LLM unavailable ({reason})")
    except Exception:
        pass

# Layout is now imported from ui_utils



class ClientLogEntry(BaseModel):
    when: Optional[str] = None
    level: str
    message: str
    url: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    stack: Optional[str] = None
    userAgent: Optional[str] = None
    origin: Optional[str] = None

def execute_sql(project_id: int, request: Request, sql: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # resolve current project and branch
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")

    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()

    # Support branch context for links back to Files/Threads views
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current = current_branch(db, project.id, branch_id)

    # Prepare standard lists for the page
    show_branch_ids = branch_filter_ids(db, project.id, current.id)
    files = db.query(FileEntry) \
        .filter(FileEntry.project_id == project.id, FileEntry.branch_id.in_(show_branch_ids)) \
        .order_by(FileEntry.created_at.desc()) \
        .all()
    threads = db.query(Thread) \
        .filter(Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids)) \
        .order_by(Thread.created_at.desc()) \
        .all()
    datasets = db.query(Dataset) \
        .filter(Dataset.project_id == project.id, Dataset.branch_id.in_(show_branch_ids)) \
        .order_by(Dataset.created_at.desc()) \
        .all()

    # Execute SQL with branch-aware preprocessing by default
    try:
        max_rows = int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200"))
    except Exception:
        max_rows = 200
    with _get_project_engine(project.id).begin() as conn:
        main = db.query(Branch).filter(Branch.project_id == project.id, Branch.name == "Main").first()
        transformed_sql, transformed = _preprocess_sql_branch_aware(conn, sql, project.id, current.id, main.id)
    result = _execute_sql_with_undo(db, transformed_sql, project.id, current.id, max_rows=max_rows)
    sql_block = _render_sql_result_html(result)

    # Changelog entry for this SQL action
    try:
        input_payload = {"sql": sql, "transformed_sql": transformed_sql}
        output_payload = {k: v for k, v in result.items() if k not in ("rows",)}
        record_changelog(db, project.id, current.id, "sql.execute", input_payload, output_payload)
    except Exception:
        pass

    # Fetch recent notes for left-pane Notes tab (roll-up across visible branches)
    try:
        notes = db.query(Note).filter(Note.project_id == project.id, Note.branch_id.in_(show_branch_ids)).order_by(Note.created_at.desc()).limit(200).all()
    except Exception:
        notes = []

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, selected_file=None, msg="Per-project database is active", sql_result_block=sql_block, notes=notes))

# _render_sql_result_html moved to sql_utils.py


# _extract_where_clause moved to sql_utils.py


# _execute_sql moved to sql_utils.py


# _execute_sql_with_undo moved to sql_utils.py

def merge_index_html(projects: List[Project]) -> str:
    rows = []
    for p in projects:
        rows.append(f"<tr><td>{escape(p.title)}</td><td><a class='pill' href='/merge/{p.id}'>Open</a></td></tr>")
    body = f"""
      <h1>Merge</h1>
      <div class='card' style='max-width:720px'>
        <h3>Projects</h3>
        <table class='table'>
          <thead><tr><th>Title</th><th>Actions</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="2" class="muted">No projects yet.</td></tr>'}</tbody>
        </table>
      </div>
    """
    return body


# _hash_payload moved to utils/project_management.py
from cedar_app.utils.project_management import _hash_payload


def get_or_create_project_registry(db: Session, title: str) -> Project:
    """Idempotent create by title.
    - SQLite: use INSERT .. ON CONFLICT DO NOTHING, then SELECT
    - Fallback: SELECT first, else create
    """
    t = (title or "").strip()
    if not t:
        raise ValueError("empty title")
    # Try SQLite upsert
    try:
        if registry_engine.dialect.name == "sqlite":
            try:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # type: ignore
            except Exception:
                sqlite_insert = None  # type: ignore
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


@app.post("/project/{project_id}/threads/create")
@app.get("/project/{project_id}/threads/new")
# LLM chat uses threads. If using the GET '/threads/new', a default title 'New Thread' is created
# and the user is redirected to the project page focusing the new tab. See README for LLM setup.
def create_thread(project_id: int, request: Request, title: Optional[str] = Form(None)):
    ensure_project_initialized(project_id)
    
    # Get project database session
    eng = _get_project_engine(project_id)
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    
    try:
        # branch selected via query parameter
        branch_id = request.query_params.get("branch_id")
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    file_q = request.query_params.get("file_id")
    dataset_q = request.query_params.get("dataset_id")
    json_q = request.query_params.get("json")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

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
            label = (file_obj.ai_title or file_obj.display_name or '').strip() or f"File {file_obj.id}"
            title = f"File: {label}"
        elif dataset_obj:
            title = f"DB: {dataset_obj.name}"
        else:
            title = "New Thread"
    title = (title or "New Thread").strip()

    t = Thread(project_id=project.id, branch_id=branch.id, title=title)
    db.add(t)
    db.commit()
    db.refresh(t)
    # Version tracking disabled for now - needs proper implementation

    redirect_url = f"/project/{project.id}?branch_id={branch.id}&thread_id={t.id}" + (f"&file_id={file_obj.id}" if file_obj else "") + (f"&dataset_id={dataset_obj.id}" if dataset_obj else "") + "&msg=Thread+created"

    try:
        # Optional JSON response for client-side creation
        if json_q is not None and str(json_q).strip() not in {"", "0", "false", "False", "no"}:
            return JSONResponse({"thread_id": t.id, "branch_id": branch.id, "redirect": redirect_url, "title": t.title})

        # Redirect to focus the newly created thread
        return RedirectResponse(redirect_url, status_code=303)
    finally:
        db.close()


