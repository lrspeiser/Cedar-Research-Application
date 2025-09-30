"""
JavaScript bundles for Cedar page rendering.

This module contains functions that generate JavaScript code for various
client-side features in the Cedar application.

Extracted from page_rendering.py as part of refactoring to keep files under 1000 lines.
"""

from typing import Optional
import os


def get_refresh_notes_script() -> str:
    """
    Generate JavaScript for handling refresh_notes URL parameter.
    
    Automatically switches to the Notes tab when refresh_notes=1 is present in URL.
    
    Returns:
        str: Complete <script> tag with JavaScript code
    """
    return """
<script>
(function() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('refresh_notes') === '1') {
    // Remove the refresh_notes parameter from URL
    urlParams.delete('refresh_notes');
    const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '') + window.location.hash;
    window.history.replaceState({}, '', newUrl);
    
    // Switch to Notes tab after page load
    window.addEventListener('DOMContentLoaded', function() {
      setTimeout(function() {
        const notesTab = document.querySelector('.tab[data-target="main-notes"]');
        if (notesTab) notesTab.click();
      }, 100);
    });
  }
})();
</script>
    """


def get_code_to_chat_script() -> str:
    """
    Generate JavaScript for code-to-chat functionality.
    
    Handles clicking code snippets to open them in chat with full context.
    Includes base64 decoding and code injection features.
    
    Returns:
        str: Complete <script> tag with JavaScript code
    """
    return """
<script>
(function(){
  var LOGP='[Code→Chat]';
  function b64utf8(b){
    try{
      var bytes = Uint8Array.from(atob(b||''), function(c){ return c.charCodeAt(0); });
      try { return new TextDecoder('utf-8').decode(bytes); } catch(e){
        var s=''; for (var i=0;i<bytes.length;i++){ s += String.fromCharCode(bytes[i]); } return s;
      }
    }catch(e){ return ''; }
  }
  function switchToChatTab(){
    try{ var chatTab = document.querySelector('.tabs .tab[data-target="main-chat"]'); if (chatTab) { chatTab.click(); return true; } } catch(_){}
    return false;
  }
  function renderCodeContextPanel(ds){
    try{
      var chatPanel = document.getElementById('main-chat');
      var msgs = document.getElementById('msgs');
      if (!chatPanel || !msgs) return;
      var panel = document.getElementById('code-context-panel');
      if (!panel){
        panel = document.createElement('div');
        panel.id = 'code-context-panel';
        panel.className = 'card';
        panel.style.marginBottom = '12px';
        panel.style.padding = '12px';
        panel.style.background = '#f8fafc';
        panel.style.borderRadius = '8px';
        msgs.parentNode.insertBefore(panel, msgs);
      }
      panel.innerHTML='';
      var h = document.createElement('h3'); h.textContent='Code Context'; panel.appendChild(h);
      var tbl = document.createElement('table'); tbl.className='table';
      var tbody = document.createElement('tbody');
      [
        ['Title', ds.title||''],
        ['Language', ds.language||''],
        ['Created', ds.created_at||''],
        ['Thread', ds.thread_title||''],
        ['mid', String(ds.mid||'')],
        ['idx', String(ds.idx||'')]
      ].forEach(function(kv){ var tr=document.createElement('tr'); var th=document.createElement('th'); th.textContent=kv[0]; var td=document.createElement('td'); td.textContent=kv[1]; tr.appendChild(th); tr.appendChild(td); tbody.appendChild(tr); });
      tbl.appendChild(tbody); panel.appendChild(tbl);
      var pre = document.createElement('pre'); pre.className='small'; pre.style.whiteSpace='pre-wrap'; pre.style.background='#f1f5f9'; pre.style.padding='8px'; pre.style.borderRadius='6px'; pre.style.maxHeight='260px'; pre.style.overflow='auto'; pre.textContent = ds.code_preview || ''; panel.appendChild(pre);
      if ((ds.code_full||'') !== (ds.code_preview||'')) { var btn=document.createElement('button'); btn.className='secondary'; btn.textContent='Show full code'; btn.style.marginTop='6px'; btn.addEventListener('click', function(){ try{ pre.textContent=ds.code_full||''; btn.remove(); }catch(_){}}); panel.appendChild(btn); }
    }catch(e){ try{ console.debug(LOGP,'render error',e); }catch(_){} }
  }
  window.__codeCtx = window.__codeCtx || { active:false, language:'text', fullCode:'' };
  document.addEventListener('click', function(ev){
    var a = ev.target && ev.target.closest ? ev.target.closest('a.js-open-code-chat') : null; if (!a) return;
    try { ev.preventDefault(); } catch(_){}
    try{
      var ds = a.dataset || {};
      var title = ds.title || '';
      var language = ds.language || 'text';
      var codePreview = b64utf8(ds.codePreviewB64 || '');
      var codeFull = b64utf8(ds.codeB64 || '');
      var createdAt = ds.createdAt || '';
      var threadTitle = ds.threadTitle || '';
      var mid = ds.mid || '';
      var idx = ds.idx || '';
      switchToChatTab();
      try { if (window.startNewChat) window.startNewChat(PROJECT_ID, BRANCH_ID); } catch(_){ }
      renderCodeContextPanel({ title:title, language:language, created_at:createdAt, thread_title:threadTitle, mid:mid, idx:idx, code_preview:codePreview, code_full:codeFull });
      var t = document.getElementById('chatInput');
      if (t) {
        var template = 'Code Context\\n' +
                       'title: ' + title + '\\n' +
                       'language: ' + language + '\\n' +
                       'created_at: ' + createdAt + '\\n' +
                       'thread_title: ' + threadTitle + '\\n' +
                       'mid: ' + mid + '\\n' +
                       'idx: ' + idx + '\\n\\n' +
                       '```' + language + '\\n' + codePreview + '\\n' + '```\\n\\n' +
                       '---\\n\\n' +
                       'Prompt:\\n';
        t.value = template; try { t.focus(); } catch(_){}
      }
      window.__codeCtx.active = true; window.__codeCtx.language = language || 'text'; window.__codeCtx.fullCode = codeFull || '';
    }catch(e){ try{ console.debug(LOGP,'click error',e); }catch(_){} }
  }, true);
  document.addEventListener('submit', function(ev){
    var form = ev.target && ev.target.closest ? ev.target.closest('#chatForm') : null; if (!form) return;
    try{
      if (window.__codeCtx && window.__codeCtx.active){
        var t = document.getElementById('chatInput'); if (t){
          var txt = String(t.value||''); var lang = window.__codeCtx.language || 'text'; var full = window.__codeCtx.fullCode || '';
          if (full){ var re = /```([a-zA-Z0-9_-]*)[\\s\\S]*?```/; var rep = '```' + lang + '\\n' + full + '\\n```'; if (re.test(txt)) { txt = txt.replace(re, rep); } else { txt += '\\n\\n' + rep + '\\n'; } t.value = txt; }
        }
        window.__codeCtx.active = false;
      }
    }catch(e){ try{ console.debug(LOGP,'submit error',e); }catch(_){} }
  }, true);
})();
</script>
    """


