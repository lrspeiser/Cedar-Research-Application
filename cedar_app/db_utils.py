"""
Database utilities for Cedar
- Central registry engine/session
- Per-project engines and storage helpers
- Light migrations for per-project DBs
- ensure_project_initialized and thread snapshotting

See PROJECT_SEPARATION_README.md for architecture details.
"""

from __future__ import annotations

import os
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from cedar_app.config import PROJECTS_ROOT, REGISTRY_DATABASE_URL
from main_models import Base, Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Setting, Version, ChangelogEntry, SQLUndoLog, Note

# ----------------------------------------------------------------------------------
# Central registry engine/session
# ----------------------------------------------------------------------------------

_engine_kwargs_base: Dict[str, Any] = dict(pool_pre_ping=True, future=True)
_registry_engine_kwargs = dict(**_engine_kwargs_base)
if REGISTRY_DATABASE_URL.startswith("sqlite"):
    _registry_engine_kwargs["connect_args"] = {"check_same_thread": False}
registry_engine = create_engine(REGISTRY_DATABASE_URL, **_registry_engine_kwargs)
RegistrySessionLocal = sessionmaker(bind=registry_engine, autoflush=False, autocommit=False, future=True)

# ----------------------------------------------------------------------------------
# Per-project engine cache and storage helpers
# ----------------------------------------------------------------------------------

_project_engines: Dict[int, Any] = {}
_project_engines_lock = threading.Lock()


def _project_dirs(project_id: int) -> Dict[str, str]:
    base = os.path.join(PROJECTS_ROOT, str(project_id))
    db_path = os.path.join(base, "database.db")
    files_root = os.path.join(base, "files")
    threads_root = os.path.join(base, "threads")
    return {"base": base, "db_path": db_path, "files_root": files_root, "threads_root": threads_root}


def _ensure_project_storage(project_id: int) -> None:
    paths = _project_dirs(project_id)
    os.makedirs(paths["base"], exist_ok=True)
    os.makedirs(paths["files_root"], exist_ok=True)
    os.makedirs(paths.get("threads_root") or os.path.join(paths["base"], "threads"), exist_ok=True)


def _get_project_engine(project_id: int):
    with _project_engines_lock:
        eng = _project_engines.get(project_id)
        if eng is not None:
            return eng
        paths = _project_dirs(project_id)
        os.makedirs(os.path.dirname(paths["db_path"]), exist_ok=True)
        kwargs = dict(**_engine_kwargs_base)
        # SQLite per project
        kwargs["connect_args"] = {"check_same_thread": False}
        eng = create_engine(f"sqlite:///{paths['db_path']}", **kwargs)
        _project_engines[project_id] = eng
        return eng


def get_registry_db() -> Session:
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_project_db(project_id: int) -> Session:
    engine = _get_project_engine(project_id)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------------------------------------
# Per-project lightweight migrations and utilities
# ----------------------------------------------------------------------------------

def _migrate_project_files_ai_columns(engine_obj):
    try:
        with engine_obj.begin() as conn:
            if engine_obj.dialect.name == "sqlite":
                res = conn.exec_driver_sql("PRAGMA table_info(files)")
                cols = [row[1] for row in res.fetchall()]
                if "ai_title" not in cols:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                if "ai_description" not in cols:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                if "ai_category" not in cols:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
                if "ai_processing" not in cols:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing INTEGER DEFAULT 0")
            elif engine_obj.dialect.name == "mysql":
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_title VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_category VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_processing TINYINT(1) DEFAULT 0")
            else:
                try:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing BOOLEAN DEFAULT 0")
                except Exception:
                    pass
    except Exception:
        pass


def _migrate_thread_messages_columns(engine_obj):
    try:
        with engine_obj.begin() as conn:
            if engine_obj.dialect.name == "sqlite":
                res = conn.exec_driver_sql("PRAGMA table_info(thread_messages)")
                cols = [row[1] for row in res.fetchall()]
                if "display_title" not in cols:
                    conn.exec_driver_sql("ALTER TABLE thread_messages ADD COLUMN display_title TEXT")
                if "payload_json" not in cols:
                    conn.exec_driver_sql("ALTER TABLE thread_messages ADD COLUMN payload_json JSON")
            elif engine_obj.dialect.name == "mysql":
                conn.exec_driver_sql("ALTER TABLE thread_messages ADD COLUMN IF NOT EXISTS display_title VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE thread_messages ADD COLUMN IF NOT EXISTS payload_json JSON")
    except Exception:
        pass


