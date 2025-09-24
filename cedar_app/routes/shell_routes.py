"""
Shell routes for Cedar app.
Handles shell command execution UI and API.
"""

from fastapi import APIRouter, Request, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional

from cedar_app.config import SHELL_API_ENABLED, SHELL_API_TOKEN
from cedar_app.utils.html import layout

router = APIRouter()

def _is_local_request(request: Request) -> bool:
    host = (request.client.host if request and request.client else None) or ""
    return host in {"127.0.0.1", "::1", "localhost"}

def require_shell_auth(
    request: Request,
    x_api_token: Optional[str] = Header(default=None)
):
    """Check shell API authentication."""
    if not SHELL_API_ENABLED:
        raise HTTPException(status_code=403, detail="Shell API disabled")
    
    if SHELL_API_TOKEN:
        if x_api_token != SHELL_API_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        if not _is_local_request(request):
            raise HTTPException(status_code=401, detail="Local requests only")

@router.get("/", response_class=HTMLResponse)
def shell_ui(request: Request):
    """Shell UI page."""
    if not SHELL_API_ENABLED:
        body = """
        <h1>Shell</h1>
        <p class='muted'>Shell API is disabled.</p>
        """
    else:
        body = """
        <h1>Shell</h1>
        <div class='card'>
            <p>Shell interface (simplified during refactoring)</p>
        </div>
        """
    return layout("Shell", body)
