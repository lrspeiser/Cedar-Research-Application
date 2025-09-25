"""
UI view rendering functions for Cedar app.
Handles rendering of HTML views for logs, changelog, projects, etc.
"""

import os
import html as html_lib
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db_utils import RegistrySessionLocal, get_project_db
from ..ui_utils import layout, escape
from ..config import LOGS_DIR
from main_models import (
    Project, Branch, Thread, ThreadMessage, 
    FileEntry, Dataset, Note, ChangelogEntry
)
from main_helpers import current_branch, branch_filter_ids


def view_logs(project_id: Optional[int] = None, branch_id: Optional[int] = None):
    """
    View application logs for debugging.
    Shows shell job logs if available.
    """
    logs_content = ""
    
    # Read log files if they exist
    if LOGS_DIR and os.path.isdir(LOGS_DIR):
        log_files = []
        for fname in os.listdir(LOGS_DIR):
            if fname.endswith('.log'):
                log_files.append(fname)
        
        log_files.sort(reverse=True)  # Most recent first
        
        for log_file in log_files[:10]:  # Limit to 10 most recent
            log_path = os.path.join(LOGS_DIR, log_file)
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    # Limit each log to 10000 chars
                    if len(content) > 10000:
                        content = content[-10000:] + "\n... (truncated)"
                    logs_content += f"\n\n=== {log_file} ===\n{content}"
            except Exception as e:
                logs_content += f"\n\n=== {log_file} ===\nError reading log: {e}"
    else:
        logs_content = "No logs directory configured or found."
    
    # Build HTML
    html_content = f"""
    <h2>Application Logs</h2>
    <pre style="background: #f4f4f4; padding: 10px; overflow: auto; max-height: 600px;">
{html_lib.escape(logs_content)}
    </pre>
    <p><a href="/">Back to Home</a></p>
    """
    
    return HTMLResponse(layout("Logs", html_content))


def view_changelog(request: Request, project_id: Optional[int] = None, branch_id: Optional[int] = None):
    """
    View changelog entries for a project.
    Shows recent actions and changes made in the project.
    """
    # Get query parameters
    project_id = project_id or request.query_params.get("project_id")
    branch_id = branch_id or request.query_params.get("branch_id")
    
    if project_id:
        try:
            project_id = int(project_id)
        except Exception:
            project_id = None
    
    if branch_id:
        try:
            branch_id = int(branch_id)
        except Exception:
            branch_id = None
    
    # Build query
    with RegistrySessionLocal() as db:
        query = db.query(ChangelogEntry).order_by(ChangelogEntry.created_at.desc())
        
        if project_id:
            query = query.filter(ChangelogEntry.project_id == project_id)
        if branch_id:
            query = query.filter(ChangelogEntry.branch_id == branch_id)
        
        entries = query.limit(100).all()
        
        # Build HTML
        rows = []
        for entry in entries:
            created = entry.created_at.strftime("%Y-%m-%d %H:%M:%S") if entry.created_at else "Unknown"
            summary = escape(entry.summary_text or entry.action)[:100]
            
            rows.append(f"""
            <tr>
                <td>{created}</td>
                <td>P{entry.project_id}/B{entry.branch_id}</td>
                <td>{escape(entry.action)}</td>
                <td>{summary}</td>
            </tr>
            """)
        
        if rows:
            table_html = f"""
            <table border="1">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Project/Branch</th>
                        <th>Action</th>
                        <th>Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """
        else:
            table_html = "<p>No changelog entries found.</p>"
        
        # Build filter form
        filter_form = f"""
        <form method="get" action="/changelog">
            <label>Project ID: <input type="number" name="project_id" value="{project_id or ''}"></label>
            <label>Branch ID: <input type="number" name="branch_id" value="{branch_id or ''}"></label>
            <button type="submit">Filter</button>
            <a href="/changelog">Clear</a>
        </form>
        """
        
        html_content = f"""
        <h2>Changelog</h2>
        {filter_form}
        {table_html}
        <p><a href="/">Back to Home</a></p>
        """
        
        return HTMLResponse(layout("Changelog", html_content))


