"""
Page rendering utilities for Cedar app.
Functions to generate HTML for various pages and components.
"""

from typing import List, Optional, Dict, Any
from main_models import Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Note
from main_helpers import escape
import html
import base64
import json

# Import JavaScript bundle generators
from cedar_app.utils.javascript_bundles import (
    get_refresh_notes_script,
    get_code_to_chat_script,
    get_main_chat_script
)


def projects_list_html(projects: List[Project], msg: Optional[str] = None) -> str:
    """Generate HTML for the projects list page with optional message display."""
    # Create message HTML if provided
    message_html = ""
    if msg:
        # Check if it's a success or error message
        is_success = "successfully" in msg.lower() or "deleted" in msg.lower()
        bg_color = "#10b981" if is_success else "#ef4444"
        message_html = f"""
        <div style="background-color: {bg_color}; color: white; padding: 12px; border-radius: 6px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
            <span>{escape(msg)}</span>
            <button onclick="this.parentElement.style.display='none'" style="background: transparent; border: none; color: white; cursor: pointer; font-size: 18px; padding: 0;">✕</button>
        </div>
        """
    
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
              <td class="small muted">{p.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
              <td>
                <form method="post" action="/project/{p.id}/delete" class="inline" onsubmit="return confirm('Delete project {escape(p.title)} and all its data?');">
                  <button type="submit" class="secondary">Delete</button>
                </form>
              </td>
            </tr>
        """)
    return f"""
        <h1>Projects</h1>
        {message_html}
        <div class="row">
          <div class="card" style="flex:2">
            <table class="table">
              <thead><tr><th>Title</th><th>Created</th><th>Actions</th></tr></thead>
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
    """# Additional imports needed for project_page_html
import os
from typing import Any
from cedar_app.db_utils import _project_dirs

# Import the unified UPLOAD_AUTOCHAT_ENABLED setting
# See README "Auto-start chat on upload" for details about CEDARPY_UPLOAD_AUTOCHAT
from cedar_app.config import UPLOAD_AUTOCHAT_ENABLED

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
    last_msgs_map: Optional[Dict[int, List[ThreadMessage]]] = None,
    notes: Optional[List[Note]] = None,
    code_items: Optional[list] = None,
    selected_code: Optional[dict] = None,
) -> str:
    # Server-side diagnostics for auto-chat conditions
    try:
        sf_id = getattr(selected_file, 'id', None)
        st_id = getattr(selected_thread, 'id', None)
        print(f"[project-page] autochat enabled={UPLOAD_AUTOCHAT_ENABLED} msg={(msg or '')} file_id={sf_id} thread_id={st_id} project_id={project.id} branch_id={current.id}")
    except Exception:
        pass
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

    
    # Build History panel with numbered chats
    from cedar_app.utils.chat_persistence import get_chat_manager
    chat_manager = get_chat_manager()
    chat_list = chat_manager.list_chats(project.id, current.id, limit=20)
    
    history_items = []
    for chat in chat_list:
        chat_num = chat['chat_number']
        title = escape(chat['title'])
        created = chat['created_at'][:19] if chat['created_at'] else 'Unknown'
        status = chat['status']
        msg_count = chat['message_count']
        
        # Status indicator - for processing status, add a data attribute for refresh
        if status == 'processing':
            status_icon = "<span class='spinner' style='width:10px; height:10px' data-chat-status='processing' data-chat-num='{}' ></span>".format(chat_num)
            # Add Stop button next to spinner
            status_icon += f" <button class=\"secondary small\" title=\"Stop this run\" onclick=\"stopChat({project.id}, {current.id}, {chat_num}); event.stopPropagation(); return false;\">Stop</button>"
        elif status == 'error':
            status_icon = "<span style='color:#ef4444'>⚠</span>"
        elif status == 'complete':
            status_icon = "<span style='color:#10b981'>✓</span>"
        else:  # active
            status_icon = "<span style='color:#3b82f6'>•</span>"
        
        history_items.append(f'''
            <div class="chat-history-item" style="border-bottom:1px solid var(--border); padding:8px 0; cursor:pointer"
                 onclick="loadChat({project.id}, {current.id}, {chat_num})">
                <div style="display:flex; align-items:center; gap:8px">
                    {status_icon}
                    <span class="pill" style="min-width:30px; text-align:center">{chat_num}</span>
                    <span style="flex:1">{title}</span>
                    <span class="small muted">{msg_count} msgs</span>
                </div>
                <div class="small muted" style="margin-left:50px">{created}</div>
            </div>
        ''')
    
    history_panel_html = f'''
        <div class="card" style="padding:12px">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px">
                <h3 style="margin:0">Chat History</h3>
                <button class="secondary" onclick="startNewChat({project.id}, {current.id})">New Chat</button>
            </div>
            <div style="max-height:400px; overflow-y:auto">
                {''.join(history_items) if history_items else '<div class="muted small">No chat history yet. Click "New Chat" to start.</div>'}
            </div>
        </div>
    '''

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

    # datasets table - show Notes database specially
    dataset_rows = []
    notes_dataset = None
    notes_count = len(notes) if notes else 0
    
    for d in datasets:
        if d.name == "Notes":
            # Special display for Notes database
            notes_dataset = d
            dataset_rows.insert(0, f'''
               <tr style="background-color: #f0f9ff">
                 <td><a href='/project/{project.id}/threads/new?branch_id={current.id}&dataset_id={d.id}' class='thread-create' data-dataset-id='{d.id}'>
                    <strong>📝 {escape(d.name)} Database</strong>
                 </a></td>
                 <td>{escape(d.branch.name if d.branch else '')}</td>
                 <td class="small muted">{notes_count} notes • {d.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
               </tr>
            ''')
        else:
            # Regular database entry
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
        # Always include the original filename in the UI (tests expect to see it)
        disp_name = escape(f.display_name or '')
        meta_sub = escape(((getattr(f, 'ai_category', None) or f.structure or f.file_type or '') or ''))
        sub = disp_name + (f" — {meta_sub}" if meta_sub else "")
        active = (selected_file and f.id == selected_file.id)
        li_style = "font-weight:600" if active else ""
        # Show spinner only while LLM classification is actively running; checkmark when classified
        if getattr(f, 'ai_processing', False):
            status_icon = "<span class='spinner' title='processing'></span>"
        elif getattr(f, 'structure', None):
            status_icon = "<span title='classified'>✓</span>"
        else:
            status_icon = ""
        file_list_items.append(f"<li style='margin:6px 0; {li_style}'>{status_icon}<a href='{href}' class='thread-create' data-file-id='{f.id}' data-display-name='{disp_name}' style='text-decoration:none; color:inherit; margin-left:6px'>{label_text}</a><div class='small muted'>{sub}</div></li>")
    file_list_html = "<ul style='list-style:none; padding-left:0; margin:0'>" + ("".join(file_list_items) or "<li class='muted'>No files yet.</li>") + "</ul>"

    # Build Images list (thumbnails)
    image_items: List[str] = []
    try:
        import os as _os
        from cedar_app.db_utils import _project_dirs as __proj_dirs
        _base_root = __proj_dirs(project.id)["files_root"]
        def _image_url_for(ff: FileEntry) -> str:
            sp = ff.storage_path or ""
            try:
                ab = _os.path.abspath(sp)
                if ab.startswith(_base_root):
                    rel = ab[len(_base_root):].lstrip(_os.sep).replace(_os.sep, "/")
                    return f"/uploads/{project.id}/{rel}"
            except Exception:
                pass
            return ""
        def _is_image(ff: FileEntry) -> bool:
            try:
                mt = (ff.mime_type or '').lower()
                ext = (ff.file_type or '').lower()
                if mt.startswith('image/'):
                    return True
                if ext in {"png","jpg","jpeg","gif","webp","bmp","tiff","svg"}:
                    return True
                if (ff.structure or '').lower() == 'images':
                    return True
            except Exception:
                pass
            return False
        imgs = [f for f in files if _is_image(f)]
        for f in imgs[:60]:
            url = _image_url_for(f)
            title = escape((getattr(f, 'ai_title', None) or f.display_name or '')[:80])
            meta = escape((f.file_type or '') + ((' • ' + (f.ai_category or '')) if getattr(f, 'ai_category', None) else ''))
            # Link opens thread with this file context
            href = f"/project/{project.id}/threads/new?branch_id={current.id}&file_id={f.id}"
            image_items.append(
                "".join([
                    "<div class='img-card' style='width:160px; display:inline-block; margin:6px; vertical-align:top'>",
                    f"  <a href='{href}' class='thread-create' data-is-image='1' data-file-id='{f.id}' data-display-name='{escape(f.display_name or '')}' "
                    f"     data-image-url='{url}' data-file-type='{escape(f.file_type or '')}' data-mime-type='{escape(f.mime_type or '')}' "
                    f"     data-ai-title='{escape(getattr(f, 'ai_title', None) or '')}' data-ai-category='{escape(getattr(f, 'ai_category', None) or '')}' "
                    f"     data-ai-desc-b64='{(base64.b64encode(((getattr(f, 'ai_description', None) or '')[:10000]).encode('utf-8')).decode('ascii') if getattr(f, 'ai_description', None) else '')}' "
                    f"     data-size='{getattr(f, 'size_bytes', None) or 0}' data-created-at='{(getattr(f, 'created_at', None).isoformat() if getattr(f, 'created_at', None) else '')}'>",
                    f"    <div style='width:160px; height:100px; background:#f3f4f6; display:flex; align-items:center; justify-content:center; overflow:hidden; border:1px solid var(--border); border-radius:6px'>",
                    (f"      <img src='{url}' alt='{title}' style='max-width:100%; max-height:100%'>" if url else "      <div class='muted small'>(no preview)</div>"),
                    "    </div>",
                    "  </a>",
                    f"  <div class='small' style='margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis' title='{title}'>{title}</div>",
                    f"  <div class='small muted'>{meta}</div>",
                    "</div>",
                ])
            )
    except Exception:
        image_items = []
    images_list_html = "".join(image_items) if image_items else "<div class='muted small'>(No images yet)</div>"

    # Build right-side Code list
    code_items_safe = code_items or []
    def _code_label(ci: dict) -> str:
        try:
            t = (ci.get('title') or '').strip()
        except Exception:
            t = ''
        if not t:
            try:
                c0 = ci.get('code') or ''
            except Exception:
                c0 = ''
            t = (c0.splitlines()[0] if c0 else '')[:80]
        return t or 'Code snippet'
    code_list_items: List[str] = []
    for ci in code_items_safe:
        try:
            mid = ci.get('mid')
            idx = ci.get('idx', 0)
            href = f"/project/{project.id}?branch_id={current.id}&code_mid={mid}&code_idx={idx}"
            # Visible label and basic fields (escaped)
            label = escape(_code_label(ci))
            lang_raw = str(ci.get('language') or 'text')
            lang = escape(lang_raw)
            th_title_raw = str(ci.get('thread_title') or '')
            th_title = escape(th_title_raw)
            # Human-readable timestamp
            when = ''
            when_iso = ''
            try:
                if ci.get('created_at'):
                    when = ci.get('created_at').strftime("%Y-%m-%d %H:%M:%S") + " UTC"
                    try:
                        when_iso = ci.get('created_at').isoformat()
                    except Exception:
                        when_iso = when
            except Exception:
                when = ''
                when_iso = ''
            is_active = bool(selected_code and selected_code.get('mid') == mid and int(selected_code.get('idx', 0)) == int(idx))
            li_style = "font-weight:600" if is_active else ""
            sub = " · ".join([x for x in [lang, th_title, when] if x])
            # Prepare code payloads (base64-encoded to keep attributes safe)
            try:
                full_code = str(ci.get('code') or '')
            except Exception:
                full_code = ''
            try:
                preview_max = 5000
                preview = full_code[:preview_max]
                if len(full_code) > preview_max:
                    preview = preview + "\n\n... (truncated)"
            except Exception:
                preview = full_code
            try:
                code_b64 = base64.b64encode(full_code.encode('utf-8')).decode('ascii') if isinstance(full_code, str) else ''
            except Exception:
                code_b64 = ''
            try:
                code_preview_b64 = base64.b64encode(preview.encode('utf-8')).decode('ascii') if isinstance(preview, str) else ''
            except Exception:
                code_preview_b64 = ''
            # Data attributes for click-to-chat
            data_attrs = (
                f"data-title='{escape(str(ci.get('title') or ''))}' "
                f"data-language='{escape(lang_raw)}' "
                f"data-code-b64='{code_b64}' "
                f"data-code-preview-b64='{code_preview_b64}' "
                f"data-created-at='{escape(when_iso)}' "
                f"data-thread-title='{escape(th_title_raw)}' "
                f"data-mid='{escape(str(mid))}' "
                f"data-idx='{escape(str(idx))}'"
            )
            # Primary: open chat with code; Secondary: Details keeps existing behavior
            code_list_items.append(
                "<li style='margin:6px 0; " + li_style + "'>"
                + f"<a href='#' class='js-open-code-chat' {data_attrs} style='text-decoration:none; color:inherit'>{label}</a>"
                + f" <a href='{href}' class='small code-details-link' style='margin-left:8px' title='View details'>(Details)</a>"
                + f"<div class='small muted'>{sub}</div>"
                + "</li>"
            )
        except Exception:
            pass
    code_list_html = "<ul style='list-style:none; padding-left:0; margin:0'>" + ("".join(code_list_items) or "<li class='muted'>No code yet.</li>") + "</ul>"

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

    # Code details panel (selected code)
    code_details_html = ""
    try:
        ci = selected_code or None
        if ci:
            title = escape(str(ci.get('title') or 'Code'))
            lang = escape(str(ci.get('language') or ''))
            th_title = escape(str(ci.get('thread_title') or ''))
            th_id = ci.get('thread_id')
            when = ''
            try:
                when = ci.get('created_at').strftime("%Y-%m-%d %H:%M:%S") + " UTC" if ci.get('created_at') else ''
            except Exception:
                when = ''
            code_text = str(ci.get('code') or '')
            pre_id = f"code_src_{ci.get('mid', 'x')}_{ci.get('idx', 0)}"
            thread_link = f"/project/{project.id}?branch_id={current.id}&thread_id={th_id}" if th_id else ""
            meta_rows = []
            meta_rows.append(f"<tr><th>Title</th><td>{title}</td></tr>")
            if lang:
                meta_rows.append(f"<tr><th>Language</th><td>{lang}</td></tr>")
            if th_title:
                meta_rows.append("<tr><th>Thread</th><td>" + (f"<a href='{thread_link}'>{th_title}</a>" if thread_link else th_title) + "</td></tr>")
            if when:
                meta_rows.append(f"<tr><th>Created</th><td class='small muted'>{when}</td></tr>")
            meta_tbl = "<table class='table'><tbody>" + "".join(meta_rows) + "</tbody></table>"
            code_prefix = ("```" + lang + "\\n") if lang else "```"
            insert_btn = f"<button class='secondary' onclick=\"var ta=document.getElementById('chatInput'); if(!ta)return; var src=document.getElementById('{pre_id}').innerText; ta.value='{code_prefix}' + src + '\\n```'; ta.focus();\">Insert into chat</button>"
            copy_btn = f"<button class='secondary' onclick=\"try{{navigator.clipboard.writeText(document.getElementById('{pre_id}').innerText);}}catch(_){{}}\">Copy</button>"
            code_pre = f"<pre id='{pre_id}' class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px; max-height:400px; overflow:auto'>" + escape(code_text) + "</pre>"
            code_details_html = ("<div class='card' style='margin-top:8px; padding:12px'><h3 style='margin-bottom:6px'>Code Details</h3>" + meta_tbl + "<div class='small' style='margin:6px 0; display:flex; gap:6px'>" + insert_btn + copy_btn + "</div>" + code_pre + "</div>")
    except Exception:
        code_details_html = ""

    # Thread tabs and All Chats panel removed - using single WebSocket chat interface

    # Build Notes table (from database) - simplified to show content directly
    notes_rows_html: List[str] = []
    try:
        for n in (notes or []):
            # Timestamp
            when = ""
            try:
                when = n.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(n, 'created_at', None) else ""
            except Exception:
                pass
            
            # Tags display
            tags_html = ""
            try:
                tags = n.tags or []
                if tags:
                    tags_html = ", ".join([escape(str(t)) for t in tags])
            except Exception:
                pass
            
            # Content - display directly without parsing JSON or markdown processing
            content = str(getattr(n, 'content', '') or '')
            # Escape for HTML display but keep it readable
            content_display = escape(content[:500])  # Limit to 500 chars for table display
            if len(content) > 500:
                content_display += "..."
            
            # Build table row
            notes_rows_html.append(f"""
                <tr>
                    <td class='small muted' style='white-space:nowrap'>{escape(when)}</td>
                    <td class='small' style='white-space:pre-wrap; max-width:600px'>{content_display}</td>
                    <td class='small muted'>{tags_html}</td>
                </tr>
            """)
    except Exception as e:
        print(f"[notes-panel-error] Failed to render notes: {e}")
        notes_rows_html = []
    
    notes_table_html = f"""
        <table class='table' style='width:100%; table-layout:fixed'>
            <thead>
                <tr>
                    <th style='width:160px'>Timestamp</th>
                    <th>Content</th>
                    <th style='width:200px'>Tags</th>
                </tr>
            </thead>
            <tbody>
                {''.join(notes_rows_html) if notes_rows_html else '<tr><td colspan="3" class="muted small">No notes yet. Notes will be automatically created by agents during chat conversations.</td></tr>'}
            </tbody>
        </table>
    """
    
    notes_panel_html = (
        "<div class='card' style='padding:12px'>"
        "  <div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:12px'>"
        "    <h3 style='margin:0'>📝 Notes</h3>"
        "    <div style='display:flex; gap:8px'>"
        f"      <button class='secondary' onclick='window.location.href=\"/project/{project.id}?branch_id={current.id}&refresh_notes=1#main-notes\"'>Refresh</button>"
        "    </div>"
        "  </div>"
        + notes_table_html
        + "</div>"
    )

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

    if not msgs:
        msg_rows.append("<div class='muted small'>(No messages yet)</div>")
    msgs_html = "".join(msg_rows)

    # Chat form (LLM keys required; see README)

    # Chat form (LLM keys required; see README)
    # Only include hidden ids when present to avoid posting empty strings, which cause int parsing errors.
    hidden_thread = f"<input type='hidden' name='thread_id' value='{selected_thread.id}' />" if selected_thread else ""
    hidden_file = f"<input type='hidden' name='file_id' value='{selected_file.id}' />" if selected_file else ""
    hidden_dataset = f"<input type='hidden' name='dataset_id' value='{selected_dataset.id}' />" if selected_dataset else ""
    chat_form = f"""
      <form id='chatForm' data-project-id='{project.id}' data-branch-id='{current.id}' data-thread-id='{selected_thread.id if selected_thread else ''}' data-file-id='{selected_file.id if selected_file else ''}' data-file-name='{escape(selected_file.display_name) if selected_file else ''}' data-dataset-id='{selected_dataset.id if selected_dataset else ''}' method='post' action='/project/{project.id}/threads/chat?branch_id={current.id}' style='margin-top:8px'>
        {hidden_thread}{hidden_file}{hidden_dataset}
        <textarea id='chatInput' name='content' rows='3' placeholder='Ask a question about this file/context...' style='width:100%; font-family: ui-monospace, Menlo, monospace;'></textarea>
        <div style='height:6px'></div>
        <div style='display:flex; gap:8px; align-items:center'>
          <button type='submit'>Submit</button>
          <button type='button' id='stopChatBtn' class='secondary' style='display:none'>Stop</button>
        </div>
      </form>
    """

    # Client-side WebSocket streaming script (word-by-word). Falls back to simulated by-word if server returns full text.
    script_js = get_main_chat_script()
    # Replace placeholders with actual IDs; avoid Python's % formatting which conflicts with '%' in CSS
    # Embed WS timeout budget (ms) for client watchdog
    try:
        _ws_timeout_s = int(os.getenv("CEDARPY_CHAT_TIMEOUT_SECONDS", "300"))
    except Exception:
        _ws_timeout_s = 300
    _ws_timeout_ms = max(1000, _ws_timeout_s * 1000)
    script_js = script_js.replace("__PID__", str(project.id)).replace("__BID__", str(current.id)).replace("__WS_TIMEOUT_MS__", str(_ws_timeout_ms))
    script_js = script_js.replace("__UPLOAD_AUTOCHAT__", "true" if UPLOAD_AUTOCHAT_ENABLED else "false")
    
    # Inject file details JSON for auto-chat (null when no selected file)
    file_details_json_text = None
    try:
        if selected_file is not None:
            # Build first_lines from sample_text (up to 40 lines, ~2000 chars)
            meta = getattr(selected_file, 'metadata_json', None) or {}
            sample_text = meta.get('sample_text') or ''
            if isinstance(sample_text, str):
                first_lines = "\n".join(sample_text.splitlines()[:40])
                if len(first_lines) > 2000:
                    first_lines = first_lines[:2000]
            else:
                first_lines = ''
            # Determine if image; omit first_lines for images
            _ft = (selected_file.file_type or '').lower()
            _struct = (selected_file.structure or '').lower()
            _is_image = (_struct == 'images') or (_ft in {'jpg','jpeg','png','gif','webp','bmp','tiff'})
            details = {
                "project_id": project.id,
                "branch_id": current.id,
                "thread_id": (selected_thread.id if selected_thread else None),
                "file_id": selected_file.id,
                "name": selected_file.display_name,
                "file_type": selected_file.file_type,
                "structure": selected_file.structure,
                "mime_type": selected_file.mime_type,
                "size_bytes": selected_file.size_bytes,
                "storage_path": selected_file.storage_path,
                "sha256": meta.get('sha256'),
            }
            if first_lines and not _is_image:
                details["first_lines"] = first_lines
            file_details_json_text = json.dumps(details, ensure_ascii=False)
    except Exception:
        file_details_json_text = None
    # Build the full initial user message as a JS string literal (compact)
    if file_details_json_text is not None:
        try:
            _fname = (json.loads(file_details_json_text).get('name') or '').strip()
        except Exception:
            _fname = ''
        display_label = _fname or 'file'
        initial_msg_text = f"Uploaded {display_label}"
    else:
        initial_msg_text = "Uploaded file"
    # IMPORTANT: Escape '</script' to avoid prematurely terminating the inline script tag
    _safe_initial_msg = initial_msg_text.replace("</script", "<\\/script")
    script_js = script_js.replace("__INITIAL_UPLOAD_USER_MESSAGE__", json.dumps(_safe_initial_msg))
    # Inject file details JSON for client-side details panel
    # This string is later JSON.parse'd on the client; keep it a JSON string, but escape '</script'
    _safe_file_details = (file_details_json_text or "").replace("</script", "<\\/script")
    script_js = script_js.replace("__FILE_DETAILS_JSON__", json.dumps(_safe_file_details))
    
    # Add script to handle refresh_notes parameter and switch to Notes tab
    refresh_notes_script = get_refresh_notes_script()

    # Click-to-chat for Code tab titles: open Chat, start new chat, render context, prefill, and inject full code on submit
    code_to_chat_js = get_code_to_chat_script()
    
    return f"""
      <h1>{escape(project.title)}</h1>
      <div class=\"muted small\">Project ID: {project.id}</div>
      <div style=\"height:10px\"></div>
      <div>Branches: {tabs_html}</div>
      { ("<div class='small' style='margin-top:8px; padding:8px; background:#ecfdf5; border:1px solid #10b981; border-radius:6px'>Last uploaded: " + escape(selected_file.display_name) + "</div>") if (msg and msg.strip() == 'File uploaded' and selected_file) else "" }
      { ("<div class='small' style='margin-top:6px'><strong>AI Title:</strong> " + (escape(selected_file.ai_title) if (selected_file and getattr(selected_file, 'ai_title', None)) else "(none)") + "</div>") if selected_file else "" }
      
      <script>
      function confirmProjectDelete(projectName) {{
        // First confirmation
        if (!confirm('Are you sure you want to delete project "' + projectName + '"?')) {{
          return false;
        }}
        // Second confirmation for safety
        var secondConfirm = confirm('⚠️ WARNING: This will permanently delete:\\n\\n' +
          '• All files in this project\\n' +
          '• All chat history\\n' + 
          '• All databases\\n' +
          '• All code snippets\\n' +
          '• All notes\\n\\n' +
          'This action CANNOT be undone. Click OK to permanently delete everything.');
        return secondConfirm;
      }}
      </script>

      <div id="page-root" style="min-height:100vh; display:flex; flex-direction:column">
        <div style="margin-top:8px; flex:1; min-height:0; display:flex; flex-direction:column">
          <div class="tabs" data-pane="main">
            <a href="#" class="tab{ ' active' if not (msg and msg.strip() == 'File uploaded') else '' }" data-target="main-chat">Chat</a>
            <a href="#" class="tab{ ' active' if (msg and msg.strip() == 'File uploaded') else '' }" data-target="main-files">Files</a>
            <a href="#" class="tab" data-target="main-images">Images</a>
            <a href="#" class="tab" data-target="main-history">History</a>
            <a href="#" class="tab" data-target="main-code">Code</a>
            <a href="#" class="tab" data-target="main-dbs">Databases</a>
            <a href="#" class="tab" data-target="main-notes">Notes</a>
          </div>
          <div class="tab-panels" style="flex:1; min-height:0">
            <div id="main-chat" class="panel{ ' hidden' if (msg and msg.strip() == 'File uploaded') else '' }" style="height:100%">
                <h3>Chat <span id="chat-number-display" style="display:none">- <span id="chat-number"></span></span>
                  <a href="#" class="small" style="margin-left:12px" onclick="startNewChat({project.id}, {current.id}); return false;">Start New Chat</a>
                </h3>
                <style>
                /* Chat area grows to fill viewport; input stays at bottom regardless of window size */
                  #main-chat {{ display:flex; flex-direction:column; flex:1; min-height:0; height:100%; }}
                  #main-chat .chat-log {{ flex:1; display:flex; flex-direction:column; gap:8px; overflow-y:auto; padding-bottom:80px; }}
                  #main-chat .chat-input {{ position: sticky; bottom: 0; margin-top:auto; padding-top:6px; background:#fff; border-top:1px solid var(--border); }}
                  .msg {{ display:flex; flex-direction:column; max-width:80%; }}
                  .msg.user {{ align-self:flex-end; }}
                  .msg.assistant {{ align-self:flex-start; }}
                  .msg.system {{ align-self:flex-start; }}
                  .msg .meta {{ display:flex; gap:8px; align-items:center; margin-bottom:4px; }}
                  .bubble {{ border:1px solid var(--border); border-radius:18px; padding:12px 14px; font-size:14px; line-height:1.45; box-shadow: 0 1px 1px rgba(0,0,0,0.04); }}
                  .bubble.user {{ background:#d9fdd3; border-color:#b2e59a; }}
                  .bubble.assistant {{ background:#ffffff; border-color:#e6e6e6; }}
                  .bubble.system {{ background:#e7f3ff; border-color:#cfe8ff; }}
                </style>
                {flash_html}
                <div id='msgs' class='chat-log'>{msgs_html}</div>
                <div class='chat-input'>{chat_form}</div>
                {script_js}
                {code_to_chat_js}
                { ("<div class='card' style='margin-top:8px; padding:12px'><h3>File Details</h3>" + left_details + "</div>") if selected_file else "" }
                {code_details_html}
              </div>
              <div id="main-history" class="panel hidden">
                {history_panel_html}
              </div>
              <div id="main-files" class="panel{ '' if (msg and msg.strip() == 'File uploaded') else ' hidden' }">
                <div class="card" style="padding:12px">
                  <h3 style='margin-bottom:6px'>Files</h3>
                  { ("<div class='small' data-testid='last-upload'>Last uploaded: " + escape(selected_file.display_name) + "</div>") if (msg and msg.strip() == 'File uploaded' and selected_file) else "" }
                  <!-- Upload form at the top of Files tab -->
                  <form method="post" action="/project/{project.id}/files/upload?branch_id={current.id}" enctype="multipart/form-data" data-testid="upload-form" style="margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid var(--border)">
                    <input type="file" name="file" required data-testid="upload-input" style="margin-right:8px" />
                    <button type="submit" data-testid="upload-submit" style="display:inline-block">Upload</button>
                  </form>
                  { ("<div class='small' style='margin:6px 0'><strong>AI Title:</strong> " + (escape(selected_file.ai_title) if (selected_file and getattr(selected_file, 'ai_title', None)) else "(none)") + "</div>") if selected_file else "" }
                  <div style="max-height:400px; overflow:auto">
                    {file_list_html}
                  </div>
                </div>
              </div>
              <div id="main-images" class="panel hidden">
                <div class="card" style="padding:12px">
                  <h3 style='margin-bottom:6px'>Images</h3>
                  <div style="max-height:600px; overflow:auto">
                    {images_list_html}
                  </div>
                </div>
              </div>
              <div id="main-code" class="panel hidden">
                <div class="card" style="padding:12px">
                  <h3 style='margin-bottom:6px'>Code</h3>
                  <div style="max-height:600px; overflow:auto">
                    {code_list_html}
                  </div>
                </div>
              </div>
              <div id="main-dbs" class="panel hidden">
                <div class="card" style="padding:12px">
                  <h3>Databases</h3>
                  <table class="table">
                    <thead><tr><th>Name</th><th>Branch</th><th>Created</th></tr></thead>
                    <tbody>{dataset_tbody}</tbody>
                  </table>
                </div>
              </div>
              <div id="main-notes" class="panel hidden">
                {notes_panel_html}
              </div>
          </div>
        </div>
      </div>
    </div>
    
    {refresh_notes_script}

    """

