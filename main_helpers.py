import os
import asyncio
from datetime import datetime
from typing import Any, Dict

# Optional Redis (Valkey) for real-time relay (Node SSE). If not available, we silently skip publishing.
REDIS_URL = os.getenv("CEDARPY_REDIS_URL") or "redis://127.0.0.1:6379/0"
try:
    import redis.asyncio as _redis  # type: ignore
except Exception:  # pragma: no cover
    _redis = None

_redis_client = None
async def _get_redis():
    global _redis_client
    try:
        if _redis is None:
            return None
        if _redis_client is None:
            _redis_client = _redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        return _redis_client
    except Exception:
        return None

async def _publish_relay_event(obj: Dict[str, Any]) -> None:
    try:
        r = await _get_redis()
        if r is None:
            return
        tid = obj.get("thread_id")
        if not tid:
            return
        chan = f"cedar:thread:{tid}:pub"
        # Keep the payload small; serialize as-is (frontend expects same shape)
        import json as _json_pub
        await r.publish(chan, _json_pub.dumps(obj))
    except Exception:
        # Best-effort only
        pass

# Step-level ack registry (best-effort, in-memory). Used to verify the UI rendered a bubble.
_ack_store: Dict[str, Dict[str, Any]] = {}

async def _register_ack(eid: str, info: Dict[str, Any], timeout_ms: int = 10000) -> None:
    try:
        _ack_store[eid] = {
            'eid': eid,
            'info': info,
            'created_at': datetime.utcnow().isoformat()+"Z",
            'acked': False,
            'ack_at': None,
        }
        async def _timeout():
            try:
                await asyncio.sleep(max(0.5, timeout_ms/1000.0))
                rec = _ack_store.get(eid)
                if rec and not rec.get('acked'):
                    try:
                        print(f"[ack-timeout] eid={eid} info={rec.get('info')}")
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            asyncio.get_event_loop().create_task(_timeout())
        except Exception:
            pass
    except Exception:
        pass

# -------------------- Shared helpers moved from main.py --------------------
import html as _html
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from main_models import Project, Branch, Version

def escape(s: str) -> str:
    return _html.escape(s, quote=True)


def add_version(db: Session, entity_type: str, entity_id: int, data: dict):
    max_ver = db.query(func.max(Version.version_num)).filter(
        Version.entity_type == entity_type, Version.entity_id == entity_id
    ).scalar()
    next_ver = (max_ver or 0) + 1
    v = Version(entity_type=entity_type, entity_id=entity_id, version_num=next_ver, data=data)
    db.add(v)
    db.commit()


def ensure_main_branch(db: Session, project_id: int) -> Branch:
    main = db.query(Branch).filter(Branch.project_id == project_id, Branch.name == "Main").first()
    if main is None:
        main = Branch(project_id=project_id, name="Main", is_default=True)
        db.add(main)
        db.commit()
        db.refresh(main)
        add_version(db, "branch", main.id, {"project_id": project_id, "name": "Main", "is_default": True})
    return main


def file_extension_to_type(filename: str) -> str:
    import os as _os
    ext = _os.path.splitext(filename)[1].lower().lstrip(".")
    mapping = {
        # images
        "jpg": "jpg", "jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp", "bmp": "bmp", "tiff": "tiff", "svg": "svg",
        # docs
        "pdf": "pdf", "md": "md", "txt": "txt", "rtf": "rtf", "html": "html", "htm": "html", "xml": "xml",
        # data
        "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml", "csv": "csv", "tsv": "tsv", "ndjson": "ndjson", "parquet": "parquet",
        # archives
        "zip": "zip", "gz": "gz", "tar": "tar", "tgz": "tgz", "bz2": "bz2", "xz": "xz",
        # notebooks
        "ipynb": "json",
        # code
        "py": "python", "rs": "rust", "js": "javascript", "ts": "typescript", "tsx": "typescript", "jsx": "javascript",
        "c": "c", "h": "c-header", "hpp": "cpp-header", "hh": "cpp-header", "hxx": "cpp-header",
        "cc": "cpp", "cpp": "cpp", "cxx": "cpp",
        "java": "java", "kt": "kotlin", "kts": "kotlin", "go": "go",
        "rb": "ruby", "php": "php", "cs": "csharp", "swift": "swift", "m": "objective-c", "mm": "objective-c++",
        "scala": "scala", "hs": "haskell", "clj": "clojure", "ex": "elixir", "exs": "elixir", "erl": "erlang",
        "lua": "lua", "r": "r", "pl": "perl", "pm": "perl", "sh": "shell", "bash": "shell", "zsh": "shell",
        "sql": "sql", "proto": "protobuf", "graphql": "graphql", "gql": "graphql",
    }
    return mapping.get(ext, ext or "bin")


def branch_filter_ids(db: Session, project_id: int, selected_branch_id: Optional[int]) -> List[int]:
    """
    Returns list of branch IDs to include when displaying items:
    - If selected is Main => include ALL branches in this project (roll-up view)
    - If selected is a non-Main branch => include [Main, selected]
    """
    main = db.query(Branch).filter(Branch.project_id == project_id, Branch.name == "Main").first()
    if not main:
        main = ensure_main_branch(db, project_id)

    if selected_branch_id is None or selected_branch_id == main.id:
        # In Main: show all branches
        ids = [b.id for b in db.query(Branch).filter(Branch.project_id == project_id).all()]
        return ids
    else:
        return [main.id, selected_branch_id]


def current_branch(db: Session, project_id: int, branch_id: Optional[int]) -> Branch:
    main = ensure_main_branch(db, project_id)
    if branch_id is None:
        return main
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.project_id == project_id).first()
    return b or main
