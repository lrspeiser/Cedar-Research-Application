
import os
import html
import shutil
import mimetypes
import json
import csv
import hashlib
import subprocess
import threading
import uuid
import queue
import signal
import time
import platform
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, Header, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean,
    UniqueConstraint, JSON, Index, func, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import re

# ----------------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------------

# Prefer a generic CEDARPY_DATABASE_URL for the central registry only; otherwise use SQLite in ~/CedarPyData/cedarpy.db
# See PROJECT_SEPARATION_README.md for architecture details.
HOME_DIR = os.path.expanduser("~")
DATA_DIR = os.getenv("CEDARPY_DATA_DIR", os.path.join(HOME_DIR, "CedarPyData"))
DEFAULT_SQLITE_PATH = os.path.join(DATA_DIR, "cedarpy.db")
PROJECTS_ROOT = os.path.join(DATA_DIR, "projects")

# Central registry DB (projects list only)
REGISTRY_DATABASE_URL = os.getenv("CEDARPY_DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"

# Deprecated: CEDARPY_UPLOAD_DIR (files now under per-project folders). Keep for backward compatibility during migration.
# Default the legacy uploads path under the user data dir so it is writable when running from a read-only app bundle.
# See PROJECT_SEPARATION_README.md for details.
_default_legacy_dir = os.path.join(DATA_DIR, "user_uploads")
LEGACY_UPLOAD_DIR = os.getenv("CEDARPY_UPLOAD_DIR", _default_legacy_dir)

# Shell API feature flag and token
# See README for details on enabling and securing the Shell API.
# - CEDARPY_SHELL_API_ENABLED: "1" to enable the UI and API, default "0" (disabled)
# - CEDARPY_SHELL_API_TOKEN: optional token. If set, requests must include X-API-Token header matching this value.
#   If unset, API is limited to local requests (127.0.0.1/::1) only.
# Default: ENABLED (set to "0" to disable). We default-on to match DMG behavior and ease local development.
SHELL_API_ENABLED = str(os.getenv("CEDARPY_SHELL_API_ENABLED", "1")).strip().lower() not in {"", "0", "false", "no", "off"}
SHELL_API_TOKEN = os.getenv("CEDARPY_SHELL_API_TOKEN")

# Logs directory for shell runs (outside DMG and writable)
LOGS_DIR = os.path.join(DATA_DIR, "logs", "shell")
os.makedirs(LOGS_DIR, exist_ok=True)

# Default working directory for shell jobs (scoped, safe by default)
SHELL_DEFAULT_WORKDIR = os.getenv("CEDARPY_SHELL_WORKDIR") or DATA_DIR
try:
    os.makedirs(SHELL_DEFAULT_WORKDIR, exist_ok=True)
except Exception:
    pass

# Ensure writable dirs exist (important when running from a read-only DMG)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROJECTS_ROOT, exist_ok=True)
os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)

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
Base = declarative_base()

# Per-project engine cache
_project_engines: Dict[int, Any] = {}
_project_engines_lock = threading.Lock()

def _project_dirs(project_id: int) -> Dict[str, str]:
    base = os.path.join(PROJECTS_ROOT, str(project_id))
    db_path = os.path.join(base, "database.db")
    files_root = os.path.join(base, "files")
    return {"base": base, "db_path": db_path, "files_root": files_root}


def _ensure_project_storage(project_id: int) -> None:
    paths = _project_dirs(project_id)
    os.makedirs(paths["base"], exist_ok=True)
    os.makedirs(paths["files_root"], exist_ok=True)


def _get_project_engine(project_id: int):
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
            elif engine_obj.dialect.name == "mysql":
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_title VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_category VARCHAR(255)")
    except Exception:
        pass


def ensure_project_initialized(project_id: int) -> None:
    """Ensure the per-project database and storage exist and are seeded.
    See PROJECT_SEPARATION_README.md
    """
    try:
        eng = _get_project_engine(project_id)
        # Create all tables for this project DB
        Base.metadata.create_all(eng)
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
            ensure_main_branch(pdb, project_id)
        finally:
            pdb.close()
        _ensure_project_storage(project_id)
        _migrate_project_files_ai_columns(eng)
    except Exception:
        pass

# ----------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"  # Central registry only
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="branches")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_branch_name"),
    )


class Thread(Base):
    __tablename__ = "threads"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")
    branch = relationship("Branch")


class FileEntry(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)  # storage name on disk
    display_name = Column(String(255), nullable=False)  # original filename
    file_type = Column(String(50))  # e.g., jpg, pdf, json (derived)
    structure = Column(String(50))  # images, sources, code, tabular (LLM-chosen)
    mime_type = Column(String(100))
    size_bytes = Column(Integer)
    storage_path = Column(String(1024))  # absolute/relative path on disk
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON)  # extracted metadata from interpreter
    # AI classification outputs
    ai_title = Column(String(255))
    ai_description = Column(Text)
    ai_category = Column(String(255))

    project = relationship("Project")
    branch = relationship("Branch")

    __table_args__ = (
        Index("ix_files_project_branch", "project_id", "branch_id"),
    )


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")
    branch = relationship("Branch")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Version(Base):
    __tablename__ = "versions"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)  # "project" | "branch" | "thread" | "file" | etc.
    entity_id = Column(Integer, nullable=False)
    version_num = Column(Integer, nullable=False)
    data = Column(JSON)  # snapshot of entity data (lightweight for now)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version_num", name="uq_version_key"),
        Index("ix_versions_entity", "entity_type", "entity_id"),
    )


class SQLUndoLog(Base):
    __tablename__ = "sql_undo_log"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    table_name = Column(String(255), nullable=False)
    op = Column(String(20), nullable=False)  # insert | update | delete
    sql_text = Column(Text)
    pk_columns = Column(JSON)  # list of PK column names
    rows_before = Column(JSON)  # list of row dicts
    rows_after = Column(JSON)   # list of row dicts
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_undo_project_branch", "project_id", "branch_id", "created_at"),
    )


# Create central registry tables
Base.metadata.create_all(registry_engine)

# Attempt a lightweight migration for existing DBs: add metadata_json if missing (registry only)
# Also add AI columns for LLM classification (ai_title, ai_description, ai_category) on the registry DB.
try:
    with registry_engine.begin() as conn:
        dialect = registry_engine.dialect.name
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
            elif dialect == "mysql":
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_title VARCHAR(255)")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN IF NOT EXISTS ai_category VARCHAR(255)")
            else:
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_title TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_description TEXT")
                conn.exec_driver_sql("ALTER TABLE files ADD COLUMN ai_category TEXT")
        except Exception:
            pass
except Exception:
    # Ignore migration issues in prototype mode
    pass

# ----------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------

# LLM classification utilities (See README: "LLM classification on file upload")
# When calling web services, configure keys via env. Do not hardcode secrets.
# See README for setup and troubleshooting; verbose logs are emitted on error.

def _llm_client_config():
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, None
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, None
    model = os.getenv("CEDARPY_OPENAI_MODEL", "gpt-5")
    try:
        client = OpenAI(api_key=api_key)
        return client, model
    except Exception:
        return None, None


