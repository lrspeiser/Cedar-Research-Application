# cedar_tools.py
#
# Centralized tool implementations for CedarPy.
# These functions are used by both the WebSocket orchestrator and the /api/test/tool route.
#
# Keys: see README "Keys & Env" for how OpenAI keys are loaded via env or ~/CedarPyData/.env
# Troubleshooting: see README "Troubleshooting LLM failures" for guidance on investigating model/tool issues
from __future__ import annotations

import os
import io
import re
import json
import mimetypes
import contextlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# -----------------------------
# Web/network tools
# -----------------------------

def tool_web(*, url: str | None = None, query: str | None = None, timeout: int = 25) -> dict:
    import urllib.request as _req
    import re as _re
    url = (url or '').strip()
    query = (query or '').strip()
    if query and not url:
        try:
            import urllib.parse as _u
            search_url = "https://duckduckgo.com/html/?q=" + _u.quote(query)
            with _req.urlopen(search_url, timeout=timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
            hrefs = list(set(_re.findall(r'href=[\"\']([^\"\']+)', body)))
            results: List[Dict[str, Any]] = []
            try:
                from urllib.parse import urlparse as _up, parse_qs as _pqs, unquote as _unq
            except Exception:
                _up = None  # type: ignore
            for h in hrefs:
                try:
                    if 'duckduckgo.com' in h and 'uddg=' in h and _up:
                        uo = _up(h)
                        qs = _pqs(uo.query)
                        if 'uddg' in qs:
                            real = _unq(qs['uddg'][0])
                            if real.startswith('http'):
                                results.append({"url": real})
                    elif h.startswith('http') and 'duckduckgo.com' not in h:
                        results.append({"url": h})
                except Exception:
                    continue
            seen = set(); uniq: List[Dict[str, Any]] = []
            for r in results:
                u = r.get('url')
                if u and u not in seen:
                    seen.add(u); uniq.append(r)
            return {"ok": True, "query": query, "results": uniq[:10], "count": len(uniq[:10])}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if url:
        try:
            with _req.urlopen(url, timeout=timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
            links = list(set(_re.findall(r'href=[\"\']([^\"\']+)', body)))
            title_m = _re.search(r'<title[^>]*>(.*?)</title>', body, _re.IGNORECASE | _re.DOTALL)
            title = title_m.group(1).strip() if title_m else ''
            return {"ok": True, "url": url, "title": title, "links": links[:200], "bytes": len(body)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": "web: provide url or query"}

# -----------------------------
# File and DB tools
# -----------------------------

def tool_download(*, project_id: int, branch_id: int, branch_name: str, urls: List[str], project_dirs: Callable[[int], Dict[str, str]], SessionLocal: Callable[[], Any], FileEntry: Any, file_extension_to_type: Callable[[str], str], timeout: int = 45) -> dict:
    import urllib.request as _req
    import re as _re
    if not urls:
        return {"ok": False, "error": "urls required"}
    paths = project_dirs(project_id)
    files_root = paths.get("files_root") or ''
    branch_dir_name = f"branch_{branch_name or 'Main'}"
    project_dir = os.path.join(files_root, branch_dir_name)
    os.makedirs(project_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        for u in urls[:10]:
            try:
                with _req.urlopen(u, timeout=timeout) as resp:
                    data = resp.read()
                parsed = _re.sub(r'[^a-zA-Z0-9._-]', '_', os.path.basename(u.split('?')[0]) or 'download.bin')
                ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                storage_name = f"{ts}__{parsed}"
                disk_path = os.path.join(project_dir, storage_name)
                with open(disk_path, 'wb') as fh:
                    fh.write(data)
                size = len(data)
                mime, _ = mimetypes.guess_type(parsed)
                ftype = file_extension_to_type(parsed)
                rec = FileEntry(project_id=project_id, branch_id=branch_id, filename=storage_name, display_name=parsed, file_type=ftype, structure=None, mime_type=mime or '', size_bytes=size, storage_path=os.path.abspath(disk_path), metadata_json=None, ai_processing=False)
                db.add(rec); db.commit(); db.refresh(rec)
                results.append({"url": u, "file_id": rec.id, "display_name": parsed, "bytes": size})
            except Exception as e:
                results.append({"url": u, "error": f"{type(e).__name__}: {e}"})
        return {"ok": True, "downloads": results}
    finally:
        try: db.close()
        except Exception: pass


def tool_extract(*, project_id: int, file_id: int, SessionLocal: Callable[[], Any], FileEntry: Any) -> dict:
    db = SessionLocal()
    try:
        f = db.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project_id).first()
        if not f or not f.storage_path or not os.path.isfile(f.storage_path):
            return {"ok": False, "error": "file not found"}
        try:
            with open(f.storage_path, 'r', encoding='utf-8') as fh:
                txt = fh.read()
        except Exception:
            return {"ok": False, "error": "binary or non-utf8 file; PDF extraction not installed"}
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        claims = [ln for ln in lines[:200]]
        citations: List[str] = []
        rx = re.compile(r'\[(\d+)\]|doi:|arxiv|http', re.I)
        for ln in lines:
            if rx.search(ln):
                citations.append(ln)
                if len(citations) >= 200:
                    break
        return {"ok": True, "claims": claims[:200], "citations": citations[:200]}
    finally:
        try: db.close()
        except Exception: pass


def tool_image(*, image_id: int, purpose: str, exec_img: Callable[[int, str], dict]) -> dict:
    try:
        return exec_img(image_id, purpose)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def tool_db(*, project_id: int, sql_text: str, execute_sql: Callable[..., dict]) -> dict:
    if not sql_text.strip():
        return {"ok": False, "error": "sql required"}
    try:
        return execute_sql(sql_text, project_id, max_rows=200)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def tool_code(*, language: str, source: str, project_id: int, branch_id: int, SessionLocal: Callable[[], Any], FileEntry: Any, branch_filter_ids: Callable[[Any, int, int], List[int]], query_sql: Callable[[str], dict]) -> dict:
    if language.lower() != 'python':
        return {"ok": False, "error": "only python supported"}
    logs = io.StringIO()
    def _cedar_query(sql_text: str):
        try:
            return query_sql(sql_text)
        except Exception as e:  # keep parity with existing behavior
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    def _cedar_list_files():
        db = SessionLocal()
        try:
            ids = branch_filter_ids(db, project_id, branch_id)
            recs = db.query(FileEntry).filter(FileEntry.project_id==project_id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(200).all()
            return [{"id": ff.id, "display_name": ff.display_name, "file_type": ff.file_type} for ff in recs]
        finally:
            try: db.close()
            except Exception: pass
    def _cedar_read(file_id: int):
        db = SessionLocal()
        try:
            f = db.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project_id).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return None
            with open(f.storage_path, 'rb') as fh:
                b = fh.read(500000)
            try:
                return b.decode('utf-8', errors='replace')
            except Exception:
                import base64 as _b64
                return "base64:" + _b64.b64encode(b).decode('ascii')
        finally:
            try: db.close()
            except Exception: pass
    safe_globals: Dict[str, Any] = {
        "__builtins__": {"print": print, "len": len, "range": range, "str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple},
        "cedar": type("CedarHelpers", (), {"query": _cedar_query, "list_files": _cedar_list_files, "read": _cedar_read})(),
        "sqlite3": __import__('sqlite3'),
        "json": json,
        "re": re,
        "io": io,
    }
    try:
        with contextlib.redirect_stdout(logs):
            exec(compile(source, filename="<cedar_code>", mode="exec"), safe_globals, safe_globals)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "logs": logs.getvalue()}
    return {"ok": True, "logs": logs.getvalue()}


def tool_shell(*, script: str) -> dict:
    if not script.strip():
        return {"ok": False, "error": "script required"}
    try:
        base = os.environ.get('SHELL') or '/bin/zsh'
        import subprocess
        proc = subprocess.run([base, '-lc', script], capture_output=True, text=True, timeout=60)
        return {"ok": proc.returncode == 0, "return_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def tool_notes(*, project_id: int, branch_id: int, themes: Any, SessionLocal: Callable[[], Any], Note: Any) -> dict:
    content = json.dumps({"themes": themes}, ensure_ascii=False)
    db = SessionLocal()
    try:
        n = Note(project_id=project_id, branch_id=branch_id, content=content, tags=["notes"])
        db.add(n); db.commit(); db.refresh(n)
        return {"ok": True, "note_id": n.id}
    finally:
        try: db.close()
        except Exception: pass


def tool_compose(*, project_id: int, branch_id: int, sections: Any, SessionLocal: Callable[[], Any], Note: Any) -> dict:
    content = json.dumps({"sections": sections}, ensure_ascii=False)
    db = SessionLocal()
    try:
        n = Note(project_id=project_id, branch_id=branch_id, content=content, tags=["compose"])
        db.add(n); db.commit(); db.refresh(n)
        return {"ok": True, "note_id": n.id}
    finally:
        try: db.close()
        except Exception: pass


def tool_tabular_import(*, project_id: int, branch_id: int, file_id: int, options: Optional[dict], SessionLocal: Callable[[], Any], FileEntry: Any, tabular_import_via_llm: Callable[..., dict]) -> dict:
    db = SessionLocal()
    try:
        rec = db.query(FileEntry).filter(FileEntry.id==file_id, FileEntry.project_id==project_id).first()
        if not rec:
            return {"ok": False, "error": "file not found"}
        res = tabular_import_via_llm(project_id, branch_id, rec, db, options=options)
        out = {"ok": bool(res.get("ok"))}
        out.update(res)
        return out
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try: db.close()
        except Exception: pass
