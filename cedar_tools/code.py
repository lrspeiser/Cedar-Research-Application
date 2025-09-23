from __future__ import annotations

import os
import io
import json
import re
import contextlib
from typing import Any, Callable, List

# Keys & Troubleshooting: see README

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
    safe_globals: dict[str, Any] = {
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