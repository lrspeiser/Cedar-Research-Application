from __future__ import annotations

from typing import Any, Callable, Optional

# This tool calls the provided tabular_import_via_llm dependency, which performs the LLM call.
# Keys: see README "Keys & Env"; for troubleshooting see README "Tabular import via LLM codegen".

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