def get_main_chat_script(
    project_id: int,
    branch_id: int,
    upload_autochat_enabled: bool,
    ws_timeout_ms: int,
    initial_upload_message: str,
    file_details_json: str
) -> str:
    """
    Generate the main WebSocket chat script.
    
    This is the primary client-side JavaScript for handling chat functionality including:
    - WebSocket connection management
    - Message streaming
    - Agent result display
    - File upload auto-chat
    - Chat history management
    - Thread creation and management
    
    Args:
        project_id: Current project ID
        branch_id: Current branch ID
        upload_autochat_enabled: Whether to auto-start chat after file upload
        ws_timeout_ms: WebSocket timeout in milliseconds
        initial_upload_message: Message to send for upload auto-chat
        file_details_json: JSON string of file details for upload context
        
    Returns:
        str: Complete <script> tag with main chat JavaScript
        
    Note:
        This script contains placeholder variables that are replaced with actual values:
        - PROJECT_ID, BRANCH_ID: For API calls
        - UPLOAD_AUTOCHAT: Boolean flag
        - __WS_TIMEOUT_MS__: Timeout value
        - __INITIAL_UPLOAD_USER_MESSAGE__: Upload message
        - __FILE_DETAILS_JSON__: File metadata
    """
    # Read the main script template from the original location
    # For now, we'll inline it but this could be moved to a separate .js file
    script_template = """
<script>
(function(){
  // Initial auto-chat message for uploads (injected from server as a string)
  var PROJECT_ID = __PID__;
  var BRANCH_ID = __BID__;
  var UPLOAD_AUTOCHAT = __UPLOAD_AUTOCHAT__;
  var SSE_ACTIVE = false;
  // File details JSON injected by server for upload auto-chat (stringified JSON)
  var FILE_DETAILS_JSON = __FILE_DETAILS_JSON__;
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
"""
    
    # Note: The full script is extremely long (~1300 lines)
    # For the initial refactoring, I'm creating a stub that references the original
    # A complete extraction would continue here with the full startWS function and all handlers
    # This requires careful line-by-line extraction which I'll do in a separate commit
    
    raise NotImplementedError(
        "get_main_chat_script is a stub. The full ~1300-line WebSocket script needs to be "
        "extracted carefully from page_rendering.py lines 713-2064. "
        "This is being left for a separate, focused commit to avoid breaking chat functionality."
    )