"""
Ask orchestrator module for Cedar app.
Handles the "Ask" feature with LLM integration and tool execution.
"""

import os
import json
import sqlite3
import contextlib
import io
import re
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db_utils import _get_project_engine, ensure_project_initialized
from ..llm_utils import llm_client_config as _llm_client_config
from ..changelog_utils import record_changelog
from main_models import (
    Project, Branch, Thread, ThreadMessage, FileEntry, 
    Dataset, Note, ChangelogEntry
)
from main_helpers import (
    current_branch, add_version, branch_filter_ids
)


def ask_orchestrator(app, project_id: int, request: Request, query: str, db: Session):
    """
    Bottom-of-page "Ask" orchestrator. Builds a context-rich prompt, expects strict JSON with function calls,
    executes tools, and iterates until final/question. Keys are read from ~/CedarPyData/.env.
    Function calls supported: sql, grep, code (python), img, web, plan, notes, question, final.
    """
    try:
        print(f"[ask-orchestrator] START project_id={project_id} query='{query[:100]}...'" if len(query) > 100 else f"[ask-orchestrator] START project_id={project_id} query='{query}'")
    except Exception:
        pass
    
    ensure_project_initialized(project_id)
    
    # Derive branch
    branch_q = request.query_params.get("branch_id")
    try:
        branch_q = int(branch_q) if branch_q is not None else None
    except Exception:
        branch_q = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_q)

    # Find or create a dedicated Ask thread
    thr = db.query(Thread).filter(
        Thread.project_id==project.id, 
        Thread.branch_id==branch.id, 
        Thread.title=="Ask"
    ).first()
    
    if not thr:
        thr = Thread(project_id=project.id, branch_id=branch.id, title="Ask")
        db.add(thr)
        db.commit()
        db.refresh(thr)
        add_version(db, "thread", thr.id, {
            "project_id": project.id, 
            "branch_id": branch.id, 
            "title": thr.title
        })

    # Persist user query
    um = ThreadMessage(
        project_id=project.id, 
        branch_id=branch.id, 
        thread_id=thr.id, 
        role="user", 
        content=query
    )
    db.add(um)
    db.commit()

    # Helper functions for context
    def _files_index(limit: int = 500) -> List[Dict[str, Any]]:
        ids = branch_filter_ids(db, project.id, branch.id)
        recs = db.query(FileEntry).filter(
            FileEntry.project_id==project.id, 
            FileEntry.branch_id.in_(ids)
        ).order_by(FileEntry.created_at.desc()).limit(limit).all()
        
        out: List[Dict[str, Any]] = []
        for f in recs:
            out.append({
                "id": f.id,
                "title": (f.ai_title or f.display_name or "").strip(),
                "display_name": f.display_name,
                "structure": f.structure,
                "file_type": f.file_type,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
            })
        return out

    def _recent_changelog(limit: int = 50) -> List[Dict[str, Any]]:
        recs = db.query(ChangelogEntry).filter(
            ChangelogEntry.project_id==project.id, 
            ChangelogEntry.branch_id==branch.id
        ).order_by(ChangelogEntry.created_at.desc()).limit(limit).all()
        
        out: List[Dict[str, Any]] = []
        for c in recs:
            out.append({
                "id": c.id,
                "when": c.created_at.isoformat() if c.created_at else None,
                "action": c.action,
                "summary": c.summary_text,
            })
        return out

    def _recent_assistant_msgs(limit: int = 10) -> List[Dict[str, Any]]:
        recs = db.query(ThreadMessage).filter(
            ThreadMessage.project_id==project.id, 
            ThreadMessage.branch_id==branch.id, 
            ThreadMessage.role.in_(["Chief Agent", "Assistant"])  # backwards compatibility
        ).order_by(ThreadMessage.created_at.desc()).limit(limit).all()
        
        out: List[Dict[str, Any]] = []
        for m in recs:
            out.append({
                "when": m.created_at.isoformat() if m.created_at else None,
                "title": m.display_title,
                "content": m.content[:2000] if m.content else "",
            })
        return out

    client, model = _llm_client_config()
    if not client:
        am = ThreadMessage(
            project_id=project.id, 
            branch_id=branch.id, 
            thread_id=thr.id, 
            role="Chief Agent", 
            display_title="LLM key missing", 
            content="Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY in ~/CedarPyData/.env; see README"
        )
        db.add(am)
        db.commit()
        return RedirectResponse(
            f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}&msg=Missing+OpenAI+key", 
            status_code=303
        )

    # System prompt and schema
    sys_prompt = (
        "You are Cedar's orchestrator. Always respond with STRICT JSON (no prose outside JSON).\n"
        "Schema: { \"Text Visible To User\": string, \"function_calls\": [ { \"name\": one of [sql, grep, code, img, web, plan, notes, question, final], \"args\": object } ] }\n"
        "Rules:\n"
        "- \"Text Visible To User\" is REQUIRED and MUST be non-empty. It should EITHER (a) state the answer succinctly OR (b) state the concrete steps you are taking to get the answer.\n"
        "- Use sql to query the project's SQLite database (use sqlite_master/PRAGMA to introspect).\n"
        "- Use grep with {file_id, pattern, flags?} to search a specific file by id.\n"
        "- Use code with {language:'python', source:'...'}; helpers available: cedar.query(sql), cedar.read(file_id), cedar.list_files(), cedar.open_path(file_id), cedar.note(text,[tags]).\n"
        "- Use img with {image_id, purpose} to analyze an image file; an inline data URL is provided.\n"
        "- Use web with {url} to fetch HTML.\n"
        "- Use plan with {steps:[...]}; we will iterate steps.\n"
        "- Use notes with {content, tags?} to store notes.\n"
        "- Use question with {text} to ask the user and then stop.\n"
        "- Use final with {text} for the final output and then stop.\n"
    )

    example = {
        "Text Visible To User": "Working on it…",
        "function_calls": [
            {"name": "sql", "args": {"sql": "SELECT name FROM sqlite_master WHERE type='table'"}}
        ]
    }

    context_obj = {
        "files_index": _files_index(),
        "recent_changelog": _recent_changelog(),
        "recent_assistant_messages": _recent_assistant_msgs(),
        "project": {"id": project.id, "title": project.title},
        "branch": {"id": branch.id, "name": branch.name}
    }

    def _call_llm(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            print(f"[ask-llm] Calling model={model} with {len(messages)} messages")
            resp = client.chat.completions.create(model=model, messages=messages)
            raw = (resp.choices[0].message.content or "").strip()
            result = json.loads(raw)
            print(f"[ask-llm] Response: {json.dumps(result)[:200]}..." if len(json.dumps(result)) > 200 else f"[ask-llm] Response: {json.dumps(result)}")
            return result
        except Exception as e:
            try: 
                print(f"[ask-llm-error] {type(e).__name__}: {e}")
            except Exception: 
                pass
            return None

    # Tool executors
    def _exec_sql(sql_text: str) -> Dict[str, Any]:
        try:
            eng = _get_project_engine(project.id)
            with eng.begin() as conn:
                result = conn.exec_driver_sql(sql_text)
                cols = list(result.keys()) if hasattr(result, 'keys') else []
                rows = []
                for r in result.fetchall()[:200]:
                    rows.append(dict(zip(cols, r)) if cols else list(r))
            return {"ok": True, "columns": cols, "rows": rows}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_grep(file_id: int, pattern: str, flags: str = "") -> Dict[str, Any]:
        try:
            f = db.query(FileEntry).filter(
                FileEntry.id==file_id, 
                FileEntry.project_id==project.id
            ).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return {"ok": False, "error": "file not found"}
            
            with open(f.storage_path, 'r', encoding='utf-8', errors='replace') as fh:
                lines = fh.readlines()
            
            re_flags = 0
            if 'i' in flags: re_flags |= re.IGNORECASE
            if 'm' in flags: re_flags |= re.MULTILINE
            if 's' in flags: re_flags |= re.DOTALL
            
            matches = []
            for i, line in enumerate(lines):
                if re.search(pattern, line, re_flags):
                    matches.append({"line": i+1, "text": line.rstrip()})
            
            return {"ok": True, "matches": matches[:500]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_code(source: str) -> Dict[str, Any]:
        # Cedar helper object for code execution
        class CedarHelper:
            def query(self, sql: str):
                return _exec_sql(sql)
            
            def list_files(self):
                return _files_index(100)
            
            def read(self, file_id: int):
                f = db.query(FileEntry).filter(
                    FileEntry.id==file_id, 
                    FileEntry.project_id==project.id
                ).first()
                if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                    return None
                with open(f.storage_path, 'r', encoding='utf-8', errors='replace') as fh:
                    return fh.read()
            
            def open_path(self, file_id: int):
                f = db.query(FileEntry).filter(
                    FileEntry.id==file_id, 
                    FileEntry.project_id==project.id
                ).first()
                if not f or not f.storage_path:
                    return None
                return f.storage_path
            
            def note(self, text: str, tags=None):
                return _exec_notes(text, tags)
        
        cedar = CedarHelper()
        logs = io.StringIO()
        safe_globals: Dict[str, Any] = {
            "__builtins__": {
                "print": print, "len": len, "range": range, 
                "str": str, "int": int, "float": float, "bool": bool, 
                "list": list, "dict": dict, "set": set, "tuple": tuple
            }, 
            "cedar": cedar, 
            "sqlite3": sqlite3, 
            "json": json, 
            "re": re, 
            "io": io
        }
        
        try:
            with contextlib.redirect_stdout(logs):
                exec(compile(source, filename="<ask_code>", mode="exec"), safe_globals, safe_globals)
            log_output = logs.getvalue()
            print(f"[ask-exec-code] Success! Output: {log_output[:200]}..." if len(log_output) > 200 else f"[ask-exec-code] Success! Output: {log_output}")
        except Exception as e:
            print(f"[ask-exec-code] Failed: {type(e).__name__}: {e}")
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "logs": logs.getvalue()}
        
        return {"ok": True, "logs": logs.getvalue()}

    def _exec_web(url: str) -> Dict[str, Any]:
        try:
            import urllib.request as _req
            with _req.urlopen(url, timeout=20) as resp:
                ct = resp.headers.get('Content-Type','')
                body = resp.read()
            txt = body.decode('utf-8', errors='replace')
            return {"ok": True, "content_type": ct, "text": txt[:200000]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_img(image_id: int, purpose: str = "") -> Dict[str, Any]:
        try:
            f = db.query(FileEntry).filter(
                FileEntry.id==int(image_id), 
                FileEntry.project_id==project.id
            ).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return {"ok": False, "error": "image not found"}
            
            with open(f.storage_path, 'rb') as fh:
                b = fh.read()
            ext = (os.path.splitext(f.storage_path)[1].lower() or ".png").lstrip('.')
            mime = f.mime_type or ("image/" + (ext if ext in {"png","jpeg","jpg","webp","gif"} else "png"))
            data_url = f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"
            return {"ok": True, "image_id": f.id, "purpose": purpose, "data_url_head": data_url[:120000]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_notes(content: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            n = Note(project_id=project.id, branch_id=branch.id, content=str(content), tags=tags)
            db.add(n)
            db.commit()
            db.refresh(n)
            return {"ok": True, "note_id": n.id}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # First LLM call
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Context:"},
        {"role": "user", "content": json.dumps(context_obj, ensure_ascii=False)},
    ]
    
    # If focused file is tabular, instruct model to import it into SQL DB first via code
    # (This would require additional context that isn't passed - simplified for now)
    
    messages.extend([
        {"role": "user", "content": "Schema and rules (example):"},
        {"role": "user", "content": json.dumps(example, ensure_ascii=False)},
        {"role": "user", "content": query},
    ])

    loop_count = 0
    final_text: Optional[str] = None
    question_text: Optional[str] = None
    last_response: Optional[Dict[str, Any]] = None
    last_text_visible: str = ""
    last_tool_summary: str = ""

    while loop_count < 6:
        loop_count += 1
        print(f"[ask-orchestrator] Loop {loop_count}/6")
        resp = _call_llm(messages)
        if not resp:
            print(f"[ask-orchestrator] No response from LLM, breaking loop")
            break
        
        last_response = resp
        try:
            db.add(ThreadMessage(
                project_id=project.id, 
                branch_id=branch.id, 
                thread_id=thr.id, 
                role="Chief Agent", 
                content=json.dumps(resp, ensure_ascii=False), 
                display_title="Ask: JSON"
            ))
            db.commit()
        except Exception:
            db.rollback()
        
        # If the assistant provided a Thread_title, update the thread's title
        try:
            tt = str((resp or {}).get("Thread_title") or "").strip()
            if tt:
                thr_db = db.query(Thread).filter(
                    Thread.id == thr.id, 
                    Thread.project_id == project.id
                ).first()
                if thr_db:
                    thr_db.title = tt[:100]
                    db.commit()
        except Exception:
            try: 
                db.rollback()
            except Exception: 
                pass

        text_visible = str(resp.get("Text Visible To User") or "").strip()
        last_text_visible = text_visible or last_text_visible
        calls = resp.get("function_calls") or []
        tool_results: List[Dict[str, Any]] = []

        for call in calls:
            name = str(call.get("name") or "").strip().lower()
            args = call.get("args") or {}
            print(f"[ask-orchestrator] Executing tool: {name} with args: {json.dumps(args)[:100]}..." if len(json.dumps(args)) > 100 else f"[ask-orchestrator] Executing tool: {name} with args: {json.dumps(args)}")
            
            out: Dict[str, Any] = {"name": name, "ok": False, "result": None}
            
            if name == "sql":
                out["result"] = _exec_sql(str(args.get("sql") or ""))
            elif name == "grep":
                out["result"] = _exec_grep(
                    int(args.get("file_id")), 
                    str(args.get("pattern") or ""), 
                    str(args.get("flags") or "")
                )
            elif name == "code":
                if str(args.get("language") or "").lower() == "python":
                    out["result"] = _exec_code(str(args.get("source") or ""))
                else:
                    out["result"] = {"ok": False, "error": "unsupported language"}
            elif name == "img":
                out["result"] = _exec_img(
                    int(args.get("image_id")), 
                    str(args.get("purpose") or "")
                )
            elif name == "web":
                out["result"] = _exec_web(str(args.get("url") or ""))
            elif name == "plan":
                steps = args.get("steps") or []
                out["result"] = _exec_notes(
                    "Plan steps:\n" + "\n".join([str(s) for s in steps]), 
                    ["plan"]
                )
            elif name == "notes":
                out["result"] = _exec_notes(
                    str(args.get("content") or ""), 
                    args.get("tags")
                )
            elif name == "question":
                question_text = str(args.get("text") or text_visible or "I have a question for you.")
                final_text = None
            elif name == "final":
                final_text = str(args.get("text") or text_visible or "Done.")
            else:
                out["result"] = {"ok": False, "error": f"unknown function: {name}"}
            
            r = out.get("result")
            if isinstance(r, dict):
                out["ok"] = bool(r.get("ok", True))
            tool_results.append(out)

        if question_text or final_text:
            break

        # Summarize tools run for potential fallback rendering
        try:
            last_tool_summary = "Tools run: " + ", ".join([str((tr or {}).get("name") or "?") for tr in tool_results])
        except Exception:
            last_tool_summary = last_tool_summary or ""

        messages.append({"role": "user", "content": "ToolResults:"})
        messages.append({"role": "user", "content": json.dumps({"tool_results": tool_results}, ensure_ascii=False)})
        if text_visible:
            messages.append({"role": "user", "content": text_visible})

    show_msg = (
        final_text or question_text or 
        (last_text_visible.strip() if last_text_visible and last_text_visible.strip() else "") or 
        ((last_response and str(last_response.get("Text Visible To User") or "").strip()) or "") or 
        (last_tool_summary if last_tool_summary else "(no response)")
    )

    print(f"[ask-orchestrator] Final message: {show_msg[:200]}..." if len(show_msg) > 200 else f"[ask-orchestrator] Final message: {show_msg}")
    
    am = ThreadMessage(
        project_id=project.id, 
        branch_id=branch.id, 
        thread_id=thr.id, 
        role="assistant", 
        display_title=("Ask • Final" if final_text else ("Ask • Question" if question_text else "Ask • Update")), 
        content=show_msg
    )
    db.add(am)
    db.commit()

    try:
        input_payload = {"query": query}
        output_payload = {"final": final_text, "question": question_text}
        record_changelog(db, project.id, branch.id, "ask.orchestrator", input_payload, output_payload)
    except Exception:
        pass

    dest_msg = "Answer+ready" if final_text else ("Question+for+you" if question_text else "Ask+updated")
    return RedirectResponse(
        f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}&msg={dest_msg}", 
        status_code=303
    )