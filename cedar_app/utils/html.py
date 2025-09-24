"""
HTML utilities module for Cedar app.
Contains layout functions and HTML generation helpers.
"""

import os
import html
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from main_models import Project

def escape(s: str) -> str:
    """Escape HTML special characters."""
    return html.escape(s, quote=True)

def layout(title: str, body: str, header_label: Optional[str] = None, header_link: Optional[str] = None, nav_query: Optional[str] = None) -> HTMLResponse:  # type: ignore[override]
    # LLM status for header (simplified for refactoring)
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
        f"<a href='/log{nav_qs}' target='_blank' rel='noopener'>Log</a> | "
        f"<a href='/settings'>Settings</a>"
    )

    # Client logging hook (console/errors -> /api/client-log)
    client_log_js = """
<script>
(function(){
  if (window.__cedarpyClientLogInitialized) return; window.__cedarpyClientLogInitialized = true;
  const endpoint = '/api/client-log';
  // Lightweight pub/sub for client logs so chat UI can mirror logs under the Processing line
  window.__cedarLogSubscribers = window.__cedarLogSubscribers || [];
  window.__cedarLogBuffer = window.__cedarLogBuffer || [];
  function emitLog(payload){
    try {
      window.__cedarLogBuffer.push(payload);
      if (window.__cedarLogBuffer.length > 2000) { window.__cedarLogBuffer.shift(); }
      (window.__cedarLogSubscribers||[]).forEach(function(fn){ try { fn(payload); } catch(_){} });
    } catch(_) {}
  }
  window.subscribeCedarLogs = function(fn){ try { (window.__cedarLogSubscribers||[]).push(fn); } catch(_){} };
  window.unsubscribeCedarLogs = function(fn){ try { var a=window.__cedarLogSubscribers||[]; var i=a.indexOf(fn); if(i>=0) a.splice(i,1); } catch(_){} };

  function post(payload){
    try {
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], {type: 'application/json'});
        navigator.sendBeacon(endpoint, blob);
      } else {
        fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body, keepalive: true}).catch(function(){});
      }
    } catch(e) {}
  }
  function base(level, message, origin, extra){
    var pl = Object.assign({
      when: new Date().toISOString(),
      level: String(level||'info'),
      message: String(message||''),
      url: String(location.href||''),
      userAgent: navigator.userAgent || '',
      origin: origin || 'console'
    }, extra||{});
    post(pl);
    emitLog(pl);
  }
  var orig = { log: console.log, info: console.info, warn: console.warn, error: console.error };
  console.log = function(){ try { base('info', Array.from(arguments).join(' '), 'console.log'); } catch(e){}; return orig.log.apply(console, arguments); };
  console.info = function(){ try { base('info', Array.from(arguments).join(' '), 'console.info'); } catch(e){}; return orig.info.apply(console, arguments); };
  console.warn = function(){ try { base('warn', Array.from(arguments).join(' '), 'console.warn'); } catch(e){}; return orig.warn.apply(console, arguments); };
  console.error = function(){ try { base('error', Array.from(arguments).join(' '), 'console.error', { stack: (arguments && arguments[0] && arguments[0].stack) ? String(arguments[0].stack) : null }); } catch(e){}; return orig.error.apply(console, arguments); };
  window.addEventListener('error', function(ev){
    try { base('error', ev.message || 'window.onerror', 'window.onerror', { line: ev.lineno||null, column: ev.colno||null, stack: ev.error && ev.error.stack ? String(ev.error.stack) : null }); } catch(e){}
  }, true);
  window.addEventListener('unhandledrejection', function(ev){
    try { var r = ev && ev.reason; base('error', (r && (r.message || r.toString())) || 'unhandledrejection', 'unhandledrejection', { stack: r && r.stack ? String(r.stack) : null }); } catch(e){}
  });
  document.addEventListener('DOMContentLoaded', function(){ try { console.log('[ui] page ready'); } catch(e){} }, { once: true });
  // Auto-restore last thread on cold open of '/' (fresh launch). Bypass with ?home=1.
  try {
    if ((location.pathname === '/' || location.pathname === '') && document.referrer === '') {
      var _sp = new URLSearchParams(location.search || '');
      if (!_sp.has('home')) {
        var _lp = null, _lb = null, _lt = null;
        try { _lp = localStorage.getItem('cedar:lastProject'); } catch(_){}
        try { _lb = localStorage.getItem('cedar:lastBranch'); } catch(_){}
        try { _lt = localStorage.getItem('cedar:lastThread'); } catch(_){}
        if (_lp && _lb && _lt) {
          var _dest = '/project/' + encodeURIComponent(String(_lp)) + '?branch_id=' + encodeURIComponent(String(_lb)) + '&thread_id=' + encodeURIComponent(String(_lt));
          location.replace(_dest);
        }
      }
    }
  } catch(_){ }
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
    main {{ padding: 20px; margin: 0; width: 100%; }}
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
    .two-col {{ display: grid; grid-template-columns: 1fr 420px; gap: 16px; align-items: start; }}
    .pane {{ display: flex; flex-direction: column; gap: 8px; }}
    .pane.right {{ display:flex; flex-direction:column; min-height:0; }}
    .pane.right .tab-panels {{ display:flex; flex-direction:column; flex:1; min-height:0; overflow:auto; }}
    .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); }}
    .tab {{ display:inline-block; padding:6px 10px; border:1px solid var(--border); border-bottom:none; border-radius:6px 6px 0 0; background:#f3f4f6; color:#111; cursor:pointer; user-select:none; }}
    .tab.active {{ background:#fff; font-weight:600; }}
    .tab-panels {{ border:1px solid var(--border); border-radius:0 6px 6px 6px; background:#fff; padding:12px; }}
    .panel.hidden {{ display:none !important; }}
    @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
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
    try:
        html_doc = html_doc.format(llm_status=llm_status, header_info=header_html, nav_html=nav_html)
    except Exception:
        pass
    return HTMLResponse(html_doc)


def projects_list_html(projects: List[Any]) -> str:
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


