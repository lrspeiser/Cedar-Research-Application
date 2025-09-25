"""
Client logging utilities for Cedar app.
Handles client-side log collection and processing.
"""

import json
import os
from typing import Dict, Any, List
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from ..db_utils import _get_project_engine, ensure_project_initialized
from main_models import ClientLog, Project, Branch


def api_client_log(app, payload: Dict[str, Any]):
    """Record client-side logs for debugging and monitoring."""
    project_id = int(payload.get("project_id"))
    branch_id = int(payload.get("branch_id", 1))
    level = str(payload.get("level", "info")).lower()
    message = str(payload.get("message", ""))
    context = payload.get("context", {})
    
    # Validate log level
    valid_levels = ["debug", "info", "warn", "error", "critical"]
    if level not in valid_levels:
        level = "info"
    
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        # Create log entry
        log_entry = ClientLog(
            project_id=project_id,
            branch_id=branch_id,
            level=level,
            message=message,
            context_json=json.dumps(context) if context else None,
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        # Also write to console for debugging (optional)
        if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS"):
            try:
                print(f"[CLIENT-{level.upper()}] P{project_id}/B{branch_id}: {message}")
                if context:
                    print(f"  Context: {json.dumps(context, indent=2)}")
            except Exception:
                pass
        
        return {"ok": True, "logged": True}
    except Exception as e:
        # Don't fail the client if logging fails
        if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS"):
            print(f"[CLIENT-LOG-ERROR] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_client_logs_batch(app, payload: Dict[str, Any]):
    """Record multiple client-side logs at once."""
    project_id = int(payload.get("project_id"))
    branch_id = int(payload.get("branch_id", 1))
    logs = payload.get("logs", [])
    
    if not logs:
        return {"ok": True, "count": 0}
    
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        count = 0
        for log_item in logs:
            try:
                level = str(log_item.get("level", "info")).lower()
                if level not in ["debug", "info", "warn", "error", "critical"]:
                    level = "info"
                
                log_entry = ClientLog(
                    project_id=project_id,
                    branch_id=branch_id,
                    level=level,
                    message=str(log_item.get("message", "")),
                    context_json=json.dumps(log_item.get("context", {})) if log_item.get("context") else None,
                    created_at=datetime.fromisoformat(log_item["timestamp"].replace("Z", "+00:00")) 
                              if "timestamp" in log_item else datetime.utcnow()
                )
                db.add(log_entry)
                count += 1
            except Exception as e:
                if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS"):
                    print(f"[CLIENT-BATCH-ERROR] Failed to log item: {e}")
                continue
        
        if count > 0:
            db.commit()
        
        return {"ok": True, "count": count}
    except Exception as e:
        if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS"):
            print(f"[CLIENT-BATCH-ERROR] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e), "count": 0}
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_client_logs_query(app, project_id: int, branch_id: int = None, 
                         level: str = None, limit: int = 100):
    """Query client logs for debugging."""
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        q = db.query(ClientLog).filter(ClientLog.project_id == project_id)
        
        if branch_id is not None:
            q = q.filter(ClientLog.branch_id == int(branch_id))
        
        if level:
            q = q.filter(ClientLog.level == level.lower())
        
        logs = q.order_by(ClientLog.created_at.desc()).limit(min(limit, 1000)).all()
        
        return {
            "ok": True,
            "logs": [
                {
                    "id": log.id,
                    "level": log.level,
                    "message": log.message,
                    "context": json.loads(log.context_json) if log.context_json else None,
                    "branch_id": log.branch_id,
                    "created_at": log.created_at.isoformat() + "Z" if log.created_at else None
                }
                for log in logs
            ]
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


def api_client_error_report(app, payload: Dict[str, Any]):
    """Handle client error reports with additional context."""
    project_id = int(payload.get("project_id"))
    branch_id = int(payload.get("branch_id", 1))
    error_type = str(payload.get("type", "unknown"))
    message = str(payload.get("message", ""))
    stack_trace = payload.get("stack_trace", "")
    user_agent = payload.get("user_agent", "")
    url = payload.get("url", "")
    context = payload.get("context", {})
    
    # Add error details to context
    error_context = {
        "error_type": error_type,
        "stack_trace": stack_trace,
        "user_agent": user_agent,
        "url": url,
        **context
    }
    
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        # Log as error level
        log_entry = ClientLog(
            project_id=project_id,
            branch_id=branch_id,
            level="error",
            message=f"[{error_type}] {message}",
            context_json=json.dumps(error_context),
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        # Also log to console for immediate visibility
        if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS") or error_type == "critical":
            print(f"[CLIENT-ERROR] P{project_id}/B{branch_id} - {error_type}: {message}")
            if stack_trace:
                print(f"  Stack: {stack_trace[:500]}")
        
        return {"ok": True, "reported": True}
    except Exception as e:
        print(f"[ERROR-REPORT-FAIL] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass


def cleanup_old_logs(project_id: int, days_to_keep: int = 7):
    """Clean up old client logs to manage storage."""
    from datetime import timedelta
    
    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Delete old logs
        deleted = db.query(ClientLog).filter(
            ClientLog.project_id == project_id,
            ClientLog.created_at < cutoff_date
        ).delete()
        
        db.commit()
        
        if os.getenv("CEDARPY_DEBUG_CLIENT_LOGS"):
            print(f"[LOG-CLEANUP] Deleted {deleted} old log entries for project {project_id}")
        
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        print(f"[CLEANUP-ERROR] {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass