"""
Client logging utilities for Cedar app.
Handles client-side log collection and processing.

Note: This module works with in-memory logging rather than database persistence,
matching the existing Cedar app architecture that uses _LOG_BUFFER.
"""

import json
import os
from typing import Dict, Any, List
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel


class ClientLogEntry(BaseModel):
    """Pydantic model for client log entries."""
    when: str = None
    level: str
    message: str
    url: str = None
    line: int = None
    column: int = None
    stack: str = None
    userAgent: str = None
    origin: str = None
    project_id: int = None
    branch_id: int = None


def api_client_log(app, payload: Dict[str, Any]):
    """Record client-side logs for debugging and monitoring.
    Uses in-memory _LOG_BUFFER for consistency with existing architecture.
    """
    try:
        # Import the global log buffer from main_impl_full
        from cedar_app.main_impl_full import _LOG_BUFFER
    except ImportError:
        # Fallback if not available
        _LOG_BUFFER = []
    
    # Extract data from payload
    project_id = payload.get("project_id")
    branch_id = payload.get("branch_id", 1)
    level = str(payload.get("level", "info")).upper()
    message = str(payload.get("message", ""))
    context = payload.get("context", {})
    url = payload.get("url", "")
    timestamp = payload.get("when") or datetime.utcnow().isoformat() + "Z"
    
    # Create log entry for the buffer
    log_entry = {
        "ts": timestamp,
        "level": level,
        "host": "client",
        "origin": f"client:P{project_id}:B{branch_id}" if project_id else "client",
        "url": url,
        "loc": "",
        "ua": payload.get("userAgent", ""),
        "message": message,
        "stack": payload.get("stack"),
    }
    
    # Append to buffer
    try:
        _LOG_BUFFER.append(log_entry)
    except Exception:
        pass
    
    # Also write to console for debugging
    try:
        print(f"[CLIENT-{level}] P{project_id}/B{branch_id}: {message}")
        if context:
            print(f"  Context: {json.dumps(context, indent=2)}")
    except Exception:
        pass
    
    return {"ok": True, "logged": True}


def api_client_logs_batch(app, payload: Dict[str, Any]):
    """Record multiple client-side logs at once."""
    project_id = payload.get("project_id")
    branch_id = payload.get("branch_id", 1)
    logs = payload.get("logs", [])
    
    if not logs:
        return {"ok": True, "count": 0}
    
    try:
        # Import the global log buffer from main_impl_full
        from cedar_app.main_impl_full import _LOG_BUFFER
    except ImportError:
        # Fallback if not available
        _LOG_BUFFER = []
    
    count = 0
    for log_item in logs:
        try:
            level = str(log_item.get("level", "info")).upper()
            message = str(log_item.get("message", ""))
            timestamp = log_item.get("timestamp") or datetime.utcnow().isoformat() + "Z"
            
            log_entry = {
                "ts": timestamp,
                "level": level,
                "host": "client",
                "origin": f"client:P{project_id}:B{branch_id}" if project_id else "client",
                "url": log_item.get("url", ""),
                "loc": "",
                "ua": log_item.get("userAgent", ""),
                "message": message,
                "stack": log_item.get("stack"),
            }
            
            _LOG_BUFFER.append(log_entry)
            count += 1
        except Exception as e:
            print(f"[CLIENT-BATCH-ERROR] Failed to log item: {e}")
            continue
    
    return {"ok": True, "count": count}


def api_client_logs_query(app, project_id: int = None, branch_id: int = None, 
                         level: str = None, limit: int = 100):
    """Query client logs for debugging from in-memory buffer."""
    try:
        # Import the global log buffer from main_impl_full
        from cedar_app.main_impl_full import _LOG_BUFFER
        logs = list(_LOG_BUFFER)
    except ImportError:
        logs = []
    
    # Filter logs
    filtered_logs = []
    for log in logs:
        # Filter by project if specified
        if project_id is not None:
            origin = log.get("origin", "")
            if f"P{project_id}" not in origin:
                continue
        
        # Filter by branch if specified
        if branch_id is not None:
            origin = log.get("origin", "")
            if f"B{branch_id}" not in origin:
                continue
        
        # Filter by level if specified
        if level and log.get("level", "").lower() != level.lower():
            continue
        
        filtered_logs.append({
            "level": log.get("level"),
            "message": log.get("message"),
            "origin": log.get("origin"),
            "url": log.get("url"),
            "created_at": log.get("ts")
        })
    
    # Limit results
    filtered_logs = filtered_logs[-limit:] if limit > 0 else filtered_logs
    
    return {
        "ok": True,
        "logs": filtered_logs
    }


def api_client_error_report(app, payload: Dict[str, Any]):
    """Handle client error reports with additional context."""
    project_id = payload.get("project_id")
    branch_id = payload.get("branch_id", 1)
    error_type = str(payload.get("type", "unknown"))
    message = str(payload.get("message", ""))
    stack_trace = payload.get("stack_trace", "")
    user_agent = payload.get("user_agent", "")
    url = payload.get("url", "")
    
    try:
        # Import the global log buffer from main_impl_full
        from cedar_app.main_impl_full import _LOG_BUFFER
    except ImportError:
        _LOG_BUFFER = []
    
    try:
        # Create error log entry
        log_entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": "ERROR",
            "host": "client",
            "origin": f"client:P{project_id}:B{branch_id}" if project_id else "client",
            "url": url,
            "loc": "",
            "ua": user_agent,
            "message": f"[{error_type}] {message}",
            "stack": stack_trace,
        }
        
        _LOG_BUFFER.append(log_entry)
        
        # Also log to console for immediate visibility
        print(f"[CLIENT-ERROR] P{project_id}/B{branch_id} - {error_type}: {message}")
        if stack_trace:
            print(f"  Stack: {stack_trace[:500]}")
        
        return {"ok": True, "reported": True}
    except Exception as e:
        print(f"[ERROR-REPORT-FAIL] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}


def cleanup_old_logs(project_id: int = None, days_to_keep: int = 7):
    """Clean up old client logs from in-memory buffer.
    Note: In-memory logs are automatically cleaned by buffer size limits.
    This function provides a consistent API but has limited effect on memory buffers.
    """
    try:
        # Import the global log buffer from main_impl_full
        from cedar_app.main_impl_full import _LOG_BUFFER
        
        # For in-memory buffer, we can only clean based on count
        # This is a no-op for memory buffers since they're automatically managed
        current_count = len(_LOG_BUFFER)
        
        print(f"[LOG-CLEANUP] In-memory buffer has {current_count} entries")
        return {"ok": True, "deleted": 0, "note": "In-memory logs auto-managed"}
    except Exception as e:
        print(f"[CLEANUP-ERROR] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}
