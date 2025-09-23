from __future__ import annotations

import json
from typing import Any, Callable


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