def _llm_classify_file(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Calls GPT model to classify a file into one of: images | sources | code | tabular
    and produce ai_title (<=100), ai_description (<=350), ai_category (<=100).

    Input: metadata produced by interpret_file(), including:
    - extension, mime_guess, format, language, is_text, size_bytes, line_count, sample_text

    Returns dict or None on error. Errors are logged verbosely.
    """
    if str(os.getenv("CEDARPY_FILE_LLM", "1")).strip().lower() in {"0","false","no","off"}:
        try:
            print("[llm-skip] CEDARPY_FILE_LLM=0")
        except Exception:
            pass
        return None
    client, model = _llm_client_config()
    if not client:
        try:
            print("[llm-skip] missing OpenAI API key; set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY")
        except Exception:
            pass
        return None
    # Prepare a bounded sample
    sample_text = (meta.get("sample_text") or "")
    if len(sample_text) > 8000:
        sample_text = sample_text[:8000]
    info = {
        k: meta.get(k) for k in [
            "extension","mime_guess","format","language","is_text","size_bytes","line_count","json_valid","json_top_level_keys","csv_dialect"
        ] if k in meta
    }
    sys_prompt = (
        "You are an expert data librarian. Classify incoming files and produce short, friendly labels.\n"
        "Output strict JSON with keys: structure, ai_title, ai_description, ai_category.\n"
        "Rules: structure must be one of: images | sources | code | tabular.\n"
        "ai_title <= 100 chars. ai_description <= 350 chars. ai_category <= 100 chars.\n"
        "Do not include newlines in values. If in doubt, choose the best fit."
    )
    user_payload = {
        "metadata": info,
        "display_name": meta.get("display_name"),
        "snippet_utf8": sample_text,
    }
    import json as _json
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Classify this file and produce JSON as specified. Input:"},
        {"role": "user", "content": _json.dumps(user_payload, ensure_ascii=False)},
    ]
    try:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0)
        content = (resp.choices[0].message.content or "").strip()
        result = _json.loads(content)
        # Normalize and enforce limits
        struct = str(result.get("structure"," ")).strip().lower()
        if struct not in {"images","sources","code","tabular"}:
            struct = None
        def _clip(s, n):
            s = '' if s is None else str(s)
            return s[:n]
        title = _clip(result.get("ai_title"), 100)
        desc = _clip(result.get("ai_description"), 350)
        cat = _clip(result.get("ai_category"), 100)
        out = {"structure": struct, "ai_title": title, "ai_description": desc, "ai_category": cat}
        try:
            print(f"[llm] model={model} structure={struct} title={len(title)} chars cat={cat}")
        except Exception:
            pass
        return out
    except Exception as e:
        try:
            print(f"[llm-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None

def _is_probably_text(path: str, sample_bytes: int = 4096) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_bytes)
        if b"\x00" in chunk:
            return False
        # If mostly ASCII or UTF-8 bytes, consider text
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
        nontext = chunk.translate(None, text_chars)
        return len(nontext) / (len(chunk) or 1) < 0.30
    except Exception:
        return False


def interpret_file(path: str, original_name: str) -> Dict[str, Any]:
    """Extracts metadata from the file for storage in FileEntry.metadata_json.

    Avoids heavy deps; best-effort using extension/mime and light parsing.
    """
    meta: Dict[str, Any] = {}
    try:
        stat = os.stat(path)
        meta["size_bytes"] = stat.st_size
        meta["mtime"] = datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
        meta["ctime"] = datetime.utcfromtimestamp(stat.st_ctime).isoformat() + "Z"
    except Exception:
        pass

    ext = os.path.splitext(original_name)[1].lower().lstrip(".")
    meta["extension"] = ext
    mime, _ = mimetypes.guess_type(original_name)
    meta["mime_guess"] = mime or ""

    # Format (high-level) and language
    ftype = file_extension_to_type(original_name)
    meta["format"] = ftype
    language_map = {
        "python": "Python", "rust": "Rust", "javascript": "JavaScript", "typescript": "TypeScript",
        "c": "C", "c-header": "C", "cpp": "C++", "cpp-header": "C++", "objective-c": "Objective-C", "objective-c++": "Objective-C++",
        "java": "Java", "kotlin": "Kotlin", "go": "Go", "ruby": "Ruby", "php": "PHP", "csharp": "C#",
        "swift": "Swift", "scala": "Scala", "haskell": "Haskell", "clojure": "Clojure", "elixir": "Elixir", "erlang": "Erlang",
        "lua": "Lua", "r": "R", "perl": "Perl", "shell": "Shell",
    }
    meta["language"] = language_map.get(ftype)

    # Text / JSON / CSV heuristics
    is_text = _is_probably_text(path)
    meta["is_text"] = is_text

    # Store a UTF-8 text sample of the first N bytes (for LLM inspection)
    try:
        limit = int(os.getenv("CEDARPY_SAMPLE_BYTES", "65536"))
    except Exception:
        limit = 65536
    try:
        with open(path, "rb") as f:
            sample_b = f.read(max(0, limit))
        sample_text = sample_b.decode("utf-8", errors="replace")
        meta["sample_text"] = sample_text
        meta["sample_bytes_read"] = len(sample_b)
        meta["sample_truncated"] = (meta.get("size_bytes") or 0) > len(sample_b)
        meta["sample_encoding"] = "utf-8-replace"
    except Exception:
        pass

    if is_text:
        # Try JSON validation for .json / .ndjson / .ipynb
        if ext in {"json", "ndjson", "ipynb"}:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    if ext == "ndjson":
                        # count lines and JSON-parse first line only
                        first = f.readline()
                        json.loads(first)
                        meta["json_valid"] = True
                    else:
                        data = json.load(f)
                        meta["json_valid"] = True
                        if isinstance(data, dict):
                            meta["json_top_level_keys"] = list(data.keys())[:50]
                        elif isinstance(data, list):
                            meta["json_list_length_sample"] = min(len(data), 1000)
            except Exception:
                meta["json_valid"] = False
        # CSV sniffing
        if ext in {"csv", "tsv"}:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    sample = f.read(2048)
                dialect = csv.Sniffer().sniff(sample)
                meta["csv_dialect"] = {
                    "delimiter": getattr(dialect, "delimiter", ","),
                    "quotechar": getattr(dialect, "quotechar", '"'),
                    "doublequote": getattr(dialect, "doublequote", True),
                    "skipinitialspace": getattr(dialect, "skipinitialspace", False),
                }
            except Exception:
                pass
        # Simple line count (bounded)
        try:
            lc = 0
            with open(path, "rb") as f:
                for i, _ in enumerate(f):
                    lc = i + 1
                    if lc > 2000000:
                        break
            meta["line_count"] = lc
        except Exception:
            pass

    # Hash (sha256)
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        meta["sha256"] = h.hexdigest()
    except Exception:
        pass

    return meta

def get_db() -> Session:
    # Backward-compat shim: default DB equals central registry
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_version(db: Session, entity_type: str, entity_id: int, data: dict):
    max_ver = db.query(func.max(Version.version_num)).filter(
        Version.entity_type == entity_type, Version.entity_id == entity_id
    ).scalar()
    next_ver = (max_ver or 0) + 1
    v = Version(entity_type=entity_type, entity_id=entity_id, version_num=next_ver, data=data)
    db.add(v)
    db.commit()


def escape(s: str) -> str:
    return html.escape(s, quote=True)


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
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
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

# ----------------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------------

app = FastAPI(title="Cedar")

# Serve uploaded files for convenience
# Serve uploaded files (legacy path no longer used). We mount a dynamic per-project files app below.
# See PROJECT_SEPARATION_README.md
# Keep legacy mount to avoid 404s for older links; it will contain only migrated symlinks if created.
# Be resilient: only mount if the directory exists; if using the default path, create it lazily.
try:
    if os.path.isdir(LEGACY_UPLOAD_DIR):
        app.mount("/uploads-legacy", StaticFiles(directory=LEGACY_UPLOAD_DIR), name="uploads_legacy")
        print(f"[cedarpy] Mounted /uploads-legacy from {LEGACY_UPLOAD_DIR}")
    else:
        if LEGACY_UPLOAD_DIR == _default_legacy_dir:
            os.makedirs(LEGACY_UPLOAD_DIR, exist_ok=True)
            app.mount("/uploads-legacy", StaticFiles(directory=LEGACY_UPLOAD_DIR), name="uploads_legacy")
            print(f"[cedarpy] Created and mounted /uploads-legacy at {LEGACY_UPLOAD_DIR}")
        else:
            print(f"[cedarpy] Skipping /uploads-legacy mount; directory does not exist: {LEGACY_UPLOAD_DIR}")
except Exception as e:
    print(f"[cedarpy] Skipping /uploads-legacy mount due to error: {e}")

@app.get("/uploads/{project_id}/{path:path}")
def serve_project_upload(project_id: int, path: str):
    # See PROJECT_SEPARATION_README.md
    base = _project_dirs(project_id)["files_root"]
    ab = os.path.abspath(os.path.join(base, path))
    base_ab = os.path.abspath(base)
    if not ab.startswith(base_ab) or not os.path.isfile(ab):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(ab)

# ----------------------------------------------------------------------------------
# HTML helpers (all inline; no external templates)
# ----------------------------------------------------------------------------------

def layout(title: str, body: str) -> HTMLResponse:
    # Inject a lightweight client logging hook so console messages and JS errors are POSTed to the server.
    # See README.md (section "Client-side logging") for details and troubleshooting.
    client_log_js = """
<script>
(function(){
  if (window.__cedarpyClientLogInitialized) return; window.__cedarpyClientLogInitialized = true;
  const endpoint = '/api/client-log';
  function post(payload){
    try {
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], {type: 'application/json'});
        navigator.sendBeacon(endpoint, blob);
        return;
      }
      fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body, keepalive: true}).catch(function(){});
    } catch(e) {}
  }
  function base(level, message, origin, extra){
    post(Object.assign({
      when: new Date().toISOString(),
      level: String(level||'info'),
      message: String(message||''),
      url: String(location.href||''),
      userAgent: navigator.userAgent || '',
      origin: origin || 'console'
    }, extra||{}));
  }
  var orig = { log: console.log, info: console.info, warn: console.warn, error: console.error };
  console.log = function(){ try { base('info', Array.from(arguments).join(' '), 'console.log'); } catch(e){}; return orig.log.apply(console, arguments); };
  console.info = function(){ try { base('info', Array.from(arguments).join(' '), 'console.info'); } catch(e){}; return orig.info.apply(console, arguments); };
  console.warn = function(){ try { base('warn', Array.from(arguments).join(' '), 'console.warn'); } catch(e){}; return orig.warn.apply(console, arguments); };
  console.error = function(){ try { base('error', Array.from(arguments).join(' '), 'console.error'); } catch(e){}; return orig.error.apply(console, arguments); };
  window.addEventListener('error', function(ev){
    try { base('error', ev.message || 'window.onerror', 'window.onerror', { line: ev.lineno||null, column: ev.colno||null, stack: ev.error && ev.error.stack ? String(ev.error.stack) : null }); } catch(e){}
  }, true);
  window.addEventListener('unhandledrejection', function(ev){
    try { var r = ev && ev.reason; base('error', (r && (r.message || r.toString())) || 'unhandledrejection', 'unhandledrejection', { stack: r && r.stack ? String(r.stack) : null }); } catch(e){}
  });
})();
</script>
"""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ --fg: #111; --bg: #fff; --accent: #2563eb; --muted: #6b7280; --border: #e5e7eb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Oxygen, Ubuntu, Cantarell, \"Helvetica Neue\", Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; color: var(--fg); background: var(--bg); }}
    header {{ padding: 16px 20px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); }}
    main {{ padding: 20px; max-width: 1100px; margin: 0 auto; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .card {{ border: 1px solid var(--border); border-radius: 8px; padding: 16px; background: #fff; flex: 1 1 340px; }}
    .muted {{ color: var(--muted); }}
    .table {{ width: 100%; border-collapse: collapse; }}
    .table th, .table td {{ border-bottom: 1px solid var(--border); padding: 8px 6px; text-align: left; vertical-align: top; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef2ff; color: #3730a3; font-size: 12px; }}
    form.inline * {{ vertical-align: middle; }}
    input[type=\"text\"], select {{ padding: 8px; border: 1px solid var(--border); border-radius: 6px; width: 100%; }}
    input[type=\"file\"] {{ padding: 6px; border: 1px dashed var(--border); border-radius: 6px; width: 100%; }}
    button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--accent); color: white; cursor: pointer; }}
    button.secondary {{ background: #f3f4f6; color: #111; }}
    .small {{ font-size: 12px; }}
    .topbar {{ display:flex; align-items:center; gap:12px; }}
  </style>
  {client_log_js}
</head>
<body>
  <header>
    <div class="topbar">
      <div><strong>Cedar</strong></div>
      <div style=\"margin-left:auto\"><a href=\"/\">Projects</a> | <a href=\"/shell\">Shell</a></div>
    </div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""
    return HTMLResponse(html_doc)


def projects_list_html(projects: List[Project]) -> str:
    # See PROJECT_SEPARATION_README.md
    if not projects:
        return f"""
        <h1>Projects</h1>
        <p class="muted">No projects yet. Create one:</p>
        <form method="post" action="/projects/create" class="card" style="max-width:520px">
            <label>Project title</label>
            <input type="text" name="title" placeholder="My First Project" required />
            <div style="height:10px"></div>
            <button type="submit">Create Project</button>
        </form>
        """
    rows = []
    for p in projects:
        rows.append(f"""
            <tr>
              <td><a href="/project/{p.id}">{escape(p.title)}</a></td>
              <td class="small muted">{p.created_at.strftime("%Y-%m-%d %H:%M:%S")} UTC</td>
            </tr>
        """)
    return f"""
        <h1>Projects</h1>
        <div class="row">
          <div class="card" style="flex:2">
            <table class="table">
              <thead><tr><th>Title</th><th>Created</th></tr></thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
          </div>
          <div class="card" style="flex:1">
            <h3>Create a new project</h3>
            <form method="post" action="/projects/create">
              <input type="text" name="title" placeholder="Project title" required />
              <div style="height:10px"></div>
              <button type="submit">Create</button>
            </form>
          </div>
        </div>
    """


def project_page_html(
    project: Project,
    branches: List[Branch],
    current: Branch,
    files: List[FileEntry],
    threads: List[Thread],
    datasets: List[Dataset],
    msg: Optional[str] = None,
    sql_result_block: Optional[str] = None,
) -> str:
    # See PROJECT_SEPARATION_README.md
    # branch tabs
    tabs = []
    for b in branches:
        selected = "style='font-weight:600'" if b.id == current.id else ""
        tabs.append(f"<a {selected} href='/project/{project.id}?branch_id={b.id}' class='pill'>{escape(b.name)}</a>")
    tabs_html = " ".join(tabs)

    # files table
    file_rows = []
    for f in files:
        # display link to file (served from /uploads/{project_id}/...)
        storage_path = f.storage_path or ""
        url = None
        try:
            abs_path = os.path.abspath(storage_path)
            base_root = _project_dirs(project.id)["files_root"]
            if abs_path.startswith(base_root):
                rel = abs_path[len(base_root):].lstrip(os.sep).replace(os.sep, "/")
                url = f"/uploads/{project.id}/{rel}"
        except Exception:
            url = None
        link_html = f"<a href='{url}' target='_blank'>{escape(f.display_name)}</a>" if url else escape(f.display_name)
        file_rows.append(f"""
            <tr>
              <td>{link_html}</td>
              <td>{escape(f.file_type or '')}</td>
              <td>{escape(f.structure or '')}</td>
              <td>{escape(f.branch.name if f.branch else '')}</td>
              <td class="small muted">{f.size_bytes or 0}</td>
              <td class="small muted">{f.created_at.strftime("%Y-%m-%d %H:%M:%S")} UTC</td>
            </tr>
        """)
    files_tbody = ''.join(file_rows) if file_rows else '<tr><td colspan="6" class="muted">No files yet.</td></tr>'

    # threads table
    thread_rows = []
    for t in threads:
        thread_rows.append(f"""
           <tr>
             <td>{escape(t.title)}</td>
             <td>{escape(t.branch.name if t.branch else '')}</td>
             <td class="small muted">{t.created_at.strftime("%Y-%m-%d %H:%M:%S")} UTC</td>
           </tr>
        """)
    thread_tbody = ''.join(thread_rows) if thread_rows else '<tr><td colspan="3" class="muted">No threads yet.</td></tr>'

    # datasets table (placeholder list)
    dataset_rows = []
    for d in datasets:
        dataset_rows.append(f"""
           <tr>
             <td>{escape(d.name)}</td>
             <td>{escape(d.branch.name if d.branch else '')}</td>
             <td class="small muted">{d.created_at.strftime("%Y-%m-%d %H:%M:%S")} UTC</td>
           </tr>
        """)
    dataset_tbody = ''.join(dataset_rows) if dataset_rows else '<tr><td colspan="3" class="muted">No databases yet.</td></tr>'

    # message
    flash = f"<div class='muted' style='margin-bottom:8px'>{escape(msg)}</div>" if msg else ""
    flash_html = flash if msg else ""

    # SQL console card with basic instructions
    examples = escape("""Examples:
-- Create a table
CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, name VARCHAR(100));
-- Insert a row
INSERT INTO demo (name) VALUES ('Alice');
-- Read rows
SELECT * FROM demo LIMIT 10;""")

    sql_card = f"""
      <div class=\"card\" style=\"flex:1\">
        <h3>SQL Console</h3>
        <div class=\"small muted\">Run SQL against the current database (SQLite by default, or your configured MySQL). Max rows is controlled by CEDARPY_SQL_MAX_ROWS.</div>
        <pre class=\"small\" style=\"white-space:pre-wrap; background:#f9fafb; padding:8px; border-radius:6px;\">{examples}</pre>
        <form method=\"post\" action=\"/project/{project.id}/sql?branch_id={current.id}\" class=\"inline\" onsubmit=\"return cedarSqlConfirm(this)\"> 
          <textarea name=\"sql\" rows=\"6\" placeholder=\"WRITE SQL HERE\" style=\"width:100%; font-family: ui-monospace, Menlo, Monaco, 'Courier New', monospace;\"></textarea>
          <div style=\"height:8px\"></div>
          <button type=\"submit\">Run SQL</button>
        </form>
        <script>
        function cedarSqlConfirm(f) {{
          var t = (f.querySelector('[name=sql]')||{{}}).value || '';
          var re = /^\\s*(drop|delete|truncate|update|alter)\\b/i;
          if (re.test(t)) {{
            return confirm('This SQL looks destructive. Proceed?');
          }}
          return true;
        }}
        </script>
        <form method=\"post\" action=\"/project/{project.id}/sql/undo_last?branch_id={current.id}\" class=\"inline\" style=\"margin-top:6px\">
          <button type=\"submit\" class=\"secondary\">Undo Last SQL</button>
        </form>
        {sql_result_block or ''}
      </div>
    """

    return f"""
      <h1>{escape(project.title)}</h1>
      <div class=\"muted small\">Project ID: {project.id}</div>
      <div style=\"height:10px\"></div>
      <div>Branches: {tabs_html}</div>

      <div class=\"row\" style=\"margin-top:16px\">
        <div class=\"card\" style=\"flex:2\">
          <h3>Files</h3>
          {flash_html}
          <table class=\"table\">
            <thead><tr><th>Name</th><th>Type</th><th>Structure</th><th>Branch</th><th>Size</th><th>Created</th></tr></thead>
            <tbody>{files_tbody}</tbody>
          </table>
          <h4>Upload a file to this branch</h4>
          <form method=\"post\" action=\"/project/{project.id}/files/upload?branch_id={current.id}\" enctype=\"multipart/form-data\">
            <input type=\"file\" name=\"file\" required />
            <div style=\"height:8px\"></div>
            <div class=\"small muted\">GPT will set structure (images | sources | code | tabular), title, description, and category. See README (LLM classification on file upload).</div>
            <div style=\"height:8px\"></div>
            <button type=\"submit\">Upload</button>
          </form>
        </div>

        <div class=\"card\" style=\"flex:1\">
          <h3>Create Branch</h3>
          <form method=\"post\" action=\"/project/{project.id}/branches/create\">
            <input type=\"text\" name=\"name\" placeholder=\"experiment-1\" required />
            <div style=\"height:8px\"></div>
            <button type=\"submit\">Create Branch</button>
          </form>
          <div style=\"height:16px\"></div>
          <h3>Create Thread</h3>
          <form method=\"post\" action=\"/project/{project.id}/threads/create?branch_id={current.id}\">
            <input type=\"text\" name=\"title\" placeholder=\"New exploration...\" required />
            <div style=\"height:8px\"></div>
            <button type=\"submit\">Create Thread</button>
          </form>
        </div>
      </div>

      <div class=\"row\">
        <div class=\"card\" style=\"flex:1\">
          <h3>Threads</h3>
          <table class=\"table\">
            <thead><tr><th>Title</th><th>Branch</th><th>Created</th></tr></thead>
            <tbody>{thread_tbody}</tbody>
          </table>
        </div>
        <div class=\"card\" style=\"flex:1\">
          <h3>Databases</h3>
          <table class=\"table\">
            <thead><tr><th>Name</th><th>Branch</th><th>Created</th></tr></thead>
            <tbody>{dataset_tbody}</tbody>
          </table>
        </div>
      </div>

      <div class=\"row\">{sql_card}
        <div class=\"card\" style=\"flex:1\">
          <h3>Branch Ops</h3>
          <div class=\"small muted\">Branch-aware SQL is active. Use these actions to manage data.</div>
          <form method=\"post\" action=\"/project/{project.id}/merge_to_main?branch_id={current.id}\" class=\"inline\" style=\"margin-bottom:6px\">
            <button type=\"submit\">Merge Branch → Main</button>
          </form>
          <form method=\"post\" action=\"/project/{project.id}/files/delete_all?branch_id={current.id}\" class=\"inline\" style=\"margin-bottom:6px\">
            <button type=\"submit\" class=\"secondary\" onclick=\"return confirm('Delete all files in this branch?');\">Delete All Files (this branch)</button>
          </form>
          <h4>Make Table Branch-aware (SQLite)</h4>
          <div class=\"small muted\">Adds project_id and branch_id, moving existing rows to Main.</div>
          <form method=\"post\" action=\"/project/{project.id}/sql/make_branch_aware?branch_id={current.id}\" class=\"inline\">
            <input type=\"text\" name=\"table\" placeholder=\"demo\" required />
            <div style=\"height:6px\"></div>
            <button type=\"submit\">Convert Table</button>
          </form>
        </div>
      </div>
    """

# ----------------------------------------------------------------------------------
# Shell execution manager
# ----------------------------------------------------------------------------------

class ShellJob:
    def __init__(self, script: str, shell_path: Optional[str] = None, trace_x: bool = False, workdir: Optional[str] = None):
        self.id = uuid.uuid4().hex
        self.script = script
        # Preserve requested shell_path if provided; resolution and fallbacks happen at run-time
        self.shell_path = shell_path or os.environ.get("SHELL")
        self.trace_x = bool(trace_x)
        self.workdir = workdir or SHELL_DEFAULT_WORKDIR
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.status = "starting"  # starting|running|finished|error|killed
        self.return_code: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.output_lines: List[str] = []
        self.log_path = os.path.join(LOGS_DIR, f"{self.start_time.strftime('%Y%m%dT%H%M%SZ')}__{self.id}.log")
        self._lock = threading.Lock()

    def append_line(self, line: str):
        try:
            with open(self.log_path, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(line)
        except Exception:
            pass
        with self._lock:
            self.output_lines.append(line)
        try:
            self.queue.put_nowait(line)
        except Exception:
            pass

    def kill(self):
        with self._lock:
            if self.proc and self.status in ("starting", "running"):
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                except Exception:
                    try:
                        self.proc.terminate()
                    except Exception:
                        pass
                self.status = "killed"


def _run_job(job: ShellJob):
    def _is_executable(p: Optional[str]) -> bool:
        try:
            return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)
        except Exception:
            return False

    def _candidate_shells(requested: Optional[str]) -> List[str]:
        cands: List[str] = []
        if requested and requested not in cands:
            cands.append(requested)
        env_shell = os.environ.get("SHELL")
        if env_shell and env_shell not in cands:
            cands.append(env_shell)
        # macOS default first when applicable
        if platform.system().lower() == "darwin" and "/bin/zsh" not in cands:
            cands.append("/bin/zsh")
        for p in ("/bin/bash", "/bin/sh"):
            if p not in cands:
                cands.append(p)
        return cands

    def _args_for(shell_path: str, script: str) -> List[str]:
        base = os.path.basename(shell_path)
        # bash/zsh/ksh/fish accept -l -c; sh/dash typically support only -c
        if base in {"bash", "zsh", "ksh", "fish"}:
            return ["-lc", script]
        return ["-c", script]

    # Resolve shell with fallbacks and emit helpful context
    candidates = _candidate_shells(job.shell_path)
    resolved: Optional[str] = None
    for p in candidates:
        if _is_executable(p):
            resolved = p
            break

    if not resolved:
        job.status = "error"
        job.end_time = datetime.utcnow()
        job.append_line(f"[shell-resolve-error] none executable among: {', '.join(candidates)}\n")
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass
        return

    # Optionally enable shell xtrace to echo commands as they are executed
    effective_script = job.script
    try:
        base_shell = os.path.basename(resolved)
    except Exception:
        base_shell = ''
    if job.trace_x:
        if base_shell in {"bash", "zsh", "ksh", "sh"}:
            effective_script = "set -x; " + effective_script
        else:
            # Non-POSIX shells may not support set -x; we note this and continue without it
            job.append_line(f"[trace] requested but not supported for shell={base_shell}\n")
    args = _args_for(resolved, effective_script)

    # Start process group so Stop can kill descendants
    job.status = "running"
    # Emit startup context to both UI and log file
    job.append_line(f"[start] job_id={job.id} at={datetime.utcnow().isoformat()}Z\n")
    job.append_line(f"[using-shell] path={resolved} args={' '.join(args[:-1])} (script length={len(job.script)} chars)\n")
    if job.trace_x:
        job.append_line("[trace] set -x enabled\n")
    job.append_line(f"[cwd] {job.workdir}\n")
    job.append_line(f"[log] {job.log_path}\n")

    try:
        # Ensure workdir exists
        try:
            os.makedirs(job.workdir, exist_ok=True)
        except Exception:
            pass
        job.proc = subprocess.Popen(
            [resolved] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
            env=os.environ.copy(),
            cwd=job.workdir,
        )
    except Exception as e:
        job.status = "error"
        job.end_time = datetime.utcnow()
        job.append_line(f"[spawn-error] {type(e).__name__}: {e}\n")
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass
        return

    # Stream output
    try:
        assert job.proc and job.proc.stdout is not None
        for line in job.proc.stdout:
            job.append_line(line)
    except Exception as e:
        job.append_line(f"[stream-error] {type(e).__name__}: {e}\n")
    finally:
        if job.proc:
            job.proc.wait()
            job.return_code = job.proc.returncode
        job.end_time = datetime.utcnow()
        if job.status != "killed":
            job.status = "finished" if (job.return_code == 0) else "error"
        # Signal end of stream
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass


_shell_jobs: Dict[str, ShellJob] = {}
_shell_jobs_lock = threading.Lock()


def start_shell_job(script: str, shell_path: Optional[str] = None, trace_x: bool = False, workdir: Optional[str] = None) -> ShellJob:
    job = ShellJob(script=script, shell_path=shell_path, trace_x=trace_x, workdir=workdir)
    with _shell_jobs_lock:
        _shell_jobs[job.id] = job
    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()
    return job


def get_shell_job(job_id: str) -> Optional[ShellJob]:
    with _shell_jobs_lock:
        return _shell_jobs.get(job_id)


# ----------------------------------------------------------------------------------
# Security helpers for Shell API
# ----------------------------------------------------------------------------------

def _is_local_request(request: Request) -> bool:
    host = (request.client.host if request and request.client else None) or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def require_shell_enabled_and_auth(request: Request, x_api_token: Optional[str] = Header(default=None)):
    if not SHELL_API_ENABLED:
        raise HTTPException(status_code=403, detail="Shell API is disabled. Set CEDARPY_SHELL_API_ENABLED=1 to enable.")
    # If a token is configured, require it
    if SHELL_API_TOKEN:
        # Allow header or cookie
        cookie_tok = request.cookies.get("Cedar-Shell-Token") if hasattr(request, "cookies") else None
        token = x_api_token or cookie_tok
        if token != SHELL_API_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized (invalid or missing token)")
    else:
        # No token set: only allow local requests
        if not _is_local_request(request):
            raise HTTPException(status_code=401, detail="Unauthorized (local requests only when no token configured)")


# ----------------------------------------------------------------------------------
# Shell UI and API routes
# ----------------------------------------------------------------------------------

class ShellRunRequest(BaseModel):
    script: str
    shell_path: Optional[str] = None
    trace_x: Optional[bool] = None
    workdir_mode: Optional[str] = None  # 'data' (default) | 'root'
    workdir: Optional[str] = None       # explicit path (optional)

@app.get("/shell", response_class=HTMLResponse)
def shell_ui(request: Request):
    if not SHELL_API_ENABLED:
        body = """
        <h1>Shell</h1>
        <p class='muted'>The Shell feature is disabled by configuration.</p>
        <p>To enable, set <code>CEDARPY_SHELL_API_ENABLED=1</code>. Optionally set <code>CEDARPY_SHELL_API_TOKEN</code> for API access. See README for details.</p>
        """
        return layout("Shell – disabled", body)

    default_shell = html.escape(os.environ.get("SHELL", "/bin/zsh"))
    default_data_dir = html.escape(SHELL_DEFAULT_WORKDIR)
    body = """
      <h1>Shell</h1>
      <p class='muted small'>Minimal shell UI. Proves WebSocket handshake on load and runs a simple script.</p>
      <div class='card' style='flex:1'>
        <label for='script'>Script</label>
        <textarea id='script' style='width:100%; height:120px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px;'>echo hello world</textarea>
        <div style='height:8px'></div>
        <div class='row'>
          <div style='flex:1'>
            <label class='small muted'>Shell path</label>
            <input id='shellPath' type='text' placeholder='__DEFAULT_SHELL__' style='width:100%; padding:8px; border:1px solid var(--border); border-radius:6px;' />
          </div>
          <div style='flex:1'>
            <label class='small muted'>X-API-Token (optional)</label>
            <input id='apiToken' type='text' placeholder='{{set if required}}' style='width:100%; padding:8px; border:1px solid var(--border); border-radius:6px;' />
          </div>
        </div>
        <div style='height:10px'></div>
        <label class='small muted'>Working directory</label>
        <div>
          <select id='workdirMode' style='padding:6px; border:1px solid var(--border); border-radius:6px;'>
            <option value='data' selected>User Data (__DATA_DIR__)</option>
            <option value='root'>Entire Disk (/)</option>
          </select>
          <div class='small muted'>User data path: __DATA_DIR__</div>
        </div>
        <div style='height:10px'></div>
        <label class='small'><input id='traceX' type='checkbox' checked /> Trace commands (-x)</label>
        <div style='height:10px'></div>
        <button id='runBtn' type='button'>Run</button>
        <button id='openWorldBtn' type='button' class='secondary'>Open World</button>
        <button id='stopBtn' type='button' class='secondary' disabled>Stop</button>
      </div>

      <div style='height:16px'></div>
      <div class='card'>
        <div class='row' style='justify-content:space-between; align-items:center'>
          <h3 style='margin:0'>Output</h3>
          <div class='small muted' id='status'>idle</div>
        </div>
        <pre id='output' style='min-height:220px; max-height:520px; overflow:auto; background:#0b1021; color:#e6e6e6; padding:12px; border-radius:6px;'></pre>
      </div>

      <div style='height:16px'></div>
      <div class='card'>
        <h3 style='margin:0 0 8px 0'>Submitted Commands</h3>
        <ul id='historyList' class='small' style='margin:0; padding-left:18px; max-height:240px; overflow:auto;'></ul>
      </div>

      <script>
        const runBtn = document.getElementById('runBtn');
        const stopBtn = document.getElementById('stopBtn');
        const openWorldBtn = document.getElementById('openWorldBtn');
        const output = document.getElementById('output');
        const statusEl = document.getElementById('status');
        const historyList = document.getElementById('historyList');
        const workdirModeEl = document.getElementById('workdirMode');
        let currentJob = null;
        let lastHistoryItem = null;
        let ws = null;

        function setStatus(s) { statusEl.textContent = s; }
        function append(text) {
          output.textContent += text;
          output.scrollTop = output.scrollHeight;
        }
        function disableRun(disabled) { runBtn.disabled = disabled; stopBtn.disabled = !disabled; }
        function addHistory(script, shellPath) {
          if (!historyList) return;
          const li = document.createElement('li');
          const ts = new Date().toISOString();
          li.textContent = '[' + ts + '] ' + (shellPath ? ('(' + shellPath + ') ') : '') + script + ' — queued';
          historyList.prepend(li);
          lastHistoryItem = li;
        }
        function updateHistoryStatus(status) {
          if (!lastHistoryItem) return;
          lastHistoryItem.textContent = lastHistoryItem.textContent.replace(/ — .+$/, '') + ' — ' + status;
        }

        // Prove WS handshake at page load via /ws/health
        (function healthWS(){
          var tokenEl0 = document.getElementById('apiToken');
          const token = tokenEl0 ? tokenEl0.value : null;
          const wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
          const qs = token ? ('?token='+encodeURIComponent(token)) : '';
          try {
            const hws = new WebSocket(wsScheme + '://' + location.host + '/ws/health' + qs);
            hws.onopen = function () { console.log('[ws-health-open]'); append('[ws-health-open]'); };
            hws.onmessage = function (e) { console.log('[ws-health]', e.data); append('[ws-health] ' + e.data); };
            hws.onerror = function (e) { console.error('[ws-health-error]', e); append('[ws-health-error]'); };
            hws.onclose = function (e) { var code=(e && e.code) ? e.code : ''; console.log('[ws-health-close]', code); append('[ws-health-close ' + code + ']'); };
          } catch (e) {
            console.error('[ws-health-exc]', e);
            append('[ws-health-exc] ' + String(e));
          }
        })();

        runBtn.addEventListener('click', async () => {
          output.textContent = '';
          console.log('[ui] run clicked');
          append('[ui] run clicked');
          const script = document.getElementById('script').value;
          const shellPathRaw = document.getElementById('shellPath').value;
          const shellPath = (shellPathRaw && shellPathRaw.trim()) ? shellPathRaw.trim() : null;
          const traceEl = document.getElementById('traceX');
          const trace_x = !!(traceEl && traceEl.checked);
          const workdir_mode = workdirModeEl ? workdirModeEl.value : 'data';
          var tokenEl = document.getElementById('apiToken');
          const token = tokenEl ? tokenEl.value : null;
          setStatus('starting...');
          disableRun(true);
          // Echo the submitted script into the output and history
          append('>>> ' + script);
          append(String.fromCharCode(10));
          addHistory(script, shellPath);
          try {
            append('[ui] POST /api/shell/run');
            const resp = await fetch('/api/shell/run', {
              method: 'POST',
              headers: Object.assign({'Content-Type': 'application/json'}, token ? {'X-API-Token': token} : {}),
              body: JSON.stringify({ script, shell_path: shellPath, trace_x, workdir_mode }),
            });
            if (!resp.ok) { const t = await resp.text(); throw new Error(t || ('HTTP '+resp.status)); }
            const data = await resp.json();
            currentJob = data.job_id;
            append('[ui] job ' + currentJob + ' started');
            setStatus('running (pid '+(data.pid || '?')+')');
            // WebSocket stream (token via query string if present)
            const wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
            const qs = token ? ('?token='+encodeURIComponent(token)) : '';
            ws = new WebSocket(wsScheme + '://' + location.host + '/ws/shell/' + data.job_id + qs);
            ws.onopen = function () { console.log('[ws-open]'); append('[ws-open]'); updateHistoryStatus('running'); };
            ws.onmessage = function (e) {
              const line = e.data;
              if (line === '__CEDARPY_EOF__') {
                setStatus('finished');
                updateHistoryStatus('finished');
                disableRun(false);
                try { ws && ws.close(); } catch (e) {}
                ws = null;
              } else {
                append(line);
              }
            };
            ws.onerror = function (e) {
              console.error('[ws-error]', e);
              append('[ws-error]');
              setStatus('error');
              updateHistoryStatus('error');
              disableRun(false);
              try { ws && ws.close(); } catch (e2) {}
              ws = null;
            };
            ws.onclose = function (e) {
              var code=(e && e.code) ? e.code : '';
              console.log('[ws-close]', code);
              if (statusEl.textContent === 'starting...' || statusEl.textContent.indexOf('running') === 0) {
                setStatus('closed');
                updateHistoryStatus('closed');
                disableRun(false);
              }
            };
          } catch (err) {
            console.error('[ui] run error', err);
            append('[error] ' + err);
            setStatus('error');
            disableRun(false);
          }
        });

        stopBtn.addEventListener('click', async () => {
          if (!currentJob) return;
          const token = document.getElementById('apiToken').value || null;
          console.log('[ui] stop clicked for job', currentJob);
          append('[ui] stop clicked');
          updateHistoryStatus('stopping');
          try {
            const resp = await fetch(`/api/shell/stop/${currentJob}`, { method: 'POST', headers: token ? {'X-API-Token': token} : {} });
            if (!resp.ok) { append('[stop-error] ' + (await resp.text())); return; }
            append('[killing]');
            try { ws && ws.close(); } catch (e2) {}
            ws = null;
          } catch (e) { console.error('[stop-error]', e); append('[stop-error] ' + e); }
        });

        // Quick action: Open World — one click to run a simple script and stream output
        if (openWorldBtn) {
          openWorldBtn.addEventListener('click', async () => {
            try {
              output.textContent = '';
              append('[ui] open world clicked');
              const tokenEl = document.getElementById('apiToken');
              const token = tokenEl ? tokenEl.value : null;
              const traceEl = document.getElementById('traceX');
              const trace_x = !!(traceEl && traceEl.checked);
              const workdir_mode = workdirModeEl ? workdirModeEl.value : 'data';
              addHistory('echo hello world', null);
              append('>>> echo hello world');
              append(String.fromCharCode(10));
              const resp = await fetch('/api/shell/run', {
                method: 'POST',
                headers: Object.assign({'Content-Type': 'application/json'}, token ? {'X-API-Token': token} : {}),
                body: JSON.stringify({ script: 'echo hello world', trace_x, workdir_mode }),
              });
              if (!resp.ok) { append('[error] ' + (await resp.text())); return; }
              const data = await resp.json();
              setStatus('running (pid '+(data.pid || '?')+')');
              const wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
              const qs = token ? ('?token='+encodeURIComponent(token)) : '';
              // Reuse outer ws so Stop can close it
              ws = new WebSocket(wsScheme + '://' + location.host + '/ws/shell/' + data.job_id + qs);
              ws.onopen = function () { console.log('[ws-open]'); append('[ws-open]'); updateHistoryStatus('running'); };
              ws.onmessage = function (e) {
                const line = e.data;
                if (line === '__CEDARPY_EOF__') {
                  setStatus('finished');
                  updateHistoryStatus('finished');
                  try { ws.close(); } catch (e) {}
                } else {
                  append(line);
                }
              };
              ws.onerror = function () { append('[ws-error]'); setStatus('error'); updateHistoryStatus('error'); try { ws.close(); } catch (e) {} };
            } catch (e) {
              console.error('[openworld-error]', e);
              append('[openworld-error] ' + e);
            }
          });
        }
      </script>
    """
    body = body.replace("__DEFAULT_SHELL__", default_shell)
    body = body.replace("__DATA_DIR__", default_data_dir)
    return layout("Shell", body)


@app.post("/api/shell/run")
def api_shell_run(request: Request, body: ShellRunRequest, x_api_token: Optional[str] = Header(default=None)):
    require_shell_enabled_and_auth(request, x_api_token)
    script = body.script
    shell_path = body.shell_path
    trace_x = bool(body.trace_x) if body.trace_x is not None else False
    # Resolve working directory
    workdir_eff = None
    try:
        if body.workdir and isinstance(body.workdir, str) and body.workdir.strip():
            workdir_eff = os.path.abspath(os.path.expanduser(body.workdir.strip()))
        else:
            mode = (body.workdir_mode or "data").strip().lower()
            if mode == "root":
                workdir_eff = "/"
            else:
                workdir_eff = SHELL_DEFAULT_WORKDIR
    except Exception:
        workdir_eff = SHELL_DEFAULT_WORKDIR
    # Server-side trace for UI clicks
    try:
        host = request.client.host if request and request.client else "?"
        cookie_tok = request.cookies.get("Cedar-Shell-Token") if hasattr(request, "cookies") else None
        tok_src = "hdr" if x_api_token else ("cookie" if cookie_tok else "no")
        print(f"[shell-api] RUN click from={host} token={tok_src} shell_path={(shell_path or os.environ.get('SHELL') or '')} script_len={len(script or '')} trace_x={trace_x} workdir={workdir_eff}")
    except Exception:
        pass
    if not script or not isinstance(script, str):
        raise HTTPException(status_code=400, detail="script is required")
    job = start_shell_job(script=script, shell_path=shell_path, trace_x=trace_x, workdir=workdir_eff)
    pid = job.proc.pid if job.proc else None
    try:
        print(f"[shell-api] job started id={job.id} pid={pid}")
    except Exception:
        pass
    return {"job_id": job.id, "pid": pid, "started_at": job.start_time.isoformat() + "Z"}


# WebSocket streaming endpoint
@app.websocket("/ws/shell/{job_id}")
async def ws_shell(websocket: WebSocket, job_id: str):
    # Auth: token via query or cookie; else local-only when no token configured
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    if not SHELL_API_ENABLED:
        try:
            print(f"[ws] reject disabled job_id={job_id}")
        except Exception:
            pass
        await websocket.close(code=4403)
        return
    if SHELL_API_TOKEN:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        tok = token_q or cookie_tok
        if tok != SHELL_API_TOKEN:
            try:
                print(f"[ws] reject auth job_id={job_id}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    else:
        # local-only
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            try:
                print(f"[ws] reject non-local job_id={job_id} from={client_host}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return

    job = get_shell_job(job_id)
    if not job:
        try:
            print(f"[ws] reject not-found job_id={job_id}")
        except Exception:
            pass
        await websocket.close(code=4404)
        return

    try:
        ch = (websocket.client.host if websocket.client else "?")
        print(f"[ws] accept job_id={job_id} from={ch}")
    except Exception:
        pass
    await websocket.accept()
    # Send backlog
    try:
        for line in job.output_lines:
            await websocket.send_text(line)
    except Exception:
        # Ignore send errors on backlog
        pass

    # Live stream
    try:
        while True:
            try:
                line = job.queue.get(timeout=1.0)
            except Exception:
                if job.status in ("finished", "error", "killed"):
                    await websocket.send_text("__CEDARPY_EOF__")
                    break
                continue
            if line == "__CEDARPY_EOF__\n":
                await websocket.send_text("__CEDARPY_EOF__")
                break
            await websocket.send_text(line)
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do
        try:
            print(f"[ws] disconnect job_id={job_id}")
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[ws] error job_id={job_id} err={type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        try:
            print(f"[ws] closed job_id={job_id} status={job.status}")
        except Exception:
            pass

# WebSocket health/handshake endpoint
@app.websocket("/ws/health")
async def ws_health(websocket: WebSocket):
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    if not SHELL_API_ENABLED:
        try:
            print("[ws-health] reject disabled")
        except Exception:
            pass
        await websocket.close(code=4403)
        return
    if SHELL_API_TOKEN:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        tok = token_q or cookie_tok
        if tok != SHELL_API_TOKEN:
            try:
                print("[ws-health] reject auth")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    else:
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            try:
                print(f"[ws-health] reject non-local from={client_host}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    try:
        ch = (websocket.client.host if websocket.client else "?")
        print(f"[ws-health] accept from={ch}")
    except Exception:
        pass
    await websocket.accept()
    try:
        await websocket.send_text("WS-OK")
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass

# WebSocket SQL endpoint (WebSockets-only contract for DB queries)
# Accepts JSON messages: { sql: "...", max_rows?: number }
# Responds with JSON per message: { ok, statement_type, columns?, rows?, rowcount?, truncated?, error? }
# Auth mirrors other WS endpoints: token via query (?token=...) when CEDARPY_SHELL_API_TOKEN is set; otherwise local-only.
@app.websocket("/ws/sql/{project_id}")
async def ws_sql(websocket: WebSocket, project_id: int):
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    if not SHELL_API_ENABLED:
        await websocket.close(code=4403)
        return
    if SHELL_API_TOKEN:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        if (token_q or cookie_tok) != SHELL_API_TOKEN:
            await websocket.close(code=4401)
            return
    else:
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    # Ensure per-project database exists
    try:
        ensure_project_initialized(project_id)
    except Exception:
        pass
    # Process messages
    while True:
        try:
            msg = await websocket.receive_text()
        except WebSocketDisconnect:
            break
        except Exception:
            break
        if not msg:
            continue
        if msg.strip() == "__CLOSE__":
            break
        payload = None
        try:
            payload = json.loads(msg)
        except Exception:
            payload = {"sql": msg}
        sql_text = (payload.get("sql") if isinstance(payload, dict) else msg) or ""
        try:
            try:
                max_rows = int(payload.get("max_rows", int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200")))) if isinstance(payload, dict) else int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200"))
            except Exception:
                max_rows = 200
            result = _execute_sql(sql_text, project_id, max_rows=max_rows)
            out = {
                "ok": bool(result.get("success")),
                "statement_type": result.get("statement_type"),
                "columns": result.get("columns"),
                "rows": result.get("rows"),
                "rowcount": result.get("rowcount"),
                "truncated": result.get("truncated"),
                "error": None if result.get("success") else result.get("error"),
            }
        except Exception as e:
            out = {"ok": False, "error": str(e)}
        try:
            await websocket.send_text(json.dumps(out))
        except Exception:
            break
    try:
        await websocket.close()
    except Exception:
        pass

# WebSocket SQL with undo and branch context
# Message format:
#  - { "action": "exec", "sql": "...", "branch_id": 2 | null, "branch_name": "Main" | null, "max_rows": 200 }
#  - { "action": "undo_last", "branch_id": 2 | null, "branch_name": "Main" | null }
@app.websocket("/ws/sqlx/{project_id}")
async def ws_sqlx(websocket: WebSocket, project_id: int):
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    if not SHELL_API_ENABLED:
        await websocket.close(code=4403); return
    if SHELL_API_TOKEN:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        if (token_q or cookie_tok) != SHELL_API_TOKEN:
            await websocket.close(code=4401); return
    else:
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            await websocket.close(code=4401); return

    await websocket.accept()

    # Ensure per-project database schema and storage are initialized
    try:
        ensure_project_initialized(project_id)
    except Exception:
        pass

    # Per-project session
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)

    def _resolve_branch_id(db: Session, branch_id: Optional[int], branch_name: Optional[str]) -> int:
        if branch_id:
            b = db.query(Branch).filter(Branch.id == branch_id, Branch.project_id == project_id).first()
            if b: return b.id
        if branch_name:
            b = db.query(Branch).filter(Branch.project_id == project_id, Branch.name == branch_name).first()
            if b: return b.id
        # default to Main
        main_b = db.query(Branch).filter(Branch.project_id == project_id, Branch.name == "Main").first()
        if not main_b:
            main_b = ensure_main_branch(db, project_id)
        return main_b.id

    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            break
        except Exception:
            break
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            msg = {"action": "exec", "sql": raw}

        action = (msg.get("action") or "exec").lower()
        sql_text = msg.get("sql") or ""
        br_id = msg.get("branch_id")
        br_name = msg.get("branch_name")
        try:
            max_rows = int(msg.get("max_rows", int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200"))))
        except Exception:
            max_rows = 200

        db = SessionLocal()
        try:
            branch_id_eff = _resolve_branch_id(db, br_id, br_name)
            if action == "undo_last":
                # Deterministic undo: allow specifying an explicit log_id
                log = None
                req_log_id = msg.get("log_id")
                if req_log_id:
                    try:
                        req_log_id = int(req_log_id)
                        log = db.query(SQLUndoLog).filter(SQLUndoLog.id==req_log_id, SQLUndoLog.project_id==project_id).first()
                    except Exception:
                        log = None
                if not log:
                    # Fallback: find last log for this project+branch
                    log = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id, SQLUndoLog.branch_id==branch_id_eff).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
                if not log:
                    # Fallback: find the latest log for this project whose rows_after indicate the target branch
                    cand = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).limit(50).all()
                    for lg in cand:
                        try:
                            ra = lg.rows_after or []
                            if any((isinstance(r, dict) and int(r.get("branch_id", -1)) == int(branch_id_eff)) for r in ra):
                                log = lg; break
                        except Exception:
                            pass
                if not log:
                    await websocket.send_text(json.dumps({"ok": False, "error": "Nothing to undo"}))
                    db.close(); continue
                table = _safe_identifier(log.table_name)
                pk_cols = log.pk_columns or []
                with _get_project_engine(project_id).begin() as conn:
                    if log.op == "insert":
                        for row in (log.rows_after or []):
                            conds = [f"{pc} = {_sql_quote(row.get(pc))}" for pc in pk_cols if pc in row]
                            conds.append(f"project_id = {project_id}")
                            conds.append(f"branch_id = {branch_id_eff}")
                            if conds:
                                conn.exec_driver_sql(f"DELETE FROM {table} WHERE " + " AND ".join(conds))
                    elif log.op == "delete":
                        for row in (log.rows_before or []):
                            cols = list(row.keys())
                            vals = ", ".join(_sql_quote(row[c]) for c in cols)
                            conn.exec_driver_sql(f"INSERT INTO {table} (" + ", ".join(cols) + ") VALUES (" + vals + ")")
                    elif log.op == "update":
                        for row in (log.rows_before or []):
                            sets = []
                            conds = []
                            for k, v in row.items():
                                if k in pk_cols or k in ("project_id","branch_id"):
                                    conds.append(f"{k} = {_sql_quote(v)}")
                                else:
                                    sets.append(f"{k} = {_sql_quote(v)}")
                            if sets and conds:
                                conn.exec_driver_sql(f"UPDATE {table} SET " + ", ".join(sets) + " WHERE " + " AND ".join(conds))
                try:
                    db.delete(log); db.commit()
                except Exception:
                    db.rollback()
                await websocket.send_text(json.dumps({"ok": True, "undone": True}))
                db.close(); continue
            else:
                # Execute with undo capture (SELECT/PRAGMA will be routed internally to _execute_sql)
                res = _execute_sql_with_undo(db, sql_text, project_id, branch_id_eff, max_rows=max_rows)
                # Use exact undo id from execution result when available; fall back to latest log for this branch
                last_log_id = res.get("undo_log_id")
                if last_log_id is None:
                    try:
                        _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id, SQLUndoLog.branch_id==branch_id_eff).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
                        if _last:
                            last_log_id = _last.id
                    except Exception:
                        pass
                out = {
                    "ok": bool(res.get("success")),
                    "statement_type": res.get("statement_type"),
                    "columns": res.get("columns"),
                    "rows": res.get("rows"),
                    "rowcount": res.get("rowcount"),
                    "truncated": res.get("truncated"),
                    "error": None if res.get("success") else res.get("error"),
                    "last_log_id": last_log_id,
                }
                await websocket.send_text(json.dumps(out))
        except Exception as e:
            try:
                await websocket.send_text(json.dumps({"ok": False, "error": str(e)}))
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    try:
        await websocket.close()
    except Exception:
        pass


@app.post("/api/shell/stop/{job_id}")
def api_shell_stop(job_id: str, request: Request, x_api_token: Optional[str] = Header(default=None)):
    require_shell_enabled_and_auth(request, x_api_token)
    job = get_shell_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.kill()
    return {"ok": True}


@app.get("/api/shell/status/{job_id}")
def api_shell_status(job_id: str, request: Request, x_api_token: Optional[str] = Header(default=None)):
    require_shell_enabled_and_auth(request, x_api_token)
    job = get_shell_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "return_code": job.return_code,
        "started_at": job.start_time.isoformat() + "Z",
        "ended_at": job.end_time.isoformat() + "Z" if job.end_time else None,
        "log_path": job.log_path,
    }


# ----------------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------------

# Client log ingestion API
# This endpoint receives client-side console/error logs sent by the injected script in layout().
# See README.md (section "Client-side logging") for details and troubleshooting.
class ClientLogEntry(BaseModel):
    when: Optional[str] = None
    level: str
    message: str
    url: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    stack: Optional[str] = None
    userAgent: Optional[str] = None
    origin: Optional[str] = None

@app.post("/api/client-log")
def api_client_log(entry: ClientLogEntry, request: Request):
    host = (request.client.host if request and request.client else "?")
    ts = entry.when or datetime.utcnow().isoformat() + "Z"
    lvl = (entry.level or "info").upper()
    url = entry.url or ""
    lc = f"{entry.line or ''}:{entry.column or ''}" if (entry.line or entry.column) else ""
    ua = entry.userAgent or ""
    origin = entry.origin or ""
    try:
        print(f"[client-log] ts={ts} level={lvl} host={host} origin={origin} url={url} loc={lc} ua={ua} msg={entry.message}")
        if entry.stack:
            print("[client-log-stack] " + str(entry.stack))
    except Exception:
        pass
    return {"ok": True}

# -------------------- Merge to Main (SQLite-first implementation) --------------------

@app.post("/project/{project_id}/merge_to_main")
def merge_to_main(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current_b = current_branch(db, project.id, branch_id)
    main_b = ensure_main_branch(db, project.id)
    if current_b.id == main_b.id:
        return RedirectResponse(f"/project/{project.id}?branch_id={main_b.id}&msg=Already+in+Main", status_code=303)

    merged_counts = {"files": 0, "threads": 0, "datasets": 0, "tables": 0}

    # Merge Files: copy physical files and create Main records
    paths_files = _project_dirs(project.id)["files_root"]
    src_dir = os.path.join(paths_files, f"branch_{current_b.name}")
    dst_dir = os.path.join(paths_files, f"branch_{main_b.name}")
    os.makedirs(dst_dir, exist_ok=True)
    files = db.query(FileEntry).filter(FileEntry.project_id == project.id, FileEntry.branch_id == current_b.id).all()
    for f in files:
        try:
            src_path = f.storage_path
            base_name = os.path.basename(f.filename)
            target_name = base_name
            target_path = os.path.join(dst_dir, target_name)
            # Avoid collision
            i = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(base_name)
                target_name = f"{name}__m{i}{ext}"
                target_path = os.path.join(dst_dir, target_name)
                i += 1
            shutil.copy2(src_path, target_path)
            rec = FileEntry(
                project_id=project.id,
                branch_id=main_b.id,
                filename=target_name,
                display_name=f.display_name,
                file_type=f.file_type,
                structure=f.structure,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                storage_path=os.path.abspath(target_path),
                metadata_json=f.metadata_json,
            )
            db.add(rec)
            db.commit(); db.refresh(rec)
            add_version(db, "file", rec.id, {"merged_from_branch_id": current_b.id, "file_id": rec.id})
            merged_counts["files"] += 1
        except Exception:
            db.rollback()

    # Merge Threads
    threads = db.query(Thread).filter(Thread.project_id == project.id, Thread.branch_id == current_b.id).all()
    for t in threads:
        nt = Thread(project_id=project.id, branch_id=main_b.id, title=t.title)
        db.add(nt)
        db.commit(); db.refresh(nt)
        add_version(db, "thread", nt.id, {"merged_from_branch_id": current_b.id, "thread_id": nt.id})
        merged_counts["threads"] += 1

    # Merge Datasets
    datasets = db.query(Dataset).filter(Dataset.project_id == project.id, Dataset.branch_id == current_b.id).all()
    for d in datasets:
        nd = Dataset(project_id=project.id, branch_id=main_b.id, name=d.name, description=d.description)
        db.add(nd)
        db.commit(); db.refresh(nd)
        add_version(db, "dataset", nd.id, {"merged_from_branch_id": current_b.id, "dataset_id": nd.id})
        merged_counts["datasets"] += 1

    # Merge user tables (SQLite only)
    try:
        with _get_project_engine(project.id).begin() as conn:
            if _dialect(_get_project_engine(project.id)) == "sqlite":
                # Find tables excluding our internal ones
                tbls = [r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                skip = {"projects","branches","threads","files","datasets","settings","versions","sql_undo_log"}
                for t in tbls:
                    if t in skip:
                        continue
                    if not _table_has_branch_columns(conn, t):
                        continue
                    pk_cols = _get_pk_columns(conn, t)
                    if not pk_cols:
                        continue
                    # Build column list
                    cols_rows = conn.exec_driver_sql(f"PRAGMA table_info({t})").fetchall()
                    cols = [r[1] for r in cols_rows]
                    nonkey_cols = [c for c in cols if c not in set(["project_id","branch_id"]) | set(pk_cols)]
                    # Insert missing
                    on_clause = " AND ".join([f"m.{c} = b.{c}" for c in pk_cols]) + f" AND m.project_id = b.project_id"
                    insert_cols = ", ".join(cols)
                    select_cols = ", ".join([f"b.{c}" if c not in ("branch_id",) else str(main_b.id) + " as branch_id" for c in cols])
                    conn.exec_driver_sql(f"""
                        INSERT INTO {t} ({insert_cols})
                        SELECT {select_cols}
                        FROM {t} b
                        LEFT JOIN {t} m ON {on_clause} AND m.branch_id = {main_b.id}
                        WHERE b.project_id = {project.id} AND b.branch_id = {current_b.id} AND m.rowid IS NULL
                    """)
                    # Update existing
                    if nonkey_cols:
                        set_clause = ", ".join([f"m.{c} = b.{c}" for c in nonkey_cols])
                        conn.exec_driver_sql(f"""
                            UPDATE {t} AS m
                            SET {set_clause}
                            FROM {t} AS b
                            WHERE m.project_id = {project.id}
                              AND m.branch_id = {main_b.id}
                              AND b.project_id = {project.id}
                              AND b.branch_id = {current_b.id}
                              AND """ + " AND ".join([f"b.{c} = m.{c}" for c in pk_cols]) + """
                        """)
                    merged_counts["tables"] += 1
    except Exception:
        pass

    msg = f"Merged files={merged_counts['files']}, threads={merged_counts['threads']}, datasets={merged_counts['datasets']}, tables={merged_counts['tables']}"
    return RedirectResponse(f"/project/{project.id}?branch_id={main_b.id}&msg=" + html.escape(msg), status_code=303)

# -------------------- Delete all files in branch --------------------

@app.post("/project/{project_id}/files/delete_all")
def delete_all_files(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current_b = current_branch(db, project.id, branch_id)
    # Delete records and physical files
    files = db.query(FileEntry).filter(FileEntry.project_id == project.id, FileEntry.branch_id == current_b.id).all()
    for f in files:
        try:
            if f.storage_path and os.path.exists(f.storage_path):
                os.remove(f.storage_path)
        except Exception:
            pass
        db.delete(f)
    db.commit()
    return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Files+deleted", status_code=303)

# -------------------- Make existing table branch-aware (SQLite) --------------------

@app.post("/project/{project_id}/sql/make_branch_aware")
def make_table_branch_aware(project_id: int, request: Request, table: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current_b = current_branch(db, project.id, branch_id)
    main_b = ensure_main_branch(db, project.id)

    tbl = _safe_identifier(table)
    try:
        with _get_project_engine(project.id).begin() as conn:
            if _dialect(_get_project_engine(project.id)) != "sqlite":
                return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Only+SQLite+supported+for+now", status_code=303)
            # Introspect
            info = conn.exec_driver_sql(f"PRAGMA table_info({tbl})").fetchall()
            if not info:
                return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Table+not+found", status_code=303)
            cols = [{"cid": r[0], "name": r[1], "type": r[2] or "", "notnull": int(r[3]) == 1, "dflt": r[4], "pk": int(r[5])} for r in info]
            names = {c["name"].lower() for c in cols}
            if "project_id" in names and "branch_id" in names:
                return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Already+branch-aware", status_code=303)
            # Rename old
            tmp = f"{tbl}_old_ba"
            conn.exec_driver_sql(f"ALTER TABLE {tbl} RENAME TO {tmp}")
            # Build CREATE for new table
            col_defs = []
            pk_cols = [c["name"] for c in cols if c["pk"]]
            for c in cols:
                line = f"{c['name']} {c['type']}".strip()
                if c["notnull"]:
                    line += " NOT NULL"
                # Inline PRIMARY KEY if single PK col
                if len(pk_cols) == 1 and c["name"] == pk_cols[0] and ("int" in c["type"].lower()):
                    line += " PRIMARY KEY"
                col_defs.append(line)
            # Add branch columns
            col_defs.append("project_id INTEGER NOT NULL")
            col_defs.append("branch_id INTEGER NOT NULL")
            # Table-level PK for composite keys
            if len(pk_cols) > 1:
                pk_list = ", ".join(pk_cols)
                col_defs.append(f"PRIMARY KEY ({pk_list})")
            create_sql = f"CREATE TABLE {tbl} (" + ", ".join(col_defs) + ")"
            conn.exec_driver_sql(create_sql)
            # Copy data into Main
            old_cols_list = ", ".join([c["name"] for c in cols])
            insert_cols_list = old_cols_list + ", project_id, branch_id"
            conn.exec_driver_sql(
                f"INSERT INTO {tbl} ({insert_cols_list}) SELECT {old_cols_list}, {project.id}, {main_b.id} FROM {tmp}"
            )
            # Drop old
            conn.exec_driver_sql(f"DROP TABLE {tmp}")
    except Exception as e:
        return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Error:+{html.escape(str(e))}", status_code=303)

    return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Converted+{tbl}+to+branch-aware", status_code=303)

BRANCH_AWARE_SQL_DEFAULT = os.getenv("CEDARPY_SQL_BRANCH_MODE", "1") == "1"

# -------------------- Undo last SQL --------------------

@app.post("/project/{project_id}/sql/undo_last")
def undo_last_sql(project_id: int, request: Request, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current_b = current_branch(db, project.id, branch_id)

    log = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project.id, SQLUndoLog.branch_id==current_b.id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
    if not log:
        return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Nothing+to+undo", status_code=303)

    table = _safe_identifier(log.table_name)
    pk_cols = log.pk_columns or []
    try:
        with _get_project_engine(project.id).begin() as conn:
            if log.op == "insert":
                # Delete rows we inserted
                for row in (log.rows_after or []):
                    conds = [f"{pc} = {_sql_quote(row.get(pc))}" for pc in pk_cols if pc in row]
                    conds.append(f"project_id = {project.id}")
                    conds.append(f"branch_id = {current_b.id}")
                    if conds:
                        conn.exec_driver_sql(f"DELETE FROM {table} WHERE " + " AND ".join(conds))
            elif log.op == "delete":
                # Re-insert rows
                for row in (log.rows_before or []):
                    cols = list(row.keys())
                    vals = ", ".join(_sql_quote(row[c]) for c in cols)
                    conn.exec_driver_sql(f"INSERT INTO {table} (" + ", ".join(cols) + ") VALUES (" + vals + ")")
            elif log.op == "update":
                # Restore before values
                for row in (log.rows_before or []):
                    sets = []
                    conds = []
                    for k, v in row.items():
                        if k in pk_cols or k in ("project_id","branch_id"):
                            conds.append(f"{k} = {_sql_quote(v)}")
                        else:
                            sets.append(f"{k} = {_sql_quote(v)}")
                    if sets and conds:
                        conn.exec_driver_sql(f"UPDATE {table} SET " + ", ".join(sets) + " WHERE " + " AND ".join(conds))
    except Exception as e:
        return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Undo+failed:+{html.escape(str(e))}", status_code=303)

    # Remove the log entry we just undid
    try:
        db.delete(log)
        db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Undone", status_code=303)

# -------------------- SQL Helpers for Branch-Aware Mode --------------------

def _dialect(engine_obj=None) -> str:
    eng = engine_obj or registry_engine
    return eng.dialect.name


def _table_has_branch_columns(conn, table: str) -> bool:
    # In per-project mode, branch-aware columns are optional. Keep helpers for backward-compat actions.
    try:
        if _dialect() == "sqlite":
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            cols = {r[1] for r in rows}
            return "project_id" in cols and "branch_id" in cols
        elif _dialect() == "mysql":
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            ).fetchall()
            cols = {r[0] for r in rows}
            return "project_id" in cols and "branch_id" in cols
    except Exception:
        return False
    return False


def _get_pk_columns(conn, table: str) -> List[str]:
    try:
        if _dialect() == "sqlite":
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            return [r[1] for r in rows if r[5]]  # r[5] is pk flag
        elif _dialect() == "mysql":
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_KEY='PRI'",
                (table,),
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []
    return []


def _safe_identifier(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "", name)


def _preprocess_sql_branch_aware(conn, sql_text: str, project_id: int, branch_id: int, main_id: int) -> Tuple[str, bool]:
    """
    STRICT EXPLICIT-ONLY MODE:
    - No automatic SQL rewriting or injection is performed.
    - SELECT/INSERT/UPDATE/DELETE/CREATE are executed exactly as provided.
    - See BRANCH_SQL_POLICY.md for required patterns when operating on branch-aware tables.
    Returns (sql_as_is, False)
    """
    s = (sql_text or "").strip()
    return (s, False)


@app.post("/project/{project_id}/sql", response_class=HTMLResponse)
def execute_sql(project_id: int, request: Request, sql: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # resolve current project and branch
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")

    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()

    # Support branch context for links back to Files/Threads views
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    current = current_branch(db, project.id, branch_id)

    # Prepare standard lists for the page
    show_branch_ids = branch_filter_ids(db, project.id, current.id)
    files = db.query(FileEntry) \
        .filter(FileEntry.project_id == project.id, FileEntry.branch_id.in_(show_branch_ids)) \
        .order_by(FileEntry.created_at.desc()) \
        .all()
    threads = db.query(Thread) \
        .filter(Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids)) \
        .order_by(Thread.created_at.desc()) \
        .all()
    datasets = db.query(Dataset) \
        .filter(Dataset.project_id == project.id, Dataset.branch_id.in_(show_branch_ids)) \
        .order_by(Dataset.created_at.desc()) \
        .all()

    # Execute SQL with branch-aware preprocessing by default
    try:
        max_rows = int(os.getenv("CEDARPY_SQL_MAX_ROWS", "200"))
    except Exception:
        max_rows = 200
    with _get_project_engine(project.id).begin() as conn:
        main = db.query(Branch).filter(Branch.project_id == project.id, Branch.name == "Main").first()
        transformed_sql, transformed = _preprocess_sql_branch_aware(conn, sql, project.id, current.id, main.id)
    result = _execute_sql_with_undo(db, transformed_sql, project.id, current.id, max_rows=max_rows)
    sql_block = _render_sql_result_html(result)

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, msg="Per-project database is active", sql_result_block=sql_block))

def _render_sql_result_html(result: dict) -> str:
    if not result:
        return ""
    if not result.get("success"):
        return f"<div class='muted' style='color:#b91c1c'>Error: {escape(str(result.get('error') or 'unknown error'))}</div>"
    info = []
    if result.get("statement_type"):
        info.append(f"<span class='pill'>{escape(result['statement_type'].upper())}</span>")
    if "rowcount" in result and result["rowcount"] is not None:
        info.append(f"<span class='small muted'>rowcount: {result['rowcount']}</span>")
    if result.get("truncated"):
        info.append("<span class='small muted'>truncated</span>")
    info_html = " ".join(info)

    # Table for rows
    rows_html = ""
    if result.get("columns") and result.get("rows") is not None:
        headers = ''.join(f"<th>{escape(str(c))}</th>" for c in result["columns"])
        body_rows = []
        for row in result["rows"]:
            tds = []
            for val in row:
                s = str(val)
                if len(s) > 400:
                    s = s[:400] + "…"
                tds.append(f"<td class='small'>{escape(s)}</td>")
            body_rows.append(f"<tr>{''.join(tds)}</tr>")
        body_rows_html = ''.join(body_rows) or '<tr><td class="muted">(no rows)</td></tr>'
        rows_html = f"<table class='table'><thead><tr>{headers}</tr></thead><tbody>{body_rows_html}</tbody></table>"

    return f"""
      <div style='margin-top:10px'>
        <div>{info_html}</div>
        {rows_html}
      </div>
    """


def _sql_quote(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return "'" + s + "'"


def _extract_where_clause(sql_text: str) -> Optional[str]:
    s = sql_text
    low = s.lower()
    i = low.find(" where ")
    if i == -1:
        return None
    return s[i+7:].strip()


def _execute_sql(sql_text: str, project_id: int, max_rows: int = 200) -> dict:
    # Execute against the per-project database
    sql_text = (sql_text or "").strip()
    if not sql_text:
        return {"success": False, "error": "Empty SQL"}
    first = sql_text.split()[0].lower() if sql_text.split() else ""
    stype = first
    result: dict = {"success": False, "statement_type": stype}
    try:
        with _get_project_engine(project_id).begin() as conn:
            if first in ("select", "pragma", "show"):
                res = conn.exec_driver_sql(sql_text)
                cols = list(res.keys()) if res.returns_rows else []
                rows = []
                count = 0
                if res.returns_rows:
                    for r in res:
                        rows.append([r[c] if isinstance(r, dict) else r[idx] for idx, c in enumerate(cols)])
                        count += 1
                        if count >= max_rows:
                            break
                result.update({
                    "success": True,
                    "columns": cols,
                    "rows": rows,
                    "rowcount": None,
                    "truncated": res.returns_rows and (count >= max_rows),
                })
            else:
                res = conn.exec_driver_sql(sql_text)
                result.update({
                    "success": True,
                    "rowcount": res.rowcount,
                })
    except Exception as e:
        result.update({"success": False, "error": str(e)})
    return result


def _execute_sql_with_undo(db: Session, sql_text: str, project_id: int, branch_id: int, max_rows: int = 200) -> dict:
    # Enforce strict explicit-branch policy for mutations; no auto-rewrites.
    # See BRANCH_SQL_POLICY.md
    s = (sql_text or "").strip()
    if not s:
        return {"success": False, "error": "Empty SQL"}
    first = s.split()[0].lower() if s.split() else ""
    if first in ("select", "pragma", "show", "create"):
        return _execute_sql(s, project_id, max_rows=max_rows)

    # Simple parse
    m_ins = re.match(r"insert\s+into\s+([a-zA-Z0-9_]+)\s*\(([^\)]+)\)\s*values\s*\((.+)\)\s*;?$", s, flags=re.IGNORECASE | re.DOTALL)
    m_upd = re.match(r"update\s+([a-zA-Z0-9_]+)\s+set\s+(.+?)\s*(where\s+(.+))?;?$", s, flags=re.IGNORECASE | re.DOTALL)
    m_del = re.match(r"delete\s+from\s+([a-zA-Z0-9_]+)\s*(where\s+(.+))?;?$", s, flags=re.IGNORECASE | re.DOTALL)

    op = None
    table = None
    where_sql = None
    cols_list = []
    vals_list = []

    if m_ins:
        op = "insert"; table = _safe_identifier(m_ins.group(1))
        cols_list = [c.strip() for c in m_ins.group(2).split(",")]
        vals_list = [v.strip() for v in m_ins.group(3).split(",")]
    elif m_upd:
        op = "update"; table = _safe_identifier(m_upd.group(1))
        where_sql = m_upd.group(4)
    elif m_del:
        op = "delete"; table = _safe_identifier(m_del.group(1))
        where_sql = m_del.group(3)

    if not op or not table:
        # Fallback
        return _execute_sql(s, project_id, max_rows=max_rows)

    # Only capture for manageable row counts
    try:
        undo_cap = int(os.getenv("CEDARPY_SQL_UNDO_MAX_ROWS", "1000"))
    except Exception:
        undo_cap = 1000

    with _get_project_engine(project_id).begin() as conn:
        # Strict explicit-only enforcement for branch-aware tables
        try:
            table_for_check = None
            if m_ins:
                table_for_check = _safe_identifier(m_ins.group(1))
            elif m_upd:
                table_for_check = _safe_identifier(m_upd.group(1))
            elif m_del:
                table_for_check = _safe_identifier(m_del.group(1))
            if table_for_check:
                if _table_has_branch_columns(conn, table_for_check):
                    # INSERT must list both project_id and branch_id columns explicitly
                    if m_ins:
                        cols_ci = [c.strip().lower() for c in cols_list]
                        missing = [c for c in ("project_id","branch_id") if c not in cols_ci]
                        if missing:
                            return {"success": False, "error": f"Strict branch policy: INSERT into '{table_for_check}' must explicitly include columns: {', '.join(missing)}. See BRANCH_SQL_POLICY.md"}
                    # UPDATE/DELETE must have WHERE that references both project_id and branch_id
                    if m_upd or m_del:
                        where_lc = (where_sql or "").lower()
                        if ("project_id" not in where_lc) or ("branch_id" not in where_lc):
                            return {"success": False, "error": f"Strict branch policy: {op.upper()} on '{table_for_check}' must include WHERE with both project_id and branch_id. See BRANCH_SQL_POLICY.md"}
        except Exception as _enf_err:
            # Be safe: if enforcement itself errors, block the write
            return {"success": False, "error": f"Strict branch policy check failed: {_enf_err}"}

        # Determine PK columns if any
        pk_cols = _get_pk_columns(conn, table)
        rows_before = []
        rows_after = []
        created_log_id = None

        if op in ("update", "delete"):
            w = _extract_where_clause(s)
            if w:
                sel_sql = f"SELECT * FROM {table} WHERE {w}"
                res = conn.exec_driver_sql(sel_sql)
                cols = list(res.keys()) if res.returns_rows else []
                count = 0
                for r in res:
                    row = {cols[i]: r[i] for i in range(len(cols))}
                    rows_before.append(row)
                    count += 1
                    if count >= undo_cap: break

        # Execute original statement
        conn.exec_driver_sql(s)

        if op == "insert":
            # Try to identify inserted row
            if pk_cols:
                # Construct a WHERE from provided PK values if present
                provided = {c.lower(): vals_list[i] for i, c in enumerate(cols_list)} if cols_list and vals_list else {}
                have_pk_vals = all(pc.lower() in provided for pc in pk_cols)
                if have_pk_vals:
                    conds = []
                    for pc in pk_cols:
                        raw = provided[pc.lower()]
                        conds.append(f"{pc} = {raw}")
                    conds.append(f"project_id = {project_id}")
                    conds.append(f"branch_id = {branch_id}")
                    sel = f"SELECT * FROM {table} WHERE " + " AND ".join(conds)
                    res2 = conn.exec_driver_sql(sel)
                    cols2 = list(res2.keys()) if res2.returns_rows else []
                    for r in res2:
                        rows_after.append({cols2[i]: r[i] for i in range(len(cols2))})
                else:
                    # SQLite last_insert_rowid for single integer PK
                    if _dialect(_get_project_engine(project_id)) == "sqlite" and len(pk_cols) == 1:
                        pk = pk_cols[0]
                        rid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
                        res2 = conn.exec_driver_sql(f"SELECT * FROM {table} WHERE {pk} = {rid}")
                        cols2 = list(res2.keys()) if res2.returns_rows else []
                        for r in res2:
                            rows_after.append({cols2[i]: r[i] for i in range(len(cols2))})
        elif op == "update":
            if where_sql:
                res3 = conn.exec_driver_sql(f"SELECT * FROM {table} WHERE {where_sql}")
                cols3 = list(res3.keys()) if res3.returns_rows else []
                count = 0
                for r in res3:
                    rows_after.append({cols3[i]: r[i] for i in range(len(cols3))})
                    count += 1
                    if count >= undo_cap: break

        # Store undo log
        try:
            log = SQLUndoLog(
                project_id=project_id,
                branch_id=branch_id,
                table_name=table,
                op=op,
                sql_text=s,
                pk_columns=pk_cols,
                rows_before=rows_before,
                rows_after=rows_after,
            )
            db.add(log)
            # Ensure PK is assigned before commit even if expire_on_commit=True
            db.flush()
            try:
                created_log_id = log.id
            except Exception:
                created_log_id = None
            db.commit()
        except Exception:
            db.rollback()

    # Return a generic result (we can run a SELECT for UPDATE/DELETE to show rowcount)
    _res = _execute_sql(
        f"SELECT changes() as affected" if _dialect(_get_project_engine(project_id)) == "sqlite" else s,
        project_id,
        max_rows=max_rows,
    )
    # Include undo_log_id when we created one
    if created_log_id is not None:
        try:
            _res["undo_log_id"] = created_log_id
        except Exception:
            pass
    return _res

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_registry_db)):
    # Central registry for list of projects
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return layout("Cedar", projects_list_html(projects))


@app.post("/projects/create")
def create_project(title: str = Form(...), db: Session = Depends(get_registry_db)):
    title = title.strip()
    if not title:
        return RedirectResponse("/", status_code=303)
    # create project in registry
    p = Project(title=title)
    db.add(p)
    db.commit()
    db.refresh(p)
    add_version(db, "project", p.id, {"title": p.title})

    # Initialize per-project DB schema and seed project + Main branch
    try:
        eng = _get_project_engine(p.id)
        Base.metadata.create_all(eng)
        SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
        pdb = SessionLocal()
        try:
            # Insert the project row in the project DB with the same ID
            if not pdb.query(Project).filter(Project.id == p.id).first():
                pdb.add(Project(id=p.id, title=p.title))
                pdb.commit()
            ensure_main_branch(pdb, p.id)
        finally:
            pdb.close()
        _ensure_project_storage(p.id)
    except Exception:
        pass

    # Redirect into the new project's Main branch
    # Open per-project DB to get Main ID again (safe)
    try:
        eng = _get_project_engine(p.id)
        SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
        with SessionLocal() as pdb:
            main = ensure_main_branch(pdb, p.id)
            main_id = main.id
    except Exception:
        main_id = 1
    return RedirectResponse(f"/project/{p.id}?branch_id={main_id}", status_code=303)


@app.get("/project/{project_id}", response_class=HTMLResponse)
def view_project(project_id: int, branch_id: Optional[int] = None, msg: Optional[str] = None, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")

    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()

    current = current_branch(db, project.id, branch_id)

    # which branches to show (roll-up logic)
    show_branch_ids = branch_filter_ids(db, project.id, current.id)

    files = db.query(FileEntry)\
        .filter(FileEntry.project_id == project.id, FileEntry.branch_id.in_(show_branch_ids))\
        .order_by(FileEntry.created_at.desc())\
        .all()

    threads = db.query(Thread)\
        .filter(Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids))\
        .order_by(Thread.created_at.desc())\
        .all()

    datasets = db.query(Dataset)\
        .filter(Dataset.project_id == project.id, Dataset.branch_id.in_(show_branch_ids))\
        .order_by(Dataset.created_at.desc())\
        .all()

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, msg=msg))


@app.post("/project/{project_id}/branches/create")
def create_branch(project_id: int, name: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)
    name = name.strip()
    if not name or name.lower() == "main":
        # prevent duplicate/invalid
        main = ensure_main_branch(db, project.id)
        return RedirectResponse(f"/project/{project.id}?branch_id={main.id}&msg=Invalid+branch+name", status_code=303)
    # create branch
    b = Branch(project_id=project.id, name=name, is_default=False)
    db.add(b)
    try:
        db.commit()
    except Exception:
        db.rollback()
        main = ensure_main_branch(db, project.id)
        return RedirectResponse(f"/project/{project.id}?branch_id={main.id}&msg=Branch+already+exists", status_code=303)
    db.refresh(b)
    add_version(db, "branch", b.id, {"project_id": project.id, "name": b.name, "is_default": False})
    return RedirectResponse(f"/project/{project.id}?branch_id={b.id}", status_code=303)


@app.post("/project/{project_id}/threads/create")
def create_thread(project_id: int, request: Request, title: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # branch selected via query parameter
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)
    t = Thread(project_id=project.id, branch_id=branch.id, title=title.strip())
    db.add(t)
    db.commit()
    db.refresh(t)
    add_version(db, "thread", t.id, {"project_id": project.id, "branch_id": branch.id, "title": t.title})
    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&msg=Thread+created", status_code=303)


@app.post("/project/{project_id}/files/upload")
# LLM classification runs after file is saved. See README for API key setup.
# If LLM fails or is disabled, the file is kept and structure fields remain unset.
def upload_file(project_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Determine path: per-project files root
    paths = _project_dirs(project.id)
    branch_dir_name = f"branch_{branch.name}"
    project_dir = os.path.join(paths["files_root"], branch_dir_name)
    os.makedirs(project_dir, exist_ok=True)

    original_name = file.filename or "upload.bin"
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_base = os.path.basename(original_name)
    storage_name = f"{ts}__{safe_base}"
    disk_path = os.path.join(project_dir, storage_name)

    with open(disk_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)

    size = os.path.getsize(disk_path)
    mime, _ = mimetypes.guess_type(original_name)
    ftype = file_extension_to_type(original_name)

    meta = interpret_file(disk_path, original_name)

    record = FileEntry(
        project_id=project.id,
        branch_id=branch.id,
        filename=storage_name,
        display_name=original_name,
        file_type=ftype,
        structure=None,
        mime_type=mime or file.content_type or "",
        size_bytes=size,
        storage_path=os.path.abspath(disk_path),
        metadata_json=meta,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # LLM classification (best-effort, no fallbacks). See README for details.
    try:
        meta_for_llm = dict(meta)
        meta_for_llm["display_name"] = original_name
        ai = _llm_classify_file(meta_for_llm)
        if ai:
            struct = ai.get("structure") if isinstance(ai, dict) else None
            record.structure = struct
            record.ai_title = ai.get("ai_title")
            record.ai_description = ai.get("ai_description")
            record.ai_category = ai.get("ai_category")
            db.commit(); db.refresh(record)
    except Exception as e:
        try:
            print(f"[llm-exec-error] {type(e).__name__}: {e}")
        except Exception:
            pass

    add_version(db, "file", record.id, {
        "project_id": project.id, "branch_id": branch.id,
        "filename": record.filename, "display_name": record.display_name,
        "file_type": record.file_type, "structure": record.structure,
        "mime_type": record.mime_type, "size_bytes": record.size_bytes,
        "metadata": meta,
    })

    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&msg=File+uploaded", status_code=303)
