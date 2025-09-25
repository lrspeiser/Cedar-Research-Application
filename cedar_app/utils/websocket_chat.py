"""
WebSocket chat streaming module for Cedar app.
Handles the legacy chat WebSocket endpoint with streaming responses.
"""

import os
import json
import uuid
import time as _time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.orm import sessionmaker, Session

from ..db_utils import ensure_project_initialized, _get_project_engine
from ..llm_utils import llm_client_config as _llm_client_config
from ..changelog_utils import record_changelog
from main_models import (
    Project, Branch, Thread, ThreadMessage, FileEntry, 
    Dataset, Note, ChangelogEntry
)
from main_helpers import (
    current_branch, add_version, branch_filter_ids
)

# Import helper functions that might be needed
async def _ws_send_safe(ws: WebSocket, text: str) -> bool:
    """Safely send text to WebSocket, handling connection state."""
    try:
        if getattr(ws, 'client_state', None) != WebSocketState.CONNECTED:
            return False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Outside of loop; fallback
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


# Placeholder functions for ACK and relay - these should be imported from appropriate modules
async def _register_ack(eid: str, info: Dict[str, Any], timeout_ms: int = 10000):
    """Register an acknowledgment for tracking. Placeholder implementation."""
    pass

async def _publish_relay_event(obj: Dict[str, Any]):
    """Publish event for relay. Placeholder implementation."""
    pass