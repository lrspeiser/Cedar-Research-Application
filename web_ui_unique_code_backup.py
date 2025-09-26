"""
Backup of unique code from web_ui.py that needs to be merged into main.py
Created: 2025-09-26

This file contains unique functionality from cedar_app/web_ui.py that wasn't present in main.py.
These features will be merged into the active main.py and then web_ui.py will be deleted.
"""

# ==================== ERROR LOGGING MIDDLEWARE ====================
# Add this middleware to catch and log unhandled exceptions
"""
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
"""

# ==================== CHANGELOG UTILITIES IMPORT ====================
# Import changelog utilities from the dedicated module
"""
from cedar_app.changelog_utils import (
    record_changelog as _record_changelog_base,
    # add_version is imported from main_helpers instead
)
"""

# Changelog wrapper function
"""
def record_changelog(db: Session, project_id: int, branch_id: int, action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]):
    '''Wrapper for record_changelog that passes our local dependencies.'''
    return _record_changelog_base(
        db, project_id, branch_id, action, input_payload, output_payload,
        ChangelogEntry=ChangelogEntry,
        llm_summarize_action_fn=_llm_summarize_action
    )
"""

# ==================== UNIFIED LOGGING SYSTEM ====================
# This includes:
# - Global logging buffers
# - CedarBufferHandler for capturing server logs
# - HTTP middleware for request logging
# - Print patching to capture stdout

"""
from collections import deque
from contextvars import ContextVar
import logging as _logging
import time as _time
import builtins as _bi

# Global logging buffers and context
_LOG_BUFFER = deque(maxlen=1000)
_SERVER_LOG_BUFFER = deque(maxlen=1000)
_current_path: ContextVar[str] = ContextVar('current_path', default='')

class CedarBufferHandler(_logging.Handler):
    def emit(self, record: _logging.LogRecord) -> None:
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
                def _cedar_print(*args, **kwargs):
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
                _bi.print = _cedar_print
            except Exception:
                pass
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
    except Exception:
        pass

# Install unified logging immediately at import time
_install_unified_logging()
"""

# ==================== TEST TOOL EXECUTION ENDPOINT ====================
"""
# Test-only tool execution API (local + CEDARPY_TEST_MODE only)
from cedar_app.utils.dev_tools import (
    ToolExecRequest,
    api_test_tool_exec as api_test_tool_exec_impl
)

@app.post("/api/test/tool")
def api_test_tool_exec(body: ToolExecRequest, request: Request):
    '''Tool execution endpoint for testing. Delegates to extracted module.'''
    return api_test_tool_exec_impl(body, request)
"""

# ==================== CLIENT LOG INGESTION ENDPOINT ====================
"""
# Client log ingestion API (merges into _LOG_BUFFER)
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
"""

# ==================== CANCEL SUMMARY ENDPOINT ====================
"""
# Cancellation summary API
# Submits a special prompt to produce a user-facing summary when a chat is cancelled.
@app.post("/api/chat/cancel-summary")
def api_chat_cancel_summary(payload: Dict[str, Any] = Body(...)):
    from cedar_app.utils.thread_management import api_chat_cancel_summary as _api_chat_cancel_summary
    return _api_chat_cancel_summary(app, payload)
"""