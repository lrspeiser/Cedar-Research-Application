
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

# Changelog utilities removed - focusing on WebSocket chat only

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
import cedar_tools as ct


def record_changelog(db: Session, project_id: int, branch_id: int, action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]):
    """Stub for record_changelog - changelog functionality removed."""
    pass  # Changelog disabled - focusing on WebSocket chat only

def add_version(db: Session, project_id: int, branch_id: int, table_name: str,
                row_id: int, column_name: str, old_value, new_value):
    """Stub for add_version - changelog functionality removed."""
    pass  # Changelog disabled - focusing on WebSocket chat only

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
# FastAPI app
# ----------------------------------------------------------------------------------

app = FastAPI(title="Cedar")

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

# Register Agents route
try:
    from cedar_app.routes.agents_route import register_agents_route
    register_agents_route(app)
    print("[startup] Agents route registered")
except Exception as e:
    print(f"[startup] Could not register agents route: {e}")

# Register Chat API routes
try:
    from cedar_app.routes.chat_api import register_chat_api_routes
    register_chat_api_routes(app)
    print("[startup] Chat API routes registered")
except Exception as e:
    print(f"[startup] Could not register chat API routes: {e}")

@app.post("/api/chat/ack")
def api_chat_ack(payload: Dict[str, Any]):
    return _api_chat_ack(payload=payload, ack_store=_ack_store)

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



@app.get("/", response_class=HTMLResponse)
def home(request: Request, msg: Optional[str] = None, db: Session = Depends(get_registry_db)):
    """Home page showing list of all projects."""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return layout("Cedar", projects_list_html(projects, msg=msg), header_label="All Projects")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(msg: Optional[str] = None):
    return _settings_page(
        msg=msg,
        env_get_fn=_env_get,
        llm_reach_ok_fn=_llm_reach_ok,
        llm_reach_reason_fn=_llm_reach_reason,
        layout_fn=layout,
        data_dir=DATA_DIR,
        llm_client_config_fn=_llm_client_config
    )


@app.post("/settings/save")
def settings_save(openai_key: str = Form(""), model: str = Form("")):
    return _settings_save(
        openai_key=openai_key,
        model=model,
        env_set_many_fn=_env_set_many
    )

@app.post("/api/model/change")
def api_model_change(payload: Dict[str, Any]):
    """API endpoint to change the LLM model from the dropdown"""
    return _api_model_change(
        payload=payload,
        env_set_many_fn=_env_set_many
    )

# Serve uploaded files for convenience
# Serve uploaded files (legacy path no longer used). We mount a dynamic per-project files app below.
# See PROJECT_SEPARATION_README.md
# Keep legacy mount to avoid 404s for older links; it will contain only migrated symlinks if created.
# Be resilient: only mount if the directory exists; if using the default path, create it lazily.
try:
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


@app.get("/uploads/{project_id}/{path:path}")
def serve_project_upload(project_id: int, path: str):
    return _serve_project_upload(
        project_id=project_id,
        path=path,
        project_dirs_fn=_project_dirs
    )

# ----------------------------------------------------------------------------------
# HTML helpers (all inline; no external templates)
# ----------------------------------------------------------------------------------

