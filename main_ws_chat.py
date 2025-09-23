import os
import io
import re
import json
import mimetypes
import sqlite3
import subprocess
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState
from sqlalchemy.orm import sessionmaker, Session


class WSDeps:
    def __init__(self, **kwargs):
        self.get_project_engine = kwargs["get_project_engine"]
        self.ensure_project_initialized = kwargs["ensure_project_initialized"]
        self.record_changelog = kwargs["record_changelog"]
        self.llm_client_config = kwargs["llm_client_config"]
        self.tabular_import_via_llm = kwargs["tabular_import_via_llm"]
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
    try:
        if getattr(ws, 'client_state', None) != WebSocketState.CONNECTED:
            return False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Outside of loop; allow send attempt to raise and be caught below
            pass
        try:
            return bool((await ws.send_text(text)) or True)  # type: ignore[misc]
        except RuntimeError:
            return False
        except Exception:
            return False
    except Exception:
        return False


def register_ws_chat(app, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    async def ws_chat_stream(websocket: WebSocket, project_id: int):  # noqa: C901
        await websocket.accept()
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
            try:
                if require_ack:
                    try:
                        eid = uuid.uuid4().hex
                        obj['eid'] = eid
                        try:
                            if ('thread_id' not in obj or obj.get('thread_id') is None):
                                pass
                        except Exception:
                            pass
                        info = { 'type': obj.get('type'), 'function': obj.get('function'), 'thread_id': obj.get('thread_id') }
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

        # The rest of ws_chat_stream is intentionally left in main.py in prior refactor steps.
        # For this extraction step, we keep a minimal stub that emits a final message to ensure route wiring works.
        try:
            _enqueue({"type": "final", "text": "Stub: WS chat route is registered.", "thread_id": thr.id}, require_ack=True)
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

    # Register route on the app
    app.add_api_websocket_route(route_path, ws_chat_stream)