def render_project_view(
    project: Project,
    branch: Branch, 
    threads: List[Thread],
    files: List[FileEntry],
    datasets: List[Dataset],
    notes: List[Note],
    code_items: List[Dict[str, Any]],
    msg: Optional[str] = None,
    file_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    code_mid: Optional[int] = None,
    code_idx: Optional[int] = None
) -> str:
    """
    Render the main project view HTML.
    This is the primary UI for interacting with a project.
    """
    # Build files list
    files_html = []
    for f in files[:50]:  # Limit display
        title = escape(f.ai_title or f.display_name or f.filename)
        struct = f.structure or "unknown"
        selected = "selected" if file_id and f.id == file_id else ""
        files_html.append(f'<div class="file-item {selected}" data-id="{f.id}">')
        files_html.append(f'  <div class="file-title">{title}</div>')
        files_html.append(f'  <div class="file-meta">{struct} • {f.size_bytes} bytes</div>')
        files_html.append('</div>')
    
    # Build datasets list
    datasets_html = []
    for d in datasets[:50]:
        name = escape(d.name)
        selected = "selected" if dataset_id and d.id == dataset_id else ""
        datasets_html.append(f'<div class="dataset-item {selected}" data-id="{d.id}">')
        datasets_html.append(f'  <div class="dataset-name">{name}</div>')
        if d.description:
            datasets_html.append(f'  <div class="dataset-desc">{escape(d.description[:100])}</div>')
        datasets_html.append('</div>')
    
    # Build threads list
    threads_html = []
    for t in threads[:50]:
        title = escape(t.title)
        selected = "selected" if thread_id and t.id == thread_id else ""
        threads_html.append(f'<div class="thread-item {selected}" data-id="{t.id}">')
        threads_html.append(f'  <div class="thread-title">{title}</div>')
        threads_html.append('</div>')
    
    # Build notes list
    notes_html = []
    for n in notes[:20]:
        content_preview = escape((n.content or "")[:100])
        tags = ", ".join(n.tags) if n.tags else "No tags"
        notes_html.append(f'<div class="note-item">')
        notes_html.append(f'  <div class="note-tags">{escape(tags)}</div>')
        notes_html.append(f'  <div class="note-content">{content_preview}</div>')
        notes_html.append('</div>')
    
    # Build code items
    code_html = []
    for idx, item in enumerate(code_items[:30]):
        lang = item.get('language', 'text')
        content = escape(item.get('content', '')[:500])
        thread_title = escape(item.get('thread_title', ''))
        tool = item.get('tool', '')
        
        selected = ""
        if code_mid and code_idx is not None:
            if item.get('message_id') == code_mid and idx == code_idx:
                selected = "selected"
        
        code_html.append(f'<div class="code-item {selected}">')
        code_html.append(f'  <div class="code-meta">{thread_title} • {tool or lang}</div>')
        code_html.append(f'  <pre class="code-content">{content}</pre>')
        code_html.append('</div>')
    
    # Build message if present
    msg_html = ""
    if msg:
        msg_html = f'<div class="message">{escape(msg)}</div>'
    
    # Main HTML structure
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{escape(project.title)} - Cedar</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 20px; }}
            .header {{ border-bottom: 1px solid #ddd; padding-bottom: 10px; margin-bottom: 20px; }}
            .main-layout {{ display: flex; gap: 20px; }}
            .sidebar {{ width: 250px; }}
            .content {{ flex: 1; }}
            .panel {{ border: 1px solid #ddd; border-radius: 4px; padding: 10px; margin-bottom: 10px; }}
            .panel h3 {{ margin-top: 0; }}
            .file-item, .dataset-item, .thread-item, .note-item, .code-item {{
                padding: 8px;
                border-bottom: 1px solid #eee;
                cursor: pointer;
            }}
            .file-item:hover, .dataset-item:hover, .thread-item:hover {{
                background: #f5f5f5;
            }}
            .selected {{ background: #e8f4ff; }}
            .file-meta, .dataset-desc, .code-meta {{ font-size: 0.9em; color: #666; }}
            pre {{ background: #f4f4f4; padding: 8px; overflow-x: auto; }}
            .message {{ background: #d4edda; color: #155724; padding: 10px; margin-bottom: 10px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{escape(project.title)}</h1>
            <div>
                Project #{project.id} • Branch: {escape(branch.name)} 
                • <a href="/">Home</a>
                • <a href="/changelog?project_id={project.id}">Changelog</a>
            </div>
        </div>
        
        {msg_html}
        
        <div class="main-layout">
            <div class="sidebar">
                <div class="panel">
                    <h3>Files ({len(files)})</h3>
                    <div class="files-list">
                        {''.join(files_html) if files_html else '<p>No files</p>'}
                    </div>
                </div>
                
                <div class="panel">
                    <h3>Databases ({len(datasets)})</h3>
                    <div class="datasets-list">
                        {''.join(datasets_html) if datasets_html else '<p>No datasets</p>'}
                    </div>
                </div>
                
                <div class="panel">
                    <h3>Threads ({len(threads)})</h3>
                    <div class="threads-list">
                        {''.join(threads_html) if threads_html else '<p>No threads</p>'}
                    </div>
                    <form method="post" action="/project/{project.id}/threads/create?branch_id={branch.id}">
                        <input type="text" name="title" placeholder="New thread title">
                        <button type="submit">Create Thread</button>
                    </form>
                </div>
            </div>
            
            <div class="content">
                <div class="panel">
                    <h3>Notes ({len(notes)})</h3>
                    <div class="notes-list">
                        {''.join(notes_html) if notes_html else '<p>No notes</p>'}
                    </div>
                </div>
                
                <div class="panel">
                    <h3>Code ({len(code_items)})</h3>
                    <div class="code-list">
                        {''.join(code_html) if code_html else '<p>No code items</p>'}
                    </div>
                </div>
                
                <div class="panel">
                    <h3>Actions</h3>
                    <form method="post" action="/project/{project.id}/files/upload?branch_id={branch.id}" enctype="multipart/form-data">
                        <input type="file" name="file" required>
                        <button type="submit">Upload File</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html