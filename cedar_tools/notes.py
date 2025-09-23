from __future__ import annotations

import json
from typing import Any, Callable


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