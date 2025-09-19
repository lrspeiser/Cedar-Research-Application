
import os
import html
import shutil
import mimetypes
import json
import csv
import io
import contextlib
import sqlite3
import math
import builtins
import hashlib
import subprocess
import threading
import asyncio
import uuid
import queue
import signal
import time
import platform
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import deque

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, Header, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse, FileResponse, JSONResponse
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

# Lightweight .env loader (no external deps). This is intentionally minimal and does not print values.
# It loads KEY=VALUE pairs, ignoring lines starting with # and blank lines. Quotes around values are trimmed.
# See README for more details about secret handling.

def _load_dotenv_files(paths: List[str]) -> None:
    def _parse_line(line: str) -> Optional[tuple]:
        s = line.strip()
        if not s or s.startswith('#'):
            return None
        if '=' not in s:
            return None
        k, v = s.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            return None
        return (k, v)
    for p in paths:
        try:
            if not p or not os.path.isfile(p):
                continue
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    kv = _parse_line(line)
                    if not kv:
                        continue
                    k, v = kv
                    # Do not override if already set in the environment
                    if os.getenv(k) is None:
                        os.environ[k] = v
        except Exception:
            # Best-effort; ignore parse errors
            pass

# First pass: load from current working directory (.env) so early config can pick it up
try:
    _load_dotenv_files([os.path.join(os.getcwd(), '.env')])
except Exception:
    pass

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

# Second pass: load .env from DATA_DIR and from app Resources (for packaged app)
try:
    candidates: List[str] = [os.path.join(DATA_DIR, '.env')]
    # If running from an app bundle or PyInstaller, try Resources or _MEIPASS
    res_env_path = None
    try:
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
            res_dir = os.path.abspath(os.path.join(app_dir, '..', 'Resources'))
            res_env_path = os.path.join(res_dir, '.env')
            candidates.append(res_env_path)
        else:
            # PyInstaller one-file (_MEIPASS)
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                res_env_path = os.path.join(meipass, '.env')
                candidates.append(res_env_path)
    except Exception:
        res_env_path = None
        pass
    # Helper to parse a simple KEY=VALUE .env
    def _parse_env_file(path: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith('#') or '=' not in s:
                        continue
                    k, v = s.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        out[k] = v
        except Exception:
            pass
        return out

    # FIRST: if DATA_DIR/.env is missing, or present but missing keys found in Resources/.env, seed/merge into user data .env
    try:
        data_env = os.path.join(DATA_DIR, '.env')
        if res_env_path and os.path.isfile(res_env_path):
            os.makedirs(DATA_DIR, exist_ok=True)
            data_vals = _parse_env_file(data_env) if os.path.isfile(data_env) else {}
            res_vals = _parse_env_file(res_env_path)

            # Add this print statement for debugging:
            try:
                print(f"[DEBUG] Seeding check. Bundled keys: {list(res_vals.keys())}, User keys: {list(data_vals.keys())}")
            except Exception:
                pass

            to_merge: Dict[str, str] = {}
            for key_name in ("OPENAI_API_KEY", "CEDARPY_OPENAI_API_KEY"):
                if key_name in res_vals and key_name not in data_vals:
                    to_merge[key_name] = res_vals[key_name]

            # Add this print statement for debugging:
            try:
                print(f"[DEBUG] Keys to merge into user .env: {list(to_merge.keys())}")
            except Exception:
                pass

            if (not os.path.isfile(data_env)) or to_merge:
                try:
                    with open(data_env, 'a', encoding='utf-8', errors='ignore') as f:
                        for k, v in to_merge.items():
                            f.write(f"{k}={v}\n")
                    try:
                        print(f"[DEBUG] Successfully wrote keys to {data_env}")
                    except Exception:
                        pass
                except Exception as e:
                    # Replace 'pass' with actual error logging
                    try:
                        print(f"[ERROR] Failed to write to user .env file at {data_env}: {e}")
                    except Exception:
                        pass
    except Exception:
        pass

    # THEN: load .env files (DATA_DIR takes precedence by being first)
    _load_dotenv_files(candidates)
except Exception:
    pass

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


def ensure_project_initialized(project_id: int) -> None:
    """Ensure the per-project database and storage exist and are seeded.
    See PROJECT_SEPARATION_README.md
    """
    try:
        eng = _get_project_engine(project_id)
        # Create all tables for this project DB
        Base.metadata.create_all(eng)
        # Lightweight migrations for this project DB
        _migrate_project_files_ai_columns(eng)
        _migrate_thread_messages_columns(eng)
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
        _migrate_thread_messages_columns(eng)
    except Exception:
        pass

# ----------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"  # Central registry only
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    branch = relationship("Branch")


class ThreadMessage(Base):
    __tablename__ = "thread_messages"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    display_title = Column(String(255))  # short title for the bubble
    payload_json = Column(JSON)          # structured prompt/result payload
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    thread = relationship("Thread")

    __table_args__ = (
        Index("ix_thread_messages_project_thread", "project_id", "thread_id", "created_at"),
    )


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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    metadata_json = Column(JSON)  # extracted metadata from interpreter
    # AI classification outputs
    ai_title = Column(String(255))
    ai_description = Column(Text)
    ai_category = Column(String(255))
    # Processing flag for UI spinner
    ai_processing = Column(Boolean, default=False)

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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    branch = relationship("Branch")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Version(Base):
    __tablename__ = "versions"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)  # "project" | "branch" | "thread" | "file" | etc.
    entity_id = Column(Integer, nullable=False)
    version_num = Column(Integer, nullable=False)
    data = Column(JSON)  # snapshot of entity data (lightweight for now)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version_num", name="uq_version_key"),
        Index("ix_versions_entity", "entity_type", "entity_id"),
    )


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    action = Column(String(255), nullable=False)
    input_json = Column(JSON)    # what we submitted (prompts, commands, SQL, etc.)
    output_json = Column(JSON)   # results (success payloads or errors)
    summary_text = Column(Text)  # LLM-produced human summary (gpt-5-nano)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_changelog_project_branch", "project_id", "branch_id", "created_at"),
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_undo_project_branch", "project_id", "branch_id", "created_at"),
    )


# Create central registry tables

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(JSON)  # optional list of strings
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_notes_project_branch", "project_id", "branch_id", "created_at"),
    )

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

# ----------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------

# LLM classification utilities (See README: "LLM classification on file upload")
# When calling web services, configure keys via env. Do not hardcode secrets.
# See README for setup and troubleshooting; verbose logs are emitted on error.
# IMPORTANT (packaged app): keys are loaded from ~/CedarPyData/.env; see README: "Where to put your OpenAI key (.env) when packaged"
# and Postmortem #7 "LLM key missing when launching the packaged app (Qt DMG)".
# Also see README section "Tabular import via LLM codegen" for the second-stage processing when structure == 'tabular'.

def _llm_client_config():
    """
    Returns (client, model) if OpenAI SDK is available and a key is configured.
    Looks up key from env first, then falls back to the user settings file via _env_get.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, None
    # Prefer env, then fallback to settings file
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or _env_get("CEDARPY_OPENAI_API_KEY") or _env_get("OPENAI_API_KEY")
    if not api_key or not str(api_key).strip():
        return None, None
    model = os.getenv("CEDARPY_OPENAI_MODEL") or _env_get("CEDARPY_OPENAI_MODEL") or "gpt-5"
    try:
        client = OpenAI(api_key=str(api_key).strip())
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
        resp = client.chat.completions.create(model=model, messages=messages)
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


def _llm_summarize_action(action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]) -> Optional[str]:
    """Summarize an action for the changelog using a small, fast model.
    Default model: gpt-5-nano (override via CEDARPY_SUMMARY_MODEL).
    Returns summary text or None on error/missing key.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("CEDARPY_SUMMARY_MODEL", "gpt-5-nano")
    try:
        client = OpenAI(api_key=api_key)
        import json as _json
        sys_prompt = (
            "You are Cedar's changelog assistant. Summarize the action in 1-3 concise sentences. "
            "Focus on what changed, why, and outcomes (including errors). Avoid secrets and long dumps."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Action: {action}"},
            {"role": "user", "content": "Input payload:"},
            {"role": "user", "content": _json.dumps(input_payload, ensure_ascii=False)},
            {"role": "user", "content": "Output payload:"},
            {"role": "user", "content": _json.dumps(output_payload, ensure_ascii=False)},
        ]
        resp = client.chat.completions.create(model=model, messages=messages)
        text = (resp.choices[0].message.content or "").strip()
        return text
    except Exception as e:
        try:
            print(f"[llm-summary-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


# ----------------------------------------------------------------------------------
# Tabular import via LLM codegen
# See README section "Tabular import via LLM codegen" for configuration and troubleshooting.
# ----------------------------------------------------------------------------------

def _snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name or "").strip("_")
    s = re.sub(r"_+", "_", s)
    s = s.lower()
    if not s:
        s = "t"
    if s[0].isdigit():
        s = "t_" + s
    return s


def _suggest_table_name(display_name: str) -> str:
    base = os.path.splitext(os.path.basename(display_name or "table"))[0]
    return _snake_case(base)


def _extract_code_from_markdown(s: str) -> str:
    try:
        import re as _re
        m = _re.search(r"```python\n(.*?)```", s, flags=_re.DOTALL | _re.IGNORECASE)
        if m:
            return m.group(1)
        m2 = _re.search(r"```\n(.*?)```", s, flags=_re.DOTALL)
        if m2:
            return m2.group(1)
        return s
    except Exception:
        return s


