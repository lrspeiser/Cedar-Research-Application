"""
Database module for Cedar app.
Handles database engines, connections, and migrations.
"""

import os
import json
import threading
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from cedar_app.config import (
    REGISTRY_DATABASE_URL,
    PROJECTS_ROOT,
    DATA_DIR
)

# Import models from main_models (we'll keep using that file for now)
from main_models import (
    Base, Project, Branch, Thread, ThreadMessage, FileEntry, 
    Dataset, Setting, Version, ChangelogEntry, SQLUndoLog, Note
)

from main_helpers import ensure_main_branch


# ----------------------------------------------------------------------------------
# Database setup
# - Central registry: global engine
# - Per-project: dynamic engine selected per request/project
# ----------------------------------------------------------------------------------

engeine_kwargs_typo_guard = None
_engine_kwargs_base = dict(pool_pre_ping=True, future=True)

# Central registry engine
_registry_engine_kwargs = dict(**_engine_kwargs_base)
if REGISTRY_DATABASE_URL.startswith("sqlite"):
    _registry_engine_kwargs["connect_args"] = {"check_same_thread": False}
registry_engine = create_engine(REGISTRY_DATABASE_URL, **_registry_engine_kwargs)
RegistrySessionLocal = sessionmaker(bind=registry_engine, autoflush=False, autocommit=False, future=True)

# Per-project engine cache
_project_engines: Dict[int, Any] = {}
_project_engines_lock = threading.Lock()


def _project_dirs(project_id: int) -> Dict[str, str]:
    """Get the directory paths for a specific project."""
    base = os.path.join(PROJECTS_ROOT, str(project_id))
    db_path = os.path.join(base, "database.db")
    files_root = os.path.join(base, "files")
    threads_root = os.path.join(base, "threads")
    return {"base": base, "db_path": db_path, "files_root": files_root, "threads_root": threads_root}


def _ensure_project_storage(project_id: int) -> None:
    """Ensure project directories exist."""
    paths = _project_dirs(project_id)
    os.makedirs(paths["base"], exist_ok=True)
    os.makedirs(paths["files_root"], exist_ok=True)
    os.makedirs(paths.get("threads_root") or os.path.join(paths["base"], "threads"), exist_ok=True)


def _get_project_engine(project_id: int):
    """Get or create a database engine for a specific project."""
    # See PROJECT_SEPARATION_README.md for architecture details
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
    """Get a database session for the central registry."""
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_project_db(project_id: int) -> Session:
    """Get a database session for a specific project."""
    engine = _get_project_engine(project_id)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
            msgs = db.query(ThreadMessage).filter(ThreadMessage.project_id==project_id, ThreadMessage.thread_id==thread_id).order_by(ThreadMessage.created_at.asc()).all()
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
            try: db.close()
            except Exception: pass
    except Exception as e:
        try:
            print(f"[thread-snapshot-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


# ----------------------------------------------------------------------------------
# Migration functions
# ----------------------------------------------------------------------------------

def _migrate_project_files_ai_columns(engine_obj):
    """Add AI-related columns to files table if missing."""
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
    """Add display_title and payload_json columns to thread_messages table if missing."""
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


def _migrate_registry_metadata_json(engine_obj):
    """Add metadata_json and AI columns to registry files table."""
    try:
        with engine_obj.begin() as conn:
            dialect = engine_obj.dialect.name
            has_col = False
            if dialect == "mysql":
                res = conn.exec_driver_sql("SHOW COLUMNS FROM files LIKE 'metadata_json'")
                has_col = res.fetchone() is not None
                if not has_col:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON NULL")
            elif dialect == "sqlite":
                res = conn.exec_driver_sql("PRAGMA table_info(files)")
                cols = [row[1] for row in res.fetchall()]
                has_col = "metadata_json" in cols
                if not has_col:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON")
            else:
                # best effort: try adding a JSON column with generic SQL
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON")
            
            # Add AI columns if missing
            try:
                if dialect == "sqlite":
                    res2 = conn.exec_driver_sql("PRAGMA table_info(files)")
                    cols2 = [row[1] for row in res2.fetchall()]
                    if "ai_title" not in cols2:
                        conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                    if "ai_description" not in cols2:
                        conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                    if "ai_category" not in cols2:
                        conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
                    if "ai_processing" not in cols2:
                        conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing INTEGER DEFAULT 0")
                elif dialect == "mysql":
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_title VARCHAR(255)")
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_description TEXT")
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_category VARCHAR(255)")
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_processing TINYINT(1) DEFAULT 0")
                else:
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                    conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
                    try:
                        conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_processing BOOLEAN DEFAULT 0")
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        # Ignore migration issues in prototype mode
        pass


def ensure_project_initialized(project_id: int) -> None:
    """Ensure the per-project database and storage exist and are seeded.
    See PROJECT_SEPARATION_README.md
    """
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
            ensure_main_branch(pdb, project_id)
        finally:
            pdb.close()
        _ensure_project_storage(project_id)
        _migrate_project_files_ai_columns(eng)
        _migrate_thread_messages_columns(eng)
        _migrate_project_langextract_tables(eng)
    except Exception as e:
        print(f"[ensure-project-error] Failed to initialize project {project_id}: {type(e).__name__}: {e}")
        raise  # Re-raise to surface the error


# Initialize registry database on module import
Base.metadata.create_all(registry_engine)

# Attempt lightweight migration for existing registry DB
_migrate_registry_metadata_json(registry_engine)