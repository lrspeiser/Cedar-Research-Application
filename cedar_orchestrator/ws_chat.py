"""
WebSocket chat orchestrator for CedarPy.

This module contains the extracted WebSocket chat streaming functionality from main.py.
It handles the full orchestration flow including:
- WebSocket connection management
- Message queue and event streaming
- LLM prompt preparation and execution
- Tool dispatch and result processing
- Redis/SSE event publishing

Keys: see README "Keys & Env" for loading from env or ~/.CedarPyData/.env
SSE relay: see README for Redis/SSE event publishing details
Troubleshooting: see README "Troubleshooting LLM failures"
"""

import os
import io
import re
import json
import mimetypes
import sqlite3
import subprocess
import asyncio
import uuid
import contextlib
import urllib.request
import time
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

from fastapi import WebSocket, FastAPI
from starlette.websockets import WebSocketState
from sqlalchemy.orm import sessionmaker, Session


class WSDeps:
    """Dependencies container for WebSocket chat orchestration."""
    
    def __init__(self, **kwargs):
        self.get_project_engine = kwargs["get_project_engine"]
        self.ensure_project_initialized = kwargs["ensure_project_initialized"]
        self.record_changelog = kwargs["record_changelog"]
        self.llm_client_config = kwargs["llm_client_config"]
        self.tabular_import_via_llm = kwargs["tabular_import_via_llm"]
        self.execute_sql = kwargs.get("execute_sql")
        self.exec_img = kwargs.get("exec_img")
        self.llm_summarize_action = kwargs.get("llm_summarize_action")
        self.RegistrySessionLocal = kwargs["RegistrySessionLocal"]
        self.FileEntry = kwargs["FileEntry"]
        self.Dataset = kwargs["Dataset"]
        self.Thread = kwargs["Thread"]
        self.ThreadMessage = kwargs["ThreadMessage"]
        self.Note = kwargs["Note"]
        self.Branch = kwargs["Branch"]
        self.ChangelogEntry = kwargs["ChangelogEntry"]
        self.branch_filter_ids = kwargs["branch_filter_ids"]
        self.current_branch = kwargs["current_branch"]
        self.file_extension_to_type = kwargs["file_extension_to_type"]
        self.publish_relay_event = kwargs["publish_relay_event"]
        self.register_ack = kwargs["register_ack"]
        self.project_dirs = kwargs["project_dirs"]


async def _ws_send_safe(ws: WebSocket, text: str) -> bool:
    """Safely send text through WebSocket, handling disconnected states."""
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


