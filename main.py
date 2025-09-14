
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
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean,
    UniqueConstraint, JSON, Index, func, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import re

# ----------------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------------

# Prefer a generic CEDARPY_DATABASE_URL; fall back to legacy CEDARPY_MYSQL_URL; otherwise use SQLite in ~/CedarPyData/cedarpy.db
HOME_DIR = os.path.expanduser("~")
DATA_DIR = os.getenv("CEDARPY_DATA_DIR", os.path.join(HOME_DIR, "CedarPyData"))
DEFAULT_SQLITE_PATH = os.path.join(DATA_DIR, "cedarpy.db")

DATABASE_URL = os.getenv("CEDARPY_DATABASE_URL") or os.getenv("CEDARPY_MYSQL_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"
UPLOAD_DIR = os.getenv("CEDARPY_UPLOAD_DIR", os.path.abspath("./user_uploads"))

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

# Ensure writable dirs exist (important when running from a read-only DMG)
os.makedirs(UPLOAD_DIR, exist_ok=True)
if DATABASE_URL.startswith("sqlite"):
    os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)

# ----------------------------------------------------------------------------------
# Database setup (SQLAlchemy, sync engine by design for simplicity)
# ----------------------------------------------------------------------------------

engeine_kwargs_typo_guard = None
engine_kwargs = dict(pool_pre_ping=True, future=True)
if DATABASE_URL.startswith("sqlite"):
    # Allow usage across threads in the web server
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# ----------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"
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
    structure = Column(String(50))  # notes, writeup, images, sources, code
    mime_type = Column(String(100))
    size_bytes = Column(Integer)
    storage_path = Column(String(1024))  # absolute/relative path on disk
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON)  # extracted metadata from interpreter

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


Base.metadata.create_all(engine)

# Attempt a lightweight migration for existing DBs: add metadata_json if missing
try:
    with engine.begin() as conn:
        dialect = engine.dialect.name
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
            res = conn.exec_driver_sql("SELECT 1")
            conn.exec_driver_sql("ALTER TABLE files ADD COLUMN metadata_json JSON")
except Exception:
    # Ignore migration issues in prototype mode
    pass

# ----------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------

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
    db = SessionLocal()
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
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ----------------------------------------------------------------------------------
# HTML helpers (all inline; no external templates)
# ----------------------------------------------------------------------------------

