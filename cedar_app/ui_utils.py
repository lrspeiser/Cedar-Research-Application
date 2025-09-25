"""
UI Utilities for Cedar
=======================

This module contains all UI-related utilities including:
- HTML layout generation
- Environment variable management for settings
- LLM status checking for UI display
- Client-side JavaScript generation
"""

import os
import time
import re
from typing import Optional, Dict
from fastapi.responses import HTMLResponse

from cedar_app.config import DATA_DIR
from main_helpers import escape

# Path to settings file
SETTINGS_PATH = os.path.join(DATA_DIR, ".env")

# Cached LLM reachability indicator for UI (TTL seconds)
_LLM_READY_CACHE = {"ts": 0.0, "ready": False, "reason": "init", "model": None}


def env_get(k: str) -> Optional[str]:
    """
    Get environment variable from env or settings file.
    
    Args:
        k: Environment variable name
        
    Returns:
        Value of the environment variable or None if not found
    """
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


def env_set_many(updates: Dict[str, str]) -> None:
    """
    Update ~/CedarPyData/.env with provided key=value pairs, preserving other lines.
    Keys are also set in-process via os.environ. We avoid printing secret values.
    See README: Settings and Postmortem #7 for details.
    
    Args:
        updates: Dictionary of environment variables to set
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


def llm_reachability(ttl_seconds: int = 300, llm_client_config_fn=None) -> tuple[bool, str, str]:
    """
    Best-effort reachability check for UI. Returns (ready, reason, model).
    Cached to avoid per-request network calls. Provides clearer reasons when unavailable.
    
    Args:
        ttl_seconds: Time to live for cache in seconds
        llm_client_config_fn: Function to get LLM client config (injected dependency)
        
    Returns:
        Tuple of (ready, reason, model)
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
        os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or 
        env_get("CEDARPY_OPENAI_API_KEY") or env_get("OPENAI_API_KEY")
    )
    
    # Get client config (use injected function or import default)
    if llm_client_config_fn:
        client, model = llm_client_config_fn()
    else:
        try:
            from cedar_app.llm_utils import llm_client_config
            client, model = llm_client_config()
        except Exception:
            client, model = None, None
    
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


def llm_reach_ok(llm_client_config_fn=None) -> bool:
    """Check if LLM is reachable."""
    try:
        ok, _, _ = llm_reachability(llm_client_config_fn=llm_client_config_fn)
        return bool(ok)
    except Exception:
        return False


def llm_reach_reason(llm_client_config_fn=None) -> str:
    """Get LLM reachability reason."""
    try:
        ok, reason, _ = llm_reachability(llm_client_config_fn=llm_client_config_fn)
        return "ok" if ok else (reason or "unknown")
    except Exception:
        return "unknown"


def is_trivial_math(msg: str) -> bool:
    """
    Helper to detect trivially simple arithmetic prompts. 
    Used only to enforce plan-first policy.
    We always use the LLM; this does not compute answers, only classifies trivial math.
    """
    try:
        s = (msg or "").strip().lower()
        return bool(re.match(r"^(what\s+is\s+)?(-?\d+)\s*([+\-*/x×])\s*(-?\d+)\s*\??$", s))
    except Exception:
        return False


def get_client_log_js() -> str:
    """
    Generate client-side logging JavaScript that posts console messages and errors to the server.
    See README.md (section "Client-side logging") for details and troubleshooting.
    """
    return """
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


def layout(title: str, body: str, header_label: Optional[str] = None, 
           header_link: Optional[str] = None, nav_query: Optional[str] = None,
           llm_client_config_fn=None) -> HTMLResponse:
    """
    Generate the main HTML layout for Cedar pages.
    
    Args:
        title: Page title
        body: HTML content for the page body
        header_label: Optional label for the header breadcrumb
        header_link: Optional link for the header breadcrumb
        nav_query: Optional query string to append to navigation links
        llm_client_config_fn: Optional function to get LLM client config
        
    Returns:
        HTMLResponse with the complete HTML page
    """
    # LLM status and model selector for header
    try:
        ready, reason, current_model = llm_reachability(llm_client_config_fn=llm_client_config_fn)
        available_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4o"]
        
        if ready:
            # Build model selector dropdown
            model_options = ""
            for m in available_models:
                selected = "selected" if m == current_model else ""
                model_options += f"<option value='{escape(m)}' {selected}>{escape(m)}</option>"
            
            llm_status = f"""
            <select id="modelSelector" onchange="changeModel(this.value)" 
                    style="padding: 3px 8px; border-radius: 999px; background: #eef2ff; color: #3730a3; 
                           font-size: 12px; border: 1px solid #c7d2fe; cursor: pointer;"
                    title="Select LLM model">
                {model_options}
            </select>
            <script>
            function changeModel(model) {{
                fetch('/api/model/change', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{model: model}})
                }}).then(function(r) {{
                    if (r.ok) {{
                        console.log('Model changed to ' + model);
                        // Optionally reload to reflect changes
                        setTimeout(function() {{ location.reload(); }}, 500);
                    }}
                }}).catch(function(e) {{
                    console.error('Failed to change model:', e);
                }});
            }}
            </script>
            """
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

    # Build right-side navigation with optional project context
    try:
        nav_qs = ("?" + nav_query.strip()) if (nav_query and nav_query.strip()) else ""
    except Exception:
        nav_qs = ""

    nav_html = (
        f"<a href='/'>&#8203;Projects</a> | "
        f"<a href='/agents'>Agents</a> | "
        f"<a href='/merge{nav_qs}'>Merge</a> | "
        f"<a href='/log{nav_qs}' target='_blank' rel='noopener'>Log</a> | "
        f"<a href='/settings'>Settings</a>"
    )

    # Client logging JavaScript
    client_log_js = get_client_log_js()

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
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji"; color: var(--fg); background: var(--bg); }}
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
      <div style="margin-left:auto">{nav_html}{llm_status}</div>
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