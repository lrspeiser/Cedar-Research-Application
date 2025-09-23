from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List

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