def layout(title: str, body: str) -> HTMLResponse:
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ --fg: #111; --bg: #fff; --accent: #2563eb; --muted: #6b7280; --border: #e5e7eb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji"; color: var(--fg); background: var(--bg); }}
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
    input[type="text"], select {{ padding: 8px; border: 1px solid var(--border); border-radius: 6px; width: 100%; }}
    input[type="file"] {{ padding: 6px; border: 1px dashed var(--border); border-radius: 6px; width: 100%; }}
    button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--accent); color: white; cursor: pointer; }}
    button.secondary {{ background: #f3f4f6; color: #111; }}
    .small {{ font-size: 12px; }}
    .topbar {{ display:flex; align-items:center; gap:12px; }}
  </style>
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
    # branch tabs
    tabs = []
    for b in branches:
        selected = "style='font-weight:600'" if b.id == current.id else ""
        tabs.append(f"<a {selected} href='/project/{project.id}?branch_id={b.id}' class='pill'>{escape(b.name)}</a>")
    tabs_html = " ".join(tabs)

    # files table
    file_rows = []
    for f in files:
        # display link to file (served from /uploads)
        # Make relative storage path under UPLOAD_DIR to create URL
        storage_path = f.storage_path or ""
        url = None
        try:
            abs_path = os.path.abspath(storage_path)
            base = os.path.abspath(os.getenv("CEDARPY_UPLOAD_DIR", "./user_uploads"))
            if abs_path.startswith(base):
                rel = abs_path[len(base):].lstrip(os.sep).replace(os.sep, "/")
                url = f"/uploads/{rel}"
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
        <form method=\"post\" action=\"/project/{project.id}/sql?branch_id={current.id}\" class=\"inline\"> 
          <textarea name=\"sql\" rows=\"6\" placeholder=\"WRITE SQL HERE\" style=\"width:100%; font-family: ui-monospace, Menlo, Monaco, 'Courier New', monospace;\"></textarea>
          <div style=\"height:8px\"></div>
          <button type=\"submit\">Run SQL</button>
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
            <label>Structure</label>
            <select name=\"structure\" required>
              <option value=\"notes\">notes</option>
              <option value=\"writeup\">writeup</option>
              <option value=\"images\">images</option>
              <option value=\"sources\">sources</option>
              <option value=\"code\">code</option>
            </select>
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
          <form method=\"post\" action=\"/project/{project.id}/files/delete_all?branch_id={current.id}\" class=\"inline\">
            <button type=\"submit\" class=\"secondary\" onclick=\"return confirm('Delete all files in this branch?');\">Delete All Files (this branch)</button>
          </form>
        </div>
      </div>
    """

# ----------------------------------------------------------------------------------
# Shell execution manager
# ----------------------------------------------------------------------------------

class ShellJob:
    def __init__(self, script: str, shell_path: Optional[str] = None):
        self.id = uuid.uuid4().hex
        self.script = script
        self.shell_path = shell_path or os.environ.get("SHELL", "/bin/bash")
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
    shell = job.shell_path
    # Run as login shell (-l) and execute command (-c) with a small wrapper to ensure POSIX semantics
    # Using a new process group so we can kill the entire tree
    job.status = "running"
    try:
        job.proc = subprocess.Popen(
            [shell, "-lc", job.script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
            env=os.environ.copy(),
        )
    except Exception as e:
        job.status = "error"
        job.end_time = datetime.utcnow()
        job.append_line(f"[spawn-error] {e}\n")
        return

    # Stream output
    try:
        assert job.proc and job.proc.stdout is not None
        for line in job.proc.stdout:
            job.append_line(line)
    except Exception as e:
        job.append_line(f"[stream-error] {e}\n")
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


def start_shell_job(script: str, shell_path: Optional[str] = None) -> ShellJob:
    job = ShellJob(script=script, shell_path=shell_path)
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
        if not x_api_token or x_api_token != SHELL_API_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized (invalid or missing X-API-Token)")
    else:
        # No token set: only allow local requests
        if not _is_local_request(request):
            raise HTTPException(status_code=401, detail="Unauthorized (local requests only when no token configured)")


# ----------------------------------------------------------------------------------
# Shell UI and API routes
# ----------------------------------------------------------------------------------

@app.get("/shell", response_class=HTMLResponse)
def shell_ui(request: Request):
    if not SHELL_API_ENABLED:
        body = """
        <h1>Shell</h1>
        <p class='muted'>The Shell feature is disabled by configuration.</p>
        <p>To enable, set <code>CEDARPY_SHELL_API_ENABLED=1</code>. Optionally set <code>CEDARPY_SHELL_API_TOKEN</code> for API access. See README for details.</p>
        """
        return layout("Shell – disabled", body)

    default_shell = escape(os.environ.get("SHELL", "/bin/bash"))
    body = """
      <h1>Shell</h1>
      <p class='muted small'>Runs scripts with your user privileges via {{SHELL or /bin/bash}}. Output streams live below. <strong>Danger:</strong> Any command you run can modify your system.</p>
      <div class='card' style='flex:1'>
        <label for='script'>Script</label>
        <textarea id='script' style='width:100%; height:180px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px;' placeholder='echo Hello world'></textarea>
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
        <button id='runBtn'>Run</button>
        <button id='stopBtn' class='secondary' disabled>Stop</button>
      </div>

      <div style='height:16px'></div>
      <div class='card'>
        <div class='row' style='justify-content:space-between; align-items:center'>
          <h3 style='margin:0'>Output</h3>
          <div class='small muted' id='status'>idle</div>
        </div>
        <pre id='output' style='min-height:220px; max-height:520px; overflow:auto; background:#0b1021; color:#e6e6e6; padding:12px; border-radius:6px;'></pre>
      </div>

      <script>
        const runBtn = document.getElementById('runBtn');
        const stopBtn = document.getElementById('stopBtn');
        const output = document.getElementById('output');
        const statusEl = document.getElementById('status');
        let currentJob = null;
        let evtSource = null;

        function setStatus(s) { statusEl.textContent = s; }
        function append(text) {
          output.textContent += text;
          output.scrollTop = output.scrollHeight;
        }
        function disableRun(disabled) { runBtn.disabled = disabled; stopBtn.disabled = !disabled; }

        runBtn.addEventListener('click', async () => {
          output.textContent = '';
          const script = document.getElementById('script').value;
          const shellPath = document.getElementById('shellPath').value || null;
          const token = document.getElementById('apiToken').value || null;
          setStatus('starting…');
          disableRun(true);
          try {
            const resp = await fetch('/api/shell/run', {
              method: 'POST',
              headers: Object.assign({'Content-Type': 'application/json'}, token ? {'X-API-Token': token} : {}),
              body: JSON.stringify({ script, shell_path: shellPath }),
            });
            if (!resp.ok) { const t = await resp.text(); throw new Error(t || ('HTTP '+resp.status)); }
            const data = await resp.json();
            currentJob = data.job_id;
            setStatus('running (pid '+(data.pid || '?')+')');
            // Stream (token via query param if present)
            const qs = token ? ('?token='+encodeURIComponent(token)) : '';
            evtSource = new EventSource(`/api/shell/stream/${data.job_id}${qs}`);
            evtSource.onmessage = (e) => {
              if (e.data === '__CEDARPY_EOF__') {
                setStatus('finished');
                disableRun(false);
                evtSource && evtSource.close();
                evtSource = null;
              } else {
                append(e.data + "\n");
              }
            };
            evtSource.onerror = (e) => {
              append('\n[stream-error]');
              setStatus('error');
              disableRun(false);
              evtSource && evtSource.close();
              evtSource = null;
            };
          } catch (err) {
            append('[error] '+err+'\n');
            setStatus('error');
            disableRun(false);
          }
        });

        stopBtn.addEventListener('click', async () => {
          if (!currentJob) return;
          const token = document.getElementById('apiToken').value || null;
          try {
            const resp = await fetch(`/api/shell/stop/${currentJob}`, { method: 'POST', headers: token ? {'X-API-Token': token} : {} });
            if (!resp.ok) { append('[stop-error] '+(await resp.text())+'\n'); return; }
            append('[killing]\n');
          } catch (e) { append('[stop-error] '+e+'\n'); }
        });
      </script>
    """
    body = body.replace("__DEFAULT_SHELL__", default_shell)
    return layout("Shell", body)


@app.post("/api/shell/run")
def api_shell_run(request: Request, payload: Dict[str, Any], x_api_token: Optional[str] = Header(default=None)):
    require_shell_enabled_and_auth(request, x_api_token)
    script = (payload or {}).get("script")
    shell_path = (payload or {}).get("shell_path")
    if not script or not isinstance(script, str):
        raise HTTPException(status_code=400, detail="script is required")
    job = start_shell_job(script=script, shell_path=shell_path)
    pid = job.proc.pid if job.proc else None
    return {"job_id": job.id, "pid": pid, "started_at": job.start_time.isoformat() + "Z"}


@app.get("/api/shell/stream/{job_id}")
def api_shell_stream(job_id: str, request: Request, token: Optional[str] = None):
    # Enforce same auth policy: if token is configured, allow token via query param for EventSource; otherwise local-only
    if not SHELL_API_ENABLED:
        raise HTTPException(status_code=403, detail="Shell API is disabled")
    if SHELL_API_TOKEN:
        if token != SHELL_API_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized (token query param required for stream)")
    else:
        if not _is_local_request(request):
            raise HTTPException(status_code=401, detail="Unauthorized (local only)")

    job = get_shell_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    def event_gen():
        # Flush any existing buffered lines first
        for line in job.output_lines:
            yield f"data: {line.rstrip()}\n\n"
        # Then stream live from queue
        while True:
            try:
                line = job.queue.get(timeout=1.0)
            except Exception:
                # Heartbeat to keep connection alive
                if job.status in ("finished", "error", "killed"):
                    yield "data: __CEDARPY_EOF__\n\n"
                    break
                else:
                    continue
            if line == "__CEDARPY_EOF__\n":
                yield "data: __CEDARPY_EOF__\n\n"
                break
            yield f"data: {line.rstrip()}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


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

# -------------------- Merge to Main (SQLite-first implementation) --------------------

@app.post("/project/{project_id}/merge_to_main")
def merge_to_main(project_id: int, request: Request, db: Session = Depends(get_db)):
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
    src_dir = os.path.join(UPLOAD_DIR, f"project_{project.id}", f"branch_{current_b.name}")
    dst_dir = os.path.join(UPLOAD_DIR, f"project_{project.id}", f"branch_{main_b.name}")
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
        with engine.begin() as conn:
            if _dialect() == "sqlite":
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
def delete_all_files(project_id: int, request: Request, db: Session = Depends(get_db)):
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

BRANCH_AWARE_SQL_DEFAULT = os.getenv("CEDARPY_SQL_BRANCH_MODE", "1") == "1"

# -------------------- SQL Helpers for Branch-Aware Mode --------------------

def _dialect() -> str:
    return engine.dialect.name


def _table_has_branch_columns(conn, table: str) -> bool:
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
    Returns (possibly transformed_sql, transformed_flag).
    Best-effort handling for simple single-table queries.
    """
    s = sql_text.strip()
    # Normalize whitespace
    s_norm = re.sub(r"\s+", " ", s)
    lower = s_norm.lower()

    # Simple SELECT ... FROM table [WHERE ...]
    m = re.match(r"select\s+(.+?)\s+from\s+([a-zA-Z0-9_]+)(\s+where\s+(.+))?", lower, flags=re.IGNORECASE)
    if m:
        table = _safe_identifier(m.group(2))
        if _table_has_branch_columns(conn, table):
            # Build roll-up select using window function
            select_cols = s[s.lower().find("select") + 6 : s.lower().find(" from ")]  # keep original projection
            where_clause = m.group(4)
            where_sql = f" AND {where_clause}" if where_clause else ""
            if _dialect() in ("sqlite", "mysql"):
                sql = f"""
                WITH __src AS (
                  SELECT *,
                         CASE WHEN branch_id = {branch_id} THEN 2 WHEN branch_id = {main_id} THEN 1 ELSE 0 END AS __rank
                  FROM {table}
                  WHERE project_id = {project_id} AND branch_id IN ({main_id}, {branch_id}){where_sql}
                ), __pick AS (
                  SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY __rank DESC) AS rn FROM __src
                )
                SELECT {select_cols} FROM __pick WHERE rn = 1
                """
                return (sql.strip(), True)
    # INSERT INTO table [(cols...)] VALUES (...)
    m = re.match(r"insert\s+into\s+([a-zA-Z0-9_]+)\s*\(([^\)]+)\)\s*values\s*\((.+)\)", lower, flags=re.IGNORECASE)
    if m:
        table = _safe_identifier(m.group(1))
        if _table_has_branch_columns(conn, table):
            cols_part = s[s.lower().find("(")+1 : s.lower().find(")", s.lower().find("("))]
            vals_start = s.lower().find("values") + len("values")
            vals_part = s[vals_start:].strip()
            # Expect single VALUES (...) form
            mv = re.match(r"\((.*)\)", vals_part, flags=re.IGNORECASE | re.DOTALL)
            if mv:
                cols_list = [c.strip() for c in cols_part.split(",")]
                vals_list = [v.strip() for v in mv.group(1).split(",")]
                if "project_id" not in [c.lower() for c in cols_list]:
                    cols_list.append("project_id")
                    vals_list.append(str(project_id))
                if "branch_id" not in [c.lower() for c in cols_list]:
                    cols_list.append("branch_id")
                    vals_list.append(str(branch_id))
                sql = f"INSERT INTO {table} (" + ", ".join(cols_list) + ") VALUES (" + ", ".join(vals_list) + ")"
                return (sql, True)
    # UPDATE table SET ... [WHERE ...]
    m = re.match(r"update\s+([a-zA-Z0-9_]+)\s+set\s+", lower, flags=re.IGNORECASE)
    if m:
        table = _safe_identifier(m.group(1))
        if _table_has_branch_columns(conn, table):
            if " where " in lower:
                sql = s + f" AND project_id = {project_id} AND branch_id = {branch_id}"
            else:
                sql = s + f" WHERE project_id = {project_id} AND branch_id = {branch_id}"
            return (sql, True)
    # DELETE FROM table [WHERE ...]
    m = re.match(r"delete\s+from\s+([a-zA-Z0-9_]+)", lower, flags=re.IGNORECASE)
    if m:
        table = _safe_identifier(m.group(1))
        if _table_has_branch_columns(conn, table):
            if " where " in lower:
                sql = s + f" AND project_id = {project_id} AND branch_id = {branch_id}"
            else:
                sql = s + f" WHERE project_id = {project_id} AND branch_id = {branch_id}"
            return (sql, True)
    # CREATE TABLE injection: add project_id/branch_id if missing and simple form
    m = re.match(r"create\s+table\s+([a-zA-Z0-9_]+)\s*\((.*)\)\s*;?$", s, flags=re.IGNORECASE | re.DOTALL)
    if m:
        table = _safe_identifier(m.group(1))
        cols_def = m.group(2)
        lower_cols = cols_def.lower()
        if "project_id" not in lower_cols and "branch_id" not in lower_cols:
            new_cols = cols_def.strip()
            if new_cols and not new_cols.endswith(","):
                new_cols += ", "
            new_cols += "project_id INTEGER NOT NULL, branch_id INTEGER NOT NULL"
            sql = f"CREATE TABLE {table} ({new_cols})"
            return (sql, True)
    return (s, False)


@app.post("/project/{project_id}/sql", response_class=HTMLResponse)
def execute_sql(project_id: int, request: Request, sql: str = Form(...), db: Session = Depends(get_db)):
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
    with engine.begin() as conn:
        main = db.query(Branch).filter(Branch.project_id == project.id, Branch.name == "Main").first()
        transformed_sql, transformed = _preprocess_sql_branch_aware(conn, sql, project.id, current.id, main.id)
    result = _execute_sql(transformed_sql, max_rows=max_rows)
    sql_block = _render_sql_result_html(result)

    return layout(project.title, project_page_html(project, branches, current, files, threads, datasets, msg="Branch-aware SQL mode is active", sql_result_block=sql_block))

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


def _execute_sql(sql_text: str, max_rows: int = 200) -> dict:
    sql_text = (sql_text or "").strip()
    if not sql_text:
        return {"success": False, "error": "Empty SQL"}
    first = sql_text.split()[0].lower() if sql_text.split() else ""
    stype = first
    result: dict = {"success": False, "statement_type": stype}
    try:
        with engine.begin() as conn:
            if first == "select" or first == "pragma" or first == "show":
                res = conn.exec_driver_sql(sql_text)
                cols = list(res.keys()) if res.returns_rows else []
                rows = []
                count = 0
                if res.returns_rows:
                    for r in res:
                        rows.append([r[c] if isinstance(r, dict) else getattr(r, c, r[idx]) if False else r[idx] for idx, c in enumerate(cols)])
                        count += 1
                        if count >= max_rows:
                            break
                result.update({
                    "success": True,
                    "columns": cols,
                    "rows": rows,
                    "rowcount": None,
                    "truncated": res.returns_rows and (count >= max_rows)
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

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return layout("Cedar", projects_list_html(projects))


@app.post("/projects/create")
def create_project(title: str = Form(...), db: Session = Depends(get_db)):
    title = title.strip()
    if not title:
        return RedirectResponse("/", status_code=303)
    # create project
    p = Project(title=title)
    db.add(p)
    db.commit()
    db.refresh(p)
    add_version(db, "project", p.id, {"title": p.title})
    # ensure main branch
    main = ensure_main_branch(db, p.id)
    return RedirectResponse(f"/project/{p.id}?branch_id={main.id}", status_code=303)


@app.get("/project/{project_id}", response_class=HTMLResponse)
def view_project(project_id: int, branch_id: Optional[int] = None, msg: Optional[str] = None, db: Session = Depends(get_db)):
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
def create_branch(project_id: int, name: str = Form(...), db: Session = Depends(get_db)):
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
def create_thread(project_id: int, request: Request, title: str = Form(...), db: Session = Depends(get_db)):
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
def upload_file(project_id: int, request: Request, file: UploadFile = File(...), structure: str = Form(...), db: Session = Depends(get_db)):
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/", status_code=303)

    branch = current_branch(db, project.id, branch_id)

    # Determine path: UPLOAD_DIR/project_{id}/branch_{name}/
    branch_dir_name = f"branch_{branch.name}"
    project_dir = os.path.join(UPLOAD_DIR, f"project_{project.id}", branch_dir_name)
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
        structure=structure.strip(),
        mime_type=mime or file.content_type or "",
        size_bytes=size,
        storage_path=os.path.abspath(disk_path),
        metadata_json=meta,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    add_version(db, "file", record.id, {
        "project_id": project.id, "branch_id": branch.id,
        "filename": record.filename, "display_name": record.display_name,
        "file_type": record.file_type, "structure": record.structure,
        "mime_type": record.mime_type, "size_bytes": record.size_bytes,
        "metadata": meta,
    })

    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&msg=File+uploaded", status_code=303)
