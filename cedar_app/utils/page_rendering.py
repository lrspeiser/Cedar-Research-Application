"""
Page rendering utilities for Cedar app.
Functions to generate HTML for various pages and components.
"""

from typing import List, Optional, Dict, Any
from main_models import Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Note
from main_helpers import escape
import html


def projects_list_html(projects: List[Project]) -> str:
    """Generate HTML for the projects list page."""
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

# Import the UPLOAD_AUTOCHAT_ENABLED setting
try:
    UPLOAD_AUTOCHAT_ENABLED = str(os.getenv("CEDARPY_UPLOAD_AUTOCHAT_ENABLED", "0")).strip().lower() not in {"", "0", "false", "no", "off"}
except Exception:
    UPLOAD_AUTOCHAT_ENABLED = False


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
    last_msgs_map: Optional[Dict[int, List[ThreadMessage]]] = None,
    notes: Optional[List[Note]] = None,
    code_items: Optional[list] = None,
    selected_code: Optional[dict] = None,
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

    # extract latest plan from selected thread messages (if any)
    plan_card_html = ""
    try:
        if thread_messages:
            last_plan = None
            for m in reversed(thread_messages):
                try:
                    pj = m.payload_json if hasattr(m, 'payload_json') else None
                except Exception:
                    pj = None
                if isinstance(pj, dict) and str(pj.get('function') or '').lower() == 'plan':
                    last_plan = pj
                    break
            if last_plan:
                # Render a compact plan card for the right column
                try:
                    pt = html.escape(str(last_plan.get('title') or 'Plan'))
                except Exception:
                    pt = 'Plan'
                steps = last_plan.get('steps') or []
                rows = []
                si = 0
                for st in steps[:10]:
                    si += 1
                    fn = html.escape(str((st or {}).get('function') or ''))
                    ti = html.escape(str((st or {}).get('title') or ''))
                    st_status = html.escape(str((st or {}).get('status') or 'in queue'))
                    rows.append(f"<tr><td class='small'>{fn}</td><td>{ti}</td><td class='small muted'>{st_status}</td></tr>")
                tbody = ''.join(rows) or "<tr><td colspan='3' class='muted small'>(no steps)</td></tr>"
                plan_card_html = f"""
                <div class='card' style='padding:12px'>
                  <h3 style='margin-bottom:6px'>Plan</h3>
                  <div class='small muted' style='margin-bottom:6px'>{pt}</div>
                  <table class='table'>
                    <thead><tr><th>Func</th><th>Title</th><th>Status</th></tr></thead>
                    <tbody>{tbody}</tbody>
                  </table>
                </div>
                """
    except Exception:
        plan_card_html = ""

    # Build plan panel content (fallback when no plan yet)
    plan_panel_html = plan_card_html or "<div class='card' style='padding:12px'><h3>Plan</h3><div class='muted small'>(No plan yet)</div></div>"
    
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
        
        # Status indicator
        if status == 'processing':
            status_icon = "<span class='spinner' style='width:10px; height:10px'></span>"
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
            label = escape(_code_label(ci))
            lang = escape(str(ci.get('language') or ''))
            th_title = escape(str(ci.get('thread_title') or ''))
            when = ''
            try:
                when = ci.get('created_at').strftime("%Y-%m-%d %H:%M:%S") + " UTC" if ci.get('created_at') else ''
            except Exception:
                when = ''
            is_active = bool(selected_code and selected_code.get('mid') == mid and int(selected_code.get('idx', 0)) == int(idx))
            li_style = "font-weight:600" if is_active else ""
            sub = " · ".join([x for x in [lang, th_title, when] if x])
            code_list_items.append(f"<li style='margin:6px 0; {li_style}'><a href='{href}' style='text-decoration:none; color:inherit'>{label}</a><div class='small muted'>{sub}</div></li>")
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
            copy_btn = f"<button class='secondary' onclick=\"try{{navigator.clipboard.writeText(document.getElementById('{pre_id}').innerText);}}catch(_){{}}\">Copy</button>"
            code_pre = f"<pre id='{pre_id}' class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px; max-height:400px; overflow:auto'>" + escape(code_text) + "</pre>"
            code_details_html = ("<div class='card' style='margin-top:8px; padding:12px'><h3 style='margin-bottom:6px'>Code Details</h3>" + meta_tbl + "<div class='small' style='margin:6px 0'>" + copy_btn + "</div>" + code_pre + "</div>")
    except Exception:
        code_details_html = ""

    # Thread tabs and All Chats panel removed - using single WebSocket chat interface

    # Build Notes list panel (LLM-generated notes)
    notes_items_html: List[str] = []
    try:
        import json as _json
        for n in (notes or []):
            try:
                when = n.created_at.strftime("%Y-%m-%d %H:%M:%S") + " UTC" if getattr(n, 'created_at', None) else ""
            except Exception:
                when = ""
            # Tags
            try:
                tags = n.tags or []
                tags_html = " ".join([f"<span class='pill'>{escape(str(t))}</span>" for t in tags])
            except Exception:
                tags_html = ""
            # Body: attempt to parse JSON for themes/sections; fallback to plain text
            body_html = ""
            try:
                data = _json.loads(n.content)
                if isinstance(data, dict) and isinstance(data.get('themes'), list):
                    parts: List[str] = []
                    for th in (data.get('themes') or [])[:10]:
                        try:
                            name = escape(str((th or {}).get('name') or ''))
                        except Exception:
                            name = ''
                        notes_list = (th or {}).get('notes') or []
                        items = "".join([f"<li class='small'>{escape(str(x))}</li>" for x in notes_list[:10]])
                        parts.append(
                            "<div style='margin-bottom:6px'>"
                            + (f"<div class='small muted' style='font-weight:600'>{name}</div>" if name else "")
                            + f"<ul class='small' style='margin:4px 0 0 16px'>{items}</ul>"
                            + "</div>"
                        )
                    body_html = "".join(parts) or "<div class='muted small'>(empty)</div>"
                elif isinstance(data, dict) and isinstance(data.get('sections'), list):
                    secs = data.get('sections') or []
                    items = "".join([f"<li class='small'><b>{escape(str((s or {}).get('title') or ''))}</b> – {escape(str((s or {}).get('text') or '')[:200])}</li>" for s in secs[:10]])
                    body_html = f"<ul class='small'>{items}</ul>" if items else "<div class='muted small'>(empty)</div>"
                else:
                    body_html = f"<pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>{escape(str(n.content)[:1000])}</pre>"
            except Exception:
                body_html = f"<pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px'>{escape(str(getattr(n, 'content', '') or '')[:1000])}</pre>"
            notes_items_html.append(
                "<div class='note-item' style='border-bottom:1px solid var(--border); padding:8px 0'>"
                + (f"<div class='small muted'>{escape(when)} {tags_html}</div>" if (when or tags_html) else "")
                + body_html
                + "</div>"
            )
    except Exception:
        notes_items_html = []
    notes_panel_html = (
        "<div class='card' style='padding:12px'>"
        "  <h3 style='margin-bottom:6px'>Notes</h3>"
        + ("".join(notes_items_html) or "<div class='muted small'>(No notes yet)</div>")
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
        <button type='submit'>Submit</button>
      </form>
    """

    # Client-side WebSocket streaming script (word-by-word). Falls back to simulated by-word if server returns full text.
    script_js = """
<script>
(function(){
  var PROJECT_ID = __PID__;
  var BRANCH_ID = __BID__;
  var UPLOAD_AUTOCHAT = __UPLOAD_AUTOCHAT__;
  var SSE_ACTIVE = false;
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

      function startWS(text, threadId, fileId, datasetId, replay){
    try {
      var msgs = document.getElementById('msgs');
      
      // Include chat number if we have one
      var chatNum = window.currentChatNumber;
      var optimisticUser = null;

      // Simple step timing helpers (annotate previous bubble/line with elapsed time)
      var currentStep = null;
      function _now(){ try { return performance.now(); } catch(_) { return Date.now(); } }
      // Running timer state for the active step
      var _timerId = null;
      var _timerEl = null;
      function _clearRunningTimer(){ try { if (_timerId) { clearInterval(_timerId); _timerId = null; } } catch(_){} }
      function annotateTime(node, dtMs){
        try {
          if (!node) return;
          var t = document.createElement('span');
          t.className = 'small muted';
          t.style.marginLeft = '6px';
          var sec = (dtMs/1000).toFixed(dtMs >= 1000 ? 1 : 2);
          t.textContent = '(' + sec + 's)';
          node.appendChild(t);
        } catch(_) {}
      }
      function startRunningTimer(node, t0){
        try {
          if (!node) return;
          var target = (function(){ try { return node.querySelector('.meta .title'); } catch(_) { return null; } })() || node;
          _timerEl = document.createElement('span');
          _timerEl.className = 'small muted';
          _timerEl.style.marginLeft = '6px';
          target.appendChild(_timerEl);
          var lastText = '';
          _timerId = setInterval(function(){
            try {
              var dt = _now() - t0;
              var sec = (dt/1000).toFixed(dt >= 1000 ? 1 : 2);
              var text = '(' + sec + 's)';
              if (_timerEl && text !== lastText) { _timerEl.textContent = text; lastText = text; }
            } catch(_){}
          }, 250);
        } catch(_){}
      }
      var stepsHistory = [];
      function stepAdvance(label, node){
        var now = _now();
        try {
          if (currentStep && currentStep.node){
            var dt = now - currentStep.t0;
            _clearRunningTimer();
            annotateTime(currentStep.node, dt);
            try {
              var rec = { project: PROJECT_ID, thread: threadId||null, from: currentStep.label, to: String(label||''), dt_ms: Math.round(dt) };
              stepsHistory.push({ from: rec.from, to: rec.to, dt_ms: rec.dt_ms });
              console.log('[perf] ' + JSON.stringify(rec));
            } catch(_) {}
          }
        } catch(_){ }
        currentStep = { label: String(label||''), t0: now, node: node || null };
        if (node) { startRunningTimer(node, now); }
      }

      // Variables for backend-driven UI
      var stream = null; // processing bubble node, created on backend 'processing' action
      var spin = null;   // spinner element inside processing bubble
      var procPre = null; // processing log area (details) created on 'processing' action
      var streamText = null; // text node to stream main answer tokens into (assigned on 'processing')
      // Live planning (thinking) bubble state
      var thinkWrap = null; // planning bubble wrapper
      var thinkText = null; // planning text node to stream tokens into
      var thinkSpin = null; // spinner inside planning bubble

      // Subscribe to client console logs while this WS session is active (appended to procPre when available)
      var logSub = function(pl){
        try {
          if (!procPre) return;
          var line = '[' + (pl.level||'INFO') + '] ' + (pl.message||'');
          var when = (pl.when||'').replace('T',' ').replace('Z','')
          if (when) line = when + ' ' + line;
          procPre.textContent += (procPre.textContent ? '\\n' : '') + line;
          if (procPre.textContent.length > 8000) {
            procPre.textContent = procPre.textContent.slice(-8000);
          }
        } catch(_){}
      };
      try { if (window.subscribeCedarLogs) window.subscribeCedarLogs(logSub); } catch(_){}

      var lastW = null;
      var stagesSeen = {};

      // Optimistic local echo of the user's message so the UI shows instant feedback
      try {
        if (msgs && text && !replay) {
          var wrapU = document.createElement('div'); wrapU.className = 'msg user';
          wrapU.setAttribute('data-temp', '1');
          var metaU = document.createElement('div'); metaU.className = 'meta small'; metaU.innerHTML = "<span class='pill'>user</span> <span class='title' style='font-weight:600'>USER</span>";
          var bubU = document.createElement('div'); bubU.className = 'bubble user';
          var contU = document.createElement('div'); contU.className='content'; contU.style.whiteSpace='pre-wrap';
          contU.textContent = String(text||'');
          bubU.appendChild(contU); wrapU.appendChild(metaU); wrapU.appendChild(bubU);
          msgs.appendChild(wrapU);
          optimisticUser = wrapU;
          stepAdvance('user:local', wrapU);
        }
      } catch(_){ }

      var wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
      var ws = new WebSocket(wsScheme + '://' + location.host + '/ws/chat/' + PROJECT_ID);
      var wsStartMs = _now();

      // Client-side watchdog to ensure the user always sees progress or a timeout
      var timeoutMs = __WS_TIMEOUT_MS__; // mirrors server CEDARPY_CHAT_TIMEOUT_SECONDS
      var finalOrError = false;
      var timedOut = false;
      var timeoutId = null;
      function clearSpinner(){ try { if (spin && spin.parentNode) spin.remove(); } catch(_){} }
      function refreshTimeout(){
        try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
        timeoutId = setTimeout(function(){
          if (!finalOrError) {
            try {
              var budgetS = Math.round(timeoutMs/1000);
              var elapsedS = (function(){ try { return (( _now() - (wsStartMs||0) )/1000).toFixed(1); } catch(_) { return 'unknown'; } })();
              streamText.textContent = '[timeout] Took too long. Exceeded ' + budgetS + 's budget; elapsed ' + elapsedS + 's. Please try again.';
            } catch(_){ }
            clearSpinner();
            stepAdvance('timeout', stream);
            finalOrError = true; timedOut = true;
            try { ws.close(); } catch(_){ }
          }
        }, timeoutMs);
      }

      ws.onopen = function(){
        try {
          wsStartMs = _now();
          refreshTimeout();
          // Do not print a local 'submitted'; rely on server info events for true order
          if (replay) {
            ws.send(JSON.stringify({action:'chat', replay_messages: replay, branch_id: BRANCH_ID, thread_id: threadId||null, file_id: (fileId||null), dataset_id: (datasetId||null), chat_number: chatNum }));
          } else {
            ws.send(JSON.stringify({action:'chat', content: text, branch_id: BRANCH_ID, thread_id: threadId||null, file_id: (fileId||null), dataset_id: (datasetId||null), chat_number: chatNum }));
          }
        } catch(e){}
      };
      function ackEvent(m){
        try {
          if (!m || !m.eid) return;
          fetch('/api/chat/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: PROJECT_ID, branch_id: BRANCH_ID, thread_id: (m.thread_id||threadId||null), eid: m.eid, type: m.type, fn: m.function||null }) }).catch(function(_){})
        } catch(_){}
      }
      // All Chats functionality removed
      function handleEvent(m){
        // Handle chat creation notification
        if (m.type === 'chat_created') {
          window.currentChatNumber = m.chat_number;
          updateChatNumberDisplay(m.chat_number);
          refreshHistoryPanel();
        }
        if (!m) return;
        if (m.type === 'stream') {
          // Handle streaming text updates
          if (streamText) {
            streamText.textContent = m.text || '';
          }
          refreshTimeout();
        } else if (m.type === 'message') { ackEvent(m);
          try {
            var r = String(m.role||'assistant');
            var rLower = r.toLowerCase();
            if (rLower === 'user') {
              // If we optimistically echoed a user bubble, reconcile it with the backend event
              try {
                var tempU = document.querySelector('#msgs .msg.user[data-temp="1"]');
                if (tempU) {
                  tempU.removeAttribute('data-temp');
                  var c = tempU.querySelector('.content'); if (c) c.textContent = String(m.text||'');
                  stepAdvance('user', tempU);
                  return;
                }
              } catch(_){ }
            }
            // Determine CSS class: user, system, or assistant (default for agents)
            var roleClass = 'assistant';  // Default for all agents
            if (rLower === 'user') roleClass = 'user';
            else if (rLower === 'system') roleClass = 'system';
            
            // For display, show the actual role/agent name
            var displayRole = r;
            var pillText = rLower.includes('agent') || rLower.includes('executor') || rLower.includes('reasoner') ? 'agent' : rLower;
            
            var wrapM = document.createElement('div'); 
            wrapM.className = 'msg ' + roleClass;
            var metaM = document.createElement('div'); 
            metaM.className = 'meta small'; 
            metaM.innerHTML = "<span class='pill'>" + pillText + "</span> <span class='title' style='font-weight:600'>" + displayRole + "</span>";
            var bubM = document.createElement('div'); 
            bubM.className = 'bubble ' + roleClass;
            var contM = document.createElement('div'); 
            contM.className='content'; 
            contM.style.whiteSpace='pre-wrap';
            
            // Parse markdown formatting if present
            var textContent = String(m.text||'');
            // Convert **text** to bold for better display
            if (textContent.includes('**')) {
              contM.innerHTML = textContent
                .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
                .replace(/_([^_]+)_/g, '<em>$1</em>')
                .replace(/\\n/g, '<br>');
            } else {
              contM.textContent = textContent;
            }
            
            bubM.appendChild(contM); 
            wrapM.appendChild(metaM); 
            wrapM.appendChild(bubM);
            if (msgs) msgs.appendChild(wrapM);
            stepAdvance(roleClass, wrapM);
          } catch(_) { }
        } else if (m.type === 'prompt') {
          try {
            try {
              window.__cedar_last_prompts = window.__cedar_last_prompts || {};
              if (m.thread_id) { window.__cedar_last_prompts[String(m.thread_id)] = m.messages || []; }
            } catch(_){ }
            // If server provided a thread_id and the form doesn't have one yet, set it now (no pre-create roundtrip)
            try {
              if (m.thread_id) {
                var chatForm2 = document.getElementById('chatForm');
                if (chatForm2 && !(chatForm2.getAttribute('data-thread-id'))) {
                  var tidStr = String(m.thread_id);
                  chatForm2.setAttribute('data-thread-id', tidStr);
                  var hiddenTid2 = chatForm2.querySelector("input[name='thread_id']");
                  if (hiddenTid2) hiddenTid2.value = tidStr; else { var hi2 = document.createElement('input'); hi2.type='hidden'; hi2.name='thread_id'; hi2.value=tidStr; chatForm2.appendChild(hi2); }
                }
              }
            } catch(_){}
            var detIdP = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            var wrapP = document.createElement('div'); wrapP.className = 'msg assistant';
            var metaP = document.createElement('div'); metaP.className = 'meta small'; metaP.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>Assistant</span>";
            var bubP = document.createElement('div'); bubP.className = 'bubble assistant'; bubP.setAttribute('data-details-id', detIdP);
            var contP = document.createElement('div'); contP.className='content'; contP.style.whiteSpace='pre-wrap';
            try { contP.textContent = 'Prepared LLM prompt (click to view JSON).'; } catch(_){}
            bubP.appendChild(contP);
            var detailsP = document.createElement('div'); detailsP.id = detIdP; detailsP.style.display='none';
            var preP = document.createElement('pre'); preP.className='small'; preP.style.whiteSpace='pre-wrap'; preP.style.background='#f8fafc'; preP.style.padding='8px'; preP.style.borderRadius='6px';
            try { preP.textContent = JSON.stringify(m.messages || [], null, 2); } catch(_){ preP.textContent = String(m.messages || ''); }
            // Action bar for details: Copy JSON
            var barP = document.createElement('div'); barP.className='small'; barP.style.margin='6px 0 8px 0';
            var copyBtnP = document.createElement('button'); copyBtnP.textContent='Copy JSON'; copyBtnP.className='secondary';
            copyBtnP.addEventListener('click', function(){ try { navigator.clipboard.writeText(preP.textContent); } catch(_){} });
            barP.appendChild(copyBtnP);
            detailsP.appendChild(barP);
            detailsP.appendChild(preP);
            wrapP.appendChild(metaP); wrapP.appendChild(bubP); wrapP.appendChild(detailsP);
            // Allow clicking the title to toggle details (to satisfy tests)
            try {
              var titleElP = metaP.querySelector('.title');
              if (titleElP) {
                titleElP.setAttribute('role', 'button');
                titleElP.setAttribute('tabindex', '0');
                var _tglP = function(){ try { var e=document.getElementById(detIdP); if (e) { e.style.display = (e.style.display==='none'?'block':'none'); } } catch(_){} };
                titleElP.addEventListener('click', function(ev){ try { ev.preventDefault(); } catch(_){}; _tglP(); });
                titleElP.addEventListener('keydown', function(ev){ try { if (ev && (ev.key==='Enter' || ev.key===' ')) { ev.preventDefault(); _tglP(); } } catch(_){} });
              }
            } catch(_) {}
            if (msgs) msgs.appendChild(wrapP);
            stepAdvance('assistant:prompt', wrapP);
            ackEvent(m);
          } catch(_) { }
        } else if (m.type === 'agent_result') {
          // Handle agent results from orchestrator
          try {
            var agentName = m.agent_name || 'Agent';
            var fullText = m.text || '';
            
            // Extract just the Answer part for collapsed view
            var answerMatch = fullText.match(/Answer:\\s*([^\\n]+(?:\\n(?!\\n|Why:|Potential Issues:|Suggested Next Steps:)[^\\n]+)*)/);
            var collapsedText = answerMatch ? answerMatch[1].trim() : fullText.split('\\n')[0];
            
            // Create unique ID for collapsible details
            var detailId = 'agent_det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            
            var wrapA = document.createElement('div');
            wrapA.className = 'msg assistant';
            var metaA = document.createElement('div');
            metaA.className = 'meta small';
            metaA.innerHTML = "<span class='pill'>agent</span> <span class='title' style='font-weight:600; cursor:pointer' role='button' tabindex='0'>" + agentName + "</span>";
            
            var bubA = document.createElement('div');
            bubA.className = 'bubble assistant';
            bubA.style.cursor = 'pointer';
            bubA.setAttribute('data-details-id', detailId);
            
            // Collapsed content - just the answer
            var contA = document.createElement('div');
            contA.className = 'content';
            contA.style.whiteSpace = 'pre-wrap';
            contA.textContent = collapsedText;
            
            // Add click hint
            var hintA = document.createElement('span');
            hintA.className = 'small muted';
            hintA.style.marginLeft = '8px';
            hintA.textContent = '(click for details)';
            contA.appendChild(hintA);
            
            bubA.appendChild(contA);
            
            // Full details (hidden by default)
            var detailsA = document.createElement('div');
            detailsA.id = detailId;
            detailsA.style.display = 'none';
            detailsA.style.padding = '12px';
            detailsA.style.background = '#f8fafc';
            detailsA.style.borderRadius = '6px';
            detailsA.style.marginTop = '8px';
            
            var preA = document.createElement('pre');
            preA.className = 'small';
            preA.style.whiteSpace = 'pre-wrap';
            preA.style.margin = '0';
            preA.textContent = fullText;
            detailsA.appendChild(preA);
            
            wrapA.appendChild(metaA);
            wrapA.appendChild(bubA);
            wrapA.appendChild(detailsA);
            
            // Make bubble and title clickable to toggle details
            var toggleDetails = function(e) {
              if (e) {
                e.preventDefault();
                e.stopPropagation();
              }
              var d = document.getElementById(detailId);
              if (d) {
                var isHidden = d.style.display === 'none';
                d.style.display = isHidden ? 'block' : 'none';
                // Update hint text
                hintA.textContent = isHidden ? '(click to collapse)' : '(click for details)';
              }
            };
            
            // Add click event listeners
            bubA.addEventListener('click', toggleDetails);
            var titleEl = metaA.querySelector('.title');
            if (titleEl) {
              titleEl.addEventListener('click', toggleDetails);
            }
            
            if (msgs) msgs.appendChild(wrapA);
            stepAdvance('agent:' + agentName.toLowerCase(), wrapA);
            ackEvent(m);
          } catch(e) {
            console.error('[agent_result] error', e);
          }
        } else if (m.type === 'action') {
          try {
            var fn = String(m.function||'').trim();
            var text = String(m.text||'');

            // Backend-driven processing ACK as assistant bubble with spinner
            if (fn === 'processing') {
              try {
                // Remove placeholder if present
                try { var first = msgs.firstElementChild; if (first && first.classList.contains('muted')) { first.remove(); } } catch(_){ }
                stream = document.createElement('div');
                stream.className = 'msg assistant';
                var meta0 = document.createElement('div'); meta0.className = 'meta small'; meta0.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>processing</span>";
                var bub0 = document.createElement('div'); bub0.className = 'bubble assistant';
                var cont0 = document.createElement('div'); cont0.className = 'content'; cont0.style.whiteSpace='pre-wrap'; cont0.textContent = text || 'Processing…';
                // Use this content node as the streaming target for main assistant tokens
                streamText = cont0;
                // Spinner
                spin = document.createElement('span'); spin.className = 'spinner'; spin.style.marginLeft = '6px'; cont0.appendChild(spin);
                bub0.appendChild(cont0);
                // Collapsible details area for logs
                var procDetId = 'proc_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
                bub0.setAttribute('data-details-id', procDetId);
                var details0 = document.createElement('div'); details0.id = procDetId; details0.style.display='none';
                procPre = document.createElement('div'); procPre.className='small'; procPre.style.whiteSpace='pre-wrap'; procPre.style.background='#0b1021'; procPre.style.color='#e6e6e6'; procPre.style.padding='8px'; procPre.style.borderRadius='6px'; procPre.style.maxHeight='260px'; procPre.style.overflow='auto';
                details0.appendChild(procPre);
                stream.appendChild(meta0); stream.appendChild(bub0); stream.appendChild(details0);
                if (msgs) msgs.appendChild(stream);
                stepAdvance('assistant:processing', stream);
              } catch(_){}
              return;
            }

            // Lightweight plan updates should not create extra bubbles
            if (fn === 'plan_update') {
              try {
                var paneU = document.getElementById('right-plan');
                if (paneU) {
                  var callU = m.call || {};
                  var stepsU = Array.isArray(callU.steps) ? callU.steps : [];
                  var rowsU = stepsU.map(function(st, idx){
                    try {
                      var f = String((st && st.function) || '');
                      var ti = String((st && st.title) || '');
                      var stStatus = String((st && st.status) || 'in queue');
                      var desc = String((st && st.description) || '');
                      var goal = String((st && st.goal_outcome) || '');
                      var args = st && st.args ? JSON.stringify(st.args) : '{}';
                      var did = 'plan_det_' + idx + '_' + Math.random().toString(36).slice(2,6);
                      return "<tr class='plan-row' data-det-id='"+did+"'><td class='small'>"+f+"</td><td>"+ti+"</td><td class='small muted'>"+stStatus+"</td></tr>"+
                             "<tr id='"+did+"' class='plan-detail' style='display:none'><td colspan='3'><div class='small'><b>Description:</b> "+desc+"<br><b>Goal:</b> "+goal+"<br><b>Args:</b> <code class='small'>"+args.replace(/</g,'&lt;')+"</code></div></td></tr>";
                    } catch(_){ return ""; }
                  }).join('');
                  if (!rowsU) rowsU = "<tr><td colspan='3' class='muted small'>(no steps)</td></tr>";
                  var htmlU = "<div class='card' style='padding:12px'>"+
                               "<h3 style='margin-bottom:6px'>Plan</h3>"+
                               "<table class='table'><thead><tr><th>Func</th><th>Title</th><th>Status</th></tr></thead><tbody>"+rowsU+"</tbody></table>"+
                               "</div>";
                  paneU.innerHTML = htmlU;
                  try {
                    paneU.querySelectorAll('.plan-row').forEach(function(r){ r.addEventListener('click', function(){ var id=r.getAttribute('data-det-id'); var e = id && document.getElementById(id); if(e){ e.style.display=(e.style.display==='none'?'table-row':'none'); } }); });
                  } catch(_) {}
                }
              } catch(_){ }
              stepAdvance('system:'+fn, null);
              return;
            }

            var detId = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            var wrap = document.createElement('div'); wrap.className = 'msg system';
            // Improved titles for special actions
            var displayTitle = fn;
            try {
              if (fn === 'tool_result') {
                var cf = m && m.call && m.call.function ? String(m.call.function) : '';
                displayTitle = cf ? ('Tool Result: ' + cf) : 'Tool Result';
              } else if (fn === 'submit_step') {
                displayTitle = 'Submitting Step';
              } else if (fn === 'plan') {
                displayTitle = 'Plan';
              }
            } catch(_){}
            var meta = document.createElement('div'); meta.className = 'meta small'; meta.innerHTML = "<span class='pill'>system</span> <span class='title' style='font-weight:600'>" + displayTitle + "</span>";
            var bub = document.createElement('div'); bub.className = 'bubble system'; bub.setAttribute('data-details-id', detId);
            var cont = document.createElement('div'); cont.className='content'; cont.style.whiteSpace='pre-wrap';
            if (fn === 'plan' && m.call && m.call.steps && Array.isArray(m.call.steps)) {
              try {
                var rows = m.call.steps.map(function(st){ var f=String(st.function||''); var ti=String(st.title||''); var de=String(st.description||''); var stS=String(st.status||'in queue'); return "- ["+stS+"] "+f+": "+ti+ (de? (" — "+de):''); }).join('\\\\n');
                cont.textContent = 'Plan:\\\\n' + rows;
              } catch(_){ }
            } else if (fn === 'submit_step' || fn === 'tool_result') {
              cont.textContent = text;
            } else {
              cont.textContent = (fn ? (fn + ' ') : '') + text;
            }
            bub.appendChild(cont);
            var details = document.createElement('div'); details.id = detId; details.style.display='none';
            var pre = document.createElement('pre'); pre.className='small'; pre.style.whiteSpace='pre-wrap'; pre.style.background='#f8fafc'; pre.style.padding='8px'; pre.style.borderRadius='6px';
            try { pre.textContent = JSON.stringify(m.call || {}, null, 2); } catch(_){ pre.textContent = String(m.call || {}); }
            details.appendChild(pre);
            wrap.appendChild(meta); wrap.appendChild(bub); wrap.appendChild(details);
            if (msgs) msgs.appendChild(wrap);
            stepAdvance('system:'+fn, wrap);
            ackEvent(m);
            try { if (fn === 'thread_update' && m.call && m.call.thread_id) { upsertAllChatsItem(m.call.thread_id, String(m.call.title||''), null); } } catch(_){ }

            // If this is a plan function, also update the right-side Plan panel live
            if (fn === 'plan') {
              try {
                var pane = document.getElementById('right-plan');
                if (pane) {
                  var call = m.call || {};
                  var steps = Array.isArray(call.steps) ? call.steps : [];
                  var rows = steps.map(function(st, idx){
                    try {
                      var f = String((st && st.function) || '');
                      var ti = String((st && st.title) || '');
                      var stStatus = String((st && st.status) || 'in queue');
                      var desc = String((st && st.description) || '');
                      var goal = String((st && st.goal_outcome) || '');
                      var args = st && st.args ? JSON.stringify(st.args) : '{}';
                      var did = 'plan_det_p_' + idx + '_' + Math.random().toString(36).slice(2,6);
                      return "<tr class='plan-row' data-det-id='"+did+"'><td class='small'>"+f+"</td><td>"+ti+"</td><td class='small muted'>"+stStatus+"</td></tr>"+
                             "<tr id='"+did+"' class='plan-detail' style='display:none'><td colspan='3'><div class='small'><b>Description:</b> "+desc+"<br><b>Goal:</b> "+goal+"<br><b>Args:</b> <code class='small'>"+args.replace(/</g,'&lt;')+"</code></div></td></tr>";
                    } catch(_){ return ""; }
                  }).join('');
                  if (!rows) rows = "<tr><td colspan='3' class='muted small'>(no steps)</td></tr>";
                  var html = "<div class='card' style='padding:12px'>"+
                             "<h3 style='margin-bottom:6px'>Plan</h3>"+
                             "<table class='table'><thead><tr><th>Func</th><th>Title</th><th>Status</th></tr></thead><tbody>"+rows+"</tbody></table>"+
                             "</div>";
                  pane.innerHTML = html;
                  try {
                    pane.querySelectorAll('.plan-row').forEach(function(r){ r.addEventListener('click', function(){ var id=r.getAttribute('data-det-id'); var e = id && document.getElementById(id); if(e){ e.style.display=(e.style.display==='none'?'table-row':'none'); } }); });
                  } catch(_) {}
                  // Ensure the Plan tab is visible
                  try {
                    var tab = document.querySelector(".tabs[data-pane='right'] .tab[data-target='right-plan']");
                    if (tab) { tab.click(); }
                  } catch(_){}
                }
              } catch(_){}
            }
          } catch(_){ }
        } else if (m.type === 'thinking_start') { ackEvent(m);
          try {
            // Create a live planning bubble if not already present
            if (!thinkWrap) {
              var detIdTh = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
              thinkWrap = document.createElement('div'); thinkWrap.className = 'msg assistant';
              var metaTh = document.createElement('div'); metaTh.className = 'meta small'; metaTh.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>planning</span>";
              var bubTh = document.createElement('div'); bubTh.className = 'bubble assistant'; bubTh.setAttribute('data-details-id', detIdTh);
              var contTh = document.createElement('div'); contTh.className = 'content'; contTh.style.whiteSpace='pre-wrap'; contTh.textContent = 'Planning…';
              // Spinner during planning
              thinkSpin = document.createElement('span'); thinkSpin.className = 'spinner'; thinkSpin.style.marginLeft = '6px'; contTh.appendChild(thinkSpin);
              thinkText = contTh;
              // Details area for planner metadata
              var detailsTh = document.createElement('div'); detailsTh.id = detIdTh; detailsTh.style.display='none';
              var preTh = document.createElement('pre'); preTh.className='small'; preTh.style.whiteSpace='pre-wrap'; preTh.style.background='#f8fafc'; preTh.style.padding='8px'; preTh.style.borderRadius='6px';
              try { preTh.textContent = JSON.stringify({ model: m.model || '' }, null, 2); } catch(_) { preTh.textContent = String(m.model||''); }
              detailsTh.appendChild(preTh);
              bubTh.appendChild(contTh);
              thinkWrap.appendChild(metaTh); thinkWrap.appendChild(bubTh); thinkWrap.appendChild(detailsTh);
              if (msgs) msgs.appendChild(thinkWrap);
              stepAdvance('assistant:thinking', thinkWrap);
            }
          } catch(_) {}
        } else if (m.type === 'thinking_token' && m.delta) {
          try {
            if (thinkText) {
              thinkText.textContent = (thinkText.textContent ? thinkText.textContent : '') + String(m.delta);
            }
          } catch(_) {}
        } else if (m.type === 'thinking') { ackEvent(m);
          try {
            // Ensure bubble exists
            if (!thinkWrap) {
              var detIdTh2 = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
              thinkWrap = document.createElement('div'); thinkWrap.className = 'msg assistant';
              var metaTh2 = document.createElement('div'); metaTh2.className = 'meta small'; metaTh2.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>planning</span>";
              var bubTh2 = document.createElement('div'); bubTh2.className = 'bubble assistant'; bubTh2.setAttribute('data-details-id', detIdTh2);
              var contTh2 = document.createElement('div'); contTh2.className = 'content'; contTh2.style.whiteSpace='pre-wrap';
              thinkText = contTh2;
              bubTh2.appendChild(contTh2);
              var detailsTh2 = document.createElement('div'); detailsTh2.id = detIdTh2; detailsTh2.style.display='none';
              var preTh2 = document.createElement('pre'); preTh2.className='small'; preTh2.style.whiteSpace='pre-wrap'; preTh2.style.background='#f8fafc'; preTh2.style.padding='8px'; preTh2.style.borderRadius='6px';
              detailsTh2.appendChild(preTh2);
              thinkWrap.appendChild(metaTh2); thinkWrap.appendChild(bubTh2); thinkWrap.appendChild(detailsTh2);
              if (msgs) msgs.appendChild(thinkWrap);
              stepAdvance('assistant:thinking', thinkWrap);
            }
            if (thinkText) { thinkText.textContent = String(m.text || ''); }
            try { if (thinkSpin && thinkSpin.parentNode) thinkSpin.remove(); } catch(_) {}
            // Update details with final planner output and metadata
            try {
              var detEl = thinkWrap ? thinkWrap.querySelector('.bubble[data-details-id]') : null;
              var did = detEl ? detEl.getAttribute('data-details-id') : null;
              var preEl = did ? document.querySelector('#'+did+' pre') : null;
              if (preEl) {
                var obj = { model: m.model || '', elapsed_ms: m.elapsed_ms || null, text: String(m.text||'') };
                preEl.textContent = JSON.stringify(obj, null, 2);
              }
            } catch(_) {}
          } catch(_) {}
        } else if (m.type === 'token' && m.word) {
          if (lastW !== m.word) {
            if (streamText) {
              streamText.textContent = (streamText.textContent ? (streamText.textContent + ' ') : '') + String(m.word);
            }
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
              stepAdvance('info:'+label, inf);
            }
            if (label === 'finalizing' || label === 'persisted' || label === 'timeout') {
              clearSpinner();
              if (label === 'timeout') { finalOrError = true; }
            }
          } catch(_){ }
        } else if (m.type === 'final' && m.text) {
          finalOrError = true;
          try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
          // Render a proper assistant bubble for the final answer, with optional JSON details
          try {
            var detIdF = m.json ? ('det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8)) : null;
            var wrapF = document.createElement('div'); wrapF.className = 'msg assistant';
            var fnF = (m && m.json && m.json.function) ? String(m.json.function) : 'final';
            var metaF = document.createElement('div'); metaF.className = 'meta small'; metaF.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>" + fnF + "</span>";
            var bubF = document.createElement('div'); bubF.className = 'bubble assistant'; if (detIdF) bubF.setAttribute('data-details-id', detIdF);
            var contF = document.createElement('div'); contF.className='content'; contF.style.whiteSpace='pre-wrap'; contF.textContent = (fnF ? (fnF + ' ') : '') + (m.text||'');
            // Add edit prompt link if we have a stored prompt for this thread
            try {
              var last = (window.__cedar_last_prompts||{})[String(threadId||'')];
              if (last && last.length) {
                var edit = document.createElement('a'); edit.href='#'; edit.className='small muted'; edit.style.marginLeft='8px'; edit.textContent='(edit prompt)';
                edit.addEventListener('click', function(ev){
                  try { ev.preventDefault(); } catch(_){}
                  // Open simple modal
                  var overlay = document.getElementById('promptEditModal');
                  if (!overlay) {
                    overlay = document.createElement('div'); overlay.id='promptEditModal'; overlay.style.position='fixed'; overlay.style.inset='0'; overlay.style.background='rgba(0,0,0,0.4)'; overlay.style.zIndex='9999';
                    var pane = document.createElement('div'); pane.style.position='absolute'; pane.style.top='10%'; pane.style.left='50%'; pane.style.transform='translateX(-50%)'; pane.style.width='80%'; pane.style.maxWidth='900px'; pane.style.background='#fff'; pane.style.borderRadius='8px'; pane.style.padding='12px';
                    var h = document.createElement('div'); h.innerHTML = "<b>Edit Prompt JSON</b>"; pane.appendChild(h);
                    var ta = document.createElement('textarea'); ta.id='promptEditArea'; ta.style.width='100%'; ta.style.height='320px'; ta.style.fontFamily='ui-monospace, Menlo, monospace'; pane.appendChild(ta);
                    var bar = document.createElement('div'); bar.style.marginTop='8px';
                    var runBtn = document.createElement('button'); runBtn.textContent='Run with edited prompt';
                    var cancelBtn = document.createElement('button'); cancelBtn.textContent='Cancel'; cancelBtn.className='secondary'; cancelBtn.style.marginLeft='8px';
                    var copyBtnM = document.createElement('button'); copyBtnM.textContent='Copy JSON'; copyBtnM.className='secondary'; copyBtnM.style.marginLeft='8px';
                    var restoreBtn = document.createElement('button'); restoreBtn.textContent='Restore default'; restoreBtn.className='secondary'; restoreBtn.style.marginLeft='8px';
                    bar.appendChild(runBtn); bar.appendChild(cancelBtn); bar.appendChild(copyBtnM); bar.appendChild(restoreBtn); pane.appendChild(bar);
                    // Schema hint
                    var hint = document.createElement('pre'); hint.className='small'; hint.style.whiteSpace='pre-wrap'; hint.style.background='#f8fafc'; hint.style.padding='8px'; hint.style.borderRadius='6px'; hint.style.marginTop='8px';
                    hint.textContent = `Messages JSON schema (simplified):\n[\n  { "role": "system|user|assistant", "content": "string" },\n  ...\n]\nYou may add multiple user entries (Resources/History/Context/examples) followed by the current user message.`;
                    pane.appendChild(hint);
                    overlay.appendChild(pane);
                    document.body.appendChild(overlay);
                    cancelBtn.addEventListener('click', function(){ try { overlay.remove(); } catch(_){} });
                    copyBtnM.addEventListener('click', function(){ try { navigator.clipboard.writeText(ta.value||''); } catch(_){} });
                    var _orig = null; try { _orig = JSON.stringify(last, null, 2); } catch(_) { _orig = '[]'; }
                    restoreBtn.addEventListener('click', function(){ try { ta.value = _orig; } catch(_){} });
                    runBtn.addEventListener('click', function(){
                      try {
                        var txt = document.getElementById('promptEditArea').value || '[]';
                        var parsed = JSON.parse(txt);
                        try { overlay.remove(); } catch(_){ }
                        // Reuse the same thread/file/dataset context, but pass replay messages
                        startWS('', threadId, fileId, datasetId, parsed);
                      } catch(e) {
                        alert('Invalid JSON: ' + e);
                      }
                    });
                  }
                  try { document.getElementById('promptEditArea').value = JSON.stringify(last, null, 2); } catch(_){}
                });
                contF.appendChild(edit);
              }
            } catch(_){ }
            bubF.appendChild(contF);
            wrapF.appendChild(metaF); wrapF.appendChild(bubF);
            if (detIdF) {
              var detailsF = document.createElement('div'); detailsF.id = detIdF; detailsF.style.display='none';
              var preF = document.createElement('pre'); preF.className='small'; preF.style.whiteSpace='pre-wrap'; preF.style.background='#f8fafc'; preF.style.padding='8px'; preF.style.borderRadius='6px';
              try { preF.textContent = JSON.stringify(m.json, null, 2); } catch(_){ preF.textContent = String(m.json); }
              // Action bar for details: Copy JSON
              var barF = document.createElement('div'); barF.className='small'; barF.style.margin='6px 0 8px 0';
              var copyBtnF = document.createElement('button'); copyBtnF.textContent='Copy JSON'; copyBtnF.className='secondary';
              copyBtnF.addEventListener('click', function(){ try { navigator.clipboard.writeText(preF.textContent); } catch(_){} });
              barF.appendChild(copyBtnF);
              detailsF.appendChild(barF);
              detailsF.appendChild(preF);
              wrapF.appendChild(detailsF);
            }
            if (msgs) msgs.appendChild(wrapF);
            // Ensure an Assistant prompt bubble exists for JSON drilldown, even if the initial 'prompt' event was missed
            try {
              // Only synthesize if no existing Assistant-titled message exists. The final bubble's title may be 'final' or a function name,
              // so do not treat that as satisfying the Assistant prompt presence check.
              var titles = Array.from(document.querySelectorAll('#msgs .msg.assistant .meta .title'));
              var haveAssistantTitle = false;
              try {
                haveAssistantTitle = titles.some(function(el){ return String(el.textContent||'').trim().toLowerCase() === 'assistant'; });
              } catch(_){ haveAssistantTitle = false; }
              if (!haveAssistantTitle) {
                var detIdP2 = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
                var wrapP2 = document.createElement('div'); wrapP2.className = 'msg assistant';
                var metaP2 = document.createElement('div'); metaP2.className = 'meta small'; metaP2.innerHTML = "<span class='pill'>assistant</span> <span class='title' style='font-weight:600'>Assistant</span>";
                var bubP2 = document.createElement('div'); bubP2.className = 'bubble assistant'; bubP2.setAttribute('data-details-id', detIdP2);
                var contP2 = document.createElement('div'); contP2.className='content'; contP2.style.whiteSpace='pre-wrap';
                try { contP2.textContent = 'Prepared LLM prompt (click to view JSON).'; } catch(_){ }
                bubP2.appendChild(contP2);
                var detailsP2 = document.createElement('div'); detailsP2.id = detIdP2; detailsP2.style.display='none';
                var preP2 = document.createElement('pre'); preP2.className='small'; preP2.style.whiteSpace='pre-wrap'; preP2.style.background='#f8fafc'; preP2.style.padding='8px'; preP2.style.borderRadius='6px';
                var fallbackMsgs = null;
                try {
                  var last = (window.__cedar_last_prompts||{})[String(threadId||'')];
                  if (last && last.length) { fallbackMsgs = last; }
                } catch(_){ }
                if (!fallbackMsgs) {
                  var fromFinal = null;
                  try { if (m && m.prompt) { fromFinal = m.prompt; } } catch(_){ }
                  if (fromFinal && Array.isArray(fromFinal)) {
                    fallbackMsgs = fromFinal;
                  } else {
                    var reason = 'No LLM prompt available';
                    try { if (m && m.json && m.json.meta && m.json.meta.fastpath) { reason = 'No LLM prompt: fast-path (' + String(m.json.meta.fastpath) + ')'; } } catch(_){ }
                    fallbackMsgs = [{ role: 'system', content: reason }];
                  }
                }
                try { preP2.textContent = JSON.stringify(fallbackMsgs, null, 2); } catch(_){ preP2.textContent = String(fallbackMsgs); }
                var barP2 = document.createElement('div'); barP2.className='small'; barP2.style.margin='6px 0 8px 0';
                var copyBtnP2 = document.createElement('button'); copyBtnP2.textContent='Copy JSON'; copyBtnP2.className='secondary';
                copyBtnP2.addEventListener('click', function(){ try { navigator.clipboard.writeText(preP2.textContent); } catch(_){} });
                barP2.appendChild(copyBtnP2);
                detailsP2.appendChild(barP2);
                detailsP2.appendChild(preP2);
                wrapP2.appendChild(metaP2); wrapP2.appendChild(bubP2); wrapP2.appendChild(detailsP2);
                // Allow clicking the title to toggle details (to satisfy tests)
                try {
                  var titleElP2 = metaP2.querySelector('.title');
                  if (titleElP2) {
                    titleElP2.setAttribute('role', 'button');
                    titleElP2.setAttribute('tabindex', '0');
                    var _tglP2 = function(){ try { var e=document.getElementById(detIdP2); if (e) { e.style.display = (e.style.display==='none'?'block':'none'); } } catch(_){} };
                    titleElP2.addEventListener('click', function(ev){ try { ev.preventDefault(); } catch(_){}; _tglP2(); });
                    titleElP2.addEventListener('keydown', function(ev){ try { if (ev && (ev.key==='Enter' || ev.key===' ')) { ev.preventDefault(); _tglP2(); } } catch(_){} });
                  }
                } catch(_) {}
                if (msgs) { try { msgs.insertBefore(wrapP2, wrapF); } catch(_) { msgs.appendChild(wrapP2); } }
                try { console.log('[ui] synthesized Assistant prompt bubble'); } catch(_){}
                try { stepAdvance('assistant:prompt', wrapP2); } catch(_){}
              }
            } catch(_){ }
          } catch(_) {
            // Fallback to replacing the processing text if bubble rendering fails
            try { streamText.textContent = m.text; } catch(_){}
          }
          // Clear spinner once final is ready; remove the transient processing bubble so tests don't see it anymore
          clearSpinner();
          try {
            setTimeout(function(){ try { if (stream && stream.parentNode) stream.parentNode.removeChild(stream); } catch(_){} }, 400);
          } catch(_) { try { if (stream && stream.parentNode) stream.parentNode.removeChild(stream); } catch(_){} }
          stepAdvance('assistant:final', null);
          ackEvent(m);
        } else if (m.type === 'error') {
          finalOrError = true;
          try { if (timeoutId) clearTimeout(timeoutId); } catch(_){}
          streamText.textContent = '[error] ' + (m.error || 'unknown'); ackEvent(m);
          clearSpinner();
          try {
            // Also append a system bubble with error details for visibility in the thread
            var wrapE = document.createElement('div'); wrapE.className = 'msg system';
            var metaE = document.createElement('div'); metaE.className = 'meta small'; metaE.innerHTML = "<span class='pill'>system</span> <span class='title' style='font-weight:600'>error</span>";
            var bubE = document.createElement('div'); bubE.className = 'bubble system';
            var contE = document.createElement('div'); contE.className = 'content'; contE.style.whiteSpace = 'pre-wrap'; contE.textContent = String(m.error||'unknown');
            bubE.appendChild(contE); wrapE.appendChild(metaE); wrapE.appendChild(bubE);
            if (msgs) msgs.appendChild(wrapE);
          } catch(_){}
        }
      }
      ws.onmessage = function(ev){
        refreshTimeout();
        var m = null; try { m = JSON.parse(ev.data); } catch(_){ return; }
        handleEvent(m);
      };
      ws.onerror = function(){ try { streamText.textContent = (streamText.textContent||'') + ' [ws-error]'; } catch(_){} };
      ws.onclose = function(){ try { if (window.unsubscribeCedarLogs && logSub) window.unsubscribeCedarLogs(logSub); } catch(_){}; try { if (currentStep && currentStep.node && !timedOut) { annotateTime(currentStep.node, _now() - currentStep.t0); currentStep = null; } if (!finalOrError && !timedOut) { streamText.textContent = (streamText.textContent||'') + ' [closed]'; } } catch(_){} };
    } catch(e) {}
  }

  // Using WebSocket for all communication
  
  // Chat history management functions
  window.currentChatNumber = null;
  
  function updateChatNumberDisplay(chatNumber) {
    var display = document.getElementById('chat-number-display');
    var numSpan = document.getElementById('chat-number');
    if (display && numSpan) {
      numSpan.textContent = chatNumber;
      display.style.display = 'inline';
    }
  }
  
  window.startNewChat = function(projectId, branchId) {
    // Create a new chat and start it
    fetch(`/api/chat/new`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_id: projectId, branch_id: branchId})
    }).then(function(r) {
      return r.json();
    }).then(function(data) {
      window.currentChatNumber = data.chat_number;
      updateChatNumberDisplay(data.chat_number);
      // Clear current messages
      var msgs = document.getElementById('msgs');
      if (msgs) msgs.innerHTML = '<div class="muted small">Chat ' + data.chat_number + ' started</div>';
      // Refresh history panel
      refreshHistoryPanel();
    }).catch(function(e) {
      console.error('Failed to create new chat:', e);
    });
  }
  
  window.loadChat = function(projectId, branchId, chatNumber) {
    // Load a specific chat's history
    window.currentChatNumber = chatNumber;
    updateChatNumberDisplay(chatNumber);
    fetch(`/api/chat/load`, {
      method: 'POST', 
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_id: projectId, branch_id: branchId, chat_number: chatNumber})
    }).then(function(r) {
      return r.json();
    }).then(function(data) {
      // Display the loaded chat messages
      var msgs = document.getElementById('msgs');
      if (msgs) {
        msgs.innerHTML = '';
        if (data.messages) {
          data.messages.forEach(function(msg) {
            var roleClass = msg.role === 'user' ? 'user' : (msg.role === 'system' ? 'system' : 'assistant');
            var wrap = document.createElement('div');
            wrap.className = 'msg ' + roleClass;
            var meta = document.createElement('div');
            meta.className = 'meta small';
            meta.innerHTML = '<span class="pill">' + msg.role + '</span>';
            var bub = document.createElement('div');
            bub.className = 'bubble ' + roleClass;
            var cont = document.createElement('div');
            cont.className = 'content';
            cont.style.whiteSpace = 'pre-wrap';
            cont.textContent = msg.content;
            bub.appendChild(cont);
            wrap.appendChild(meta);
            wrap.appendChild(bub);
            msgs.appendChild(wrap);
          });
        }
      }
    }).catch(function(e) {
      console.error('Failed to load chat:', e);
    });
  }
  
  window.refreshHistoryPanel = function() {
    // Refresh the history panel to show updated chat list
    // For now, manually switch to history tab to see updates
    var histTab = document.querySelector('[data-target="right-history"]');
    if (histTab) {
      // Could trigger refresh here if needed
    }
  }
  document.addEventListener('DOMContentLoaded', function(){
    try {
      var chatForm = document.getElementById('chatForm');

      // Ensure we always have a thread as soon as the page opens so submissions are instant and consistent
      // Do NOT create a new thread if one is already in the URL (e.g., after upload redirect)
      try {
        (async function(){
          try {
            var sp0 = new URLSearchParams(location.search || '');
            var tidFromUrl = sp0.get('thread_id');
            if (chatForm && !chatForm.getAttribute('data-thread-id') && !tidFromUrl) {
              var fidInit = chatForm.getAttribute('data-file-id') || null;
              var dsidInit = chatForm.getAttribute('data-dataset-id') || null;
              var tidInit = await ensureThreadId(null, fidInit, dsidInit);
              if (tidInit) {
                // Normalize URL to include the created thread_id
                try {
                  var urlInit = `/project/${PROJECT_ID}?branch_id=${BRANCH_ID}&thread_id=${encodeURIComponent(tidInit)}` + (fidInit?`&file_id=${encodeURIComponent(fidInit)}`:'') + (dsidInit?`&dataset_id=${encodeURIComponent(dsidInit)}`:'');
                  if (history && history.replaceState) { history.replaceState({}, '', urlInit); }
                } catch(_){}
              }
            }
          } catch(_){}
        })();
      } catch(_){}

      // Persist last active context and attach SSE for the current thread (rehydrate on reopen)
      try {
        var _savedOnce = false;
        function _saveAndAttachIfReady(){
          try {
            var sp1 = new URLSearchParams(location.search || '');
            var tidNow = sp1.get('thread_id') || (chatForm && chatForm.getAttribute('data-thread-id')) || null;
            if (tidNow && !_savedOnce) {
              _savedOnce = true;
              try { localStorage.setItem('cedar:lastProject', String(PROJECT_ID||'')); } catch(_){}
              try { localStorage.setItem('cedar:lastBranch', String(BRANCH_ID||'')); } catch(_){}
              try { localStorage.setItem('cedar:lastThread', String(tidNow||'')); } catch(_){}
            }
          } catch(_){ }
        }
        _saveAndAttachIfReady();
        setTimeout(_saveAndAttachIfReady, 700);
      } catch(_){}

      // Auto-start chat once after upload redirect so user sees processing in Chat
      try {
        if (UPLOAD_AUTOCHAT && !window.__uploadAutoChatStarted) {
          var sp = new URLSearchParams(location.search || '');
          var msg = (sp.get('msg')||'').replace(/\+/g,' ');
          var tid0 = sp.get('thread_id') || (chatForm && chatForm.getAttribute('data-thread-id')) || null;
          var fid0 = sp.get('file_id') || (chatForm && chatForm.getAttribute('data-file-id')) || null;
          var dsid0 = sp.get('dataset_id') || (chatForm && chatForm.getAttribute('data-dataset-id')) || null;
          if (msg === 'File uploaded' && (tid0 || fid0)) {
            window.__uploadAutoChatStarted = true;
            startWS('The user uploaded this file to the system', tid0, fid0, dsid0);
          }
        }
      } catch(_) {}

      // Auto-scroll behavior similar to modern chat apps: scroll to bottom on new messages unless user scrolled up
      function initAutoScroll(){
        try {
          var msgs = document.getElementById('msgs');
          if (!msgs) return;
          var userScrolledUp = false;
          msgs.addEventListener('scroll', function(){
            try {
              var delta = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight;
              userScrolledUp = delta > 80; // pixels from bottom
            } catch(_) {}
          });
          var obs = new MutationObserver(function(){
            try {
              if (!userScrolledUp) {
                if (msgs.lastElementChild && msgs.lastElementChild.scrollIntoView) {
                  msgs.lastElementChild.scrollIntoView({block:'end'});
                } else {
                  msgs.scrollTop = msgs.scrollHeight;
                }
              }
            } catch(_) {}
          });
          obs.observe(msgs, {childList:true});
        } catch(_) {}
      }
      initAutoScroll();

      if (chatForm) {
        chatForm.addEventListener('submit', async function(ev){
          try { ev.preventDefault(); } catch(_){ }
          var t = document.getElementById('chatInput');
          var text = (t && t.value || '').trim(); if (!text) return;
          var tid = chatForm.getAttribute('data-thread-id') || null;
          var fid = chatForm.getAttribute('data-file-id') || null;
          var dsid = chatForm.getAttribute('data-dataset-id') || null;
          // Start streaming immediately via WebSocket
          startWS(text, tid, fid, dsid); try { t.value=''; } catch(_){ }
        });
      }

      // Toggle details by clicking the bubble/content
      try {
        var msgsEl = document.getElementById('msgs');
        if (msgsEl) {
          msgsEl.addEventListener('click', function(ev){
            var root = ev.target && ev.target.closest ? ev.target.closest('.msg') : null;
            if (!root) return;
            var bubble = root.querySelector('.bubble[data-details-id]');
            if (!bubble) return;
            var did = bubble.getAttribute('data-details-id');
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
              // propagate human-readable file name when available
              try { f.setAttribute('data-file-name', (a.getAttribute('data-display-name')||'')); } catch(_){ }
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

      // Thread selection removed - using single chat interface

    } catch(_) {}
  }, { once: true });
})();
</script>
"""
    # Replace placeholders with actual IDs; avoid Python's % formatting which conflicts with '%' in CSS
    # Embed WS timeout budget (ms) for client watchdog
    try:
        _ws_timeout_s = int(os.getenv("CEDARPY_CHAT_TIMEOUT_SECONDS", "300"))
    except Exception:
        _ws_timeout_s = 300
    _ws_timeout_ms = max(1000, _ws_timeout_s * 1000)
    script_js = script_js.replace("__PID__", str(project.id)).replace("__BID__", str(current.id)).replace("__WS_TIMEOUT_MS__", str(_ws_timeout_ms))
    script_js = script_js.replace("__UPLOAD_AUTOCHAT__", "true" if UPLOAD_AUTOCHAT_ENABLED else "false")
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
              <a href="#" class="tab" data-target="left-notes">Notes</a>
            </div>
            <div class="tab-panels" style="flex:1; min-height:0">
              <div id="left-chat" class="panel">
                <h3>Chat <span id="chat-number-display" style="display:none">- <span id="chat-number"></span></span></h3>
                <style>
                /* Chat area grows to fill viewport; input stays at bottom regardless of window size */
                  #left-chat {{ display:flex; flex-direction:column; flex:1; min-height:0; }}
                  #left-chat .chat-log {{ flex:1; display:flex; flex-direction:column; gap:8px; overflow-y:auto; padding-bottom:80px; }}
                  #left-chat .chat-input {{ position: sticky; bottom: 0; margin-top:auto; padding-top:6px; background:#fff; border-top:1px solid var(--border); }}
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
                { ("<div class='card' style='margin-top:8px; padding:12px'><h3>File Details</h3>" + left_details + "</div>") if selected_file else "" }
                {code_details_html}
              </div>
              <div id="left-notes" class="panel hidden">
                {notes_panel_html}
              </div>
            </div>
          </div>

          <div class="pane right">
            <div class="tabs" data-pane="right">
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              {''}
              <a href="#" class="{('tab active' if not (selected_code or False) else 'tab')}" data-target="right-plan">Plan</a>
              <a href="#" class="tab" data-target="right-history">History</a>
              <a href="#" class="tab" data-target="right-files">Files</a>
              <a href="#" class="{('tab active' if (selected_code or False) else 'tab')}" data-target="right-code">Code</a>
              <a href=\"#\" class=\"tab\" data-target=\"right-upload\" data-testid=\"open-uploader\">Upload</a>
              <a href="#" class="tab" data-target="right-sql">SQL</a>
              <a href="#" class="tab" data-target="right-dbs">Databases</a>
            </div>
            <div class="tab-panels">
              <div id="right-plan" class="{('panel' if not (selected_code or False) else 'panel hidden')}">
                {plan_panel_html}
              </div>
              <div id="right-history" class="panel hidden">
                {history_panel_html}
              </div>
              <div id="right-files" class="panel">
                <div class="card" style="max-height:220px; overflow:auto; padding:12px">
                  <h3 style='margin-bottom:6px'>Files</h3>
                  {file_list_html}
                </div>
              </div>
              <div id="right-code" class="{('panel' if (selected_code or False) else 'panel hidden')}">
                <div class="card" style="max-height:220px; overflow:auto; padding:12px">
                  <h3 style='margin-bottom:6px'>Code</h3>
                  {code_list_html}
                </div>
              </div>
              <div id="right-upload" class="panel">
                <div class="card" style='padding:12px'>
                  <h3 style='margin-bottom:6px'>Upload</h3>
                  <form method="post" action="/project/{project.id}/files/upload?branch_id={current.id}" enctype="multipart/form-data" data-testid="upload-form">
                    <input type="file" name="file" required data-testid="upload-input" />
                    <div style="height:6px"></div>
                    <div style="height:6px"></div>
                    <button type="submit" data-testid="upload-submit">Upload</button>
                  </form>
                </div>
              </div>
              <div id="right-sql" class="panel hidden">
                {sql_card}
              </div>
              <div id="right-dbs" class="panel hidden">
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
      </div>
    </div>

    """

