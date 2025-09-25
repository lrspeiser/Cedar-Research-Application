"""
main.py (orchestrator)

This thin module delegates the full application implementation to cedar_app.web_ui.
It exists to keep the entrypoint stable (main:app) while moving the heavy code into a separate
module so this file stays small (< 1000 lines) and only coordinates top-level wiring.

Notes:
- The previous full implementation has been moved to cedar_app/web_ui.py
- Backup snapshots of the original main.py are stored at main_backup_*.py
- Packaging scripts that import main:app continue to work unchanged.

Security/Secrets:
- See README for instructions on configuring API keys via ~/.env. Do not print or log secret values.
"""
from __future__ import annotations

# Re-export the FastAPI app and public helpers from the full implementation module.
# This keeps existing imports working (e.g., `from main import app`).
import importlib

try:
    _impl = importlib.import_module('cedar_app.web_ui')
    # Force a reload so per-test environment changes (e.g., CEDARPY_* vars) take effect.
    _impl = importlib.reload(_impl)
    app = getattr(_impl, 'app')  # FastAPI instance
except Exception as e:
    # Provide a clear import-time error if the implementation module is missing
    raise RuntimeError(f"Failed to import cedar_app.web_ui: {type(e).__name__}: {e}")

# Optional: re-export commonly used functions/objects to preserve backwards-compat usage across the codebase
# without forcing immediate refactors. If you want stricter encapsulation, narrow this list over time.
try:  # noqa: F401
    # Pull attributes off the freshly reloaded implementation module for backward compatibility exports
    RegistrySessionLocal = getattr(_impl, 'RegistrySessionLocal')
    get_registry_db = getattr(_impl, 'get_registry_db')
    get_project_db = getattr(_impl, 'get_project_db')
    _get_project_engine = getattr(_impl, '_get_project_engine')
    ensure_project_initialized = getattr(_impl, 'ensure_project_initialized')
    Base = getattr(_impl, 'Base')
    Project = getattr(_impl, 'Project')
    Branch = getattr(_impl, 'Branch')
    Thread = getattr(_impl, 'Thread')
    ThreadMessage = getattr(_impl, 'ThreadMessage')
    FileEntry = getattr(_impl, 'FileEntry')
    Dataset = getattr(_impl, 'Dataset')
    Setting = getattr(_impl, 'Setting')
    Version = getattr(_impl, 'Version')
    ChangelogEntry = getattr(_impl, 'ChangelogEntry')
    SQLUndoLog = getattr(_impl, 'SQLUndoLog')
    Note = getattr(_impl, 'Note')
    interpret_file = getattr(_impl, 'interpret_file')
    record_changelog = getattr(_impl, 'record_changelog')
    layout = getattr(_impl, 'layout', None)
except Exception:
    # It's OK if some names are not present; we only need app re-exported for the server to run.
    layout = None  # type: ignore
    pass

# Minimal HTML renderer used by tests to verify formatting. Returns a string of HTML (not a Response).
# We keep this here to avoid importing the entire implementation when only a small formatter is needed.
from html import escape as _esc
from datetime import datetime, timezone as _tz
from typing import Iterable as _Iterable

def projects_list_html(projects: _Iterable[object]) -> str:
    rows = []
    for p in projects:
        pid = getattr(p, 'id', None)
        title = _esc(str(getattr(p, 'title', 'Untitled') or 'Untitled'))
        dt = getattr(p, 'created_at', None)
        if isinstance(dt, datetime):
            ts = dt.astimezone(_tz.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        else:
            ts = ''
        rows.append(f"<tr><td>{pid}</td><td>{title}</td><td class='muted small'>{_esc(ts)}</td></tr>")
    table = (
        "<table class='table'>"
        "<thead><tr><th>ID</th><th>Title</th><th>Created</th></tr></thead>"
        f"<tbody>{''.join(rows) if rows else '<tr><td colspan=3 class=\"muted\">No projects yet.</td></tr>'}</tbody>"
        "</table>"
    )
    # If a full-page layout is available, wrap it, otherwise return the table only.
    if callable(layout):  # type: ignore[name-defined]
        try:
            return layout('Projects', f"<h1>Projects</h1>{table}").body.decode('utf-8')  # type: ignore[attr-defined]
        except Exception:
            return f"<h1>Projects</h1>{table}"
    return f"<h1>Projects</h1>{table}"

# If executed directly (e.g., `python main.py`), provide a simple dev server entrypoint.
# Production/packaged runs should invoke the app via the existing runners (uvicorn/pyinstaller launchers).
if __name__ == "__main__":
    try:
        import uvicorn  # type: ignore
        uvicorn.run(app, host="127.0.0.1", port=int("8000"))
    except Exception as e:
        raise SystemExit(f"Failed to start dev server: {type(e).__name__}: {e}")
