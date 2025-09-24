"""
Logging utilities module for Cedar app.
Handles unified logging and client log ingestion.
"""

import os
import sys
import time as _time
import logging as _logging
import builtins as _bi
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import deque
from contextvars import ContextVar

from fastapi import Request
from pydantic import BaseModel

# Global logging buffers
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