# Note: env_get, env_set_many, llm_reachability and layout are now imported from ui_utils




    # Inject a lightweight client logging hook so console messages and JS errors are POSTed to the server.
    # See README.md (section "Client-side logging") for details and troubleshooting.
    client_log_js = """
<script>
(function(){
  if (window.__cedarpyClientLogInitialized) return; window.__cedarpyClientLogInitialized = true;
  const endpoint = '/api/client-log';
  function post(payload){
    try {
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], {type: 'application/json'});
        navigator.sendBeacon(endpoint, blob);
        return;
      }
      fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body, keepalive: true}).catch(function(){});
    } catch(e) {}
  }
  function base(level, message, origin, extra){
    post(Object.assign({
      when: new Date().toISOString(),
      level: String(level||'info'),
      message: String(message||''),
      url: String(location.href||''),
      userAgent: navigator.userAgent || '',
      origin: origin || 'console'
    }, extra||{}));
  }
  var orig = { log: console.log, info: console.info, warn: console.warn, error: console.error };
  console.log = function(){ try { base('info', Array.from(arguments).join(' '), 'console.log'); } catch(e){}; return orig.log.apply(console, arguments); };
  console.info = function(){ try { base('info', Array.from(arguments).join(' '), 'console.info'); } catch(e){}; return orig.info.apply(console, arguments); };
  console.warn = function(){ try { base('warn', Array.from(arguments).join(' '), 'console.warn'); } catch(e){}; return orig.warn.apply(console, arguments); };
  console.error = function(){ try { base('error', Array.from(arguments).join(' '), 'console.error'); } catch(e){}; return orig.error.apply(console, arguments); };
  window.addEventListener('error', function(ev){
    try { base('error', ev.message || 'window.onerror', 'window.onerror', { line: ev.lineno||null, column: ev.colno||null, stack: ev.error && ev.error.stack ? String(ev.error.stack) : null }); } catch(e){}
  }, true);
  window.addEventListener('unhandledrejection', function(ev){
    try { var r = ev && ev.reason; base('error', (r && (r.message || r.toString())) || 'unhandledrejection', 'unhandledrejection', { stack: r && r.stack ? String(r.stack) : null }); } catch(e){}
  });
  // Client-side upload UI instrumentation (logs to console -> forwarded to /api/client-log). See README: Client-side logging.
  document.addEventListener('DOMContentLoaded', function(){
    try {
      // Typing indicator for Ask form
      try {
        var askForm = document.getElementById('askForm');
        if (askForm) {
          askForm.addEventListener('submit', function(){
            try {
              var msgs = document.getElementById('msgs');
              if (!msgs) return;
              var d = document.createElement('div');
              d.className = 'small typing';
              d.id = 'typingIndicator';
              d.innerHTML = "<span class='pill'>assistant</span> Thinking <span class='dots'><span>.</span><span>.</span><span>.</span></span>";
              msgs.appendChild(d);
            } catch(e) { try { console.error('[ui] typing indicator error', e); } catch(_) {} }
          });
        }
      } catch(e) {}

      var form = document.querySelector('[data-testid=upload-form]');
      var input = document.querySelector('[data-testid=upload-input]');
      var button = document.querySelector('[data-testid=upload-submit]');
      function setUploadingState(){
        try {
          if (!button) return;
          // Preserve original text for potential future restore (not used currently)
          if (!button.getAttribute('data-original-text')) {
            button.setAttribute('data-original-text', button.textContent || 'Upload');
          }
          button.disabled = true;
          button.setAttribute('aria-busy', 'true');
          button.innerHTML = "<span class='spinner' style=\"margin-right:6px\"></span> Uploading…";
        } catch(e) { try { console.error('[ui] setUploadingState error', e); } catch(_) {} }
      }
      if (input) {
        input.addEventListener('click', function(){ console.log('[ui] upload input clicked'); });
        input.addEventListener('change', function(ev){
          try {
            var f = (ev && ev.target && ev.target.files && ev.target.files[0]) || null;
            var name = f ? f.name : '(none)';
            var size = f ? String(f.size) : '';
            console.log('[ui] file selected', name, size);
            // Auto-open the right Upload tab so the submit stays visible/testable
            try {
              var upTab = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-upload']");
              if (upTab) { upTab.click(); }
              // Fallback: force-activate Upload panel/tabs to ensure the submit button is visible in headless tests
              try {
                var panels = document.querySelectorAll(".pane.right .tab-panels .panel");
                panels.forEach(function(p){ p.classList.add('hidden'); });
                var upPanel = document.getElementById('right-upload');
                if (upPanel) { upPanel.classList.remove('hidden'); upPanel.style.display='block'; }
                var tabs = document.querySelectorAll(".tabs[data-pane='right'] .tab");
                tabs.forEach(function(t){ t.classList.remove('active'); });
                var upTab2 = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-upload']"); if (upTab2) upTab2.classList.add('active');
                // Retry once on the next tick in case tab handlers were not ready yet
                setTimeout(function(){
                  try {
                    var panels2 = document.querySelectorAll(".pane.right .tab-panels .panel");
                    panels2.forEach(function(p){ p.classList.add('hidden'); });
                    var upPanel2 = document.getElementById('right-upload');
                    if (upPanel2) { upPanel2.classList.remove('hidden'); upPanel2.style.display='block'; }
                    var tabs2 = document.querySelectorAll(".tabs[data-pane='right'] .tab");
                    tabs2.forEach(function(t){ t.classList.remove('active'); });
                    var upTab3 = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-upload']"); if (upTab3) upTab3.classList.add('active');
                  } catch(_) {}
                }, 0);
              } catch(_) {}
            } catch(_) {}
          } catch(e) { console.error('[ui] file select error', e); }
        });
      }
      if (button) {
        button.addEventListener('click', function(){
          console.log('[ui] upload clicked');
          try {
            if (input && input.files && input.files.length > 0) { setUploadingState(); }
          } catch(e) {}
        });
      }
      if (form) {
        form.addEventListener('submit', function(){
          console.log('[ui] upload submit');
          // Only fires if required fields are satisfied; safe to show uploading state now.
          setUploadingState();
        });
      }
      // After a successful upload redirect (?msg=File+uploaded), auto-switch to the Files panel so the Files heading is visible
      try {
        var sp = new URLSearchParams(location.search || '');
        var msg = sp.get('msg');
  var decoded = msg ? msg.replace(/\\+/g, ' ') : '';
        if (decoded === 'File uploaded') {
          var panelsFx = document.querySelectorAll(".pane.right .tab-panels .panel");
          panelsFx.forEach(function(p){ p.classList.add('hidden'); });
          var filesPanel = document.getElementById('right-files'); if (filesPanel) filesPanel.classList.remove('hidden');
          var tabsFx = document.querySelectorAll(".tabs[data-pane='right'] .tab");
          tabsFx.forEach(function(t){ t.classList.remove('active'); });
          var filesTab = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-files']"); if (filesTab) filesTab.classList.add('active');
        }
      } catch(_) {}

      // Safety net: if a file is already selected via automation, ensure the Upload tab becomes visible soon after
      try {
        var _tries = 20;
        var _iv = setInterval(function(){
          try {
            if (_tries-- <= 0) { clearInterval(_iv); return; }
            var inp = document.querySelector('[data-testid=upload-input]');
            if (inp && inp.files && inp.files.length > 0) {
              var panels = document.querySelectorAll(".pane.right .tab-panels .panel");
              panels.forEach(function(p){ p.classList.add('hidden'); });
              var upPanel = document.getElementById('right-upload');
              if (upPanel) { upPanel.classList.remove('hidden'); upPanel.style.display='block'; }
              var tabs = document.querySelectorAll(".tabs[data-pane='right'] .tab");
              tabs.forEach(function(t){ t.classList.remove('active'); });
              var upTab = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-upload']");
              if (upTab) upTab.classList.add('active');
              clearInterval(_iv);
            }
          } catch(_) {}
        }, 100);
      } catch(_) {}
    } catch(e) {
      try { base('error', 'upload instrumentation error', 'client-log', { stack: e && e.stack ? String(e.stack) : null }); } catch(_) {}
    }
  }, { once: true });

  // Global button click feedback: show a brief 'Received' toast near the clicked button (no-op for non-buttons)
  (function initButtonClickFeedback(){
    try {
      function showReceived(btn){
        try {
          var t = document.createElement('div');
          t.className = 'click-received';
          t.textContent = 'Received';
          document.body.appendChild(t);
          var r = btn.getBoundingClientRect();
          var tw = t.offsetWidth || 60;
          var th = t.offsetHeight || 18;
          var left = Math.max(6, Math.min((window.innerWidth - tw - 6), r.left + (r.width/2) - (tw/2)));
          var top = Math.max(6, Math.min((window.innerHeight - th - 6), r.bottom + 6));
          t.style.left = left + 'px';
          t.style.top = top + 'px';
          setTimeout(function(){ if (t && t.parentNode) { t.parentNode.removeChild(t); } }, 1300);
          // Screen reader announcement
          try {
            var sr = document.getElementById('sr-live');
            if (!sr) {
              sr = document.createElement('div');
              sr.id = 'sr-live';
              sr.setAttribute('aria-live', 'polite');
              sr.style.position = 'absolute'; sr.style.width='1px'; sr.style.height='1px'; sr.style.overflow='hidden'; sr.style.clip='rect(1px,1px,1px,1px)'; sr.style.clipPath='inset(50%)'; sr.style.whiteSpace='nowrap'; sr.style.border='0';
              document.body.appendChild(sr);
            }
            sr.textContent = 'Received';
          } catch(_) {}
        } catch(_) {}
      }
      document.addEventListener('click', function(ev){
        try {
          var el = ev.target && ev.target.closest ? ev.target.closest('button') : null;
          if (!el) return;
          // Buttons already get a press animation via CSS :active; add a toast as confirmation
          showReceived(el);
        } catch(_) {}
      }, true);
    } catch(_) {}
  })();

})();
</script>
"""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ --fg: #111; --bg: #fff; --accent: #2563eb; --muted: #6b7280; --border: #e5e7eb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Oxygen, Ubuntu, Cantarell, \"Helvetica Neue\", Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; color: var(--fg); background: var(--bg); }}
    header {{ padding: 16px 20px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); }}
    main {{ padding: 20px; margin: 0; width: 100%; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .card {{ border: 1px solid var(--border); border-radius: 8px; padding: 16px; background: #fff; flex: 1 1 340px; }}
    .muted {{ color: var(--muted); }}
    .table {{ width: 100%; border-collapse: collapse; }}
    .table th, .table td {{ border-bottom: 1px solid var(--border); padding: 8px 6px; text-align: left; vertical-align: top; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef2ff; color: #3730a3; font-size: 12px; }}
    form.inline * {{ vertical-align: middle; }}
    input[type=\"text\"], select {{ padding: 8px; border: 1px solid var(--border); border-radius: 6px; width: 100%; }}
    input[type=\"file\"] {{ padding: 6px; border: 1px dashed var(--border); border-radius: 6px; width: 100%; position: relative; z-index: 1; display: block; }}
    button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--accent); color: white; cursor: pointer; position: relative; z-index: 2; pointer-events: auto; transition: transform 80ms ease, filter 120ms ease, box-shadow 120ms ease; will-change: transform; user-select: none; }}
    button:active {{ transform: scale(0.98); filter: brightness(0.98); }}
    button.secondary {{ background: #f3f4f6; color: #111; }}
    .small {{ font-size: 12px; }}
    .topbar {{ display:flex; align-items:center; gap:12px; }}
    .spinner {{ display:inline-block; width:12px; height:12px; border:2px solid #cbd5e1; border-top-color:#334155; border-radius:50%; animation: spin 1s linear infinite; }}
    @keyframes spin {{ from {{ transform: rotate(0deg);}} to {{ transform: rotate(360deg);}} }}

    /* Two-column layout and tabs */
.two-col {{ display: grid; grid-template-columns: 1fr 420px; gap: 16px; align-items: start; }}
    .pane {{ display: flex; flex-direction: column; gap: 8px; }}
    .pane.right {{ display:flex; flex-direction:column; min-height:0; }}
    .pane.right .tab-panels {{ display:flex; flex-direction:column; flex:1; min-height:0; overflow:auto; }}
    .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); }}
    .tab {{ display:inline-block; padding:6px 10px; border:1px solid var(--border); border-bottom:none; border-radius:6px 6px 0 0; background:#f3f4f6; color:#111; cursor:pointer; user-select:none; }}
    .tab.active {{ background:#fff; font-weight:600; }}
    .tab-panels {{ border:1px solid var(--border); border-radius:0 6px 6px 6px; background:#fff; padding:12px; }}
    .panel.hidden {{ display:none !important; }}
    @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    /* Typing indicator */
    .typing {{ color: var(--muted); font-style: italic; }}
    .dots span {{ display:inline-block; opacity: 0; animation: blink 1.2s infinite; }}
    .dots span:nth-child(1) {{ animation-delay: 0s; }}
    .dots span:nth-child(2) {{ animation-delay: 0.2s; }}
    .dots span:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes blink {{ 0%, 20% {{ opacity: 0; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0; }} }}
    /* Click feedback toast */
    .click-received {{ position: fixed; background: #f1f5f9; color: #111; border: 1px solid var(--border); border-radius: 9999px; padding: 2px 8px; font-size: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); pointer-events: none; opacity: 0; transform: translateY(-4px); animation: crFade 1200ms ease forwards; }}
    @keyframes crFade {{ 0% {{ opacity: 0; transform: translateY(-4px); }} 15% {{ opacity: 1; transform: translateY(0); }} 85% {{ opacity: 1; }} 100% {{ opacity: 0; transform: translateY(-6px); }} }}
  </style>
  {client_log_js}
  <script>
  (function(){{
    function activateTab(tab) {{
      try {{
        var pane = tab.closest('.pane') || document;
        var tabs = tab.parentElement.querySelectorAll('.tab');
        tabs.forEach(function(t){{ t.classList.remove('active'); }});
        tab.classList.add('active');
        var target = tab.getAttribute('data-target');
        if (!target) return;
        var panelsRoot = pane.querySelector('.tab-panels');
        if (!panelsRoot) return;
        panelsRoot.querySelectorAll('.panel').forEach(function(p){{ p.classList.add('hidden'); }});
        var el = pane.querySelector('#' + target);
        if (el) el.classList.remove('hidden');
      }} catch(e) {{ try {{ console.error('[ui] tab error', e); }} catch(_) {{}} }}
    }}
    function initTabs(){{
      document.querySelectorAll('.tabs .tab').forEach(function(tab){{
        tab.addEventListener('click', function(ev){{ ev.preventDefault(); activateTab(tab); }});
      }});
    }}
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', initTabs, {{ once: true }});
    }} else {{
      initTabs();
    }}
  }})();
  </script>
</head>
<body>
  <header>
    <div class="topbar">
      <div><strong>Cedar</strong> <span class='muted'>•</span> {header_info}</div>
      <div style=\"margin-left:auto\">{nav_html}{llm_status}</div>
    </div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""
    # Render header status
    try:
        html_doc = html_doc.format(llm_status=llm_status, header_info=header_html, nav_html=nav_html)
    except Exception:
        pass
    return HTMLResponse(html_doc)


# Moved to utils/page_rendering.py
from cedar_app.utils.page_rendering import projects_list_html
from cedar_app.utils.page_rendering import project_page_html

# Import extracted functions
from cedar_app.utils.file_upload import serve_project_upload as _serve_project_upload_impl, upload_file as _upload_file_impl
from cedar_app.utils.sql_websocket import ws_sqlx as _ws_sqlx_impl
from cedar_app.utils.test_tools import api_test_tool_exec as _api_test_tool_exec_impl



@app.post("/api/shell/run")
def api_shell_run(request: Request, body: ShellRunRequest, x_api_token: Optional[str] = Header(default=None)):
    require_shell_enabled_and_auth(request, x_api_token)
    script = body.script
    shell_path = body.shell_path
    trace_x = bool(body.trace_x) if body.trace_x is not None else False
    # Resolve working directory
    workdir_eff = None
    try:
        if body.workdir and isinstance(body.workdir, str) and body.workdir.strip():
            workdir_eff = os.path.abspath(os.path.expanduser(body.workdir.strip()))
        else:
            mode = (body.workdir_mode or "data").strip().lower()
            if mode == "root":
                workdir_eff = "/"
            else:
                workdir_eff = SHELL_DEFAULT_WORKDIR
    except Exception:
        workdir_eff = SHELL_DEFAULT_WORKDIR
    # Server-side trace for UI clicks
    try:
        host = request.client.host if request and request.client else "?"
        cookie_tok = request.cookies.get("Cedar-Shell-Token") if hasattr(request, "cookies") else None
        tok_src = "hdr" if x_api_token else ("cookie" if cookie_tok else "no")
        print(f"[shell-api] RUN click from={host} token={tok_src} shell_path={(shell_path or os.environ.get('SHELL') or '')} script_len={len(script or '')} trace_x={trace_x} workdir={workdir_eff}")
    except Exception:
        pass
    if not script or not isinstance(script, str):
        raise HTTPException(status_code=400, detail="script is required")
    job = start_shell_job(script=script, shell_path=shell_path, trace_x=trace_x, workdir=workdir_eff)
    pid = job.proc.pid if job.proc else None
    try:
        print(f"[shell-api] job started id={job.id} pid={pid}")
    except Exception:
        pass
    return {"job_id": job.id, "pid": pid, "started_at": job.start_time.isoformat() + "Z"}


# WebSocket streaming endpoint
@app.websocket("/ws/shell/{job_id}")
async def ws_shell(websocket: WebSocket, job_id: str):
    """Handle WebSocket for shell job output streaming."""
    await handle_shell_websocket(
        websocket=websocket,
        job_id=job_id,
        job_manager=_shell_job_manager,
        shell_enabled=SHELL_API_ENABLED,
        shell_token=SHELL_API_TOKEN
    )

# WebSocket health/handshake endpoint
@app.websocket("/ws/health")
async def ws_health(websocket: WebSocket):
    """Handle WebSocket health check."""
    await handle_health_websocket(
        websocket=websocket,
        shell_enabled=SHELL_API_ENABLED,
        shell_token=SHELL_API_TOKEN
    )
# SQL WebSocket handler - delegated to sql_utils module
@app.websocket("/ws/sql/{project_id}")
async def ws_sql(websocket: WebSocket, project_id: int):
    await handle_sql_websocket(websocket, project_id)

# WebSocket SQL with undo and branch context
# Message format:
#  - { "action": "exec", "sql": "...", "branch_id": 2 | null, "branch_name": "Main" | null, "max_rows": 200 }
#  - { "action": "undo_last", "branch_id": 2 | null, "branch_name": "Main" | null }

# Import ClientLogEntry for the client-log endpoint
from cedar_app.utils.logging import ClientLogEntry, _LOG_BUFFER

@app.post("/api/client-log")
def api_client_log(entry: ClientLogEntry, request: Request):
    # Keep the legacy in-memory buffer approach for compatibility
    host = (request.client.host if request and request.client else "?")
    ts = entry.when or datetime.utcnow().isoformat() + "Z"
    lvl = (entry.level or "info").upper()
    url = entry.url or ""
    lc = f"{entry.line or ''}:{entry.column or ''}" if (entry.line or entry.column) else ""
    ua = entry.userAgent or ""
    origin = entry.origin or "client"
    # Append to unified in-memory buffer for viewing in /log
    try:
        _LOG_BUFFER.append({
            "ts": ts,
            "level": lvl,
            "host": host,
            "origin": origin,
            "url": url,
            "loc": lc,
            "ua": ua,
            "message": entry.message,
            "stack": entry.stack or None,
        })
    except Exception:
        pass
    try:
        # This print will also be captured by the unified print patch if enabled.
        print(f"[client-log] ts={ts} level={lvl} host={host} origin={origin} url={url} loc={lc} ua={ua} msg={entry.message}")
        if entry.stack:
            print("[client-log-stack] " + str(entry.stack))
    except Exception:
        pass
    return {"ok": True}

# Cancellation summary API
# Submits a special prompt to produce a user-facing summary when a chat is cancelled.
# See README: Chat cancellation and run summaries.
@app.post("/api/chat/cancel-summary")
def api_chat_cancel_summary(payload: Dict[str, Any] = Body(...)):
    from cedar_app.utils.thread_management import api_chat_cancel_summary as _api_chat_cancel_summary
    return _api_chat_cancel_summary(app, payload)

# -------------------- Merge to Main (SQLite-first implementation) --------------------

@app.post("/project/{project_id}/merge_to_main")
def merge_to_main(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    from cedar_app.utils.project_management import merge_to_main as _merge_to_main
    return _merge_to_main(app, project_id, request, db)

# -------------------- Delete all files in branch --------------------

@app.post("/project/{project_id}/files/delete_all")
def delete_all_files(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    from cedar_app.utils.project_management import delete_all_files as _delete_all_files
    return _delete_all_files(app, project_id, request, db)

# -------------------- Make existing table branch-aware (SQLite) --------------------

@app.post("/project/{project_id}/sql/make_branch_aware")
def make_table_branch_aware(project_id: int, request: Request, table: str = Form(...), db: Session = Depends(get_project_db)):
    """Make table branch-aware. Delegates to extracted module."""
    return make_table_branch_aware_impl(project_id, request, table, db)
@app.post("/project/{project_id}/delete")
def delete_project(project_id: int, db: Session = Depends(get_registry_db)):
    """Delete a project and all its associated data."""
    from cedar_app.utils.project_management import delete_project as _delete_project
    return _delete_project(app, project_id)

# -------------------- Undo last SQL --------------------

@app.post("/project/{project_id}/sql/undo_last")
def undo_last_sql(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    """Undo last SQL operation. Delegates to extracted module."""
    return undo_last_sql_impl(project_id, request, db)
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

@app.get("/api/threads/list")
def api_threads_list(project_id: int, branch_id: Optional[int] = None):
    from cedar_app.utils.thread_management import api_threads_list as _api_threads_list
    return _api_threads_list(app, project_id, branch_id)

@app.get("/api/threads/session/{thread_id}")
def api_threads_session(thread_id: int, project_id: int):
    from cedar_app.utils.thread_management import api_threads_session as _api_threads_session
    return _api_threads_session(app, thread_id, project_id)

@app.get("/log", response_class=HTMLResponse)
def view_logs(project_id: Optional[int] = None, branch_id: Optional[int] = None):
    # Render recent client + server logs (newest last for readability)
    rows = []
    try:
        logs = list(_LOG_BUFFER)
    except Exception:
        logs = []
    if logs:
        for e in logs:
            ts = escape(str(e.get("ts") or ""))
            lvl = escape(str(e.get("level") or ""))
            url = escape(str(e.get("url") or ""))
            origin = escape(str(e.get("origin") or ""))
            msg = escape(str(e.get("message") or ""))
            loc = escape(str(e.get("loc") or ""))
            stack = escape(str(e.get("stack") or ""))
            ua = escape(str(e.get("ua") or ""))
            rows.append(f"<tr><td class='small'>{ts}</td><td class='small'>{lvl}</td><td class='small'>{origin}</td><td class='small'>{loc}</td><td>{msg}</td><td class='small'>{url}</td></tr>" + (f"<tr><td colspan='6'><pre class='small' style='white-space:pre-wrap'>{stack}</pre></td></tr>" if stack else ""))
    body = f"""
      <h1>Client Log</h1>
      <div class='card'>
        <div class='small muted'>Most recent {len(logs)} entries.</div>
        <table class='table'>
          <thead><tr><th>When</th><th>Level</th><th>Origin</th><th>Loc</th><th>Message</th><th>URL</th></tr></thead>
          <tbody>{''.join(rows) or "<tr><td colspan='6' class='muted'>(no entries)</td></tr>"}</tbody>
        </table>
      </div>
    """
    # Optional project context in header
    header_lbl = None
    header_lnk = None
    nav_q = None
    try:
        if project_id is not None:
            pid = int(project_id)
            try:
                with RegistrySessionLocal() as reg:
                    p = reg.query(Project).filter(Project.id == pid).first()
                    if p:
                        header_lbl = p.title
            except Exception:
                pass
            bid = None
            try:
                bid = int(branch_id) if branch_id is not None else None
            except Exception:
                bid = None
            if bid is None:
                try:
                    SessionLocal = sessionmaker(bind=_get_project_engine(pid), autoflush=False, autocommit=False, future=True)
                    with SessionLocal() as pdb:
                        mb = ensure_main_branch(pdb, pid)
                        bid = mb.id
                except Exception:
                    bid = 1
            header_lnk = f"/project/{pid}?branch_id={bid}"
            nav_q = f"project_id={pid}&branch_id={bid}"
    except Exception:
        pass
    return layout("Log", body, header_label=header_lbl, header_link=header_lnk, nav_query=nav_q)


# Changelog route removed - focusing on WebSocket chat only

# ----------------------------------------------------------------------------------
# Merge dashboard pages
# ----------------------------------------------------------------------------------

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


@app.get("/merge", response_class=HTMLResponse)
def merge_index(request: Request, db: Session = Depends(get_registry_db)):
    """Merge landing should be project-scoped, not a cross-project dashboard.
    Behavior:
    - If ?project_id= is present, redirect to /merge/{project_id}
    - Else, if exactly one project exists, redirect to that project's merge page
    - Else, show guidance to open a project first (no global project list)
    """
    # 1) Respect explicit context from nav link
    pid_qs = request.query_params.get("project_id")
    if pid_qs is not None:
        try:
            pid = int(pid_qs)
            return RedirectResponse(f"/merge/{pid}", status_code=303)
        except Exception:
            pass
    # 2) Single-project convenience redirect
    try:
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    except Exception:
        projects = []
    if len(projects) == 1:
        return RedirectResponse(f"/merge/{projects[0].id}", status_code=303)
    # 3) No context: instruct user to open a project first
    body = (
        "<h1>Merge</h1>"
        "<div class='card' style='max-width:720px'>"
        "  <p>This page is scoped to a single project. Open a project and use the Merge tab to merge a feature branch back into Main.</p>"
        "  <p><a class='pill' href='/'>Go to Projects</a></p>"
        "</div>"
    )
    return layout("Merge", body)


@app.get("/merge/{project_id}", response_class=HTMLResponse)
def merge_project_view(project_id: int, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")
    # Branches
    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    main_b = ensure_main_branch(db, project.id)

    # Build main changelog hash set
    main_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==main_b.id).order_by(ChangelogEntry.created_at.desc()).limit(500).all()
    seen = set((ce.action, _hash_payload(ce.input_json)) for ce in main_entries)

    # For each branch, compute unique entries (not present in main by action+input)
    cards = []
    for b in branches:
        if b.id == main_b.id:
            # Render main summary card
            cards.append(f"""
              <div class='card'>
                <h3>Main</h3>
                <div class='small muted'>Branch ID: {b.id}</div>
                <div class='small muted'>Changelog entries: {len(main_entries)}</div>
              </div>
            """)
            continue
        entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==b.id).order_by(ChangelogEntry.created_at.desc()).limit(200).all()
        unique = []
        for ce in entries:
            key = (ce.action, _hash_payload(ce.input_json))
            if key not in seen:
                unique.append(ce)
        # Render card with unique entries and a merge button
        ul_items = []
        for ce in unique[:20]:
            summ = escape((ce.summary_text or ce.action or '').strip() or '(no summary)')
            ul_items.append(f"<li class='small'>{summ}</li>")
        unique_html = "<ul class='small'>" + ("".join(ul_items) or "<li class='muted small'>(no unique items found)</li>") + "</ul>"
        merge_form = f"""
          <form method='post' action='/project/{project.id}/merge_to_main?branch_id={b.id}' class='inline'>
            <button type='submit' data-testid='merge-branch-{b.id}'>Merge {escape(b.name)} → Main</button>
          </form>
        """
        cards.append(f"""
          <div class='card'>
            <h3>Branch: {escape(b.name)}</h3>
            <div class='small muted'>Branch ID: {b.id}</div>
            <div>{merge_form}</div>
            <div style='height:8px'></div>
            <div><strong>Unique vs Main</strong></div>
            {unique_html}
          </div>
        """)

    body = f"""
      <h1>Merge: {escape(project.title)}</h1>
      <div class='small muted'>This page lists branches for this project only and lets you merge a feature branch back into Main.</div>
      <div style='height:8px'></div>
      <div class='row'>
        {''.join(cards)}
      </div>
    """
    return layout(f"Merge • {project.title}", body, header_label=project.title, header_link=f"/project/{project.id}?branch_id={main_b.id}", nav_query=f"project_id={project.id}&branch_id={main_b.id}")


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


@app.post("/projects/create")
def create_project(title: str = Form(...), db: Session = Depends(get_registry_db)):
    """Create a new project."""
    from main_helpers import ensure_main_branch, add_version
    from sqlalchemy.orm import sessionmaker
    
    title = title.strip()
    if not title:
        return RedirectResponse("/", status_code=303)
    # create or get existing project in registry
    p = get_or_create_project_registry(db, title)
    add_version(db, "project", p.id, {"title": p.title})

    # Initialize per-project DB schema and seed project + Main branch
    try:
        eng = _get_project_engine(p.id)
        Base.metadata.create_all(eng)
        SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
        pdb = SessionLocal()
        try:
            # Insert the project row in the project DB with the same ID
            if not pdb.query(Project).filter(Project.id == p.id).first():
                pdb.add(Project(id=p.id, title=p.title))
                pdb.commit()
            ensure_main_branch(pdb, p.id)
        finally:
            pdb.close()
        _ensure_project_storage(p.id)
        print(f"[create-project] Successfully initialized project {p.id} DB with tables")
    except Exception as e:
        print(f"[create-project-error] Failed to initialize project {p.id} DB: {type(e).__name__}: {e}")
        # Still redirect but project may be broken
        pass

    # Redirect into the new project's Main branch
    # Open per-project DB to get Main ID again (safe)
    try:
        eng = _get_project_engine(p.id)
        SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
        with SessionLocal() as pdb:
            main = ensure_main_branch(pdb, p.id)
            main_id = main.id
    except Exception:
        main_id = 1
    return RedirectResponse(f"/project/{p.id}?branch_id={main_id}", status_code=303)


@app.get("/project/{project_id}", response_class=HTMLResponse)
def view_project(project_id: int, branch_id: Optional[int] = None, msg: Optional[str] = None, file_id: Optional[int] = None, dataset_id: Optional[int] = None, thread_id: Optional[int] = None, code_mid: Optional[int] = None, code_idx: Optional[int] = None, db: Session = Depends(get_project_db)):
    try:
        ensure_project_initialized(project_id)
    except Exception as e:
        print(f"[view-project-error] Failed to ensure project {project_id} initialized: {e}")
        return layout("Error", f"<h1>Project Initialization Error</h1><p class='muted'>Failed to initialize project database: {html.escape(str(e))}</p><p><a href='/'>Return to Projects</a></p>")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")

    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()

    current = current_branch(db, project.id, branch_id)

    # which branches to show (roll-up logic)
    show_branch_ids = branch_filter_ids(db, project.id, current.id)

    files = db.query(FileEntry)\
        .filter(FileEntry.project_id == project.id, FileEntry.branch_id.in_(show_branch_ids))\
        .order_by(FileEntry.created_at.desc())\
        .all()

    threads = db.query(Thread)\
        .filter(Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids))\
        .order_by(Thread.created_at.desc())\
        .all()

    datasets = db.query(Dataset)\
        .filter(Dataset.project_id == project.id, Dataset.branch_id.in_(show_branch_ids))\
        .order_by(Dataset.created_at.desc())\
        .all()

    # resolve selected file if provided
    selected_file = None
    try:
        if file_id is not None:
            selected_file = db.query(FileEntry).filter(
                FileEntry.id == int(file_id),
                FileEntry.project_id == project.id,
                FileEntry.branch_id.in_(show_branch_ids)
            ).first()
    except Exception:
        selected_file = None

    # resolve selected dataset if provided
    selected_dataset = None
    try:
        if dataset_id is not None:
            selected_dataset = db.query(Dataset).filter(
                Dataset.id == int(dataset_id),
                Dataset.project_id == project.id,
                Dataset.branch_id.in_(show_branch_ids)
            ).first()
    except Exception:
        selected_dataset = None

    # resolve selected thread and messages
    selected_thread = None
    thread_messages: List[ThreadMessage] = []
    try:
        if thread_id is not None:
            selected_thread = db.query(Thread).filter(Thread.id == int(thread_id), Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids)).first()
            if selected_thread:
                thread_messages = db.query(ThreadMessage).filter(ThreadMessage.project_id==project.id, ThreadMessage.thread_id==selected_thread.id).order_by(ThreadMessage.created_at.asc()).all()
    except Exception:
        selected_thread = None

    # Build per-thread recent messages for the All Chats panel (last 3 messages each)
    last_msgs_map: Dict[int, List[ThreadMessage]] = {}
    try:
        for t in threads:
            try:
                recs = db.query(ThreadMessage).filter(ThreadMessage.project_id == project.id, ThreadMessage.thread_id == t.id).order_by(ThreadMessage.created_at.desc()).limit(3).all()
                last_msgs_map[t.id] = list(reversed(recs))
            except Exception:
                last_msgs_map[t.id] = []
    except Exception:
        last_msgs_map = {}

    # Fetch recent notes for left-pane Notes tab (roll-up across visible branches)
    try:
        notes = db.query(Note).filter(Note.project_id == project.id, Note.branch_id.in_(show_branch_ids)).order_by(Note.created_at.desc()).limit(200).all()
    except Exception:
        notes = []

    # Build Code items across visible threads
    try:
        code_items = _collect_code_items(db, project.id, threads)
    except Exception:
        code_items = []
    # Resolve selected code item if query params provided
    selected_code = None
    try:
        if code_mid is not None:
            cmid = int(code_mid)
            cidx = int(code_idx) if code_idx is not None else 0
            for ci in code_items:
                try:
                    if int(ci.get('mid')) == cmid and int(ci.get('idx', 0)) == cidx:
                        selected_code = ci
                        break
                except Exception:
                    pass
    except Exception:
        selected_code = None

    return layout(
        project.title,
        project_page_html(
            project,
            branches,
            current,
            files,
            threads,
            datasets,
            selected_file=selected_file,
            selected_dataset=selected_dataset,
            selected_thread=selected_thread,
            thread_messages=thread_messages,
            msg=msg,
            last_msgs_map=last_msgs_map,
            notes=notes,
            code_items=code_items,
            selected_code=selected_code,
        ),
        header_label=project.title,
        header_link=f"/project/{project.id}?branch_id={current.id}",
        nav_query=f"project_id={project.id}&branch_id={current.id}"
    )


@app.post("/project/{project_id}/branches/create")
def create_branch(project_id: int, name: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    name = name.strip()
    if not name or name.lower() == "main":
        # prevent duplicate/invalid
        main = ensure_main_branch(db, project.id)
        return RedirectResponse(f"/project/{project.id}?branch_id={main.id}&msg=Invalid+branch+name", status_code=303)
    # create branch
    b = Branch(project_id=project.id, name=name, is_default=False)
    db.add(b)
    try:
        db.commit()
    except Exception:
        db.rollback()
        main = ensure_main_branch(db, project.id)
        return RedirectResponse(f"/project/{project.id}?branch_id={main.id}&msg=Branch+already+exists", status_code=303)
    db.refresh(b)
    add_version(db, "branch", b.id, {"project_id": project.id, "name": b.name, "is_default": False})
    return RedirectResponse(f"/project/{project.id}?branch_id={b.id}", status_code=303)


@app.post("/project/{project_id}/threads/create")
@app.get("/project/{project_id}/threads/new")
# LLM chat uses threads. If using the GET '/threads/new', a default title 'New Thread' is created
# and the user is redirected to the project page focusing the new tab. See README for LLM setup.
def create_thread(project_id: int, request: Request, title: Optional[str] = Form(None), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # branch selected via query parameter
    branch_id = request.query_params.get("branch_id")
    try:
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
    add_version(db, "thread", t.id, {"project_id": project.id, "branch_id": branch.id, "title": t.title})

    redirect_url = f"/project/{project.id}?branch_id={branch.id}&thread_id={t.id}" + (f"&file_id={file_obj.id}" if file_obj else "") + (f"&dataset_id={dataset_obj.id}" if dataset_obj else "") + "&msg=Thread+created"

    # Optional JSON response for client-side creation
    if json_q is not None and str(json_q).strip() not in {"", "0", "false", "False", "no"}:
        return JSONResponse({"thread_id": t.id, "branch_id": branch.id, "redirect": redirect_url, "title": t.title})

    # Redirect to focus the newly created thread
    return RedirectResponse(redirect_url, status_code=303)


@app.post("/project/{project_id}/ask")
def ask_endpoint(project_id: int, request: Request, query: str = Form(...), db: Session = Depends(get_project_db)):
    """Endpoint for the Ask orchestrator feature."""
    from .utils.ask_orchestrator import ask_orchestrator
    return ask_orchestrator(app, project_id, request, query, db)


@app.post("/project/{project_id}/threads/chat")
def thread_chat_endpoint(project_id: int, request: Request, content: str = Form(...), thread_id: Optional[str] = Form(None), file_id: Optional[str] = Form(None), dataset_id: Optional[str] = Form(None), db: Session = Depends(get_project_db)):
    """Endpoint for thread chat feature."""
    from .utils.thread_chat import thread_chat
    return thread_chat(project_id, request, content, thread_id, file_id, dataset_id, db)

# ----------------------------------------------------------------------------------
# WebSocket chat streaming endpoint (word-by-word)
# ----------------------------------------------------------------------------------
async def _ws_send_safe(ws: WebSocket, text: str) -> bool:
    try:
        if getattr(ws, 'client_state', None) != WebSocketState.CONNECTED:
            return False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Outside of loop; fallback
            pass
        try:
            # Attempt send; catch RuntimeError from closed/closing socket
            import json as _json  # ensure json exists in scope used elsewhere
        except Exception:
            pass
        try:
            # starlette will raise RuntimeError if closing/closed
            return bool((await ws.send_text(text)) or True)
        except RuntimeError:
            return False
        except Exception:
            return False
    except Exception:
        return False

# Legacy WebSocket endpoint removed - using only /ws/chat/{project_id}



# Background workers and upload function moved to utils/file_operations.py
from cedar_app.utils.file_operations import (
    _run_langextract_ingest_background,
    _run_upload_postprocess_background,
    upload_file as upload_file_impl
)


@app.post("/project/{project_id}/files/upload")
def upload_file(project_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_project_db)):
    """Route handler for file uploads. Delegates to extracted module."""
    return upload_file_impl(project_id, request, file, db)