def _tabular_import_via_llm(project_id: int, branch_id: int, file_rec: FileEntry, db: Session) -> Dict[str, Any]:
    """
    Generate Python code via LLM to import a tabular file into the per-project SQLite DB and execute it safely.
    - Uses only stdlib modules (csv/json/sqlite3/re/io) in a restricted exec environment.
    - Creates a branch-aware table with columns: id (INTEGER PRIMARY KEY AUTOINCREMENT), project_id, branch_id, + inferred columns.
    - Inserts rows scoped to (project_id, branch_id).
    Returns a result dict with keys: ok, table, rows_inserted, columns, warnings, logs, code_size, model.
    """
    # Determine DB path and table suggestion
    paths = _project_dirs(project_id)
    sqlite_path = paths.get("db_path")
    src_path = os.path.abspath(file_rec.storage_path or "")
    table_suggest = _suggest_table_name(file_rec.display_name or file_rec.filename or "data")

    # Collect lightweight metadata for prompt
    meta = file_rec.metadata_json or {}
    sample_text = (meta.get("sample_text") or "")
    if len(sample_text) > 4000:
        sample_text = sample_text[:4000]
    info = {
        "extension": meta.get("extension"),
        "mime_guess": meta.get("mime_guess"),
        "csv_dialect": meta.get("csv_dialect"),
        "line_count": meta.get("line_count"),
        "size_bytes": meta.get("size_bytes"),
    }

    client, model_default = _llm_client_config()
    if not client:
        return {"ok": False, "error": "missing OpenAI key", "model": None}
    model = os.getenv("CEDARPY_TABULAR_MODEL") or model_default or "gpt-5"

    sys_prompt = (
        "You generate safe, robust Python 3 code to import a local tabular file into SQLite.\n"
        "Requirements:\n"
        "- Define a function run_import(src_path, sqlite_path, table_name, project_id, branch_id) -> dict.\n"
        "- Use ONLY Python standard library modules: csv, json, sqlite3, re, io, typing, math.\n"
        "- Do NOT use pandas, requests, openpyxl, numpy, duckdb, or any external libraries.\n"
        "- Create table if not exists with schema: id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, branch_id INTEGER NOT NULL, and columns inferred from the file.\n"
        "- Infer column names from headers (for CSV/TSV) or keys (for NDJSON). Normalize to snake_case, TEXT/INTEGER/REAL types conservatively.\n"
        "- Insert rows with project_id and branch_id set from the function arguments.\n"
        "- Stream the file (avoid loading everything into memory).\n"
        "- Return a JSON-serializable dict: {ok: bool, table: str, rows_inserted: int, columns: [str], warnings: [str]}.\n"
        "- Print minimal progress is okay; main signal should be the returned dict.\n"
        "- Do not write any files except via sqlite3 to the provided sqlite_path.\n"
        "Output: ONLY Python source code, no surrounding explanations."
    )

    user_payload = {
        "context": {
            "meta": info,
            "display_name": file_rec.display_name,
            "table_suggest": table_suggest,
            "hints": [
                "CSV/TSV: use csv module; prefer provided delimiter if available",
                "NDJSON: each line is a JSON object; union keys from first 100 rows",
                "If no headers, synthesize col_1..col_n"
            ]
        },
        "paths": {"src_path": src_path, "sqlite_path": sqlite_path},
        "project": {"project_id": project_id, "branch_id": branch_id},
        "snippet_utf8": sample_text,
    }

    import json as _json
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Generate the code now."},
        {"role": "user", "content": _json.dumps(user_payload, ensure_ascii=False)},
    ]

    try:
        print(f"[tabular] codegen model={model} file={file_rec.display_name} table_suggest={table_suggest}")
    except Exception:
        pass

    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        try:
            print(f"[tabular-error] codegen {type(e).__name__}: {e}")
        except Exception:
            pass
        return {"ok": False, "error": str(e), "stage": "codegen", "model": model}

    code = _extract_code_from_markdown(content)

    # Prepare a restricted exec environment
    import csv as _csv, json as _json2, sqlite3 as _sqlite3, re as _re, io as _io, math as _math

    allowed_modules = {
        "csv": _csv,
        "json": _json2,
        "sqlite3": _sqlite3,
        "re": _re,
        "io": _io,
        "math": _math,
        "typing": None,  # allow import but not used at runtime
    }

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in allowed_modules and allowed_modules[name] is not None:
            return allowed_modules[name]
        if name in allowed_modules and allowed_modules[name] is None:
            # create a minimal dummy module for typing
            import types as _types
            return _types.SimpleNamespace(__name__="typing")
        raise ImportError(f"disallowed import: {name}")

    def _safe_open(p, mode="r", *args, **kwargs):
        ab = os.path.abspath(p)
        if ("w" in mode) or ("a" in mode) or ("+" in mode):
            raise PermissionError("open() write modes are not allowed")
        if ab != src_path:
            raise PermissionError("open() denied for this path")
        return builtins.open(p, mode, *args, **kwargs)

    allowed_builtin_names = [
        "abs", "min", "max", "sum", "len", "range", "enumerate", "zip", "map", "filter",
        "any", "all", "sorted", "reversed", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
        "print"
    ]
    _base_builtins = {}
    try:
        for n in allowed_builtin_names:
            _base_builtins[n] = getattr(builtins, n)
    except Exception:
        pass
    _base_builtins["__import__"] = _safe_import
    _base_builtins["open"] = _safe_open

    safe_globals: Dict[str, Any] = {"__builtins__": _base_builtins}

    # Also inject modules for import-less usage
    safe_globals.update({"csv": _csv, "json": _json2, "sqlite3": _sqlite3, "re": _re, "io": _io})

    buf = io.StringIO()
    run_ok = False
    result: Dict[str, Any] = {}
    try:
        with contextlib.redirect_stdout(buf):
            # Compile then exec
            compiled = compile(code, filename="<llm_tabular_import>", mode="exec")
            exec(compiled, safe_globals, safe_globals)
            run_import = safe_globals.get("run_import")
            if not callable(run_import):
                raise RuntimeError("Generated code did not define run_import()")
            ret = run_import(src_path, sqlite_path, table_suggest, int(project_id), int(branch_id))
            if not isinstance(ret, dict):
                raise RuntimeError("run_import() did not return a dict")
            result = ret
            run_ok = bool(ret.get("ok"))
    except Exception as e:
        result = {"ok": False, "error": f"exec: {type(e).__name__}: {e}"}
    logs = buf.getvalue()

    # Optionally verify row count via our engine
    table_name = str(result.get("table") or table_suggest)
    rows_inserted = int(result.get("rows_inserted") or 0)
    try:
        with _get_project_engine(project_id).begin() as conn:
            try:
                cnt = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar()
                result["rowcount_check"] = int(cnt or 0)
            except Exception:
                pass
    except Exception:
        pass

    # Create Dataset entry on success
    if run_ok:
        try:
            ds = Dataset(project_id=project_id, branch_id=branch_id, name=table_name, description=f"Imported from {file_rec.display_name}")
            db.add(ds); db.commit()
        except Exception:
            db.rollback()

    out = {
        "ok": run_ok,
        "table": table_name,
        "rows_inserted": rows_inserted,
        "columns": result.get("columns"),
        "warnings": result.get("warnings"),
        "code_size": len(code or ""),
        "logs": logs[-10000:] if logs else "",
        "model": model,
    }
    if not run_ok and result.get("error"):
        out["error"] = result.get("error")
    return out

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
        meta["mtime"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        meta["ctime"] = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()
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


def record_changelog(db: Session, project_id: int, branch_id: int, action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]):
    """Persist a changelog entry and try to LLM-summarize it. Best-effort; stores even if summary fails.
    """
    summary = _llm_summarize_action(action, input_payload, output_payload)
    try:
        entry = ChangelogEntry(
            project_id=project_id,
            branch_id=branch_id,
            action=action,
            input_json=input_payload,
            output_json=output_payload,
            summary_text=summary,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        try:
            print(f"[changelog-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        db.rollback()


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

@app.on_event("startup")
def _cedarpy_startup_llm_probe():
    try:
        ok, reason, model = _llm_reachability(ttl_seconds=0)
        if ok:
            print(f"[startup] LLM ready (model={model})")
        else:
            print(f"[startup] LLM unavailable ({reason})")
    except Exception:
        pass

# Primary layout for the application (single source of truth).
# This function renders all pages; there is no secondary/stub layout.
# CI smoke tests exercise this rendering so DMG builds will block on failures.
from fastapi.responses import HTMLResponse as _HTMLResponse

def layout(title: str, body: str, header_label: Optional[str] = None, header_link: Optional[str] = None, nav_query: Optional[str] = None) -> HTMLResponse:  # type: ignore[override]
    # LLM status for header (best-effort; cached)
    try:
        ready, reason, model = _llm_reachability()
        if ready:
            llm_status = f" <a href='/settings' class='pill' title='LLM connected — click to manage key'>LLM: {escape(model)}</a>"
        else:
            llm_status = f" <a href='/settings' class='pill' style='background:#fef2f2; color:#991b1b' title='LLM unavailable — click to paste your key'>LLM unavailable ({escape(reason)})</a>"
    except Exception:
        llm_status = ""

    # Build header breadcrumb/label (optional)
    try:
        if header_label:
            lbl = escape(header_label)
            if header_link:
                header_html = f"<a href='{escape(header_link)}' style='font-weight:600'>{lbl}</a>"
            else:
                header_html = f"<span style='font-weight:600'>{lbl}</span>"
        else:
            header_html = ""
        header_info = header_html
    except Exception:
        header_html = ""
        header_info = ""

    # Build right-side navigation with optional project context (propagates ?project_id=&branch_id=)
    try:
        nav_qs = ("?" + nav_query.strip()) if (nav_query and nav_query.strip()) else ""
    except Exception:
        nav_qs = ""

    nav_html = (
        f"<a href='/'>&#8203;Projects</a> | "
        f"<a href='/shell{nav_qs}'>Shell</a> | "
        f"<a href='/merge{nav_qs}'>Merge</a> | "
        f"<a href='/changelog{nav_qs}'>Changelog</a> | "
        f"<a href='/log{nav_qs}'>Log</a> | "
        f"<a href='/settings'>Settings</a>"
    )

    # Client logging hook (console/errors -> /api/client-log)
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
  document.addEventListener('DOMContentLoaded', function(){ try { console.log('[ui] page ready'); } catch(e){} }, { once: true });
})();
</script>
"""

    # Build HTML document
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
    .small {{ font-size: 12px; }}
    .topbar {{ display:flex; align-items:center; gap:12px; }}
    .spinner {{ display:inline-block; width:12px; height:12px; border:2px solid #cbd5e1; border-top-color:#334155; border-radius:50%; animation: spin 1s linear infinite; }}
    @keyframes spin {{ from {{ transform: rotate(0deg);}} to {{ transform: rotate(360deg);}} }}

    /* Two-column layout and tabs */
    .two-col {{ display: grid; grid-template-columns: 1fr 360px; gap: 16px; align-items: start; }}
    .pane {{ display: flex; flex-direction: column; gap: 8px; }}
    .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); }}
    .tab {{ display:inline-block; padding:6px 10px; border:1px solid var(--border); border-bottom:none; border-radius:6px 6px 0 0; background:#f3f4f6; color:#111; cursor:pointer; user-select:none; }}
    .tab.active {{ background:#fff; font-weight:600; }}
    .tab-panels {{ border:1px solid var(--border); border-radius:0 6px 6px 6px; background:#fff; padding:12px; }}
    .panel.hidden {{ display:none !important; }}
    @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
  </style>
  {client_log_js}
</head>
<body>
  <header>
    <div class="topbar">
      <div><strong>Cedar</strong> <span class='muted'>•</span> {header_info}</div>
      <div style=\"margin-left:auto\">{nav_html}{llm_status}</div>
    </div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""
    try:
        html_doc = html_doc.format(llm_status=llm_status, header_info=header_html, nav_html=nav_html)
    except Exception:
        pass
    return HTMLResponse(html_doc)



@app.get("/settings", response_class=HTMLResponse)
def settings_page(msg: Optional[str] = None):
    # Do not display the actual key; show presence only
    key_present = bool(_env_get("CEDARPY_OPENAI_API_KEY") or _env_get("OPENAI_API_KEY"))
    model = _env_get("CEDARPY_OPENAI_MODEL") or _env_get("OPENAI_API_KEY_MODEL") or _env_get("CEDARPY_OPENAI_MODEL") or "gpt-5"
    banner = f"<div class='notice'>{html.escape(msg)}</div>" if msg else ""
    body = f"""
    <h1>Settings</h1>
    {banner}
    <p class='muted'>LLM keys are read from <code>{html.escape(SETTINGS_PATH)}</code>. We will not display keys here.</p>
    <p>OpenAI key status: <strong>{'Present' if key_present else 'Missing'}</strong></p>
    <p>LLM connectivity: {('✅ <strong>OK</strong> – ' + html.escape(str(model))) if _llm_reach_ok() else ('❌ <strong>Unavailable</strong> – ' + html.escape(_llm_reach_reason()))}</p>
    <form method='post' action='/settings/save'>
      <div>
        <label>OpenAI API Key</label><br/>
        <input type='password' name='openai_key' placeholder='sk-...' style='width:420px' autocomplete='off' />
      </div>
      <div style='margin-top:8px;'>
        <label>Model (optional)</label><br/>
        <input type='text' name='model' value='{html.escape(str(model))}' style='width:420px' />
      </div>
      <div style='margin-top:12px;'>
        <button type='submit'>Save</button>
      </div>
    </form>
    """
    return layout("Settings", body)


@app.post("/settings/save")
def settings_save(openai_key: str = Form("") , model: str = Form("")):
    # Persist to ~/CedarPyData/.env; do not print the key
    updates: Dict[str, str] = {}
    if openai_key and str(openai_key).strip():
        updates["OPENAI_API_KEY"] = str(openai_key).strip()
    if model and str(model).strip():
        updates["CEDARPY_OPENAI_MODEL"] = str(model).strip()
    if updates:
        _env_set_many(updates)
        return RedirectResponse("/settings?msg=Saved", status_code=303)
    else:
        return RedirectResponse("/settings?msg=No+changes", status_code=303)

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

SETTINGS_PATH = os.path.join(DATA_DIR, ".env")


def _env_get(k: str) -> Optional[str]:
    try:
        v = os.getenv(k)
        if v is None and os.path.isfile(SETTINGS_PATH):
            # Fallback: try file parse
            with open(SETTINGS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    kk, vv = s.split("=", 1)
                    if kk.strip() == k:
                        return vv.strip().strip('"').strip("'")
        return v
    except Exception:
        return None


def _env_set_many(updates: Dict[str, str]) -> None:
    """Update ~/CedarPyData/.env with provided key=value pairs, preserving other lines.
    Keys are also set in-process via os.environ. We avoid printing secret values.
    See README: Settings and Postmortem #7 for details.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # Read existing lines
        existing: Dict[str, str] = {}
        order: list[str] = []
        if os.path.isfile(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        k = k.strip()
                        if k and k not in existing:
                            existing[k] = v.rstrip("\n")
                            order.append(k)
        # Apply updates
        for k, v in updates.items():
            existing[k] = v
            if k not in order:
                order.append(k)
            # set in-process
            try:
                os.environ[k] = v
            except Exception:
                pass
        # Write back, one VAR=VALUE per line
        with open(SETTINGS_PATH, "w", encoding="utf-8", errors="ignore") as f:
            for k in order:
                val = existing.get(k)
                if val is None:
                    continue
                # Write raw; we do not quote to avoid surprises
                f.write(f"{k}={val}\n")
        # Invalidate LLM reachability cache so header updates quickly
        try:
            _LLM_READY_CACHE.update({"ts": 0.0})
        except Exception:
            pass
    except Exception:
        pass

# Cached LLM reachability indicator for UI (TTL seconds)
_LLM_READY_CACHE = {"ts": 0.0, "ready": False, "reason": "init", "model": None}


def _llm_reachability(ttl_seconds: int = 300) -> tuple[bool, str, str]:
    """Best-effort reachability check for UI. Returns (ready, reason, model).
    Cached to avoid per-request network calls. Provides clearer reasons when unavailable.
    """
    now = time.time()
    try:
        if (now - float(_LLM_READY_CACHE.get("ts") or 0)) <= max(5, ttl_seconds):
            return bool(_LLM_READY_CACHE.get("ready")), str(_LLM_READY_CACHE.get("reason") or ""), str(_LLM_READY_CACHE.get("model") or "")
    except Exception:
        pass
    # Determine SDK availability
    sdk_ok = True
    try:
        from openai import OpenAI  # type: ignore  # noqa: F401
    except Exception:
        sdk_ok = False
    # Determine key presence (env or settings file)
    key_present = bool(
        os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or _env_get("CEDARPY_OPENAI_API_KEY") or _env_get("OPENAI_API_KEY")
    )
    client, model = _llm_client_config()
    if not client:
        reason = "missing key"
        if key_present and not sdk_ok:
            reason = "OpenAI SDK missing"
        elif (not key_present) and sdk_ok:
            reason = "missing key"
        elif (not key_present) and (not sdk_ok):
            reason = "SDK+key missing"
        else:
            reason = "init error"
        _LLM_READY_CACHE.update({"ts": now, "ready": False, "reason": reason, "model": model or ""})
        return False, reason, model or ""
    try:
        # Cheap probe: retrieve the model
        client.models.retrieve(model)
        prev_ready = bool(_LLM_READY_CACHE.get("ready"))
        _LLM_READY_CACHE.update({"ts": now, "ready": True, "reason": "ok", "model": model})
        try:
            if not prev_ready:
                print(f"[llm-ready] model={model} key=ok")
        except Exception:
            pass
        return True, "ok", model
    except Exception as e:
        _LLM_READY_CACHE.update({"ts": now, "ready": False, "reason": f"{type(e).__name__}", "model": model or ""})
        return False, f"{type(e).__name__}", model or ""

# Module-level helpers used by Settings and Layout
def _llm_reach_ok() -> bool:
    try:
        ok, _, _ = _llm_reachability()
        return bool(ok)
    except Exception:
        return False

def _llm_reach_reason() -> str:
    try:
        ok, reason, _ = _llm_reachability()
        return "ok" if ok else (reason or "unknown")
    except Exception:
        return "unknown"



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
  // Client-side upload UI instrumentation (logs to console -> forwarded to /api/client-log). See README: Client-side logging.
  document.addEventListener('DOMContentLoaded', function(){
    try {
      // Typing indicator for Ask form
      try {
        var askForm = document.getElementById('askForm');
        if (askForm) {
          askForm.addEventListener('submit', function(){
            try {
              var msgs = document.getElementById('msgs');
              if (!msgs) return;
              var d = document.createElement('div');
              d.className = 'small typing';
              d.id = 'typingIndicator';
              d.innerHTML = "<span class='pill'>assistant</span> Thinking <span class='dots'><span>.</span><span>.</span><span>.</span></span>";
              msgs.appendChild(d);
            } catch(e) { try { console.error('[ui] typing indicator error', e); } catch(_) {} }
          });
        }
      } catch(e) {}

      var form = document.querySelector('[data-testid=upload-form]');
      var input = document.querySelector('[data-testid=upload-input]');
      var button = document.querySelector('[data-testid=upload-submit]');
      function setUploadingState(){
        try {
          if (!button) return;
          // Preserve original text for potential future restore (not used currently)
          if (!button.getAttribute('data-original-text')) {
            button.setAttribute('data-original-text', button.textContent || 'Upload');
          }
          button.disabled = true;
          button.setAttribute('aria-busy', 'true');
          button.innerHTML = "<span class='spinner' style=\"margin-right:6px\"></span> Uploading…";
        } catch(e) { try { console.error('[ui] setUploadingState error', e); } catch(_) {} }
      }
      if (input) {
        input.addEventListener('click', function(){ console.log('[ui] upload input clicked'); });
        input.addEventListener('change', function(ev){
          try {
            var f = (ev && ev.target && ev.target.files && ev.target.files[0]) || null;
            var name = f ? f.name : '(none)';
            var size = f ? String(f.size) : '';
            console.log('[ui] file selected', name, size);
          } catch(e) { console.error('[ui] file select error', e); }
        });
      }
      if (button) {
        button.addEventListener('click', function(){
          console.log('[ui] upload clicked');
          try {
            if (input && input.files && input.files.length > 0) { setUploadingState(); }
          } catch(e) {}
        });
      }
      if (form) {
        form.addEventListener('submit', function(){
          console.log('[ui] upload submit');
          // Only fires if required fields are satisfied; safe to show uploading state now.
          setUploadingState();
        });
      }
    } catch(e) {
      try { base('error', 'upload instrumentation error', 'client-log', { stack: e && e.stack ? String(e.stack) : null }); } catch(_) {}
    }
  }, { once: true });

  // Global button click feedback: show a brief 'Received' toast near the clicked button (no-op for non-buttons)
  (function initButtonClickFeedback(){
    try {
      function showReceived(btn){
        try {
          var t = document.createElement('div');
          t.className = 'click-received';
          t.textContent = 'Received';
          document.body.appendChild(t);
          var r = btn.getBoundingClientRect();
          var tw = t.offsetWidth || 60;
          var th = t.offsetHeight || 18;
          var left = Math.max(6, Math.min((window.innerWidth - tw - 6), r.left + (r.width/2) - (tw/2)));
          var top = Math.max(6, Math.min((window.innerHeight - th - 6), r.bottom + 6));
          t.style.left = left + 'px';
          t.style.top = top + 'px';
          setTimeout(function(){ if (t && t.parentNode) { t.parentNode.removeChild(t); } }, 1300);
          // Screen reader announcement
          try {
            var sr = document.getElementById('sr-live');
            if (!sr) {
              sr = document.createElement('div');
              sr.id = 'sr-live';
              sr.setAttribute('aria-live', 'polite');
              sr.style.position = 'absolute'; sr.style.width='1px'; sr.style.height='1px'; sr.style.overflow='hidden'; sr.style.clip='rect(1px,1px,1px,1px)'; sr.style.clipPath='inset(50%)'; sr.style.whiteSpace='nowrap'; sr.style.border='0';
              document.body.appendChild(sr);
            }
            sr.textContent = 'Received';
          } catch(_) {}
        } catch(_) {}
      }
      document.addEventListener('click', function(ev){
        try {
          var el = ev.target && ev.target.closest ? ev.target.closest('button') : null;
          if (!el) return;
          // Buttons already get a press animation via CSS :active; add a toast as confirmation
          showReceived(el);
        } catch(_) {}
      }, true);
    } catch(_) {}
  })();

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
    input[type=\"file\"] {{ padding: 6px; border: 1px dashed var(--border); border-radius: 6px; width: 100%; position: relative; z-index: 1; display: block; }}
    button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--accent); color: white; cursor: pointer; position: relative; z-index: 2; pointer-events: auto; transition: transform 80ms ease, filter 120ms ease, box-shadow 120ms ease; will-change: transform; user-select: none; }}
    button:active {{ transform: scale(0.98); filter: brightness(0.98); }}
    button.secondary {{ background: #f3f4f6; color: #111; }}
    .small {{ font-size: 12px; }}
    .topbar {{ display:flex; align-items:center; gap:12px; }}
    .spinner {{ display:inline-block; width:12px; height:12px; border:2px solid #cbd5e1; border-top-color:#334155; border-radius:50%; animation: spin 1s linear infinite; }}
    @keyframes spin {{ from {{ transform: rotate(0deg);}} to {{ transform: rotate(360deg);}} }}

    /* Two-column layout and tabs */
.two-col {{ display: grid; grid-template-columns: 1fr 360px; gap: 16px; align-items: start; }}
    .pane {{ display: flex; flex-direction: column; gap: 8px; }}
    .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); }}
    .tab {{ display:inline-block; padding:6px 10px; border:1px solid var(--border); border-bottom:none; border-radius:6px 6px 0 0; background:#f3f4f6; color:#111; cursor:pointer; user-select:none; }}
    .tab.active {{ background:#fff; font-weight:600; }}
    .tab-panels {{ border:1px solid var(--border); border-radius:0 6px 6px 6px; background:#fff; padding:12px; }}
    .panel.hidden {{ display:none !important; }}
    @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    /* Typing indicator */
    .typing {{ color: var(--muted); font-style: italic; }}
    .dots span {{ display:inline-block; opacity: 0; animation: blink 1.2s infinite; }}
    .dots span:nth-child(1) {{ animation-delay: 0s; }}
    .dots span:nth-child(2) {{ animation-delay: 0.2s; }}
    .dots span:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes blink {{ 0%, 20% {{ opacity: 0; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0; }} }}
    /* Click feedback toast */
    .click-received {{ position: fixed; background: #f1f5f9; color: #111; border: 1px solid var(--border); border-radius: 9999px; padding: 2px 8px; font-size: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); pointer-events: none; opacity: 0; transform: translateY(-4px); animation: crFade 1200ms ease forwards; }}
    @keyframes crFade {{ 0% {{ opacity: 0; transform: translateY(-4px); }} 15% {{ opacity: 1; transform: translateY(0); }} 85% {{ opacity: 1; }} 100% {{ opacity: 0; transform: translateY(-6px); }} }}
  </style>
  {client_log_js}
  <script>
  (function(){{
    function activateTab(tab) {{
      try {{
        var pane = tab.closest('.pane') || document;
        var tabs = tab.parentElement.querySelectorAll('.tab');
        tabs.forEach(function(t){{ t.classList.remove('active'); }});
        tab.classList.add('active');
        var target = tab.getAttribute('data-target');
        if (!target) return;
        var panelsRoot = pane.querySelector('.tab-panels');
        if (!panelsRoot) return;
        panelsRoot.querySelectorAll('.panel').forEach(function(p){{ p.classList.add('hidden'); }});
        var el = pane.querySelector('#' + target);
        if (el) el.classList.remove('hidden');
      }} catch(e) {{ try {{ console.error('[ui] tab error', e); }} catch(_) {{}} }}
    }}
    function initTabs(){{
      document.querySelectorAll('.tabs .tab').forEach(function(tab){{
        tab.addEventListener('click', function(ev){{ ev.preventDefault(); activateTab(tab); }});
      }});
    }}
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', initTabs, {{ once: true }});
    }} else {{
      initTabs();
    }}
  }})();
  </script>
</head>
<body>
  <header>
    <div class="topbar">
      <div><strong>Cedar</strong> <span class='muted'>•</span> {header_info}</div>
      <div style=\"margin-left:auto\">{nav_html}{llm_status}</div>
    </div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""
    # Render header status
    try:
        html_doc = html_doc.format(llm_status=llm_status, header_info=header_html, nav_html=nav_html)
    except Exception:
        pass
    return HTMLResponse(html_doc)


def projects_list_html(projects: List[Project]) -> str:
    # See PROJECT_SEPARATION_README.md
    if not projects:
        return f"""
        <h1>Projects</h1>
        <p class=\"muted\">No projects yet. Create one:</p>
        <form method=\"post\" action=\"/projects/create\" class=\"card\" style=\"max-width:520px\">
            <label>Project title</label>
            <input type=\"text\" name=\"title\" placeholder=\"My First Project\" required />
            <div style=\"height:10px\"></div>
            <button type=\"submit\">Create Project</button>
        </form>
        """
    rows = []
    for p in projects:
        rows.append(f"""
            <tr>
              <td><a href=\"/project/{p.id}\">{escape(p.title)}</a></td>
              <td class=\"small muted\">{p.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
              <td>
                <form method=\"post\" action=\"/project/{p.id}/delete\" class=\"inline\" onsubmit=\"return confirm('Delete project {escape(p.title)} and all its data?');\">
                  <button type=\"submit\" class=\"secondary\">Delete</button>
                </form>
              </td>
            </tr>
        """)
    return f"""
        <h1>Projects</h1>
        <div class=\"row\">
          <div class=\"card\" style=\"flex:2\">
            <table class=\"table\">
              <thead><tr><th>Title</th><th>Created</th><th>Actions</th></tr></thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
          </div>
          <div class=\"card\" style=\"flex:1\">
            <h3>Create a new project</h3>
            <form method=\"post\" action=\"/projects/create\">
              <input type=\"text\" name=\"title\" placeholder=\"Project title\" required />
              <div style=\"height:10px\"></div>
              <button type=\"submit\">Create</button>
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
    selected_file: Optional[FileEntry] = None,
    selected_dataset: Optional[Dataset] = None,
    selected_thread: Optional[Thread] = None,
    thread_messages: Optional[List[ThreadMessage]] = None,
    msg: Optional[str] = None,
    sql_result_block: Optional[str] = None,
) -> str:
    # See PROJECT_SEPARATION_README.md
    # branch tabs
    tabs = []
    for b in branches:
        selected = "style='font-weight:600'" if b.id == current.id else ""
        tabs.append(f"<a {selected} href='/project/{project.id}?branch_id={b.id}' class='pill'>{escape(b.name)}</a>")
    # Inline new-branch form toggle
    new_branch_form = f"""
      <form id='branchCreateForm' method='post' action='/project/{project.id}/branches/create' class='inline' style='display:none; margin-left:8px'>
        <input type='text' name='name' placeholder='experiment-1' required style='width:160px; padding:6px; border:1px solid var(--border); border-radius:6px' />
        <button type='submit' class='secondary'>Create</button>
      </form>
      <a href='#' class='pill' title='New branch' onclick="var f=document.getElementById('branchCreateForm'); if(f){{f.style.display=(f.style.display==='none'?'inline-block':'none'); var i=f.querySelector('input[name=name]'); if(i){{i.focus();}}}} return false;">+</a>
    """
    tabs_html = (" ".join(tabs)) + new_branch_form

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
              <td class=\"small muted\">{f.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
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
             <td class=\"small muted\">{t.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
           </tr>
        """)
    thread_tbody = ''.join(thread_rows) if thread_rows else '<tr><td colspan="3" class="muted">No threads yet.</td></tr>'

    # datasets table (placeholder list)
    dataset_rows = []
    for d in datasets:
        dataset_rows.append(f"""
           <tr>
             <td><a href='/project/{project.id}/threads/new?branch_id={current.id}&dataset_id={d.id}' class='thread-create' data-dataset-id='{d.id}'>{escape(d.name)}</a></td>
             <td>{escape(d.branch.name if d.branch else '')}</td>
             <td class=\"small muted\">{d.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
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
      <div class=\"card\" style=\"padding:12px\">
        <h3>SQL Console</h3>
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

    # Thread select + create controls at the top
    threads_options = ''.join([f"<option value='{escape(t.title)}'>{escape(t.title)}</option>" for t in threads])
    thread_top = f"""
      <div class='card' style='margin-top:8px; padding:12px'>
        <div class='row' style='align-items:center; gap:12px'>
          <div>
            <label class='small muted'>Select Thread</label>
            <select style='padding:6px; border:1px solid var(--border); border-radius:6px; min-width:220px'>
              {threads_options or '<option>(none)</option>'}
            </select>
          </div>
          <div>
            <form method='post' action='/project/{project.id}/threads/create?branch_id={current.id}' class='inline'>
              <label class='small muted'>Create Thread</label>
              <input type='text' name='title' placeholder='New exploration...' required style='padding:6px; border:1px solid var(--border); border-radius:6px;' />
              <button type='submit' class='secondary' style='margin-left:6px'>Create</button>
            </form>
          </div>
        </div>
      </div>
    """

    # Build right-side file list (AI title if present, else display name)
    def _file_label(ff: FileEntry) -> str:
        return (getattr(ff, 'ai_title', None) or ff.display_name or '').strip()
    files_sorted = sorted(files, key=lambda ff: (_file_label(ff).lower(), ff.created_at))
    file_list_items = []
    for f in files_sorted:
        href = f"/project/{project.id}/threads/new?branch_id={current.id}&file_id={f.id}"
        label_text = escape(_file_label(f) or f.display_name)
        sub = escape(((getattr(f, 'ai_category', None) or f.structure or f.file_type or '') or ''))
        active = (selected_file and f.id == selected_file.id)
        li_style = "font-weight:600" if active else ""
        # Show spinner only while LLM classification is actively running; checkmark when classified
        if getattr(f, 'ai_processing', False):
            status_icon = "<span class='spinner' title='processing'></span>"
        elif getattr(f, 'structure', None):
            status_icon = "<span title='classified'>✓</span>"
        else:
            status_icon = ""
        file_list_items.append(f"<li style='margin:6px 0; {li_style}'>{status_icon}<a href='{href}' class='thread-create' data-file-id='{f.id}' style='text-decoration:none; color:inherit; margin-left:6px'>{label_text}</a><div class='small muted'>{sub}</div></li>")
    file_list_html = "<ul style='list-style:none; padding-left:0; margin:0'>" + ("".join(file_list_items) or "<li class='muted'>No files yet.</li>") + "</ul>"

    # Left details panel for selected file
    def _file_detail_panel(f: Optional[FileEntry]) -> str:
        if not f:
            return "<div class='muted'>Select a file from the list to view details.</div>"
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
        meta = f.metadata_json or {}
        meta_keys = ', '.join([escape(str(k)) for k in (list(meta.keys())[:20])])
        ai_block = f"""
          <div class='small'>
            <div><strong>AI Title:</strong> {escape(getattr(f, 'ai_title', None) or '(none)')}</div>
            <div><strong>AI Category:</strong> {escape(getattr(f, 'ai_category', None) or '(none)')}</div>
            <div><strong>AI Description:</strong> {escape((getattr(f, 'ai_description', None) or '')[:350])}</div>
          </div>
        """
        tbl = f"""
          <table class='table'>
            <tbody>
              <tr><th>Name</th><td>{link_html}</td></tr>
              <tr><th>Type</th><td>{escape(f.file_type or '')}</td></tr>
              <tr><th>Structure</th><td>{escape(f.structure or '')}</td></tr>
              <tr><th>Branch</th><td>{escape(f.branch.name if f.branch else '')}</td></tr>
              <tr><th>Size</th><td class='small muted'>{f.size_bytes or 0}</td></tr>
              <tr><th>Created</th><td class='small muted'>{f.created_at:%Y-%m-%d %H:%M:%S} UTC</td></tr>
              <tr><th>Metadata keys</th><td class='small muted'>{meta_keys or '(none)'}</td></tr>
            </tbody>
          </table>
        """
        return ai_block + tbl

    left_details = _file_detail_panel(selected_file)

    # Thread tabs (above left panel)
    thr_tabs = []
    for t in threads:
        cls = "tab active" if (selected_thread and t.id == selected_thread.id) else "tab"
        thr_tabs.append(f"<a href='/project/{project.id}?branch_id={current.id}" + (f"&file_id={selected_file.id}" if selected_file else "") + f"&thread_id={t.id}' class='{cls}'>{escape(t.title)}</a>")
    thr_tabs_html = " ".join(thr_tabs) + f" <a href='/project/{project.id}/threads/new?branch_id={current.id}" + (f"&dataset_id={selected_dataset.id}" if selected_dataset else (f"&file_id={selected_file.id}" if selected_file else "")) + "' class='tab new thread-create' title='New Thread'>+</a>"

    # Render thread messages
    msgs = thread_messages or []
    msg_rows = []
    if msgs:
        idx = 0
        for m in msgs:
            idx += 1
            role = escape(m.role)
            title_txt = escape(getattr(m, 'display_title', None) or (role.upper()))
            details_id = f"msgd_{idx}"
            # Prefer payload_json when available; else show content
            details = ''
            try:
                import json as _json
                if getattr(m, 'payload_json', None) is not None:
                    try:
                        raw_json = _json.dumps(m.payload_json, ensure_ascii=False, indent=2)
                    except Exception:
                        raw_json = _json.dumps(m.payload_json, ensure_ascii=False)
                    # Attempt to surface logs fields when present
                    logs_txt = ''
                    try:
                        pj = m.payload_json or {}
                        logs_val = pj.get('logs') if isinstance(pj, dict) else None
                        if isinstance(logs_val, list):
                            logs_txt = "\n".join([str(x) for x in logs_val])
                        elif logs_val is not None:
                            logs_txt = str(logs_val)
                    except Exception:
                        logs_txt = ''
                    sections = []
                    sections.append(f"<h4 class='small muted' style='margin:6px 0'>Raw JSON</h4><pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>{escape(raw_json)}</pre>")
                    if logs_txt:
                        sections.append(f"<h4 class='small muted' style='margin:6px 0'>Logs</h4><pre class='small' style='white-space:pre-wrap; background:#0b1021; color:#e6e6e6; padding:8px; border-radius:6px; max-height:260px; overflow:auto'>{escape(logs_txt)}</pre>")
                    details = f"<div id='{details_id}' style='display:none'>" + "".join(sections) + "</div>"
                else:
                    details = f"<div id='{details_id}' style='display:none'><pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>" + escape(m.content) + "</pre></div>"
            except Exception:
                details = f"<div id='{details_id}' style='display:none'><pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>" + escape(m.content) + "</pre></div>"
            # Build a short preview to show inline in a bubble
            try:
                if getattr(m, 'payload_json', None) is not None:
                    import json as _json
                    _preview_json = _json.dumps(m.payload_json, ensure_ascii=False)
                    preview = (_preview_json[:400] + ('…' if len(_preview_json) > 400 else ''))
                else:
                    txt = m.content or ''
                    preview = (txt[:400] + ('…' if len(txt) > 400 else ''))
            except Exception:
                preview = ''
            # Role class for styling
            try:
                role_raw = (getattr(m, 'role', '') or '').strip().lower()
                role_css = 'user' if role_raw == 'user' else ('assistant' if role_raw == 'assistant' else 'system')
            except Exception:
                role_css = 'assistant'

            msg_rows.append(
                f"<div class='msg {role_css}'>"
                f"  <div class='meta small'>"
                f"    <span class='pill'>{role}</span> "
                f"    <span class='title' style='font-weight:600'>{title_txt}</span> "
                f"    <a href='#' class='small muted' onclick=\"var e=document.getElementById('{details_id}'); if(e){{ e.style.display = (e.style.display==='none'?'block':'none'); }} return false;\">details</a>"
                f"  </div>"
                f"  <div class='bubble {role_css}' data-details-id='{details_id}'><div class='content' style='white-space:pre-wrap'>{escape(preview)}</div></div>"
                f"  {details}"
                f"</div>"
            )
    else:
        msg_rows.append("<div class='muted small'>(No messages yet)</div>")
    msgs_html = "".join(msg_rows)

    # Chat form (LLM keys required; see README)
    # Only include hidden ids when present to avoid posting empty strings, which cause int parsing errors.
    hidden_thread = f"<input type='hidden' name='thread_id' value='{selected_thread.id}' />" if selected_thread else ""
    hidden_file = f"<input type='hidden' name='file_id' value='{selected_file.id}' />" if selected_file else ""
    hidden_dataset = f"<input type='hidden' name='dataset_id' value='{selected_dataset.id}' />" if selected_dataset else ""
    chat_form = f"""
      <form id='chatForm' data-project-id='{project.id}' data-branch-id='{current.id}' data-thread-id='{selected_thread.id if selected_thread else ''}' data-file-id='{selected_file.id if selected_file else ''}' data-dataset-id='{selected_dataset.id if selected_dataset else ''}' method='post' action='/project/{project.id}/threads/chat?branch_id={current.id}' style='margin-top:8px'>
        {hidden_thread}{hidden_file}{hidden_dataset}
        <textarea id='chatInput' name='content' rows='3' placeholder='Ask a question about this file/context...' style='width:100%; font-family: ui-monospace, Menlo, monospace;'></textarea>
        <div style='height:6px'></div>
        <button type='submit'>Submit</button>
        <span class='small muted'>LLM API key required; see README for setup.</span>
      </form>
    """

    # Client-side WebSocket streaming script (word-by-word). Falls back to simulated by-word if server returns full text.
    script_js = """
<script>
(function(){
  var PROJECT_ID = %d;
  var BRANCH_ID = %d;
  async function ensureThreadId(tid, fid, dsid) {
    if (tid) return tid;
    try {
      var url = `/project/${PROJECT_ID}/threads/new?branch_id=${BRANCH_ID}` + (fid?`&file_id=${encodeURIComponent(fid)}`:'') + (dsid?`&dataset_id=${encodeURIComponent(dsid)}`:'') + `&json=1`;
      var resp = await fetch(url, { method: 'GET' });
      if (!resp.ok) throw new Error('thread create failed');
      var data = await resp.json();
      var newTid = data.thread_id ? String(data.thread_id) : null;
      if (newTid) {
        try {
          var chatForm = document.getElementById('chatForm');
          if (chatForm) {
            chatForm.setAttribute('data-thread-id', newTid);
            var hiddenTid = chatForm.querySelector("input[name='thread_id']");
            if (hiddenTid) hiddenTid.value = newTid; else { var hi = document.createElement('input'); hi.type='hidden'; hi.name='thread_id'; hi.value=newTid; chatForm.appendChild(hi); }
          }
          var tabsBar = document.querySelector('.thread-tabs');
          if (tabsBar) {
            var a = document.createElement('a');
            a.href = data.redirect || (`/project/${PROJECT_ID}?branch_id=${BRANCH_ID}&thread_id=${newTid}`);
            a.className = 'tab active';
            a.textContent = data.title || 'New Thread';
            tabsBar.appendChild(a);
          }
        } catch(_){ }
      }
      return newTid;
    } catch(_err) {
      return null;
    }
  }

  function startWS(text, threadId, fileId, datasetId){
    try {
      var msgs = document.getElementById('msgs');
      if (msgs && text) {
        // Remove placeholder if present
        try { var first = msgs.firstElementChild; if (first && first.classList.contains('muted')) { first.remove(); } } catch(_){ }
        var u = document.createElement('div');
        u.className = 'small';
        u.innerHTML = "<span class='pill'>user</span> " + text.replace(/</g,'&lt;');
        msgs.appendChild(u);
      }
      var stream = document.createElement('div');
      stream.className = 'small';
      var pill = document.createElement('span'); pill.className = 'pill'; pill.textContent = 'assistant';
      var streamText = document.createElement('span');
      stream.appendChild(pill); stream.appendChild(document.createTextNode(' ')); stream.appendChild(streamText);
      // Initial visible ACK to the user
      var spin = null;
      try {
        streamText.textContent = 'Processing…';
        spin = document.createElement('span'); spin.className = 'spinner'; spin.style.marginLeft = '6px'; stream.appendChild(spin);
      } catch(_){ }
      if (msgs) msgs.appendChild(stream);

      var lastW = null;
      var stagesSeen = {};
      var wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
      var ws = new WebSocket(wsScheme + '://' + location.host + '/ws/chat/' + PROJECT_ID);

      // Client-side watchdog to ensure the user always sees progress or a timeout
      var timeoutMs = 90000; // 90s default; mirrors server CEDARPY_CHAT_TIMEOUT_SECONDS
      var finalOrError = false;
      var timeoutId = null;
      function clearSpinner(){ try { if (spin && spin.parentNode) spin.remove(); } catch(_){} }
      function refreshTimeout(){
        try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
        timeoutId = setTimeout(function(){
          if (!finalOrError) {
            try { streamText.textContent = '[timeout] Took too long. Please try again.'; } catch(_){ }
            clearSpinner();
            try { ws.close(); } catch(_){ }
          }
        }, timeoutMs);
      }

      ws.onopen = function(){
        try {
          refreshTimeout();
          // Do not print a local 'submitted'; rely on server info events for true order
          ws.send(JSON.stringify({action:'chat', content: text, branch_id: BRANCH_ID, thread_id: threadId||null, file_id: (fileId||null), dataset_id: (datasetId||null) }));
        } catch(e){}
      };
      ws.onmessage = function(ev){
        refreshTimeout();
        var m = null; try { m = JSON.parse(ev.data); } catch(_){ return; }
        if (!m) return;
        if (m.type === 'action') {
          try {
            var fn = String(m.function||'').trim();
            var args = m.args || {};
            var detId = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            var wrap = document.createElement('div'); wrap.className = 'msg system';
            var meta = document.createElement('div'); meta.className = 'meta small'; meta.innerHTML = "<span class='pill'>system</span> <span class='title' style='font-weight:600'>" + (fn==='plan' ? 'Plan created' : ('Next: ' + fn)) + "</span>";
            var bub = document.createElement('div'); bub.className = 'bubble system'; bub.setAttribute('data-details-id', detId);
            var cont = document.createElement('div'); cont.className='content'; cont.style.whiteSpace='pre-wrap';
            cont.textContent = (fn==='plan' ? ('Plan with ' + ((args.steps||[]).length) + ' step(s). Click to view.') : ('About to run ' + fn + '. Click to view args.'));
            bub.appendChild(cont);
            var details = document.createElement('div'); details.id = detId; details.style.display='none';
            var pre = document.createElement('pre'); pre.className='small'; pre.style.whiteSpace='pre-wrap'; pre.style.background='#f8fafc'; pre.style.padding='8px'; pre.style.borderRadius='6px';
            try { pre.textContent = JSON.stringify(args, null, 2); } catch(_){ pre.textContent = String(args); }
            details.appendChild(pre);
            wrap.appendChild(meta); wrap.appendChild(bub); wrap.appendChild(details);
            if (msgs) msgs.appendChild(wrap);
          } catch(_){ }
        } else if (m.type === 'token' && m.word) {
          if (lastW !== m.word) {
            streamText.textContent = (streamText.textContent ? (streamText.textContent + ' ') : '') + String(m.word);
            lastW = m.word;
          }
        } else if (m.type === 'info') {
          try {
            var label = String(m.stage || m.message || 'info');
            if (!stagesSeen[label]) {
              stagesSeen[label] = 1;
              var inf = document.createElement('div');
              inf.className = 'small muted';
              inf.textContent = label;
              if (msgs) msgs.appendChild(inf);
            }
            if (label === 'finalizing' || label === 'persisted' || label === 'timeout') {
              clearSpinner();
              if (label === 'timeout') { finalOrError = true; }
            }
          } catch(_){ }
        } else if (m.type === 'final' && m.text) {
          finalOrError = true;
          try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
          streamText.textContent = m.text;
          clearSpinner();
        } else if (m.type === 'error') {
          finalOrError = true;
          try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
          streamText.textContent = '[error] ' + (m.error || 'unknown');
          clearSpinner();
        }
      };
      ws.onerror = function(){ try { streamText.textContent = (streamText.textContent||'') + ' [ws-error]'; } catch(_){} };
      ws.onclose = function(){ try { if (!finalOrError) { streamText.textContent = (streamText.textContent||'') + ' [closed]'; } } catch(_){} };
    } catch(e) {}
  }
  document.addEventListener('DOMContentLoaded', function(){
    try {
      var chatForm = document.getElementById('chatForm');
      if (chatForm) {
        chatForm.addEventListener('submit', async function(ev){
          try { ev.preventDefault(); } catch(_){ }
          var t = document.getElementById('chatInput');
          var text = (t && t.value || '').trim(); if (!text) return;
          var tid = chatForm.getAttribute('data-thread-id') || null;
          var fid = chatForm.getAttribute('data-file-id') || null;
          var dsid = chatForm.getAttribute('data-dataset-id') || null;
          if (!tid) { tid = await ensureThreadId(tid, fid, dsid); }
          startWS(text, tid, fid, dsid); try { t.value=''; } catch(_){ }
        });
      }

      // Toggle details by clicking the bubble/content
      try {
        var msgsEl = document.getElementById('msgs');
        if (msgsEl) {
          msgsEl.addEventListener('click', function(ev){
            var b = ev.target && ev.target.closest ? ev.target.closest('.bubble') : null;
            if (!b) return;
            var did = b.getAttribute('data-details-id');
            if (!did) return;
            var el = document.getElementById(did);
            if (el) { el.style.display = (el.style.display==='none'?'block':'none'); }
          });
        }
      } catch(_){ }

      // Intercept clicks on file/db links to create a new tab without navigation
      document.addEventListener('click', function(ev){
        var a = ev.target && ev.target.closest ? ev.target.closest('a.thread-create') : null;
        if (!a) return;
        try { ev.preventDefault(); } catch(_){ }
        var fid = a.getAttribute('data-file-id') || null;
        var dsid = a.getAttribute('data-dataset-id') || null;
        if (!fid || !dsid) {
          try {
            var urlObj = new URL(a.getAttribute('href'), window.location.href);
            if (!fid) fid = urlObj.searchParams.get('file_id');
            if (!dsid) dsid = urlObj.searchParams.get('dataset_id');
          } catch(_){ }
        }
        (async function(){
          var tid = await ensureThreadId(null, fid, dsid);
          if (!tid) return;
          // Update chat form context
          try {
            var f = document.getElementById('chatForm');
            if (f) {
              f.setAttribute('data-thread-id', tid);
              f.setAttribute('data-file-id', fid||'');
              f.setAttribute('data-dataset-id', dsid||'');
              var hidT = f.querySelector("input[name='thread_id']"); if (hidT) hidT.value = tid; else { var i=document.createElement('input'); i.type='hidden'; i.name='thread_id'; i.value=tid; f.appendChild(i); }
              var hidF = f.querySelector("input[name='file_id']"); if (fid) { if (hidF) hidF.value = fid; else { var j=document.createElement('input'); j.type='hidden'; j.name='file_id'; j.value=fid; f.appendChild(j);} } else if (hidF) { hidF.remove(); }
              var hidD = f.querySelector("input[name='dataset_id']"); if (dsid) { if (hidD) hidD.value = dsid; else { var k=document.createElement('input'); k.type='hidden'; k.name='dataset_id'; k.value=dsid; f.appendChild(k);} } else if (hidD) { hidD.remove(); }
            }
          } catch(_){ }
          // Clear messages panel to indicate a fresh thread
          try {
            var msgs = document.getElementById('msgs');
            if (msgs) { msgs.innerHTML = "<div class='muted small'>(No messages yet)</div>"; }
          } catch(_){ }
          // Update URL
          try {
            var url = `/project/${PROJECT_ID}?branch_id=${BRANCH_ID}&thread_id=${encodeURIComponent(tid)}` + (fid?`&file_id=${encodeURIComponent(fid)}`:'') + (dsid?`&dataset_id=${encodeURIComponent(dsid)}`:'');
            if (history && history.pushState) { history.pushState({}, '', url); }
          } catch(_){ }
        })();
      }, true);

    } catch(_) {}
  }, { once: true });
})();
</script>
""" % (project.id, current.id)

    return f"""
      <h1>{escape(project.title)}</h1>
      <div class=\"muted small\">Project ID: {project.id}</div>
      <div style=\"height:10px\"></div>
      <div>Branches: {tabs_html}</div>

      <div style="margin-top:8px; display:flex; gap:8px; align-items:center">
        <form method="post" action="/project/{project.id}/delete" class="inline" onsubmit="return confirm('Delete project {escape(project.title)} and all its data?');">
          <button type="submit" class="secondary">Delete Project</button>
        </form>
      </div>

      <div id="page-root" style="min-height:100vh; display:flex; flex-direction:column">
        <div class="two-col" style="margin-top:8px; flex:1; min-height:0">
          <div class="pane" style="display:flex; flex-direction:column; min-height:0">
            <div class="tabs" data-pane="left">
              <a href="#" class="tab active" data-target="left-chat">Chat</a>
            </div>
            <div class="tab-panels" style="flex:1; min-height:0">
              <div id="left-chat" class="panel">
                <div class='tabbar thread-tabs' style='margin-bottom:6px'>{thr_tabs_html}</div>
                <h3>Chat</h3>
                <style>
                  /* Chat area grows to fill viewport; input stays at bottom regardless of window size */
                  #left-chat {{ display:flex; flex-direction:column; flex:1; min-height:0; }}
                  #left-chat .chat-log {{ flex:1; display:flex; flex-direction:column; gap:8px; overflow-y:auto; padding-bottom:6px; }}
                  #left-chat .chat-input {{ margin-top:auto; padding-top:6px; background:#fff; }}
                  .msg {{ display:flex; flex-direction:column; max-width:80%; }}
                  .msg.user {{ align-self:flex-end; }}
                  .msg.assistant {{ align-self:flex-start; }}
                  .msg.system {{ align-self:flex-start; }}
                  .msg .meta {{ display:flex; gap:8px; align-items:center; margin-bottom:4px; }}
                  .bubble {{ border:1px solid var(--border); border-radius:18px; padding:12px 14px; font-size:14px; line-height:1.45; box-shadow: 0 1px 1px rgba(0,0,0,0.04); }}
                  .bubble.user {{ background:#d9fdd3; border-color:#b2e59a; }}
                  .bubble.assistant {{ background:#ffffff; border-color:#e6e6e6; }}
                  .bubble.system {{ background:#e7f3ff; border-color:#cfe8ff; }}
                  .thread-tabs .tab {{ display:inline-block; padding:6px 10px; border:1px solid var(--border); border-bottom:none; border-radius:6px 6px 0 0; background:#f3f4f6; color:#111; margin-right:4px; }}
                  .thread-tabs .tab.active {{ background:#fff; font-weight:600; }}
                  .thread-tabs .tab.new {{ background:#e5f6ff; }}
                </style>
                {flash_html}
                <div id='msgs' class='chat-log'>{msgs_html}</div>
                <div class='chat-input'>{chat_form}</div>
                {script_js}
                { ("<div class='card' style='margin-top:8px; padding:12px'><h3>File Details</h3>" + left_details + "</div>") if selected_file else "" }
              </div>
            </div>
          </div>

          <div class="pane right">
          <div class="card" style="max-height:220px; overflow:auto; padding:12px">
            <h3 style='margin-bottom:6px'>Files</h3>
            {file_list_html}
          </div>
          <div style="height:8px"></div>
          <div class="card" style='padding:12px'>
            <h3 style='margin-bottom:6px'>Upload</h3>
            <form method="post" action="/project/{project.id}/files/upload?branch_id={current.id}" enctype="multipart/form-data" data-testid="upload-form">
              <input type="file" name="file" required data-testid="upload-input" />
              <div style="height:6px"></div>
              <div class="small muted">LLM classification runs automatically on upload. See README for API key setup.</div>
              <div style="height:6px"></div>
              <button type="submit" data-testid="upload-submit">Upload</button>
            </form>
          </div>
          <div style="height:8px"></div>
          {sql_card}
          <div style="height:8px"></div>
          <div class="card" style="padding:12px">
            <h3>Databases</h3>
            <table class="table">
              <thead><tr><th>Name</th><th>Branch</th><th>Created</th></tr></thead>
              <tbody>{dataset_tbody}</tbody>
            </table>
          </div>
        </div>
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
        self.start_time = datetime.now(timezone.utc)
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
    # Optional project context (for header + nav context)
    header_lbl = None
    header_lnk = None
    nav_q = None
    try:
        pid_q = request.query_params.get("project_id")
        bid_q = request.query_params.get("branch_id")
        if pid_q:
            pid = int(pid_q)
            # Resolve project title from registry
            try:
                with RegistrySessionLocal() as reg:
                    p = reg.query(Project).filter(Project.id == pid).first()
                    if p:
                        header_lbl = p.title
            except Exception:
                pass
            # Determine branch for link (prefer query, else Main)
            bid = None
            try:
                bid = int(bid_q) if bid_q is not None else None
            except Exception:
                bid = None
            if bid is None:
                try:
                    SessionLocal = sessionmaker(bind=_get_project_engine(pid), autoflush=False, autocommit=False, future=True)
                    with SessionLocal() as pdb:
                        mb = ensure_main_branch(pdb, pid)
                        bid = mb.id
                except Exception:
                    bid = 1
            header_lnk = f"/project/{pid}?branch_id={bid}"
            nav_q = f"project_id={pid}&branch_id={bid}"
    except Exception:
        pass

    if not SHELL_API_ENABLED:
        body = """
        <h1>Shell</h1>
        <p class='muted'>The Shell feature is disabled by configuration.</p>
        <p>To enable, set <code>CEDARPY_SHELL_API_ENABLED=1</code>. Optionally set <code>CEDARPY_SHELL_API_TOKEN</code> for API access. See README for details.</p>
        """
        return layout("Shell – disabled", body, header_label=header_lbl, header_link=header_lnk, nav_query=nav_q)

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
    return layout("Shell", body, header_label=header_lbl, header_link=header_lnk, nav_query=nav_q)


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
                        # Ensure session sees freshest state
                        try:
                            db.expire_all()
                        except Exception:
                            pass
                        _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id, SQLUndoLog.branch_id==branch_id_eff).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
                        if not _last:
                            _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
                        if _last:
                            last_log_id = _last.id
                    except Exception:
                        pass
                # Use 0 as a sentinel when we couldn't determine a specific undo id; this allows downstream callers
                # to treat it as "unknown" while still providing a non-null value and relying on branch-based fallbacks.
                if last_log_id is None:
                    last_log_id = 0
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
# In-memory ring buffer of recent client logs (latest first when rendered)
_CLIENT_LOG_BUFFER: deque = deque(maxlen=1000)

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
    # Append to in-memory buffer for viewing in /log
    try:
        _CLIENT_LOG_BUFFER.append({
            "ts": ts,
            "level": lvl,
            "host": host,
            "origin": origin,
            "url": url,
            "loc": lc,
            "ua": ua,
            "message": entry.message,
            "stack": entry.stack or None,
        })
    except Exception:
        pass
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

    # After merging data rows, also adopt unique changelog entries from the branch into Main
    try:
        main_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==main_b.id).order_by(ChangelogEntry.created_at.desc()).limit(500).all()
        seen = set((ce.action, _hash_payload(ce.input_json)) for ce in main_entries)
        branch_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==current_b.id).order_by(ChangelogEntry.created_at.asc()).all()
        adopted = 0
        for ce in branch_entries:
            key = (ce.action, _hash_payload(ce.input_json))
            if key in seen:
                continue
            ne = ChangelogEntry(
                project_id=project.id,
                branch_id=main_b.id,
                action=ce.action,
                input_json=ce.input_json,
                output_json={"merged_from_branch_id": current_b.id, "merged_from_branch": current_b.name, "original_output": ce.output_json},
                summary_text=(ce.summary_text or f"Adopted from {current_b.name}: {ce.action}"),
            )
            db.add(ne)
            adopted += 1
        if adopted:
            db.commit()
    except Exception:
        db.rollback()

    msg = f"Merged files={merged_counts['files']}, threads={merged_counts['threads']}, datasets={merged_counts['datasets']}, tables={merged_counts['tables']}"
    try:
        record_changelog(db, project.id, main_b.id, "branch.merge_to_main", {"from_branch": current_b.name}, {"merged_counts": merged_counts})
    except Exception:
        pass
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
    try:
        record_changelog(db, project.id, current_b.id, "files.delete_all", {}, {"deleted_count": len(files)})
    except Exception:
        pass
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
        try:
            record_changelog(db, project.id, current_b.id, "sql.make_branch_aware", {"table": tbl}, {"error": str(e)})
        except Exception:
            pass
        return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Error:+{html.escape(str(e))}", status_code=303)

    try:
        record_changelog(db, project.id, current_b.id, "sql.make_branch_aware", {"table": tbl}, {"ok": True})
    except Exception:
        pass
    return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Converted+{tbl}+to+branch-aware", status_code=303)

BRANCH_AWARE_SQL_DEFAULT = os.getenv("CEDARPY_SQL_BRANCH_MODE", "1") == "1"

# -------------------- Delete project (registry + files + per-project DB dir) --------------------

@app.post("/project/{project_id}/delete")
def delete_project(project_id: int):
    # Remove from central registry
    try:
        with RegistrySessionLocal() as reg:
            proj = reg.query(Project).filter(Project.id == project_id).first()
            if proj:
                reg.delete(proj)
                reg.commit()
    except Exception:
        pass
    # Dispose cached engine if present
    try:
        with _project_engines_lock:
            eng = _project_engines.pop(project_id, None)
        if eng is not None:
            try:
                eng.dispose()
            except Exception:
                pass
    except Exception:
        pass
    # Remove project storage directory (DB + files)
    try:
        base = _project_dirs(project_id)["base"]
        if os.path.isdir(base):
            shutil.rmtree(base, ignore_errors=True)
    except Exception:
        pass
    return RedirectResponse("/", status_code=303)

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
        try:
            record_changelog(db, project.id, current_b.id, "sql.undo_last", {"undo_log_id": getattr(log, 'id', None)}, {"error": str(e)})
        except Exception:
            pass
        return RedirectResponse(f"/project/{project.id}?branch_id={current_b.id}&msg=Undo+failed:+{html.escape(str(e))}", status_code=303)

    # Remove the log entry we just undid
    try:
        db.delete(log)
        db.commit()
    except Exception:
        db.rollback()

    try:
        record_changelog(db, project.id, current_b.id, "sql.undo_last", {"undo_log_id": getattr(log, 'id', None)}, {"ok": True})
    except Exception:
        pass

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

    # Changelog entry for this SQL action
    try:
        input_payload = {"sql": sql, "transformed_sql": transformed_sql}
        output_payload = {k: v for k, v in result.items() if k not in ("rows",)}
        record_changelog(db, project.id, current.id, "sql.execute", input_payload, output_payload)
    except Exception:
        pass

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, selected_file=None, msg="Per-project database is active", sql_result_block=sql_block))

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
        # Deduplicate headers to avoid showing duplicate column names (observed in some drivers)
        cols_unique = []
        for c in (result["columns"] or []):
            if c not in cols_unique:
                cols_unique.append(c)
        headers = ''.join(f"<th>{escape(str(c))}</th>" for c in cols_unique)
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

        # Done with data mutations; log insertion happens outside this transaction to avoid SQLite locking

    # Store undo log using the ORM session (separate transaction)
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
    except Exception as e:
        try:
            print(f"[undo-log-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        db.rollback()

    # Best-effort fallback: if we did not capture an explicit created_log_id, query the latest log for this project+branch
    if created_log_id is None:
        try:
            _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id, SQLUndoLog.branch_id==branch_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
            if not _last:
                _last = db.query(SQLUndoLog).filter(SQLUndoLog.project_id==project_id).order_by(SQLUndoLog.created_at.desc(), SQLUndoLog.id.desc()).first()
            if _last:
                created_log_id = _last.id
        except Exception:
            created_log_id = None

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
    return layout("Cedar", projects_list_html(projects), header_label="All Projects")


# ----------------------------------------------------------------------------------
# Log page
# ----------------------------------------------------------------------------------

@app.get("/log", response_class=HTMLResponse)
def view_logs(project_id: Optional[int] = None, branch_id: Optional[int] = None):
    # Render recent client logs (newest last for readability)
    rows = []
    try:
        logs = list(_CLIENT_LOG_BUFFER)
    except Exception:
        logs = []
    if logs:
        for e in logs:
            ts = escape(str(e.get("ts") or ""))
            lvl = escape(str(e.get("level") or ""))
            url = escape(str(e.get("url") or ""))
            origin = escape(str(e.get("origin") or ""))
            msg = escape(str(e.get("message") or ""))
            loc = escape(str(e.get("loc") or ""))
            stack = escape(str(e.get("stack") or ""))
            ua = escape(str(e.get("ua") or ""))
            rows.append(f"<tr><td class='small'>{ts}</td><td class='small'>{lvl}</td><td class='small'>{origin}</td><td class='small'>{loc}</td><td>{msg}</td><td class='small'>{url}</td></tr>" + (f"<tr><td colspan='6'><pre class='small' style='white-space:pre-wrap'>{stack}</pre></td></tr>" if stack else ""))
    body = f"""
      <h1>Client Log</h1>
      <div class='card'>
        <div class='small muted'>Most recent {len(logs)} entries.</div>
        <table class='table'>
          <thead><tr><th>When</th><th>Level</th><th>Origin</th><th>Loc</th><th>Message</th><th>URL</th></tr></thead>
          <tbody>{''.join(rows) or "<tr><td colspan='6' class='muted'>(no entries)</td></tr>"}</tbody>
        </table>
      </div>
    """
    # Optional project context in header
    header_lbl = None
    header_lnk = None
    nav_q = None
    try:
        if project_id is not None:
            pid = int(project_id)
            try:
                with RegistrySessionLocal() as reg:
                    p = reg.query(Project).filter(Project.id == pid).first()
                    if p:
                        header_lbl = p.title
            except Exception:
                pass
            bid = None
            try:
                bid = int(branch_id) if branch_id is not None else None
            except Exception:
                bid = None
            if bid is None:
                try:
                    SessionLocal = sessionmaker(bind=_get_project_engine(pid), autoflush=False, autocommit=False, future=True)
                    with SessionLocal() as pdb:
                        mb = ensure_main_branch(pdb, pid)
                        bid = mb.id
                except Exception:
                    bid = 1
            header_lnk = f"/project/{pid}?branch_id={bid}"
            nav_q = f"project_id={pid}&branch_id={bid}"
    except Exception:
        pass
    return layout("Log", body, header_label=header_lbl, header_link=header_lnk, nav_query=nav_q)


@app.get("/changelog", response_class=HTMLResponse)
def view_changelog(request: Request, project_id: Optional[int] = None, branch_id: Optional[int] = None):
    # Prefer project-specific context. If missing, try to infer from Referer header.
    if project_id is None:
        try:
            ref = request.headers.get("referer") or ""
            if ref:
                from urllib.parse import urlparse, parse_qs
                u = urlparse(ref)
                pid = None
                try:
                    parts = [p for p in u.path.split("/") if p]
                    if len(parts) >= 2 and parts[0] == "project":
                        pid = int(parts[1])
                except Exception:
                    pid = None
                bid = None
                try:
                    bvals = parse_qs(u.query).get("branch_id")
                    if bvals:
                        bid = int(bvals[0])
                except Exception:
                    bid = None
                if pid is not None:
                    return RedirectResponse(f"/changelog?project_id={pid}" + (f"&branch_id={bid}" if bid is not None else ""), status_code=303)
        except Exception:
            pass
    # Global index (no project selected): list projects with links to their changelog
    if project_id is None:
        try:
            with RegistrySessionLocal() as reg:
                projects = reg.query(Project).order_by(Project.created_at.desc()).all()
        except Exception:
            projects = []
        rows = []
        for p in projects:
            rows.append(f"<tr><td>{escape(p.title)}</td><td><a class='pill' href='/changelog?project_id={p.id}'>Open</a></td></tr>")
        body = f"""
          <h1>Changelog</h1>
          <div class='card' style='max-width:720px'>
            <h3>Projects</h3>
            <table class='table'>
              <thead><tr><th>Title</th><th>Actions</th></tr></thead>
              <tbody>{''.join(rows) or '<tr><td colspan="2" class="muted">No projects yet.</td></tr>'}</tbody>
            </table>
          </div>
        """
        return layout("Changelog", body)

    # Project context: show branch toggles and entries for selected branch (default Main)
    ensure_project_initialized(project_id)
    # Load branches from per-project DB
    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return layout("Not found", "<h1>Project not found</h1>")
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
        if not branches:
            ensure_main_branch(db, project.id)
            branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
        main_b = ensure_main_branch(db, project.id)
        try:
            branch_id_eff = int(branch_id) if branch_id is not None else main_b.id
        except Exception:
            branch_id_eff = main_b.id
        # Build branch toggle pills
        pills = []
        for b in branches:
            selected = "style='font-weight:600'" if b.id == branch_id_eff else ""
            pills.append(f"<a {selected} href='/changelog?project_id={project.id}&branch_id={b.id}' class='pill'>{escape(b.name)}</a>")
        pills_html = " ".join(pills)
        # Query entries for selected branch
        entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==branch_id_eff).order_by(ChangelogEntry.created_at.desc(), ChangelogEntry.id.desc()).limit(500).all()
        rows = []
        idx = 0
        for ce in entries:
            idx += 1
            did = f"chg_{idx}"
            when = escape(ce.created_at.strftime("%Y-%m-%d %H:%M:%S")) + " UTC" if getattr(ce, 'created_at', None) else ""
            action = escape(ce.action or '')
            summ = escape((ce.summary_text or '').strip() or action)
            # Details: pretty-print input/output JSON
            try:
                import json as _json
                inp = _json.dumps(ce.input_json, ensure_ascii=False, indent=2) if ce.input_json is not None else "{}"
                out = _json.dumps(ce.output_json, ensure_ascii=False, indent=2) if ce.output_json is not None else "{}"
            except Exception:
                inp = escape(str(ce.input_json))
                out = escape(str(ce.output_json))
            details = (
                f"<div id='{did}' style='display:none'><pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>"
                f"Input:\n{escape(inp)}\n\nOutput:\n{escape(out)}</pre></div>"
            )
            toggle = f"<a href='#' class='small' onclick=\"var e=document.getElementById('{did}'); if(e){{ e.style.display=(e.style.display==='none'?'block':'none'); }} return false;\">details</a>"
            rows.append(f"<tr><td class='small'>{when}</td><td class='small'>{action}</td><td>{summ} <span class='muted small'>[{toggle}]</span>{details}</td></tr>")
        body = f"""
          <h1>Changelog: {escape(project.title)}</h1>
          <div class='small muted'>Branch: {pills_html}</div>
          <div class='card' style='margin-top:8px'>
            <table class='table'>
              <thead><tr><th>When</th><th>Action</th><th>Summary</th></tr></thead>
              <tbody>{''.join(rows) or '<tr><td colspan="3" class="muted">(no entries)</td></tr>'}</tbody>
            </table>
          </div>
        """
        return layout(f"Changelog • {project.title}", body, header_label=project.title, header_link=f"/project/{project.id}?branch_id={branch_id_eff}", nav_query=f"project_id={project.id}&branch_id={branch_id_eff}")

# ----------------------------------------------------------------------------------
# Merge dashboard pages
# ----------------------------------------------------------------------------------

def merge_index_html(projects: List[Project]) -> str:
    rows = []
    for p in projects:
        rows.append(f"<tr><td>{escape(p.title)}</td><td><a class='pill' href='/merge/{p.id}'>Open</a></td></tr>")
    body = f"""
      <h1>Merge</h1>
      <div class='card' style='max-width:720px'>
        <h3>Projects</h3>
        <table class='table'>
          <thead><tr><th>Title</th><th>Actions</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="2" class="muted">No projects yet.</td></tr>'}</tbody>
        </table>
      </div>
    """
    return body


def _hash_payload(obj: Any) -> str:
    try:
        import json as _json
        s = _json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(obj)
    h = hashlib.sha256(s.encode('utf-8', errors='ignore')).hexdigest()
    return h


@app.get("/merge", response_class=HTMLResponse)
def merge_index(request: Request, db: Session = Depends(get_registry_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return layout("Merge", merge_index_html(projects))


@app.get("/merge/{project_id}", response_class=HTMLResponse)
def merge_project_view(project_id: int, db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return layout("Not found", "<h1>Project not found</h1>")
    # Branches
    branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    if not branches:
        ensure_main_branch(db, project.id)
        branches = db.query(Branch).filter(Branch.project_id == project.id).order_by(Branch.created_at.asc()).all()
    main_b = ensure_main_branch(db, project.id)

    # Build main changelog hash set
    main_entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==main_b.id).order_by(ChangelogEntry.created_at.desc()).limit(500).all()
    seen = set((ce.action, _hash_payload(ce.input_json)) for ce in main_entries)

    # For each branch, compute unique entries (not present in main by action+input)
    cards = []
    for b in branches:
        if b.id == main_b.id:
            # Render main summary card
            cards.append(f"""
              <div class='card'>
                <h3>Main</h3>
                <div class='small muted'>Branch ID: {b.id}</div>
                <div class='small muted'>Changelog entries: {len(main_entries)}</div>
              </div>
            """)
            continue
        entries = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==b.id).order_by(ChangelogEntry.created_at.desc()).limit(200).all()
        unique = []
        for ce in entries:
            key = (ce.action, _hash_payload(ce.input_json))
            if key not in seen:
                unique.append(ce)
        # Render card with unique entries and a merge button
        ul_items = []
        for ce in unique[:20]:
            summ = escape((ce.summary_text or ce.action or '').strip() or '(no summary)')
            ul_items.append(f"<li class='small'>{summ}</li>")
        unique_html = "<ul class='small'>" + ("".join(ul_items) or "<li class='muted small'>(no unique items found)</li>") + "</ul>"
        merge_form = f"""
          <form method='post' action='/project/{project.id}/merge_to_main?branch_id={b.id}' class='inline'>
            <button type='submit' data-testid='merge-branch-{b.id}'>Merge {escape(b.name)} → Main</button>
          </form>
        """
        cards.append(f"""
          <div class='card'>
            <h3>Branch: {escape(b.name)}</h3>
            <div class='small muted'>Branch ID: {b.id}</div>
            <div>{merge_form}</div>
            <div style='height:8px'></div>
            <div><strong>Unique vs Main</strong></div>
            {unique_html}
          </div>
        """)

    body = f"""
      <h1>Merge: {escape(project.title)}</h1>
      <div class='row'>
        {''.join(cards)}
      </div>
    """
    return layout(f"Merge • {project.title}", body, header_label=project.title, header_link=f"/project/{project.id}?branch_id={main_b.id}", nav_query=f"project_id={project.id}&branch_id={main_b.id}")


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
def view_project(project_id: int, branch_id: Optional[int] = None, msg: Optional[str] = None, file_id: Optional[int] = None, dataset_id: Optional[int] = None, thread_id: Optional[int] = None, db: Session = Depends(get_project_db)):
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

    # resolve selected file if provided
    selected_file = None
    try:
        if file_id is not None:
            selected_file = db.query(FileEntry).filter(
                FileEntry.id == int(file_id),
                FileEntry.project_id == project.id,
                FileEntry.branch_id.in_(show_branch_ids)
            ).first()
    except Exception:
        selected_file = None

    # resolve selected dataset if provided
    selected_dataset = None
    try:
        if dataset_id is not None:
            selected_dataset = db.query(Dataset).filter(
                Dataset.id == int(dataset_id),
                Dataset.project_id == project.id,
                Dataset.branch_id.in_(show_branch_ids)
            ).first()
    except Exception:
        selected_dataset = None

    # resolve selected thread and messages
    selected_thread = None
    thread_messages: List[ThreadMessage] = []
    try:
        if thread_id is not None:
            selected_thread = db.query(Thread).filter(Thread.id == int(thread_id), Thread.project_id == project.id, Thread.branch_id.in_(show_branch_ids)).first()
            if selected_thread:
                thread_messages = db.query(ThreadMessage).filter(ThreadMessage.project_id==project.id, ThreadMessage.thread_id==selected_thread.id).order_by(ThreadMessage.created_at.asc()).all()
    except Exception:
        selected_thread = None

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, selected_file=selected_file, selected_dataset=selected_dataset, selected_thread=selected_thread, thread_messages=thread_messages, msg=msg), header_label=project.title, header_link=f"/project/{project.id}?branch_id={current.id}", nav_query=f"project_id={project.id}&branch_id={current.id}")


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
@app.get("/project/{project_id}/threads/new")
# LLM chat uses threads. If using the GET '/threads/new', a default title 'New Thread' is created
# and the user is redirected to the project page focusing the new tab. See README for LLM setup.
def create_thread(project_id: int, request: Request, title: Optional[str] = Form(None), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # branch selected via query parameter
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    file_q = request.query_params.get("file_id")
    dataset_q = request.query_params.get("dataset_id")
    json_q = request.query_params.get("json")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Derive a default title from file/dataset context when GET and no explicit title
    file_obj = None
    dataset_obj = None
    try:
        if file_q is not None:
            file_obj = db.query(FileEntry).filter(FileEntry.id == int(file_q), FileEntry.project_id == project.id).first()
    except Exception:
        file_obj = None
    try:
        if dataset_q is not None:
            dataset_obj = db.query(Dataset).filter(Dataset.id == int(dataset_q), Dataset.project_id == project.id).first()
    except Exception:
        dataset_obj = None

    if request.method.upper() == 'GET' and (title is None or not str(title).strip()):
        if file_obj:
            label = (file_obj.ai_title or file_obj.display_name or '').strip() or f"File {file_obj.id}"
            title = f"File: {label}"
        elif dataset_obj:
            title = f"DB: {dataset_obj.name}"
        else:
            title = "New Thread"
    title = (title or "New Thread").strip()

    t = Thread(project_id=project.id, branch_id=branch.id, title=title)
    db.add(t)
    db.commit()
    db.refresh(t)
    add_version(db, "thread", t.id, {"project_id": project.id, "branch_id": branch.id, "title": t.title})

    redirect_url = f"/project/{project.id}?branch_id={branch.id}&thread_id={t.id}" + (f"&file_id={file_obj.id}" if file_obj else "") + (f"&dataset_id={dataset_obj.id}" if dataset_obj else "") + "&msg=Thread+created"

    # Optional JSON response for client-side creation
    if json_q is not None and str(json_q).strip() not in {"", "0", "false", "False", "no"}:
        return JSONResponse({"thread_id": t.id, "branch_id": branch.id, "redirect": redirect_url, "title": t.title})

    # Redirect to focus the newly created thread
    return RedirectResponse(redirect_url, status_code=303)


@app.post("/project/{project_id}/ask")
# Bottom-of-page "Ask" orchestrator. Builds a context-rich prompt, expects strict JSON with function calls,
# executes tools, and iterates until final/question. Keys are read from ~/CedarPyData/.env.
# See README (Settings, Client-side logging) and Postmortem #7 for key setup and troubleshooting.
# Function calls supported: sql, grep, code (python), img, web, plan, notes, question, final.
# We log all I/O to thread messages and to the changelog; verbose on errors.
# Code/tool execution is sandboxed best-effort and limited to project DB/files.
def ask_orchestrator(project_id: int, request: Request, query: str = Form(...), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # derive branch
    branch_q = request.query_params.get("branch_id")
    try:
        branch_q = int(branch_q) if branch_q is not None else None
    except Exception:
        branch_q = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_q)

    # Find or create a dedicated Ask thread
    thr = db.query(Thread).filter(Thread.project_id==project.id, Thread.branch_id==branch.id, Thread.title=="Ask").first()
    if not thr:
        thr = Thread(project_id=project.id, branch_id=branch.id, title="Ask")
        db.add(thr); db.commit(); db.refresh(thr)
        add_version(db, "thread", thr.id, {"project_id": project.id, "branch_id": branch.id, "title": thr.title})

    # Persist user query
    um = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="user", content=query)
    db.add(um); db.commit()

    import json as _json

    def _files_index(limit: int = 500) -> List[Dict[str, Any]]:
        ids = branch_filter_ids(db, project.id, branch.id)
        recs = db.query(FileEntry).filter(FileEntry.project_id==project.id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(limit).all()
        out: List[Dict[str, Any]] = []
        for f in recs:
            out.append({
                "id": f.id,
                "title": (f.ai_title or f.display_name or "").strip(),
                "display_name": f.display_name,
                "structure": f.structure,
                "file_type": f.file_type,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
            })
        return out

    def _recent_changelog(limit: int = 50) -> List[Dict[str, Any]]:
        recs = db.query(ChangelogEntry).filter(ChangelogEntry.project_id==project.id, ChangelogEntry.branch_id==branch.id).order_by(ChangelogEntry.created_at.desc()).limit(limit).all()
        out: List[Dict[str, Any]] = []
        for c in recs:
            out.append({
                "id": c.id,
                "when": c.created_at.isoformat() if c.created_at else None,
                "action": c.action,
                "summary": c.summary_text,
            })
        return out

    def _recent_assistant_msgs(limit: int = 10) -> List[Dict[str, Any]]:
        recs = db.query(ThreadMessage).filter(ThreadMessage.project_id==project.id, ThreadMessage.branch_id==branch.id, ThreadMessage.role=="assistant").order_by(ThreadMessage.created_at.desc()).limit(limit).all()
        out: List[Dict[str, Any]] = []
        for m in recs:
            out.append({
                "when": m.created_at.isoformat() if m.created_at else None,
                "title": m.display_title,
                "content": m.content[:2000] if m.content else "",
            })
        return out

    client, model = _llm_client_config()
    if not client:
        am = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title="LLM key missing", content="Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY in ~/CedarPyData/.env; see README")
        db.add(am); db.commit()
        return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}&msg=Missing+OpenAI+key", status_code=303)

    # System prompt and schema
    sys_prompt = (
        "You are Cedar's orchestrator. Always respond with STRICT JSON (no prose outside JSON).\n"
        "Schema: { \"Text Visible To User\": string, \"function_calls\": [ { \"name\": one of [sql, grep, code, img, web, plan, notes, question, final], \"args\": object } ] }\n"
        "Rules:\n"
        "- \"Text Visible To User\" is REQUIRED and MUST be non-empty. It should EITHER (a) state the answer succinctly OR (b) state the concrete steps you are taking to get the answer.\n"
        "- Use sql to query the project's SQLite database (use sqlite_master/PRAGMA to introspect).\n"
        "- Use grep with {file_id, pattern, flags?} to search a specific file by id.\n"
        "- Use code with {language:'python', source:'...'}; helpers available: cedar.query(sql), cedar.read(file_id), cedar.list_files(), cedar.open_path(file_id), cedar.note(text,[tags]).\n"
        "- Use img with {image_id, purpose} to analyze an image file; an inline data URL is provided.\n"
        "- Use web with {url} to fetch HTML.\n"
        "- Use plan with {steps:[...]}; we will iterate steps.\n"
        "- Use notes with {content, tags?} to store notes.\n"
        "- Use question with {text} to ask the user and then stop.\n"
        "- Use final with {text} for the final output and then stop.\n"
    )

    example = {
        "Text Visible To User": "Working on it…",
        "function_calls": [
            {"name": "sql", "args": {"sql": "SELECT name FROM sqlite_master WHERE type='table'"}}
        ]
    }

    context_obj = {
        "files_index": _files_index(),
        "recent_changelog": _recent_changelog(),
        "recent_assistant_messages": _recent_assistant_msgs(),
        "project": {"id": project.id, "title": project.title},
        "branch": {"id": branch.id, "name": branch.name}
    }

    def _call_llm(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            resp = client.chat.completions.create(model=model, messages=messages)
            raw = (resp.choices[0].message.content or "").strip()
            return json.loads(raw)
        except Exception as e:
            try: print(f"[ask-llm-error] {type(e).__name__}: {e}")
            except Exception: pass
            return None

    # Tool executors
    def _exec_sql(sql_text: str) -> Dict[str, Any]:
        try:
            eng = _get_project_engine(project.id)
            rows: List[List[Any]] = []
            cols: List[str] = []
            with eng.begin() as conn:
                res = conn.exec_driver_sql(sql_text)
                if res.returns_rows:
                    cols = list(res.keys())
                    for i, r in enumerate(res.fetchall()):
                        if i >= 200: break
                        row = []
                        for v in r:
                            if isinstance(v, (int, float)) or v is None:
                                row.append(v)
                            else:
                                row.append(str(v))
                        rows.append(row)
            return {"ok": True, "columns": cols, "rows": rows}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_grep(file_id: int, pattern: str, flags: str = "") -> Dict[str, Any]:
        try:
            f = db.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project.id).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return {"ok": False, "error": "file not found"}
            rx_flags = 0
            if 'i' in (flags or ''): rx_flags |= re.IGNORECASE
            if 'm' in (flags or ''): rx_flags |= re.MULTILINE
            rx = re.compile(pattern, rx_flags)
            matches: List[Dict[str, Any]] = []
            with open(f.storage_path, 'r', encoding='utf-8', errors='replace') as fh:
                for ln, line in enumerate(fh, start=1):
                    if rx.search(line):
                        matches.append({"line": ln, "text": line.rstrip()})
                        if len(matches) >= 200: break
            return {"ok": True, "matches": matches}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_code(source: str) -> Dict[str, Any]:
        logs = io.StringIO()
        def _cedar_query(sql_text: str):
            return _exec_sql(sql_text)
        def _cedar_list_files():
            return _files_index()
        def _cedar_read(file_id: int):
            f = db.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project.id).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return None
            try:
                with open(f.storage_path, 'rb') as fh:
                    b = fh.read(500000)
                    try:
                        return b.decode('utf-8', errors='replace')
                    except Exception:
                        import base64 as _b64
                        return "base64:" + _b64.b64encode(b).decode('ascii')
            except Exception:
                return None
        def _cedar_open_path(file_id: int):
            f = db.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project.id).first()
            return f.storage_path if (f and f.storage_path) else None
        def _cedar_note(content: str, tags: Optional[List[str]] = None):
            n = Note(project_id=project.id, branch_id=branch.id, content=str(content), tags=tags)
            db.add(n); db.commit()
            return {"id": n.id}
        cedar = type("CedarHelpers", (), {"query": _cedar_query, "list_files": _cedar_list_files, "read": _cedar_read, "open_path": _cedar_open_path, "note": _cedar_note})()
        safe_globals: Dict[str, Any] = {"__builtins__": {"print": print, "len": len, "range": range, "str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple}, "cedar": cedar, "sqlite3": sqlite3, "json": json, "re": re, "io": io}
        try:
            with contextlib.redirect_stdout(logs):
                exec(compile(source, filename="<ask_code>", mode="exec"), safe_globals, safe_globals)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "logs": logs.getvalue()}
        return {"ok": True, "logs": logs.getvalue()}

    def _exec_web(url: str) -> Dict[str, Any]:
        try:
            import urllib.request as _req
            with _req.urlopen(url, timeout=20) as resp:
                ct = resp.headers.get('Content-Type','')
                body = resp.read()
            txt = body.decode('utf-8', errors='replace')
            return {"ok": True, "content_type": ct, "text": txt[:200000]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_img(image_id: int, purpose: str = "") -> Dict[str, Any]:
        try:
            f = db.query(FileEntry).filter(FileEntry.id==int(image_id), FileEntry.project_id==project.id).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return {"ok": False, "error": "image not found"}
            import base64 as _b64
            with open(f.storage_path, 'rb') as fh:
                b = fh.read()
            ext = (os.path.splitext(f.storage_path)[1].lower() or ".png").lstrip('.')
            mime = f.mime_type or ("image/" + (ext if ext in {"png","jpeg","jpg","webp","gif"} else "png"))
            data_url = f"data:{mime};base64,{_b64.b64encode(b).decode('ascii')}"
            return {"ok": True, "image_id": f.id, "purpose": purpose, "data_url_head": data_url[:120000]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _exec_notes(content: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            n = Note(project_id=project.id, branch_id=branch.id, content=str(content), tags=tags)
            db.add(n); db.commit(); db.refresh(n)
            return {"ok": True, "note_id": n.id}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # First LLM call
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Context:"},
        {"role": "user", "content": _json.dumps(context_obj, ensure_ascii=False)},
        {"role": "user", "content": "Schema and rules (example):"},
        {"role": "user", "content": _json.dumps(example, ensure_ascii=False)},
        {"role": "user", "content": query},
    ]

    loop_count = 0
    final_text: Optional[str] = None
    question_text: Optional[str] = None
    last_response: Optional[Dict[str, Any]] = None
    last_text_visible: str = ""
    last_tool_summary: str = ""

    while loop_count < 6:
        loop_count += 1
        resp = _call_llm(messages)
        if not resp:
            break
        last_response = resp
        try:
            db.add(ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=_json.dumps(resp, ensure_ascii=False), display_title="Ask: JSON")); db.commit()
        except Exception:
            db.rollback()

        text_visible = str(resp.get("Text Visible To User") or "").strip()
        last_text_visible = text_visible or last_text_visible
        calls = resp.get("function_calls") or []
        tool_results: List[Dict[str, Any]] = []

        for call in calls:
            name = str(call.get("name") or "").strip().lower()
            args = call.get("args") or {}
            out: Dict[str, Any] = {"name": name, "ok": False, "result": None}
            if name == "sql":
                out["result"] = _exec_sql(str(args.get("sql") or ""))
            elif name == "grep":
                out["result"] = _exec_grep(int(args.get("file_id")), str(args.get("pattern") or ""), str(args.get("flags") or ""))
            elif name == "code":
                if str(args.get("language") or "").lower() == "python":
                    out["result"] = _exec_code(str(args.get("source") or ""))
                else:
                    out["result"] = {"ok": False, "error": "unsupported language"}
            elif name == "img":
                out["result"] = _exec_img(int(args.get("image_id")), str(args.get("purpose") or ""))
            elif name == "web":
                out["result"] = _exec_web(str(args.get("url") or ""))
            elif name == "plan":
                steps = args.get("steps") or []
                out["result"] = _exec_notes("Plan steps:\n" + "\n".join([str(s) for s in steps]), ["plan"])
            elif name == "notes":
                out["result"] = _exec_notes(str(args.get("content") or ""), args.get("tags"))
            elif name == "question":
                question_text = str(args.get("text") or text_visible or "I have a question for you.")
                final_text = None
            elif name == "final":
                final_text = str(args.get("text") or text_visible or "Done.")
            else:
                out["result"] = {"ok": False, "error": f"unknown function: {name}"}
            r = out.get("result")
            if isinstance(r, dict):
                out["ok"] = bool(r.get("ok", True))
            tool_results.append(out)

        if question_text or final_text:
            break

        # Summarize tools run for potential fallback rendering
        try:
            last_tool_summary = "Tools run: " + ", ".join([str((tr or {}).get("name") or "?") for tr in tool_results])
        except Exception:
            last_tool_summary = last_tool_summary or ""

        messages.append({"role": "user", "content": "ToolResults:"})
        messages.append({"role": "user", "content": _json.dumps({"tool_results": tool_results}, ensure_ascii=False)})
        if text_visible:
            messages.append({"role": "user", "content": text_visible})

    show_msg = final_text or question_text or (last_text_visible.strip() if last_text_visible and last_text_visible.strip() else "") or ( (last_response and str(last_response.get("Text Visible To User") or "").strip()) or "") or (last_tool_summary if last_tool_summary else "(no response)")

    am = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title=("Ask • Final" if final_text else ("Ask • Question" if question_text else "Ask • Update")), content=show_msg)
    db.add(am); db.commit()

    try:
        input_payload = {"query": query}
        output_payload = {"final": final_text, "question": question_text}
        record_changelog(db, project.id, branch.id, "ask.orchestrator", input_payload, output_payload)
    except Exception:
        pass

    dest_msg = "Answer+ready" if final_text else ("Question+for+you" if question_text else "Ask+updated")
    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}&msg={dest_msg}", status_code=303)


@app.post("/project/{project_id}/threads/chat")
# Submit a chat message in the selected thread; includes file metadata context to LLM.
# Requires OpenAI API key; see README for setup. Verbose errors are surfaced to the UI/log.
def thread_chat(project_id: int, request: Request, content: str = Form(...), thread_id: Optional[str] = Form(None), file_id: Optional[str] = Form(None), dataset_id: Optional[str] = Form(None), db: Session = Depends(get_project_db)):
    ensure_project_initialized(project_id)
    # derive branch context
    branch_q = request.query_params.get("branch_id")
    try:
        branch_q = int(branch_q) if branch_q is not None else None
    except Exception:
        branch_q = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_q)

    # Parse optional ids safely (empty strings -> None)
    thr_id_val: Optional[int] = None
    if thread_id is not None and str(thread_id).strip() != "":
        try:
            thr_id_val = int(str(thread_id).strip())
        except Exception:
            thr_id_val = None
    file_id_val: Optional[int] = None
    if file_id is not None and str(file_id).strip() != "":
        try:
            file_id_val = int(str(file_id).strip())
        except Exception:
            file_id_val = None
    dataset_id_val: Optional[int] = None
    if dataset_id is not None and str(dataset_id).strip() != "":
        try:
            dataset_id_val = int(str(dataset_id).strip())
        except Exception:
            dataset_id_val = None

    # Resolve thread; if missing, auto-create a default one
    thr = None
    if thr_id_val:
        try:
            thr = db.query(Thread).filter(Thread.id == thr_id_val, Thread.project_id == project.id).first()
        except Exception:
            thr = None
    if not thr:
        thr = Thread(project_id=project.id, branch_id=branch.id, title="New Thread")
        db.add(thr)
        db.commit(); db.refresh(thr)

    # Persist user message
    um = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="user", content=content)
    db.add(um); db.commit()

    # Build file metadata context if provided
    fctx = None
    if file_id_val:
        try:
            fctx = db.query(FileEntry).filter(FileEntry.id == file_id_val, FileEntry.project_id == project.id).first()
        except Exception:
            fctx = None
    dctx = None
    if dataset_id_val:
        try:
            dctx = db.query(Dataset).filter(Dataset.id == dataset_id_val, Dataset.project_id == project.id).first()
        except Exception:
            dctx = None

    # LLM call (OpenAI). See README for keys setup. No fallbacks; verbose errors.
    reply_text = None
    reply_title = None
    reply_payload = None
    client, model = _llm_client_config()
    if not client:
        reply_text = "[llm-missing-key] Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY."
    else:
        try:
            sys_prompt = (
                "This is a research tool to help people understand the breadth of existing research in the area,\n"
                "collect and analyze data, and build out reports and visuals to help communicate their findings.\n"
                "You will have a number of tools to select from when responding to a user.\n"
                "For simple queries, you can answer with the \"final\" function.\n"
                "For more complex queries, or ones that require precise numerical answers, begin with the \"plan\" function.\n"
                "Within \"plan\" indicate the functions you will use for each step.\n"
                "Functions include web, download, extract, image, db, code, shell, notes, compose, question, final.\n"
                "In every response, output STRICT JSON and always include output_to_user and changelog_summary.\n"
                "Include examples for each function so the system can parse it afterwards.\n"
                "We pass Resources (files/dbs), History (recent conversation), and Context (selected file/DB) with each query.\n"
                "All data systems are queriable via db/download/extract—provide concrete, executable specs.\n"
            )

            # Build context JSON
            ctx = {}
            if fctx:
                ctx["file"] = {
                    "display_name": fctx.display_name,
                    "file_type": fctx.file_type,
                    "structure": fctx.structure,
                    "ai_title": fctx.ai_title,
                    "ai_category": fctx.ai_category,
                    "ai_description": (fctx.ai_description or "")[:350],
                }
            if dctx:
                ctx["dataset"] = {
                    "name": dctx.name,
                    "description": (dctx.description or "")[:500]
                }

            # Resources (files/dbs) and history
            resources = {"files": [], "databases": []}
            history = []
            try:
                ids = branch_filter_ids(db, project.id, branch.id)
                recs = db.query(FileEntry).filter(FileEntry.project_id==project.id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(200).all()
                for f in recs:
                    resources["files"].append({
                        "id": f.id,
                        "title": (f.ai_title or f.display_name or "").strip(),
                        "display_name": f.display_name,
                        "structure": f.structure,
                        "file_type": f.file_type,
                        "mime_type": f.mime_type,
                        "size_bytes": f.size_bytes,
                    })
                dsets = db.query(Dataset).filter(Dataset.project_id==project.id, Dataset.branch_id.in_(ids)).order_by(Dataset.created_at.desc()).limit(200).all()
                for d in dsets:
                    resources["databases"].append({
                        "id": d.id,
                        "name": d.name,
                        "description": (d.description or "")[:500],
                    })
            except Exception:
                pass
            try:
                recent = db.query(ThreadMessage).filter(ThreadMessage.project_id==project.id, ThreadMessage.thread_id==thr.id).order_by(ThreadMessage.created_at.desc()).limit(15).all()
                for m in reversed(recent):
                    history.append({
                        "role": m.role,
                        "title": (m.display_title or None),
                        "content": (m.content or "")[:2000]
                    })
            except Exception:
                pass

            examples_json = {
                "plan": {
                    "function": "plan",
                    "steps": [
                        {"description": "Search the web for background", "will_call": ["web", "download"]},
                        {"description": "Extract claims/citations from PDFs", "will_call": ["extract"]},
                        {"description": "Query DB for aggregates", "will_call": ["db"]},
                        {"description": "Write draft", "will_call": ["compose", "final"]}
                    ],
                    "output_to_user": "Plan with steps and tools",
                    "changelog_summary": "created plan"
                },
                "web": {"function": "web", "args": {"query": "example query"}, "output_to_user": "Searched web", "changelog_summary": "web search"},
                "download": {"function": "download", "args": {"urls": ["https://example.org/a.pdf"]}, "output_to_user": "Downloading 1 file", "changelog_summary": "download start"},
                "extract": {"function": "extract", "args": {"file_id": 1}, "output_to_user": "Extracted claims/citations", "changelog_summary": "extract done"},
                "image": {"function": "image", "args": {"image_id": 2, "purpose": "diagram analysis"}, "output_to_user": "Analyzed image", "changelog_summary": "image"},
                "db": {"function": "db", "args": {"sql": "SELECT COUNT(*) FROM citations"}, "output_to_user": "Ran SQL", "changelog_summary": "db query"},
                "code": {"function": "code", "args": {"language": "python", "packages": ["pandas"], "source": "print(2+2)"}, "output_to_user": "Executed code", "changelog_summary": "code run"},
                "shell": {"function": "shell", "args": {"script": "echo hello"}, "output_to_user": "Ran shell", "changelog_summary": "shell"},
                "notes": {"function": "notes", "args": {"themes": [{"name": "Background", "notes": ["note1"]}]}, "output_to_user": "Saved notes", "changelog_summary": "notes saved"},
                "compose": {"function": "compose", "args": {"sections": [{"title": "Intro", "text": "…"}]}, "output_to_user": "Drafted text", "changelog_summary": "compose"},
                "question": {"function": "question", "args": {"text": "Clarify scope?"}, "output_to_user": "Need input", "changelog_summary": "asked user"},
                "final": {"function": "final", "args": {"text": "Answer."}, "output_to_user": "Answer for user", "changelog_summary": "finalized"}
            }

            import json as _json
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Resources:"},
                {"role": "user", "content": _json.dumps(resources, ensure_ascii=False)},
                {"role": "user", "content": "History:"},
                {"role": "user", "content": _json.dumps(history, ensure_ascii=False)}
            ]
            if ctx:
                messages.append({"role": "user", "content": "Context:"})
                messages.append({"role": "user", "content": _json.dumps(ctx, ensure_ascii=False)})
            messages.append({"role": "user", "content": "Functions and examples:"})
            messages.append({"role": "user", "content": _json.dumps(examples_json, ensure_ascii=False)})
            messages.append({"role": "user", "content": content})
            resp = client.chat.completions.create(model=model, messages=messages)
            raw = (resp.choices[0].message.content or "").strip()
            # Feed assistant JSON back into conversation so the next turn has the full prior output
            try:
                messages.append({"role": "assistant", "content": raw})
            except Exception:
                pass
            try:
                parsed = _json.loads(raw)
                reply_title = str(parsed.get("title") or "Assistant")
                reply_payload = parsed.get("data")
                reply_text = raw
            except Exception:
                reply_title = "Assistant"
                reply_text = raw
        except Exception as e:
            reply_text = f"[llm-error] {type(e).__name__}: {e}"
            reply_title = "LLM Error"
    # Persist assistant message (with title/payload if available)
    am = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=reply_text or "", display_title=reply_title, payload_json=reply_payload)
    try:
        db.add(am); db.commit()
    except Exception:
        db.rollback()

    # Changelog for chat with full prompts and raw result
    try:
        input_payload = {"messages": messages, "file_context_id": (fctx.id if fctx else None)}
        output_payload = {"assistant_title": reply_title, "assistant_raw": reply_text, "assistant_payload": reply_payload}
        record_changelog(db, project.id, branch.id, "thread.chat", input_payload, output_payload)
    except Exception:
        pass

    # Redirect back focusing this thread
    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&thread_id={thr.id}" + (f"&file_id={file_id}" if file_id else ""), status_code=303)

# ----------------------------------------------------------------------------------
# WebSocket chat streaming endpoint (word-by-word)
# ----------------------------------------------------------------------------------
@app.websocket("/ws/chat/{project_id}")
async def ws_chat_stream(websocket: WebSocket, project_id: int):
    await websocket.accept()
    try:
        try:
            print(f"[ws-chat] accepted project_id={project_id}")
        except Exception:
            pass
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"action": "chat", "content": raw}
        content = (payload.get("content") or "").strip()
        br_id = payload.get("branch_id")
        thr_id = payload.get("thread_id")
    except Exception:
        await websocket.send_text(json.dumps({"type": "error", "error": "invalid payload"}))
        await websocket.close(); return

    SessionLocal = sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
    branch = None
    thr = None
    db = SessionLocal()
    try:
        ensure_project_initialized(project_id)
        branch = current_branch(db, project_id, int(br_id) if br_id is not None else None)
        if thr_id:
            try:
                thr = db.query(Thread).filter(Thread.id == int(thr_id), Thread.project_id == project_id).first()
            except Exception:
                thr = None
        if not thr:
            thr = db.query(Thread).filter(Thread.project_id==project_id, Thread.branch_id==branch.id, Thread.title=="Ask").first()
            if not thr:
                thr = Thread(project_id=project_id, branch_id=branch.id, title="Ask")
                db.add(thr); db.commit(); db.refresh(thr)
        if content:
            db.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="user", content=content))
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        try: db.close()
        except Exception: pass

    # Inform client that the request has been submitted
    try:
        await websocket.send_text(json.dumps({"type": "info", "stage": "submitted"}))
        try:
            print("[ws-chat] submitted")
        except Exception:
            pass
    except Exception:
        pass

    client, model = _llm_client_config()
    if not client:
        try:
            print("[ws-chat] missing-key")
        except Exception:
            pass
        db2 = SessionLocal()
        try:
            am = ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", content="[llm-missing-key] Set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY.")
            db2.add(am); db2.commit()
        except Exception:
            try: db2.rollback()
            except Exception: pass
        finally:
            try: db2.close()
            except Exception: pass
        await websocket.send_text(json.dumps({"type": "error", "error": "missing_key"}))
        await websocket.close(); return

    # Build context/resources/history using a fresh session
    db2 = SessionLocal()
    try:
        # Optional context from file/dataset
        fctx = None
        dctx = None
        try:
            fid = payload.get("file_id")
            if fid is not None:
                fctx = db2.query(FileEntry).filter(FileEntry.id == int(fid), FileEntry.project_id == project_id).first()
        except Exception:
            fctx = None
        try:
            did = payload.get("dataset_id")
            if did is not None:
                dctx = db2.query(Dataset).filter(Dataset.id == int(did), Dataset.project_id == project_id).first()
        except Exception:
            dctx = None

        ctx = {}
        if fctx:
            ctx["file"] = {
                "display_name": fctx.display_name,
                "file_type": fctx.file_type,
                "structure": fctx.structure,
                "ai_title": fctx.ai_title,
                "ai_category": fctx.ai_category,
                "ai_description": (fctx.ai_description or "")[:350],
            }
        if dctx:
            ctx["dataset"] = {
                "name": dctx.name,
                "description": (dctx.description or "")[:500]
            }

        # Build resources index (files/dbs) and recent thread history
        resources = {"files": [], "databases": []}
        history = []
        try:
            ids = branch_filter_ids(db2, project_id, branch.id)
            recs = db2.query(FileEntry).filter(FileEntry.project_id==project_id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(200).all()
            for f in recs:
                resources["files"].append({
                    "id": f.id,
                    "title": (f.ai_title or f.display_name or "").strip(),
                    "display_name": f.display_name,
                    "structure": f.structure,
                    "file_type": f.file_type,
                    "mime_type": f.mime_type,
                    "size_bytes": f.size_bytes,
                })
            dsets = db2.query(Dataset).filter(Dataset.project_id==project_id, Dataset.branch_id.in_(ids)).order_by(Dataset.created_at.desc()).limit(200).all()
            for d in dsets:
                resources["databases"].append({
                    "id": d.id,
                    "name": d.name,
                    "description": (d.description or "")[:500],
                })
        except Exception:
            pass
        try:
            recent = db2.query(ThreadMessage).filter(ThreadMessage.project_id==project_id, ThreadMessage.thread_id==thr.id).order_by(ThreadMessage.created_at.desc()).limit(15).all()
            for m in reversed(recent):
                history.append({
                    "role": m.role,
                    "title": (m.display_title or None),
                    "content": (m.content or "")[:2000]
                })
        except Exception:
            pass

        # Research tool system prompt and examples
        sys_prompt = (
            "This is a research tool to help people understand the breadth of existing research in the area,\n"
            "collect and analyze data, and build out reports and visuals to help communicate their findings.\n"
            "You will have a number of tools to select from when responding to a user.\n"
            "For simple queries, you can answer with the \"final\" function.\n"
            "For more complex queries, or ones that require precise numerical answers, begin with the \"plan\" function.\n"
            "Within \"plan\" indicate the functions you will use for each step.\n"
            "Functions include: \n"
            "- web: run a web search and obtain a webpage with all links extracted.\n"
            "- download: download one or more URLs.\n"
            "- extract: take a file (e.g., PDF) and break it into claims (unique findings) and citations (references).\n"
            "- image: analyze a provided image.\n"
            "- db: execute an SQL statement against the built-in DB.\n"
            "- code: execute code; specify language, required packages, and the code.\n"
            "- shell: execute a shell script.\n"
            "- notes: write notes organized by themes.\n"
            "- compose: write the paper from notes.\n"
            "- question: ask a question of the user.\n"
            "- final: the last step in the plan.\n"
            "In every response, output STRICT JSON. Always include output_to_user (what to show the user) and changelog_summary.\n"
            "Include examples of the JSON schema for each function so the system can parse it afterwards.\n"
            "We will pass with each query: (a) a list of files and databases you can access (Resources), (b) recent conversation history (History), and (c) optional Context (selected file/DB).\n"
            "All data systems are queriable by you via the db/download/extract functions. Provide concrete, executable specs for those.\n"
            "IMPORTANT: Constrain yourself to at most 3 turns in total. Always end with a \"final\" function within 3 turns, especially for simple queries like arithmetic.\n"
        )

        examples_json = {
            "plan": {
                "function": "plan",
                "steps": [
                    {"description": "Search for recent survey papers", "will_call": ["web", "download", "extract"]},
                    {"description": "Aggregate key findings and compute statistics", "will_call": ["db", "code"]},
                    {"description": "Write summary", "will_call": ["compose", "final"]}
                ],
                "output_to_user": "High-level plan with steps and intended tools",
                "changelog_summary": "created plan with 3 steps"
            },
            "web": {"function": "web", "args": {"query": "site:nature.com CRISPR review 2024"}, "output_to_user": "Searched web", "changelog_summary": "web search"},
            "download": {"function": "download", "args": {"urls": ["https://example.org/paper.pdf"]}, "output_to_user": "Queued 1 download", "changelog_summary": "download requested"},
            "extract": {"function": "extract", "args": {"file_id": 123}, "output_to_user": "Extracted claims/citations", "changelog_summary": "extracted PDF"},
            "image": {"function": "image", "args": {"image_id": 42, "purpose": "chart reading"}, "output_to_user": "Analyzed image", "changelog_summary": "image analysis"},
            "db": {"function": "db", "args": {"sql": "SELECT COUNT(*) FROM claims"}, "output_to_user": "Ran SQL", "changelog_summary": "db query"},
            "code": {"function": "code", "args": {"language": "python", "packages": ["pandas"], "source": "print(2+2)"}, "output_to_user": "Executed code", "changelog_summary": "code run"},
            "shell": {"function": "shell", "args": {"script": "echo hello"}, "output_to_user": "Ran shell", "changelog_summary": "shell run"},
            "notes": {"function": "notes", "args": {"themes": [{"name": "Risks", "notes": ["…"]}]}, "output_to_user": "Saved notes", "changelog_summary": "notes saved"},
            "compose": {"function": "compose", "args": {"sections": [{"title": "Intro", "text": "…"}]}, "output_to_user": "Drafted section(s)", "changelog_summary": "compose partial"},
            "question": {"function": "question", "args": {"text": "Which domain do you care about?"}, "output_to_user": "Need clarification", "changelog_summary": "asked user"},
            "final": {"function": "final", "args": {"text": "2+2=4"}, "output_to_user": "2+2=4", "changelog_summary": "finalized answer"}
        }

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": "Resources:"},
            {"role": "user",   "content": json.dumps(resources, ensure_ascii=False)},
            {"role": "user",   "content": "History:"},
            {"role": "user",   "content": json.dumps(history, ensure_ascii=False)}
        ]
        if ctx:
            try:
                messages.append({"role": "user", "content": "Context:"})
                messages.append({"role": "user", "content": json.dumps(ctx, ensure_ascii=False)})
            except Exception:
                pass
        messages.append({"role": "user", "content": "Functions and examples:"})
        try:
            messages.append({"role": "user", "content": json.dumps(examples_json, ensure_ascii=False)})
        except Exception:
            messages.append({"role": "user", "content": "{""error"":""examples unavailable""}"})
        messages.append({"role": "user", "content": content})
    except Exception as e:
        import traceback as _tb
        try:
            print(f"[ws-chat-build-error] {type(e).__name__}: {e}\n" + "".join(_tb.format_exception(type(e), e, e.__traceback__))[-1500:])
        except Exception:
            pass
        try:
            await websocket.send_text(json.dumps({"type": "error", "error": f"{type(e).__name__}: {e}"}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        return
    finally:
        try:
            db2.close()
        except Exception:
            pass

    # Optional: emit debug prompt for testing
    try:
        if bool(payload.get('debug')):
            await websocket.send_text(json.dumps({"type": "debug", "prompt": messages}))
            try:
                print("[ws-chat] debug-sent")
            except Exception:
                pass
    except Exception as e:
        try:
            print(f"[ws-chat-debug-error] {type(e).__name__}: {e}")
        except Exception:
            pass

    # Orchestrated plan/execute loop (non-streaming JSON)
    try:
        await websocket.send_text(json.dumps({"type": "info", "stage": "planning"}))
        try:
            print("[ws-chat] planning-sent")
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[ws-chat-planinfo-error] {type(e).__name__}: {e}")
        except Exception:
            pass

    import urllib.request as _req
    import re as _re

    def _send_info(label: str):
        try:
            return asyncio.create_task(websocket.send_text(json.dumps({"type": "info", "stage": label})))
        except Exception:
            return None

    # Tool executors
    def tool_web(args: dict) -> dict:
        q = (args or {}).get("query")
        url = (args or {}).get("url")
        if url:
            try:
                with _req.urlopen(url, timeout=25) as resp:
                    body = resp.read().decode('utf-8', errors='replace')
                    links = list(set(_re.findall(r'href=["\']([^"\']+)', body)))
                    title_m = _re.search(r'<title[^>]*>(.*?)</title>', body, _re.IGNORECASE | _re.DOTALL)
                    title = title_m.group(1).strip() if title_m else ''
                    return {"ok": True, "url": url, "title": title, "links": links[:200], "bytes": len(body)}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": False, "error": "web.search not configured; provide args.url"}

    def tool_download(args: dict) -> dict:
        urls = (args or {}).get("urls") or []
        if not isinstance(urls, list) or not urls:
            return {"ok": False, "error": "urls required"}
        results = []
        tdb = SessionLocal()
        try:
            # Determine project files dir
            paths = _project_dirs(project_id)
            branch_dir_name = f"branch_{branch.name}"
            project_dir = os.path.join(paths["files_root"], branch_dir_name)
            os.makedirs(project_dir, exist_ok=True)
            for u in urls[:10]:
                try:
                    with _req.urlopen(u, timeout=45) as resp:
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
                        rec = FileEntry(project_id=project_id, branch_id=branch.id, filename=storage_name, display_name=parsed, file_type=ftype, structure=None, mime_type=mime or '', size_bytes=size, storage_path=os.path.abspath(disk_path), metadata_json=None, ai_processing=False)
                        tdb.add(rec); tdb.commit(); tdb.refresh(rec)
                        results.append({"url": u, "file_id": rec.id, "display_name": parsed, "bytes": size})
                except Exception as e:
                    results.append({"url": u, "error": f"{type(e).__name__}: {e}"})
            return {"ok": True, "downloads": results}
        finally:
            try: tdb.close()
            except Exception: pass

    def tool_extract(args: dict) -> dict:
        fid = (args or {}).get("file_id")
        if fid is None:
            return {"ok": False, "error": "file_id required"}
        tdb = SessionLocal()
        try:
            f = tdb.query(FileEntry).filter(FileEntry.id==int(fid), FileEntry.project_id==project_id).first()
            if not f or not f.storage_path or not os.path.isfile(f.storage_path):
                return {"ok": False, "error": "file not found"}
            # Minimal extractor: try to read as UTF-8 text; PDFs and binaries return error
            try:
                with open(f.storage_path, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
            except Exception:
                return {"ok": False, "error": "binary or non-utf8 file; PDF extraction not installed"}
            # Naive claims/citations split
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            claims = [ln for ln in lines[:200]]
            citations = []
            rx = _re.compile(r'\[(\d+)\]|doi:|arxiv|http', _re.I)
            for ln in lines:
                if rx.search(ln):
                    citations.append(ln)
                    if len(citations) >= 200:
                        break
            return {"ok": True, "claims": claims[:200], "citations": citations[:200]}
        finally:
            try: tdb.close()
            except Exception: pass

    def tool_image(args: dict) -> dict:
        try:
            image_id = int((args or {}).get("image_id"))
        except Exception:
            return {"ok": False, "error": "image_id required"}
        # Reuse existing helper
        return _exec_img(image_id, str((args or {}).get("purpose") or ""))

    def tool_db(args: dict) -> dict:
        sql_text = str((args or {}).get("sql") or "").strip()
        if not sql_text:
            return {"ok": False, "error": "sql required"}
        try:
            return _execute_sql(sql_text, project_id, max_rows=200)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def tool_code(args: dict) -> dict:
        lang = str((args or {}).get("language") or "").lower()
        source = str((args or {}).get("source") or "")
        if lang != 'python':
            return {"ok": False, "error": "only python supported"}
        logs = io.StringIO()
        def _cedar_query(sql_text: str):
            return tool_db({"sql": sql_text})
        def _cedar_list_files():
            tdb = SessionLocal()
            try:
                ids = branch_filter_ids(tdb, project_id, branch.id)
                recs = tdb.query(FileEntry).filter(FileEntry.project_id==project_id, FileEntry.branch_id.in_(ids)).order_by(FileEntry.created_at.desc()).limit(200).all()
                return [{"id": ff.id, "display_name": ff.display_name, "file_type": ff.file_type} for ff in recs]
            finally:
                try: tdb.close()
                except Exception: pass
        def _cedar_read(file_id: int):
            tdb = SessionLocal()
            try:
                f = tdb.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==project_id).first()
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
                try: tdb.close()
                except Exception: pass
        safe_globals: Dict[str, Any] = {"__builtins__": {"print": print, "len": len, "range": range, "str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple}, "cedar": type("CedarHelpers", (), {"query": _cedar_query, "list_files": _cedar_list_files, "read": _cedar_read})(), "sqlite3": sqlite3, "json": json, "re": re, "io": io}
        try:
            with contextlib.redirect_stdout(logs):
                exec(compile(source, filename="<ws_code>", mode="exec"), safe_globals, safe_globals)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "logs": logs.getvalue()}
        return {"ok": True, "logs": logs.getvalue()}

    def tool_shell(args: dict) -> dict:
        script = str((args or {}).get("script") or "").strip()
        if not script:
            return {"ok": False, "error": "script required"}
        try:
            base = os.environ.get('SHELL') or '/bin/zsh'
            proc = subprocess.run([base, '-lc', script], capture_output=True, text=True, timeout=60)
            return {"ok": proc.returncode == 0, "return_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def tool_notes(args: dict) -> dict:
        themes = (args or {}).get("themes")
        content = json.dumps({"themes": themes}, ensure_ascii=False)
        tdb = SessionLocal()
        try:
            n = Note(project_id=project_id, branch_id=branch.id, content=content, tags=["notes"])
            tdb.add(n); tdb.commit(); tdb.refresh(n)
            return {"ok": True, "note_id": n.id}
        finally:
            try: tdb.close()
            except Exception: pass

    def tool_compose(args: dict) -> dict:
        secs = (args or {}).get("sections") or []
        content = json.dumps({"sections": secs}, ensure_ascii=False)
        tdb = SessionLocal()
        try:
            n = Note(project_id=project_id, branch_id=branch.id, content=content, tags=["compose"])
            tdb.add(n); tdb.commit(); tdb.refresh(n)
            return {"ok": True, "note_id": n.id}
        finally:
            try: tdb.close()
            except Exception: pass

    tools_map = {
        "web": tool_web,
        "download": tool_download,
        "extract": tool_extract,
        "image": tool_image,
        "db": tool_db,
        "code": tool_code,
        "shell": tool_shell,
        "notes": tool_notes,
        "compose": tool_compose,
        "question": lambda args: {"ok": True, "question": (args or {}).get("text") or "Please clarify"},
        "final": lambda args: {"ok": True, "text": (args or {}).get("text") or "Done."},
    }

    loop_count = 0
    final_text = None
    question_text = None

    # Overall budget: ensure we eventually time out and inform the client
    import time as _time
    try:
        timeout_s = int(os.getenv("CEDARPY_CHAT_TIMEOUT_SECONDS", "90"))
    except Exception:
        timeout_s = 90
    t0 = _time.time()

    try:
        while loop_count < 8:
            # Timeout guard (pre-turn)
            try:
                if (_time.time() - t0) > timeout_s:
                    try:
                        await websocket.send_text(json.dumps({"type": "info", "stage": "timeout"}))
                    except Exception:
                        pass
                    final_text = f"Timed out after {timeout_s} seconds. Please try again."
                    break
            except Exception:
                pass
            loop_count += 1
            # Call LLM for next action
            try:
                try:
                    print("[ws-chat] llm-call")
                except Exception:
                    pass
                resp = client.chat.completions.create(model=model, messages=messages)
                raw = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                try:
                    print(f"[ws-chat-llm-error] {type(e).__name__}: {e}")
                except Exception:
                    pass
                await websocket.send_text(json.dumps({"type": "error", "error": f"{type(e).__name__}: {e}"}))
                await websocket.close(); return

            # Persist assistant JSON response for traceability
            dbj = SessionLocal()
            try:
                dbj.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=raw, display_title="Research JSON"))
                dbj.commit()
            except Exception:
                try: dbj.rollback()
                except Exception: pass
            finally:
                try: dbj.close()
                except Exception: pass

            # Parse function call(s)
            calls: List[Dict[str, Any]] = []
            obj = None
            try:
                obj = json.loads(raw)
            except Exception:
                obj = None
            if isinstance(obj, list):
                calls = [c for c in obj if isinstance(c, dict)]
            elif isinstance(obj, dict):
                if 'function' in obj:
                    calls = [obj]
                elif 'steps' in obj:
                    calls = [{"function": "plan", "steps": obj.get('steps') or []}]
            else:
                # Not parseable; ask for one function call
                messages.append({"role": "user", "content": "Please respond with ONE function call in strict JSON."})
                continue

            for call in calls:
                name = str((call.get('function') or '')).strip().lower()
                args = call.get('args') or {}
                if name == 'plan':
                    _send_info('plan')
                    # Persist plan
                    dbp = SessionLocal()
                    try:
                        dbp.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title="Plan", content=json.dumps(call, ensure_ascii=False), payload_json=call))
                        dbp.commit()
                    except Exception:
                        try: dbp.rollback()
                        except Exception: pass
                    finally:
                        try: dbp.close()
                        except Exception: pass
                    # Emit an action bubble to the client with plan steps preview
                    try:
                        await websocket.send_text(json.dumps({"type": "action", "function": "plan", "args": {"steps": call.get("steps") or []}}))
                    except Exception:
                        pass
                    # Ask to proceed with the first step
                    messages.append({"role": "user", "content": "Proceed with the first step now. Respond with ONE function call in strict JSON only."})
                    break  # go to next LLM turn
                if name in ('final', 'question'):
                    if name == 'final':
                        final_text = str((args or {}).get('text') or call.get('output_to_user') or '').strip() or 'Done.'
                    else:
                        question_text = str((args or {}).get('text') or call.get('output_to_user') or '').strip() or 'I have a question for you.'
                    break
                # Execute tool
                _send_info(f"tool:{name}")
                try:
                    await websocket.send_text(json.dumps({"type": "action", "function": name, "args": args or {}}))
                except Exception:
                    pass
                fn = tools_map.get(name)
                try:
                    result = fn(args) if fn else {"ok": False, "error": f"unknown tool: {name}"}
                except Exception as e:
                    try:
                        print(f"[ws-chat-tool-error] {name}: {type(e).__name__}: {e}")
                    except Exception:
                        pass
                    result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                # Persist tool result
                dbt = SessionLocal()
                try:
                    payload = {"function": name, "args": args, "result": result}
                    dbt.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title=f"Tool: {name}", content=json.dumps(payload, ensure_ascii=False), payload_json=payload))
                    dbt.commit()
                except Exception:
                    try: dbt.rollback()
                    except Exception: pass
                finally:
                    try: dbt.close()
                    except Exception: pass
                # Feed result back to LLM
                messages.append({"role": "user", "content": "ToolResult:"})
                messages.append({"role": "user", "content": json.dumps({"function": name, "result": result}, ensure_ascii=False)})
            if final_text or question_text:
                break
    except Exception as e:
        try:
            print(f"[ws-chat-loop-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            await websocket.send_text(json.dumps({"type": "error", "error": f"{type(e).__name__}: {e}"}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        return

    # If the loop ended without a 'final' or 'question', nudge once more to produce a 'final'.
    if not final_text and not question_text:
        try:
            messages.append({"role": "user", "content": "Respond NOW with one function call ONLY: {\"function\":\"final\",\"args\":{\"text\":\"<answer>\"}}. STRICT JSON. No prose."})
            resp = client.chat.completions.create(model=model, messages=messages)
            raw2 = (resp.choices[0].message.content or "").strip()
            try:
                obj2 = json.loads(raw2)
            except Exception:
                obj2 = None
            if isinstance(obj2, dict) and str(obj2.get('function') or '').lower() == 'final':
                a2 = obj2.get('args') or {}
                final_text = str(a2.get('text') or obj2.get('output_to_user') or '').strip() or 'Done.'
                # Suppress noisy 'final-forced' from user UI; emit only when debug=true in payload
                try:
                    if bool(payload.get('debug')):
                        await websocket.send_text(json.dumps({"type": "info", "stage": "final-forced"}))
                except Exception:
                    pass
        except Exception:
            pass

    # Finalize
    try:
        await websocket.send_text(json.dumps({"type": "info", "stage": "finalizing"}))
    except Exception:
        pass

    dbf = SessionLocal()
    try:
        if final_text:
            dbf.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=final_text, display_title="Final"))
        elif question_text:
            dbf.add(ThreadMessage(project_id=project_id, branch_id=branch.id, thread_id=thr.id, role="assistant", content=question_text, display_title="Question"))
        dbf.commit()
    except Exception:
        try: dbf.rollback()
        except Exception: pass
    finally:
        try: dbf.close()
        except Exception: pass

    if final_text:
        # Emit only the final message to avoid confusing 'Next: final' system bubble in the UI
        await websocket.send_text(json.dumps({"type": "final", "text": final_text}))
    elif question_text:
        # For questions, continue to use 'final' type for compatibility with existing tests/clients
        await websocket.send_text(json.dumps({"type": "final", "text": question_text}))
    try:
        await websocket.send_text(json.dumps({"type": "info", "stage": "persisted"}))
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass


def _run_tabular_import_background(project_id: int, branch_id: int, file_id: int, thread_id: int) -> None:
    """Background worker to run tabular import without blocking the upload response.
    See README: Tabular import via LLM codegen.
    """
    try:
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        import json as _json
    except Exception:
        return
    try:
        SessionLocal = _sessionmaker(bind=_get_project_engine(project_id), autoflush=False, autocommit=False, future=True)
        dbj = SessionLocal()
    except Exception:
        return
    try:
        rec = dbj.query(FileEntry).filter(FileEntry.id == int(file_id), FileEntry.project_id == project_id).first()
        if not rec:
            return
        try:
            imp_res = _tabular_import_via_llm(project_id, branch_id, rec, dbj)
        except Exception as e:
            imp_res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        # Persist outcome to thread and changelog
        try:
            # Keep test compatibility: title begins with "File analyzed" so existing assertions still pass
            title = ("File analyzed — Tabular import completed" if imp_res.get("ok") else "File analyzed — Tabular import failed")
            dbj.add(ThreadMessage(project_id=project_id, branch_id=branch_id, thread_id=thread_id, role="assistant", display_title=title, content=_json.dumps(imp_res), payload_json=imp_res))
            dbj.commit()
        except Exception:
            try: dbj.rollback()
            except Exception: pass
        try:
            record_changelog(dbj, project_id, branch_id, "file.tabular_import", {"file_id": file_id}, imp_res)
        except Exception:
            pass
    finally:
        try: dbj.close()
        except Exception: pass


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
    # Verbose request logging for uploads; see README (Client-side logging)
    try:
        host = request.client.host if request and request.client else "?"
        print(f"[upload-api] from={host} project_id={project.id} branch={branch.name} filename={original_name} ctype={getattr(file, 'content_type', '')}")
    except Exception:
        pass
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_base = os.path.basename(original_name)
    storage_name = f"{ts}__{safe_base}"
    disk_path = os.path.join(project_dir, storage_name)

    with open(disk_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)

    size = os.path.getsize(disk_path)
    mime, _ = mimetypes.guess_type(original_name)
    ftype = file_extension_to_type(original_name)

    try:
        print(f"[upload-api] saved project_id={project.id} branch={branch.name} path={disk_path} size={size} mime={mime or file.content_type or ''} ftype={ftype}")
    except Exception:
        pass

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
        ai_processing=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Create a processing thread entry so the user can see steps
    thr_title = (f"File: {original_name}")[:100]
    thr = Thread(project_id=project.id, branch_id=branch.id, title=thr_title)
    db.add(thr); db.commit(); db.refresh(thr)
    try:
        import json as _json
        # Add a 'system' message with the planned classification prompt payload
        payload = {
            "action": "classify_file",
            "metadata_sample": {
                k: meta.get(k) for k in [
                    "extension","mime_guess","format","language","is_text","size_bytes","line_count","json_valid","json_top_level_keys","csv_dialect"] if k in meta
            },
            "display_name": original_name
        }
        tm = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="system", display_title="Submitting file to LLM to analyze...", content=_json.dumps(payload, ensure_ascii=False), payload_json=payload)
        db.add(tm); db.commit()
    except Exception:
        db.rollback()

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
            record.ai_processing = False
            db.commit(); db.refresh(record)
            try:
                print(f"[upload-api] classified structure={record.structure or ''} ai_title={(record.ai_title or '')[:80]}")
            except Exception:
                pass
            # Persist assistant message with result
            tm2 = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title="File analyzed", content=json.dumps(ai), payload_json=ai)
            db.add(tm2); db.commit()
        else:
            record.ai_processing = False
            db.commit()
            try:
                print("[upload-api] classification skipped (disabled or missing key)")
            except Exception:
                pass
            tm2 = ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="assistant", display_title="File analysis skipped", content="LLM classification disabled or missing key")
            db.add(tm2); db.commit()
    except Exception as e:
        try:
            print(f"[llm-exec-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            record.ai_processing = False
            db.commit()
        except Exception:
            db.rollback()

    add_version(db, "file", record.id, {
        "project_id": project.id, "branch_id": branch.id,
        "filename": record.filename, "display_name": record.display_name,
        "file_type": record.file_type, "structure": record.structure,
        "mime_type": record.mime_type, "size_bytes": record.size_bytes,
        "metadata": meta,
    })

    # Changelog for file upload + classification
    try:
        input_payload = {"action": "classify_file", "metadata_for_llm": meta_for_llm}
        output_payload = {"ai": ai, "thread_id": thr.id}
        record_changelog(db, project.id, branch.id, "file.upload+classify", input_payload, output_payload)
    except Exception:
        pass

    # Second-stage: If the file is tabular, run LLM codegen to import into the per-project database.
    try:
        do_tabular = str(os.getenv("CEDARPY_TABULAR_IMPORT", "1")).strip().lower() not in {"", "0", "false", "no", "off"}
    except Exception:
        do_tabular = True
    if do_tabular and (getattr(record, "structure", None) == "tabular"):
        try:
            # Emit a thread message to show next step
            db.add(ThreadMessage(project_id=project.id, branch_id=branch.id, thread_id=thr.id, role="system", display_title="Tabular file detected — generating import code...", content=json.dumps({"action":"tabular_import","file_id": record.id, "display_name": original_name})))
            db.commit()
        except Exception:
            db.rollback()
        # Offload tabular import to a background thread to avoid blocking the upload redirect
        try:
            import threading as _threading
            _threading.Thread(target=_run_tabular_import_background, args=(project.id, branch.id, record.id, thr.id), daemon=True).start()
        except Exception as e2:
            try:
                print(f"[tabular-bg-error] {type(e2).__name__}: {e2}")
            except Exception:
                pass

    # Redirect focusing the uploaded file and processing thread, so the user sees the steps
    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&file_id={record.id}&thread_id={thr.id}&msg=File+uploaded", status_code=303)