def _migrate_project_langextract_tables(engine_obj):
    """Create per-project tables for LangExtract chunk storage and FTS.
    Delegates to cedar_langextract.ensure_langextract_schema for single source of truth.
    """
    try:
        from cedar_langextract import ensure_langextract_schema
        ensure_langextract_schema(engine_obj)
    except Exception:
        # Best-effort; ignore if cedar_langextract is unavailable
        pass


# ----------------------------------------------------------------------------------
# Snapshotting and initialization
# ----------------------------------------------------------------------------------

def save_thread_snapshot(project_id: int, thread_id: int) -> Optional[str]:
    """Write a JSON snapshot of a thread's session (metadata + messages) to threads_root.
    Returns the absolute path of the snapshot on success, else None.
    """
    try:
        _ensure_project_storage(project_id)
        paths = _project_dirs(project_id)
        out_dir = paths.get("threads_root") or os.path.join(paths["base"], "threads")
        os.makedirs(out_dir, exist_ok=True)
        SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
        db = SessionLocal()
        try:
            thr = db.query(Thread).filter(Thread.id==int(thread_id), Thread.project_id==project_id).first()
            if not thr:
                return None
            msgs = (
                db.query(ThreadMessage)
                .filter(ThreadMessage.project_id==project_id, ThreadMessage.thread_id==thread_id)
                .order_by(ThreadMessage.created_at.asc())
                .all()
            )
            out = {
                "project_id": project_id,
                "thread_id": int(thread_id),
                "branch_id": getattr(thr, 'branch_id', None),
                "title": getattr(thr, 'title', None),
                "created_at": (thr.created_at.isoformat()+"Z") if getattr(thr, 'created_at', None) else None,
                "messages": []
            }
            for m in msgs:
                try:
                    out["messages"].append({
                        "role": m.role,
                        "title": getattr(m, 'display_title', None),
                        "content": m.content,
                        "payload": getattr(m, 'payload_json', None),
                        "created_at": (m.created_at.isoformat()+"Z") if getattr(m, 'created_at', None) else None,
                    })
                except Exception:
                    pass
            abs_path = os.path.abspath(os.path.join(out_dir, f"thread_{int(thread_id)}.json"))
            tmp_path = abs_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, abs_path)
            try:
                print(f"[thread-snapshot] wrote {abs_path}")
            except Exception:
                pass
            return abs_path
        finally:
            try:
                db.close()
            except Exception:
                pass
    except Exception as e:
        try:
            print(f"[thread-snapshot-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


def ensure_project_initialized(project_id: int) -> None:
    """Ensure the per-project database and storage exist and are seeded."""
    try:
        eng = _get_project_engine(project_id)
        # Create all tables for this project DB
        Base.metadata.create_all(eng)
        print(f"[ensure-project] Created tables for project {project_id}")
        # Lightweight migrations for this project DB
        _migrate_project_files_ai_columns(eng)
        _migrate_thread_messages_columns(eng)
        _migrate_project_langextract_tables(eng)
        # Seed project row and Main branch if missing
        SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
        pdb = SessionLocal()
        try:
            proj = pdb.query(Project).filter(Project.id == project_id).first()
            if not proj:
                title = None
                try:
                    # Look up title in registry
                    with RegistrySessionLocal() as reg:
                        reg_proj = reg.query(Project).filter(Project.id == project_id).first()
                        title = getattr(reg_proj, "title", None)
                except Exception:
                    title = None
                title = title or f"Project {project_id}"
                pdb.add(Project(id=project_id, title=title))
                pdb.commit()
                print(f"[ensure-project] Added project row for {project_id}")
            # Ensure Main branch exists
            try:
                from main_helpers import ensure_main_branch as _ensure_main_branch
                _ensure_main_branch(pdb, project_id)
            except Exception:
                pass
        finally:
            pdb.close()
        _ensure_project_storage(project_id)
        _migrate_project_files_ai_columns(eng)
        _migrate_thread_messages_columns(eng)
        _migrate_project_langextract_tables(eng)
    except Exception as e:
        print(f"[ensure-project-error] Failed to initialize project {project_id}: {type(e).__name__}: {e}")
        raise