def register_ws_chat(app: FastAPI, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    """
    Register the WebSocket chat orchestrator on the given FastAPI app.
    
    Args:
        app: FastAPI application instance
        deps: WSDeps container with all required dependencies
        route_path: WebSocket route path (default: /ws/chat/{project_id})
    """
    
    @app.websocket(route_path)
    async def ws_chat_stream(websocket: WebSocket, project_id: int):  # noqa: C901
        """
        Main WebSocket chat orchestrator handler.
        
        This function handles the entire chat orchestration flow:
        1. Accepts WebSocket connection
        2. Sets up event queue and sender task
        3. Processes initial message and validates project/thread
        4. Builds LLM context from resources, history, notes, changelog
        5. Executes orchestration loop with tool dispatch
        6. Streams all events to client via WebSocket and Redis/SSE
        
        Keys: see README "Keys & Env"
        """
        await websocket.accept()
        
        # Queue-based event streaming to the client
        import asyncio as _aio
        event_q: _aio.Queue[str] = _aio.Queue()
        
        async def _sender():
            try:
                while True:
                    item = await event_q.get()
                    if item is None:
                        break
                    try:
                        await _ws_send_safe(websocket, item)
                    except Exception:
                        pass
            except Exception:
                pass
        
        sender_task = _aio.create_task(_sender())
        
        def _enqueue(obj: dict, require_ack: bool = False):
            """Enqueue event for WebSocket sending and Redis/SSE publishing."""
            try:
                if require_ack:
                    try:
                        eid = uuid.uuid4().hex
                        obj['eid'] = eid
                        # Ensure thread_id present when possible
                        try:
                            if ('thread_id' not in obj or obj.get('thread_id') is None) and ('thr' in locals() or True):
                                try:
                                    # thr is defined later; capture from closure if available
                                    _tid_local = None
                                    try:
                                        _tid_local = thr.id  # type: ignore[name-defined]
                                    except Exception:
                                        _tid_local = obj.get('thread_id')
                                    if _tid_local is not None:
                                        obj['thread_id'] = _tid_local
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        info = {'type': obj.get('type'), 'function': obj.get('function'), 'thread_id': obj.get('thread_id')}
                        try:
                            t_ms = int(os.getenv('CEDARPY_ACK_TIMEOUT_MS', '10000'))
                        except Exception:
                            t_ms = 10000
                        try:
                            asyncio.get_event_loop().create_task(deps.register_ack(eid, info, timeout_ms=t_ms))
                        except Exception:
                            pass
                    except Exception:
                        pass
                # Publish to Redis (best-effort) for Node SSE relay
                try:
                    asyncio.get_event_loop().create_task(deps.publish_relay_event(obj))
                except Exception:
                    pass
                event_q.put_nowait(json.dumps(obj))
            except Exception:
                pass
        
        try:
            try:
                print(f"[ws-chat] accepted project_id={project_id}")
            except Exception:
                pass
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"action": "chat", "content": raw}
            content = (payload.get("content") or "").strip()
            br_id = payload.get("branch_id")
            thr_id = payload.get("thread_id")
        except Exception:
            _enqueue({"type": "error", "error": "invalid payload"})
            try:
                await event_q.put(None)
                await sender_task
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
            return
        
        # Immediately inform client that the request is submitted and planning has started (for responsiveness)
        try:
            _enqueue({"type": "info", "stage": "submitted", "t": datetime.utcnow().isoformat()+"Z"})
            _enqueue({"type": "info", "stage": "planning", "t": datetime.utcnow().isoformat()+"Z"})
            try:
                print("[ws-chat] submitted+planning-sent-early")
            except Exception:
                pass
        except Exception:
            pass
        
        SessionLocal = sessionmaker(bind=deps.get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
        branch = None
        thr = None
        db = SessionLocal()
        try:
            deps.ensure_project_initialized(project_id)
            branch = deps.current_branch(db, project_id, int(br_id) if br_id is not None else None)
            if thr_id:
                try:
                    thr = db.query(deps.Thread).filter(deps.Thread.id == int(thr_id), deps.Thread.project_id == project_id).first()
                except Exception:
                    thr = None
            if not thr:
                thr = db.query(deps.Thread).filter(deps.Thread.project_id==project_id, deps.Thread.branch_id==branch.id, deps.Thread.title=="Ask").first()
                if not thr:
                    thr = deps.Thread(project_id=project_id, branch_id=branch.id, title="Ask")
                    db.add(thr); db.commit(); db.refresh(thr)
            # Capture branch context as plain values to avoid detached-instance refreshes later in tool closures
            try:
                branch_id_int = int(getattr(branch, 'id', 0)) if branch is not None else 0
            except Exception:
                branch_id_int = 0
            try:
                branch_name_str = str(getattr(branch, 'name', 'Main') or 'Main') if branch is not None else 'Main'
            except Exception:
                branch_name_str = 'Main'
            if content:
                db.add(deps.ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="user", content=content))
                db.commit()
                # Set thread title from the first 10 characters of the first prompt when thread has a default/placeholder title
                try:
                    title_now = (thr.title or '').strip()
                    if not title_now or title_now in {"Ask", "New Thread"} or title_now.startswith("File:") or title_now.startswith("DB:"):
                        new_title = (content.strip().splitlines()[0])[:10] or "(untitled)"
                        thr.title = new_title
                        db.commit()
                        try:
                            _enqueue({"type": "action", "function": "thread_update", "text": "Thread updated", "call": {"thread_id": thr.id, "title": new_title}, "thread_id": thr.id}, require_ack=True)
                        except Exception:
                            pass
                except Exception:
                    try: db.rollback()
                    except Exception: pass
                # Emit backend-driven user message and processing ACK (frontend only renders backend events)
                try:
                    _enqueue({"type": "message", "role": "user", "text": content, "thread_id": thr.id}, require_ack=True)
                except Exception:
                    pass
                try:
                    ack_text = "Processing…"
                    try:
                        fid_ack = payload.get("file_id") if isinstance(payload, dict) else None
                        if fid_ack is not None:
                            f_ack = db.query(deps.FileEntry).filter(deps.FileEntry.id == int(fid_ack), deps.FileEntry.project_id == project_id).first()
                            if f_ack and getattr(f_ack, 'display_name', None):
                                ack_text = f"Processing {f_ack.display_name}…"
                    except Exception:
                        pass
                    _enqueue({"type": "action", "function": "processing", "text": ack_text, "thread_id": thr.id}, require_ack=True)
                except Exception:
                    pass
        except Exception:
            try: db.rollback()
            except Exception: pass
        finally:
            try: db.close()
            except Exception: pass
        
        client, model = deps.llm_client_config()
        if not client:
            try:
                print("[ws-chat] missing-key")
            except Exception:
                pass
            db2 = SessionLocal()
            try:
                am = deps.ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", content="[llm-missing-key] Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY.")
                db2.add(am); db2.commit()
            except Exception:
                try: db2.rollback()
                except Exception: pass
            finally:
                try: db2.close()
                except Exception: pass
            _enqueue({"type": "error", "error": "missing_key"})
            try:
                await event_q.put(None)
                await sender_task
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
            return
        
        # Build context/resources/history using a fresh session
        db2 = SessionLocal()
        try:
            # Optional context from file/dataset
            fctx = None
            dctx = None
            try:
                fid = payload.get("file_id")
                if fid is not None:
                    fctx = db2.query(deps.FileEntry).filter(deps.FileEntry.id == int(fid), deps.FileEntry.project_id == project_id).first()
            except Exception:
                fctx = None
            try:
                did = payload.get("dataset_id")
                if did is not None:
                    dctx = db2.query(deps.Dataset).filter(deps.Dataset.id == int(did), deps.Dataset.project_id == project_id).first()
            except Exception:
                dctx = None
            
            ctx = {}
            if fctx:
                ctx["file"] = {
                    "display_name": fctx.display_name,
                    "file_type": fctx.file_type,
                    "structure": fctx.structure,
                    "ai_title": fctx.ai_title,
                    "ai_category": fctx.ai_category,
                    "ai_description": (fctx.ai_description or "")[:350],
                }
            if dctx:
                ctx["dataset"] = {
                    "name": dctx.name,
                    "description": (dctx.description or "")[:500]
                }
            
            # Build resources index (files/dbs) and recent thread history
            resources = {"files": [], "databases": []}
            history = []
            try:
                ids = deps.branch_filter_ids(db2, project_id, branch.id)
                recs = db2.query(deps.FileEntry).filter(deps.FileEntry.project_id==project_id, deps.FileEntry.branch_id.in_(ids)).order_by(deps.FileEntry.created_at.desc()).limit(200).all()
                for f in recs:
                    resources["files"].append({
                        "id": f.id,
                        "title": (f.ai_title or f.display_name or "").strip(),
                        "display_name": f.display_name,
                        "structure": f.structure,
                        "file_type": f.file_type,
                        "mime_type": f.mime_type,
                        "size_bytes": f.size_bytes,
                    })
                dsets = db2.query(deps.Dataset).filter(deps.Dataset.project_id==project_id, deps.Dataset.branch_id.in_(ids)).order_by(deps.Dataset.created_at.desc()).limit(200).all()
                for d in dsets:
                    resources["databases"].append({
                        "id": d.id,
                        "name": d.name,
                        "description": (d.description or "")[:500],
                    })
            except Exception:
                pass
            try:
                recent = db2.query(deps.ThreadMessage).filter(deps.ThreadMessage.project_id==project_id, deps.ThreadMessage.thread_id==thr.id).order_by(deps.ThreadMessage.created_at.desc()).limit(15).all()
                for m in reversed(recent):
                    history.append({
                        "role": m.role,
                        "title": (m.display_title or None),
                        "content": (m.content or "")[:2000]
                    })
            except Exception:
                pass
            
            # Gather Notes and Changelog (recent)
            notes = []
            try:
                recent_notes = db2.query(deps.Note).filter(deps.Note.project_id==project_id, deps.Note.branch_id==branch.id).order_by(deps.Note.created_at.desc()).limit(50).all()
                for n in reversed(recent_notes):
                    notes.append({"id": n.id, "tags": (n.tags or []), "content": (n.content or "")[:1000], "created_at": n.created_at.isoformat() if getattr(n, 'created_at', None) else None})
            except Exception:
                notes = []
            changelog = []
            try:
                with deps.RegistrySessionLocal() as reg:
                    ents = reg.query(deps.ChangelogEntry).filter(deps.ChangelogEntry.project_id==project_id, deps.ChangelogEntry.branch_id==branch.id).order_by(deps.ChangelogEntry.created_at.desc()).limit(50).all()
                    for ce in reversed(ents):
                        try:
                            when = ce.created_at.isoformat() if getattr(ce, 'created_at', None) else None
                        except Exception:
                            when = None
                        changelog.append({"when": when, "action": ce.action, "summary": (ce.summary_text or "")[:500]})
            except Exception:
                changelog = []
            
            # Research tool system prompt and examples
            # When chat_mode == single-shot, we override this with a simpler directive that returns plain text, not JSON.
            sys_prompt = """
You are an orchestrator that ALWAYS uses the LLM on each user prompt.

FIRST TURN POLICY: Your FIRST response MUST be a {"function":"plan"} object — no exceptions. Do NOT return 'final' or a standalone 'question' on the first turn. If clarification is needed, include a 'question' step as step 1 in the plan.

Plan requirements (STRICT JSON):
- The plan is an executable list of function steps (web, download, extract, image, db, code, notes, compose, question, final).
- The LLM may rewrite or refine the plan at any time based on tool results (adaptive planning).
- Schema for plan/steps:
  - function: 'plan' | 'web' | 'download' | 'extract' | 'image' | 'db' | 'code' | 'notes' | 'compose' | 'question' | 'final'
  - title, description, goal_outcome
  - status: 'in queue' | 'currently running' | 'done' | 'failed'
  - state: 'new plan' | 'diff change'
  - steps (for function=='plan'): non-empty array of step objects with the SAME fields above plus an 'args' object appropriate for that step's function.
  - output_to_user, changelog_summary.

Execution rules:
- We will execute steps in-order. For each step, you must return EXACTLY ONE function call with a fully-specified 'args'.
- When a step completes, set its status to 'done'. If a step needs more work, set status 'currently running' (or 'in process') and we will re-issue that step with the updated thread context. If the step fails, set 'failed' and either repair or rewrite the plan.
- Strongly prefer using 'web'+'download'+'extract' to gather sources, 'db' for queries/aggregation, and 'code' for local processing when it improves quality or precision. Do not fabricate results—ground answers via these functions when relevant.

PLANNING POLICY (strict):
- After the FIRST plan is accepted, do NOT emit a new 'plan' unless following the CURRENT plan would likely fail given the latest tool results/context.
- If the current plan is still valid, return ONE function call for the next step (not a new plan).
- If you conclude the plan would fail, you may return a single {"function":"plan"} with the revised steps; otherwise return the next function.

Response formatting:
- Respond with STRICT JSON only (no prose), one function object per turn.
- For 'code', include: language, packages (list), and source. For 'db', include: sql.
- When the user asks to write code, include a 'code' step (with language, packages, source) before 'final'.
- Always end the session with a single {"function":"final"} that includes args.text (answer), args.title (3–6 words), and args.run_summary (bulleted summary of actions and outcomes).
            """
            
            # If a file is focused, add upload policy notes so the plan avoids re-ingestion
            try:
                if ctx and isinstance(ctx, dict) and ctx.get('file') is not None:
                    sys_prompt = sys_prompt + "\n\nUPLOAD POLICY (strict):\n" + \
                        "- The file has already been saved, classified (structure + ai_*), and (if tabular) may already be imported. Do NOT repeat ingestion steps.\n" + \
                        "- If cleanup is needed for tabular data (e.g., header rows, wrong delimiter), propose a single 'tabular_import' tool call with explicit options (header_skip, delimiter, quotechar, encoding, date_formats, rename). The re-import should replace the existing table.\n" + \
                        "- Otherwise, prefer 'db' queries (schema overview, COUNT/AVG/etc.) against the per-file table.\n" + \
                        "- For non-tabular files, prefer retrieval/summarization over LangExtract chunks; avoid tabular steps.\n"
            except Exception:
                pass
            
            examples_json = {
                "plan": {
                    "function": "plan",
                    "title": "Analyze Files and Summarize",
                    "description": "Gather relevant files, extract key findings, compute simple stats, and write a short summary.",
                    "goal_outcome": "A concise answer with references to analyzed files",
                    "status": "in queue",
                    "state": "new plan",
                    "steps": [
                        {
                            "function": "web",
                            "title": "Search recent survey",
                            "description": "Find a relevant survey article to provide context",
                            "goal_outcome": "One authoritative survey URL",
                            "status": "in queue",
                            "state": "new plan",
                            "args": {"query": "site:nature.com CRISPR review 2024"}
                        },
                        {
                            "function": "download",
                            "title": "Download article",
                            "description": "Download the selected article for analysis",
                            "goal_outcome": "PDF saved to project files",
                            "status": "in queue",
                            "state": "new plan",
                            "args": {"urls": ["https://example.org/paper.pdf"]}
                        },
                        {
                            "function": "extract",
                            "title": "Extract claims/citations",
                            "description": "Extract key claims and references",
                            "goal_outcome": "Structured list of claims and citations",
                            "status": "in queue",
                            "state": "new plan",
                            "args": {"file_id": 123}
                        },
                        {
                            "function": "final",
                            "title": "Write the answer",
                            "description": "Produce the final answer",
                            "goal_outcome": "Clear, concise answer",
                            "status": "in queue",
                            "state": "new plan",
                            "args": {"text": "<answer>", "title": "<3-6 words>"}
                        }
                    ],
                    "output_to_user": "High-level plan with steps and intended tools",
                    "changelog_summary": "created plan"
                },
                "web": {"function": "web", "args": {"query": "site:nature.com CRISPR review 2024"}, "output_to_user": "Searched web", "changelog_summary": "web search"},
                "download": {"function": "download", "args": {"urls": ["https://example.org/paper.pdf"]}, "output_to_user": "Queued 1 download", "changelog_summary": "download requested"},
                "extract": {"function": "extract", "args": {"file_id": 123}, "output_to_user": "Extracted claims/citations", "changelog_summary": "extracted PDF"},
                "image": {"function": "image", "args": {"image_id": 42, "purpose": "chart reading"}, "output_to_user": "Analyzed image", "changelog_summary": "image analysis"},
                "db": {"function": "db", "args": {"sql": "SELECT COUNT(*) FROM claims"}, "output_to_user": "Ran SQL", "changelog_summary": "db query"},
                "code": {"function": "code", "args": {"language": "python", "packages": ["pandas"], "source": "print(2+2)"}, "output_to_user": "Executed code", "changelog_summary": "code run"},
                "shell": {"function": "shell", "args": {"script": "echo hello"}, "output_to_user": "Ran shell", "changelog_summary": "shell run"},
                "notes": {"function": "notes", "args": {"themes": [{"name": "Risks", "notes": ["…"]}]}, "output_to_user": "Saved notes", "changelog_summary": "notes saved"},
                "compose": {"function": "compose", "args": {"sections": [{"title": "Intro", "text": "…"}]}, "output_to_user": "Drafted section(s)", "changelog_summary": "compose partial"},
                "tabular_import": {"function": "tabular_import", "args": {"file_id": 123, "options": {"header_skip": 1, "delimiter": ","}}, "output_to_user": "Re-imported tabular data", "changelog_summary": "tabular re-import"},
                "question": {"function": "question", "args": {"text": "Which domain do you care about?"}, "output_to_user": "Need clarification", "changelog_summary": "asked user"},
                "final": {"function": "final", "args": {"text": "2+2=4", "title": "Simple Arithmetic", "run_summary": ["Trivial query detected; skipped planning.", "No tools executed.", "No files created; no DB changes."]}, "output_to_user": "2+2=4", "changelog_summary": "finalized answer"}
            }
            
            # Allow replay mode: if the payload provides a full messages array, use it instead of building
            replay_messages = None
            try:
                if isinstance(payload, dict) and payload.get('replay_messages'):
                    replay_messages = payload.get('replay_messages')
            except Exception:
                replay_messages = None
            
            # In-session plan tracking (steps, pointer)
            plan_ctx: Dict[str, Any] = {"steps": [], "ptr": None}
            plan_seen = False
            forced_submit_once = False
            
            # Build LLM messages (orchestrated mode)
            if replay_messages:
                messages = replay_messages
            else:
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": "Resources (files, databases):"},
                    {"role": "user",   "content": json.dumps(resources, ensure_ascii=False)},
                    {"role": "user",   "content": "History (recent thread messages):"},
                    {"role": "user",   "content": json.dumps(history, ensure_ascii=False)},
                    {"role": "user",   "content": "Notes (recent):"},
                    {"role": "user",   "content": json.dumps(notes, ensure_ascii=False)},
                    {"role": "user",   "content": "Changelog (recent):"},
                    {"role": "user",   "content": json.dumps(changelog, ensure_ascii=False)}
                ]
                if ctx:
                    try:
                        messages.append({"role": "user", "content": "Context (focused file/DB):"})
                        messages.append({"role": "user", "content": json.dumps(ctx, ensure_ascii=False)})
                    except Exception:
                        pass
                # Include plan state so the model can judge whether replanning is necessary
                try:
                    messages.append({"role": "user", "content": "Plan state (JSON):"})
                    messages.append({"role": "user", "content": json.dumps({"steps": plan_ctx.get("steps") or [], "ptr": plan_ctx.get("ptr")}, ensure_ascii=False)})
                    messages.append({"role": "user", "content": "Plan policy (strict): Do NOT emit a new 'plan' unless following the current plan would likely fail. If plan remains valid, return ONE function call for the next step."})
                except Exception:
                    pass
                messages.append({"role": "user", "content": "Functions and examples:"})
                try:
                    messages.append({"role": "user", "content": json.dumps(examples_json, ensure_ascii=False)})
                except Exception:
                    messages.append({"role": "user", "content": "{\"error\":\"examples unavailable\"}"})
                messages.append({"role": "user", "content": content})
            
            # Emit the prepared prompt so the UI can show an "assistant prompt" bubble with full JSON
            try:
                _enqueue({"type": "prompt", "messages": messages, "thread_id": thr.id}, require_ack=True)
            except Exception:
                pass
            
            # Persist the prepared prompt for replay across app restarts
            try:
                dbpmsg = SessionLocal()
                dbpmsg.add(deps.ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title="Assistant", content="Prepared LLM prompt", payload_json=messages))
                dbpmsg.commit()
            except Exception:
                try: dbpmsg.rollback()
                except Exception: pass
            finally:
                try: dbpmsg.close()
                except Exception: pass
        
        except Exception as e:
            import traceback as _tb
            try:
                print(f"[ws-chat-build-error] {type(e).__name__}: {e}\n" + "".join(_tb.format_exception(type(e), e, e.__traceback__))[-1500:])
            except Exception:
                pass
            try:
                _enqueue({"type": "error", "error": f"{type(e).__name__}: {e}"})
            except Exception:
                pass
            try:
                await event_q.put(None)
                await sender_task
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
            return
        finally:
            try:
                db2.close()
            except Exception:
                pass
        
        # Optional: emit debug prompt for testing
        try:
            if bool(payload.get('debug')):
                _enqueue({"type": "debug", "prompt": messages})
                try:
                    print("[ws-chat] debug-sent")
                except Exception:
                    pass
        except Exception as e:
            try:
                print(f"[ws-chat-debug-error] {type(e).__name__}: {e}")
            except Exception:
                pass

        # -----------------------------
        # M4: Fan-out/fan-in over components
        # -----------------------------
        import time as _time
        from cedar_components import registry as _reg
        # Ensure components are imported to register themselves
        try:
            import cedar_components.example.summarize  # noqa: F401
            import cedar_components.retrieval.retrieve_docs  # noqa: F401
        except Exception:
            pass

        # Select candidate components (simple heuristic for now)
        candidates = []
        try:
            # Always try summarize; retrieval based on content length
            candidates.append("example.summarize")
            if len(content or "") > 0:
                candidates.append("retrieval.retrieve_docs")
        except Exception:
            candidates = ["example.summarize"]
        # De-dup and keep order
        seen = set(); cand = []
        for n in candidates:
            if n not in seen:
                seen.add(n); cand.append(n)

        # Dispatch concurrently with per-component timeouts
        try:
            timeout_s = int(os.getenv("CEDARPY_COMPONENT_TIMEOUT_SECONDS", "15"))
        except Exception:
            timeout_s = 15

        async def _run_component(name: str):
            t0 = _time.time()
            try:
                _enqueue({"type": "action", "function": "component", "text": f"Dispatch {name}", "call": {"component": name}, "thread_id": thr.id}, require_ack=True)
            except Exception:
                pass
            try:
                res = await asyncio.wait_for(_reg.invoke(name, {"text": content, "query": content}, ctx={"project_id": project_id} and None or None), timeout=timeout_s)  # type: ignore[arg-type]
            except asyncio.TimeoutError:
                dt = int((_time.time() - t0) * 1000)
                return {"name": name, "ok": False, "status": "timeout", "duration_ms": dt, "debug": None, "content": None, "error": f"timeout after {timeout_s}s"}
            except Exception as e:
                dt = int((_time.time() - t0) * 1000)
                return {"name": name, "ok": False, "status": "error", "duration_ms": dt, "debug": None, "content": None, "error": f"{type(e).__name__}: {e}"}
            # Normalize ComponentResult -> dict
            try:
                dt = res.duration_ms or int((_time.time() - t0) * 1000)
                dbg = res.debug if hasattr(res, 'debug') else None
                return {"name": name, "ok": bool(res.ok), "status": res.status, "duration_ms": dt, "debug": dbg, "content": res.content, "error": res.error}
            except Exception:
                dt = int((_time.time() - t0) * 1000)
                return {"name": name, "ok": False, "status": "error", "duration_ms": dt, "debug": None, "content": None, "error": "invalid component result"}

        tasks = [asyncio.create_task(_run_component(n)) for n in cand]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Emit per-component debug and completion events
        for r in results:
            try:
                if r.get("debug") and isinstance(r["debug"], dict) and r["debug"].get("prompt"):
                    _enqueue({"type": "debug", "prompt": r["debug"]["prompt"], "component": r["name"], "thread_id": thr.id})
            except Exception:
                pass
            try:
                txt = f"{r['name']} {'ok' if r.get('ok') else r.get('status')}"
                _enqueue({"type": "action", "function": "component_result", "text": txt, "call": {"component": r['name'], "status": r.get('status'), "error": r.get('error')}, "thread_id": thr.id}, require_ack=True)
            except Exception:
                pass

        # Simple aggregator stub: prefer example.summarize summary; else compose basic text
        final_text = None
        final_title = None
        try:
            for r in results:
                if r["name"] == "example.summarize" and isinstance(r.get("content"), dict):
                    s = r["content"].get("summary") if isinstance(r["content"], dict) else None
                    if isinstance(s, str) and s.strip():
                        final_text = s.strip()
                        final_title = "Summary"
                        break
        except Exception:
            pass
        if not final_text:
            # Fallback aggregation (no fabrication: present minimal info)
            final_text = (content or "").strip()[:200] or "Done."
            final_title = "Assistant"

        final_json = {"function": "final", "args": {"text": final_text, "title": final_title, "run_summary": [f"components: {', '.join(cand)}"]}}

        try:
            _enqueue({"type": "final", "text": final_text, "json": final_json, "thread_id": thr.id}, require_ack=True)
        except Exception:
            pass

        try:
            await event_q.put(None)
            await sender_task
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
