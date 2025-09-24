"""
Logging routes for Cedar app.
Handles log viewing and client log ingestion.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from cedar_app.utils.html import layout
from cedar_app.utils.logging import _LOG_BUFFER, ClientLogEntry

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def view_logs():
    """View application logs."""
    logs = list(_LOG_BUFFER)
    rows = []
    for entry in logs:
        rows.append(f"<tr><td>{entry.get('ts', '')}</td><td>{entry.get('level', '')}</td><td>{entry.get('message', '')}</td></tr>")
    
    body = f"""
    <h1>Logs</h1>
    <div class='card'>
        <table class='table'>
            <thead><tr><th>Time</th><th>Level</th><th>Message</th></tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="3">No logs</td></tr>'}</tbody>
        </table>
    </div>
    """
    return layout("Logs", body)

@router.post("/client")
def client_log(entry: ClientLogEntry):
    """Receive client-side logs."""
    _LOG_BUFFER.append({
        "ts": entry.when or "",
        "level": entry.level,
        "message": entry.message
    })
    return {"ok": True}
