
import os
import html
import shutil
import mimetypes
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean,
    UniqueConstraint, JSON, Index, func
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# ----------------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------------

DATABASE_URL = os.getenv("CEDARPY_MYSQL_URL", "mysql+pymysql://root:password@localhost/cedarpython")
UPLOAD_DIR = os.getenv("CEDARPY_UPLOAD_DIR", os.path.abspath("./user_uploads"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------------------------------------------------------------------------
# Database setup (SQLAlchemy, sync engine by design for simplicity)
# ----------------------------------------------------------------------------------

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
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

# ----------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------

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
        "jpg": "jpg", "jpeg": "jpg", "png": "png", "gif": "gif",
        "pdf": "pdf", "json": "json", "txt": "txt", "md": "md",
        "py": "code", "rs": "code", "js": "code", "ts": "code",
        "ipynb": "json"
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

app = FastAPI(title="CedarPython (Stage 1)")

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
      <div><strong>CedarPython</strong> <span class="muted">– Stage 1</span></div>
      <div class="muted small">FastAPI + MySQL prototype</div>
      <div style="margin-left:auto"><a href="/">Projects</a></div>
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
    msg: Optional[str] = None
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

    # message
    flash = f"<div class='muted' style='margin-bottom:8px'>{escape(msg)}</div>" if msg else ""

    return f"""
      <h1>{escape(project.title)}</h1>
      <div class="muted small">Project ID: {project.id}</div>
      <div style="height:10px"></div>
      <div>Branches: {tabs_html}</div>

      <div class="row" style="margin-top:16px">
        <div class="card" style="flex:2">
          <h3>Files</h3>
          {flash if msg else ""}
          <table class="table">
            <thead><tr><th>Name</th><th>Type</th><th>Structure</th><th>Branch</th><th>Size</th><th>Created</th></tr></thead>
            <tbody>{''.join(file_rows) if file_rows else '<tr><td colspan="6" class="muted">No files yet.</td></tr>'}</tbody>
          </table>
          <h4>Upload a file to this branch</h4>
          <form method="post" action="/project/{project.id}/files/upload?branch_id={current.id}" enctype="multipart/form-data">
            <input type="file" name="file" required />
            <div style="height:8px"></div>
            <label>Structure</label>
            <select name="structure" required>
              <option value="notes">notes</option>
              <option value="writeup">writeup</option>
              <option value="images">images</option>
              <option value="sources">sources</option>
              <option value="code">code</option>
            </select>
            <div style="height:8px"></div>
            <button type="submit">Upload</button>
          </form>
        </div>

        <div class="card" style="flex:1">
          <h3>Create Branch</h3>
          <form method="post" action="/project/{project.id}/branches/create">
            <input type="text" name="name" placeholder="experiment-1" required />
            <div style="height:8px"></div>
            <button type="submit">Create Branch</button>
          </form>
          <div style="height:16px"></div>
          <h3>Create Thread</h3>
          <form method="post" action="/project/{project.id}/threads/create?branch_id={current.id}">
            <input type="text" name="title" placeholder="New exploration..." required />
            <div style="height:8px"></div>
            <button type="submit">Create Thread</button>
          </form>
        </div>
      </div>

      <div class="row">
        <div class="card" style="flex:1">
          <h3>Threads</h3>
          <table class="table">
            <thead><tr><th>Title</th><th>Branch</th><th>Created</th></tr></thead>
            <tbody>{''.join(thread_rows) if thread_rows else '<tr><td colspan="3" class="muted">No threads yet.</td></tr>'}</tbody>
          </table>
        </div>
        <div class="card" style="flex:1">
          <h3>Databases</h3>
          <table class="table">
            <thead><tr><th>Name</th><th>Branch</th><th>Created</th></tr></thead>
            <tbody>{''.join(dataset_rows) if dataset_rows else '<tr><td colspan="3" class="muted">No databases yet.</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    """

# ----------------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return layout("Projects – CedarPython", projects_list_html(projects))


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
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    add_version(db, "file", record.id, {
        "project_id": project.id, "branch_id": branch.id,
        "filename": record.filename, "display_name": record.display_name,
        "file_type": record.file_type, "structure": record.structure,
        "mime_type": record.mime_type, "size_bytes": record.size_bytes
    })

    return RedirectResponse(f"/project/{project.id}?branch_id={branch.id}&msg=File+uploaded", status_code=303)
