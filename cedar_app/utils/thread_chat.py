"""
Thread chat module for Cedar app.
Handles chat message submission with LLM integration.
"""

import json
from typing import Optional
from datetime import datetime
from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db_utils import ensure_project_initialized
from ..llm_utils import llm_client_config as _llm_client_config
from ..changelog_utils import record_changelog
from main_models import (
    Project, Branch, Thread, ThreadMessage, FileEntry, 
    Dataset
)
from main_helpers import (
    current_branch, add_version, branch_filter_ids
)


def thread_chat(project_id: int, request: Request, content: str, thread_id: Optional[str], 
                file_id: Optional[str], dataset_id: Optional[str], db: Session):
    """
    Submit a chat message in the selected thread; includes file metadata context to LLM.
    Requires OpenAI API key; see README for setup. Verbose errors are surfaced to the UI/log.
    """
    ensure_project_initialized(project_id)
    # derive branch context
    branch_q = request.query_params.get("branch_id")
    try:
        branch_q = int(branch_q) if branch_q is not None else None
    except Exception:
        branch_q = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_q)

    # Parse optional ids safely (empty strings -> None)
    thr_id_val: Optional[int] = None
    if thread_id is not None and str(thread_id).strip() != "":
        try:
            thr_id_val = int(str(thread_id).strip())
        except Exception:
            thr_id_val = None
    file_id_val: Optional[int] = None
    if file_id is not None and str(file_id).strip() != "":
        try:
            file_id_val = int(str(file_id).strip())
        except Exception:
            file_id_val = None
    dataset_id_val: Optional[int] = None
    if dataset_id is not None and str(dataset_id).strip() != "":
        try:
            dataset_id_val = int(str(dataset_id).strip())
        except Exception:
            dataset_id_val = None

    # Resolve thread; if missing, auto-create a default one
    thr = None
    if thr_id_val:
        try:
            thr = db.query(Thread).filter(Thread.id == thr_id_val, Thread.project_id == project.id).first()
        except Exception:
            thr = None
    if not thr:
        thr = Thread(project_id=project.id, branch_id=branch.id, title="New Thread")
        db.add(thr)
        db.commit()
        db.refresh(thr)

    # Persist user message
    um = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="user", content=content)
    db.add(um)
    db.commit()

    # Build file metadata context if provided
    fctx = None
    if file_id_val:
        try:
            fctx = db.query(FileEntry).filter(FileEntry.id == file_id_val, FileEntry.project_id == project.id).first()
        except Exception:
            fctx = None
    dctx = None
    if dataset_id_val:
        try:
            dctx = db.query(Dataset).filter(Dataset.id == dataset_id_val, Dataset.project_id == project.id).first()
        except Exception:
            dctx = None

    # LLM call (OpenAI). See README for keys setup. No fallbacks; verbose errors.
    reply_text = None
    reply_title = None
    reply_payload = None
    client, model = _llm_client_config()
    if not client:
        reply_text = "[llm-missing-key] Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY."
    else:
        try:
            sys_prompt = (
                "This is a research and coding tool to collect/analyze data and build reports and visuals.\n"
                "You have multiple tools: web, download, extract, image, db, code, shell, notes, compose, question, final.\n"
                "FIRST TURN POLICY: Your FIRST response MUST be a {\"function\":\"plan\"} object — no exceptions.\n"
                "If user information is needed, include a 'question' as the first step in the plan; do NOT return a standalone question.\n"
                "When the user asks to write code, your plan MUST include a 'code' step with language, packages, and source, followed by a 'final'.\n"
                "Output STRICT JSON for every response (no prose) and include output_to_user and changelog_summary when appropriate.\n"
                "Also include a field named Thread_title with a concise (<=5 words) title for this conversation.\n"
                "We pass Resources (files/dbs), History (recent conversation), and Context (selected file/DB) with each query.\n"
                "All data systems are queriable via db/download/extract/code — provide concrete, executable specs.\n"
            )

            # Build context JSON
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

            # Resources (files/dbs) and history
            resources = {"files": [], "databases": []}
            history = []
            try:
                ids = branch_filter_ids(db, project.id, branch.id)
                recs = db.query(FileEntry).filter(FileEntry.project_id==project.id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(200).all()
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
                dsets = db.query(Dataset).filter(Dataset.project_id==project.id, Dataset.branch_id.in_(ids)).order_by(Dataset.created_at.desc()).limit(200).all()
                for d in dsets:
                    resources["databases"].append({
                        "id": d.id,
                        "name": d.name,
                        "description": (d.description or "")[:500],
                    })
            except Exception:
                pass
            try:
                recent = db.query(ThreadMessage).filter(ThreadMessage.project_id==project.id, ThreadMessage.thread_id==thr.id).order_by(ThreadMessage.created_at.desc()).limit(15).all()
                for m in reversed(recent):
                    history.append({
                        "role": m.role,
                        "title": (m.display_title or None),
                        "content": (m.content or "")[:2000]
                    })
            except Exception:
                pass

            # Keep example code out of inline JSON literal to avoid string-escape issues
            EXAMPLE_TABULAR_SOURCE = '''import base64
import io as _io
import pandas as pd

# Read file contents by id (text or base64)
RAW = cedar.read(123)  # replace 123 with actual file_id
if isinstance(RAW, str) and RAW.startswith('base64:'):
    RAW = base64.b64decode(RAW[7:]).decode('utf-8', errors='replace')

# Parse CSV (adjust for TSV or other delimiters as needed)
df = pd.read_csv(_io.StringIO(RAW))

# Derive a simple table name and create table with basic types
TABLE = 'tabular_file'
cols = []
for name, dtype in zip(df.columns, df.dtypes):
    col = str(name).strip().replace(' ', '_')
    sqlt = 'REAL' if str(dtype).lower().startswith(('float','int')) else 'TEXT'
    cols.append(col + ' ' + sqlt)
cedar.query('CREATE TABLE IF NOT EXISTS ' + TABLE + ' (' + ', '.join(cols) + ')')

# Insert all rows
for _, row in df.iterrows():
    names = [str(c).strip().replace(' ', '_') for c in df.columns]
    vals = []
    for v in row.values.tolist():
        if v is None or (isinstance(v, float) and (v != v)):
            vals.append('NULL')
        elif isinstance(v, (int, float)):
            vals.append(str(v))
        else:
            s = str(v).replace("'", "''")
            vals.append("'" + s + "'")
    cedar.query('INSERT INTO ' + TABLE + ' (' + ', '.join(names) + ') VALUES (' + ', '.join(vals) + ')')

print('imported rows:', len(df))'''

            examples_json = {
                "plan": {
                    "function": "plan",
                    "title": "Research and draft",
                    "description": "Gather info/files, analyze, and produce an answer.",
                    "goal_outcome": "A concise answer grounded in data",
                    "status": "in queue",
                    "state": "new plan",
                    "steps": [
                        {"function": "web", "title": "Search", "description": "Find background", "goal_outcome": "authoritative link", "status": "in queue", "state": "new plan", "args": {"query": "example query"}},
                        {"function": "code", "title": "Compute", "description": "Run Python analysis", "goal_outcome": "computed result", "status": "in queue", "state": "new plan", "args": {"language": "python", "packages": ["numpy"], "source": "print(2+2)"}},
                        {"function": "final", "title": "Write answer", "description": "Deliver final", "goal_outcome": "Clear answer", "status": "in queue", "state": "new plan", "args": {"text": "<answer>", "title": "<3-6 words>"}}
                    ],
                    "output_to_user": "Plan with steps and tools",
                    "changelog_summary": "created plan"
                },
                "web": {"function": "web", "args": {"query": "example query"}, "output_to_user": "Searched web", "changelog_summary": "web search"},
                "download": {"function": "download", "args": {"urls": ["https://example.org/a.pdf"]}, "output_to_user": "Downloading 1 file", "changelog_summary": "download start"},
                "extract": {"function": "extract", "args": {"file_id": 1}, "output_to_user": "Extracted claims/citations", "changelog_summary": "extract done"},
                "image": {"function": "image", "args": {"image_id": 2, "purpose": "diagram analysis"}, "output_to_user": "Analyzed image", "changelog_summary": "image"},
                "db": {"function": "db", "args": {"sql": "SELECT COUNT(*) FROM citations"}, "output_to_user": "Ran SQL", "changelog_summary": "db query"},
                "code": {"function": "code", "args": {"language": "python", "packages": ["pandas"], "source": "print(2+2)"}, "output_to_user": "Executed code", "changelog_summary": "code run"},
                "code_tabular_import": {"function": "code", "args": {"language": "python", "packages": ["pandas"], "source": EXAMPLE_TABULAR_SOURCE}, "output_to_user": "Imported tabular file into SQL", "changelog_summary": "tabular import"},
                "shell": {"function": "shell", "args": {"script": "echo hello"}, "output_to_user": "Ran shell", "changelog_summary": "shell"},
                "notes": {"function": "notes", "args": {"themes": [{"name": "Background", "notes": ["note1"]}]}, "output_to_user": "Saved notes", "changelog_summary": "notes saved"},
                "compose": {"function": "compose", "args": {"sections": [{"title": "Intro", "text": "…"}]}, "output_to_user": "Drafted text", "changelog_summary": "compose"},
                "question": {"function": "question", "args": {"text": "Clarify scope?"}, "output_to_user": "Need input", "changelog_summary": "asked user"},
                "final": {"function": "final", "args": {"text": "Answer."}, "output_to_user": "Answer for user", "changelog_summary": "finalized"}
            }

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Resources:"},
                {"role": "user", "content": json.dumps(resources, ensure_ascii=False)},
                {"role": "user", "content": "History:"},
                {"role": "user", "content": json.dumps(history, ensure_ascii=False)}
            ]
            if ctx:
                messages.append({"role": "user", "content": "Context:"})
                messages.append({"role": "user", "content": json.dumps(ctx, ensure_ascii=False)})
            # If the focused file is tabular, instruct the model to import it into the per-project SQL DB first
            try:
                _fctx_ws = ctx.get("file") if isinstance(ctx, dict) else None
                if _fctx_ws and str(_fctx_ws.get("structure") or "").strip().lower() == "tabular":
                    fid_hint_ws = int(getattr(fctx, 'id', 0)) if fctx and getattr(fctx, 'id', None) is not None else None
                    import re as _re1
                    base1 = str(getattr(fctx, 'display_name', '') or getattr(fctx, 'filename', '') or 'table')
                    base1 = _re1.sub(r"\.[A-Za-z0-9]+$", "", base1)
                    base1 = _re1.sub(r"[^A-Za-z0-9]+", "_", base1).strip("_") or "tabular_file"
                    messages.append({"role": "user", "content": f"Tabular import policy: Context.file is tabular. Include a 'code' step to import file_id {fid_hint_ws if fid_hint_ws is not None else '<file_id>'} into SQL (CREATE TABLE {base1.lower()}, INSERT rows), then use 'db' for analysis."})
            except Exception:
                pass
            messages.append({"role": "user", "content": "Functions and examples:"})
            messages.append({"role": "user", "content": json.dumps(examples_json, ensure_ascii=False)})
            messages.append({"role": "user", "content": content})
            resp = client.chat.completions.create(model=model, messages=messages)
            raw = (resp.choices[0].message.content or "").strip()
            try:
                parsed = json.loads(raw)
                reply_title = str(parsed.get("title") or "Assistant")
            except Exception:
                pass
            try:
                parsed = json.loads(raw)
                reply_title = str(parsed.get("title") or "Assistant")
                reply_payload = parsed.get("data")
                reply_text = raw
            except Exception:
                reply_title = "Assistant"
                reply_text = raw
        except Exception as e:
            reply_text = f"[llm-error] {type(e).__name__}: {e}"
            reply_title = "LLM Error"
    
    # Persist assistant message (with title/payload if available)
    am = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=reply_text or "", display_title=reply_title, payload_json=reply_payload)
    try:
        db.add(am)
        db.commit()
    except Exception:
        db.rollback()

    # If this is a new/default thread, rename it using reply_title
    try:
        if reply_title and (thr.title in {"Ask", "New Thread"} or thr.title.startswith("File:") or thr.title.startswith("DB:")):
            thr.title = reply_title[:100]
            db.commit()
    except Exception:
        db.rollback()

    # Changelog for chat with full prompts and raw result
    try:
        input_payload = {"messages": messages, "file_context_id": (fctx.id if fctx else None)}
        output_payload = {"assistant_title": reply_title, "assistant_raw": reply_text, "assistant_payload": reply_payload}
        record_changelog(db, project.id, branch.id, "thread.chat", input_payload, output_payload)
    except Exception:
        pass

    # Redirect back focusing this thread
    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}" + (f"&file_id={file_id}" if file_id else ""), status_code=303)