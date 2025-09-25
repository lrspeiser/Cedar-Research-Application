"""
Thread management utilities for Cedar app.
Handles thread operations and chat message management.
"""

import json
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import HTTPException, Depends, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, sessionmaker

from ..db_utils import _get_project_engine, ensure_project_initialized, save_thread_snapshot
from main_models import Thread, ThreadMessage, Project, Branch, ChangelogEntry
from main_helpers import current_branch, escape, branch_filter_ids


def api_threads_list(app, project_id: int, branch_id: Optional[int] = None):
    """API endpoint to list threads for a project."""
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        q = db.query(Thread).filter(Thread.project_id==project_id)
        if branch_id is not None:
            try:
                q = q.filter(Thread.branch_id==int(branch_id))
            except Exception:
                pass
        threads = q.order_by(Thread.created_at.desc()).limit(200).all()
        out = []
        for t in threads:
            last_at = None
            try:
                last = db.query(ThreadMessage).filter(
                    ThreadMessage.project_id==project_id, 
                    ThreadMessage.thread_id==t.id
                ).order_by(ThreadMessage.created_at.desc()).first()
                if last and getattr(last, 'created_at', None):
                    last_at = last.created_at.isoformat()+"Z"
            except Exception:
                pass
            out.append({
                "id": int(t.id),
                "title": (t.title or ""),
                "branch_id": getattr(t, 'branch_id', None),
                "created_at": (t.created_at.isoformat()+"Z") if getattr(t, 'created_at', None) else None,
                "last_message_at": last_at,
            })
        return {"ok": True, "threads": out}
    finally:
        try: 
            db.close()
        except Exception: 
            pass


def api_threads_session(app, thread_id: int, project_id: int):
    """Get thread session data including messages."""
    # Ensure snapshot exists; generate if missing
    p = save_thread_snapshot(project_id, int(thread_id))
    try:
        if not p:
            # Fallback: build in-memory from DB
            SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
            db = SessionLocal()
            try:
                thr = db.query(Thread).filter(Thread.id==int(thread_id), Thread.project_id==project_id).first()
                if not thr:
                    raise HTTPException(status_code=404, detail="thread not found")
                msgs = db.query(ThreadMessage).filter(
                    ThreadMessage.project_id==project_id, 
                    ThreadMessage.thread_id==thread_id
                ).order_by(ThreadMessage.created_at.asc()).all()
                out = {
                    "project_id": int(project_id),
                    "thread_id": int(thread_id),
                    "branch_id": getattr(thr, 'branch_id', None),
                    "title": getattr(thr, 'title', None),
                    "created_at": (thr.created_at.isoformat()+"Z") if getattr(thr, 'created_at', None) else None,
                    "messages": [
                        {
                            "role": m.role, 
                            "title": getattr(m, 'display_title', None), 
                            "content": m.content, 
                            "payload": getattr(m, 'payload_json', None), 
                            "created_at": (m.created_at.isoformat()+"Z") if getattr(m, 'created_at', None) else None
                        }
                        for m in msgs
                    ]
                }
                return out
            finally:
                try: 
                    db.close()
                except Exception: 
                    pass
        else:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


def api_chat_cancel_summary(app, payload: Dict[str, Any]):
    """Generate a summary when chat is cancelled."""
    from ..llm_utils import llm_client_config as _llm_client_config
    from ..changelog_utils import record_changelog as _record_changelog_base
    from ..llm_utils import llm_summarize_action as _llm_summarize_action
    
    try:
        project_id = int(payload.get("project_id"))
        branch_id = int(payload.get("branch_id"))
        thread_id = int(payload.get("thread_id"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid ids")

    ensure_project_initialized(project_id)
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        # Collect thread history (last 20)
        history: List[Dict[str, Any]] = []
        try:
            msgs = db.query(ThreadMessage).filter(
                ThreadMessage.project_id==project_id, 
                ThreadMessage.thread_id==thread_id
            ).order_by(ThreadMessage.created_at.desc()).limit(20).all()
            for m in reversed(msgs):
                history.append({
                    "role": m.role, 
                    "title": (m.display_title or None), 
                    "content": (m.content or "")[:1500]
                })
        except Exception:
            history = []
        
        timings = payload.get("timings") or []
        prompt_messages = payload.get("prompt_messages") or []
        reason = str(payload.get("reason") or "user_clicked_cancel")

        # Build a concise summary via LLM (fallback to deterministic text if key missing)
        client, model = _llm_client_config()
        summary_text = None
        if client:
            try:
                sys_prompt = (
                    "You are Cedar's cancellation assistant. Write a concise user-facing summary (4-8 short bullet lines) of what the run did and didn't do, "
                    "why it stopped (user cancel), and suggested next steps. Avoid secrets; include key tool steps if available."
                )
                import json as _json
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": "Reason:"},
                    {"role": "user", "content": reason},
                    {"role": "user", "content": "Timings (ms):"},
                    {"role": "user", "content": _json.dumps(timings, ensure_ascii=False)},
                    {"role": "user", "content": "Thread history (recent):"},
                    {"role": "user", "content": _json.dumps(history, ensure_ascii=False)},
                    {"role": "user", "content": "Prepared prompt messages (if any):"},
                    {"role": "user", "content": _json.dumps(prompt_messages, ensure_ascii=False)},
                    {"role": "user", "content": "Output STRICT plain text, each bullet starting with •"},
                ]
                resp = client.chat.completions.create(
                    model=(os.getenv("CEDARPY_SUMMARY_MODEL", "gpt-4-mini")), 
                    messages=messages
                )
                summary_text = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                try:
                    print(f"[cancel-summary-error] {type(e).__name__}: {e}")
                except Exception:
                    pass
        
        if not summary_text:
            # Deterministic fallback (no network)
            try:
                bullets = [
                    "• Run cancelled by user.",
                    "• Partial steps may have executed before cancel.",
                    "• See Changelog for recorded steps and timings.",
                    "• Re-run to continue or refine your question.",
                ]
                summary_text = "\n".join(bullets)
            except Exception:
                summary_text = "Run cancelled by user."

        # Persist assistant message and changelog
        tm = ThreadMessage(
            project_id=project_id, 
            branch_id=branch_id, 
            thread_id=thread_id, 
            role="assistant", 
            display_title="Cancelled", 
            content=summary_text
        )
        db.add(tm)
        db.commit()
        
        try:
            _record_changelog_base(
                db, project_id, branch_id, "chat.cancel", 
                {"reason": reason, "timings": timings, "prompt_messages": prompt_messages}, 
                {"text": summary_text},
                ChangelogEntry=ChangelogEntry, 
                llm_summarize_action_fn=_llm_summarize_action
            )
        except Exception:
            pass
        
        return {"ok": True, "text": summary_text}
    finally:
        try: 
            db.close()
        except Exception: 
            pass