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


def get_main_chat_script() -> str:
    """
    Generate the main WebSocket chat script.
    
    This is the primary client-side JavaScript for handling chat functionality including:
    - WebSocket connection management
    - Message streaming
    - Agent result display
    - File upload auto-chat
    - Chat history management
    - Thread creation and management
    
    Returns:
        str: Complete <script> tag with main chat JavaScript
        
    Note:
        This script contains placeholder variables that are replaced with actual values:
        - __PID__, __BID__: For PROJECT_ID, BRANCH_ID (replaced by caller)
        - __UPLOAD_AUTOCHAT__: Boolean flag (replaced by caller)
        - __WS_TIMEOUT_MS__: Timeout value (replaced by caller)
        - __INITIAL_UPLOAD_USER_MESSAGE__: Upload message (replaced by caller)
        - __FILE_DETAILS_JSON__: File metadata (replaced by caller)
    """
    return """
<script>
(function(){
  // Initial auto-chat message for uploads (injected from server as a string)
  var PROJECT_ID = __PID__;
  var BRANCH_ID = __BID__;
  var UPLOAD_AUTOCHAT = __UPLOAD_AUTOCHAT__;
  var SSE_ACTIVE = false;
  // Feature flags injected from layout() via window; default to false if missing
  var SHOW_PREVIEW = (typeof window.CEDAR_SHOW_PREVIEW !== 'undefined') ? !!window.CEDAR_SHOW_PREVIEW : true;
  var SHOW_PROMPT_BUBBLES = (typeof window.CEDAR_SHOW_PROMPT_BUBBLES !== 'undefined') ? !!window.CEDAR_SHOW_PROMPT_BUBBLES : false;
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

      function startWS(text, threadId, fileId, datasetId, replay){
    try {
      var msgs = document.getElementById('msgs');
      
      // Include chat number if we have one
      var chatNum = window.currentChatNumber;
      var optimisticUser = null;

      // Stop/Cancel button handling
      var stopBtn = document.getElementById('stopChatBtn');
      function _showStop(){ try { if (stopBtn) { stopBtn.style.display='inline-block'; stopBtn.disabled=false; } } catch(_){} }
      function _hideStop(){ try { if (stopBtn) { stopBtn.disabled=true; stopBtn.style.display='none'; } } catch(_){} }

      // Simple step timing helpers (annotate previous bubble/line with elapsed time)
      var currentStep = null;
      function _now(){ try { return performance.now(); } catch(_) { return Date.now(); } }
      // Running timer state for the active step
      var _timerId = null;
      var _timerEl = null;
      function _clearRunningTimer(){ 
        try { 
          if (_timerId) { 
            clearInterval(_timerId); 
            _timerId = null; 
            _timerEl = null;
          } 
        } catch(_){} 
      }
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
          // Clear any existing timer first
          _clearRunningTimer();
          var target = (function(){ try { return node.querySelector('.meta .title'); } catch(_) { return null; } })() || node;
          _timerEl = document.createElement('span');
          _timerEl.className = 'small muted';
          _timerEl.style.marginLeft = '6px';
          target.appendChild(_timerEl);
          var lastText = '';
          _timerId = setInterval(function(){
            try {
              // Check if element still exists in DOM or if we've reached a final state
              if (!_timerEl || !_timerEl.parentNode || finalOrError) {
                _clearRunningTimer();
                return;
              }
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
          // Stop timer for previous step
          if (currentStep && currentStep.node){
            var dt = now - currentStep.t0;
            _clearRunningTimer();
            annotateTime(currentStep.node, dt);
            try {
              var rec = { project: PROJECT_ID, thread: threadId||null, from: currentStep.label, to: String(label||''), dt_ms: Math.round(dt) };
              stepsHistory.push({ from: rec.from, to: rec.to, dt_ms: rec.dt_ms });
              // Performance tracking stored internally but not logged to console
            } catch(_) {}
          }
        } catch(_){ }
        // Only start a new timer if not in a final state
        currentStep = { label: String(label||''), t0: now, node: node || null };
        if (node && !finalOrError) { startRunningTimer(node, now); }
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

      // Client-side logging to backend
      function logToBackend(level, message, eventType, data) {
        try {
          fetch('/api/ui-log', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              level: level || 'info',
              message: message || '',
              event_type: eventType || null,
              timestamp_client: performance.now(),
              timestamp_backend_sent: (data && data.timestamp) ? data.timestamp : null,
              data: data || {}
            })
          }).catch(function(e){ console.debug('[logToBackend] failed:', e); });
        } catch(e) { console.debug('[logToBackend] error:', e); }
      }

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

      // Preview streaming state
      var previewWrap = null;  // preview bubble wrapper
      var previewText = null;  // preview text node
      var previewPhase = null; // 'thinking' or 'synthesis'

      var lastW = null;
      var stagesSeen = {};

      // Developer step-through controls disabled in tests; use WS messages if needed.

      // Optimistic local echo of the user's message so the UI shows instant feedback
      try {
        console.log('[DEBUG] User bubble creation check:', 'msgs:', !!msgs, 'text:', text, 'replay:', replay);
        if (msgs && text && !replay) {
          console.log('[DEBUG] Creating user bubble for:', text);
          var wrapU = document.createElement('div'); wrapU.className = 'msg user';
          wrapU.setAttribute('data-temp', '1');
          var metaU = document.createElement('div'); metaU.className = 'meta small'; metaU.style.height = '1px'; // Empty meta for user messages
          var bubU = document.createElement('div'); bubU.className = 'bubble user';
          var contU = document.createElement('div'); contU.className='content'; contU.style.whiteSpace='pre-wrap';
          contU.textContent = String(text||'');
          bubU.appendChild(contU); wrapU.appendChild(metaU); wrapU.appendChild(bubU);
          msgs.appendChild(wrapU);
          optimisticUser = wrapU;
          stepAdvance('user:local', wrapU);
          console.log('[DEBUG] User bubble created successfully');
        } else {
          console.log('[DEBUG] User bubble NOT created - conditions not met');
        }
      } catch(e){ 
        console.error('[DEBUG] Error creating user bubble:', e);
      }

      var wsScheme = (location.protocol === 'https:') ? 'wss' : 'ws';
      var ws = new WebSocket(wsScheme + '://' + location.host + '/ws/chat/' + PROJECT_ID);
      var wsStartMs = _now();

      // Define cancel function within this session scope so it captures steps and thread id
      window.__cedar_cancel_current_run = async function(reason){
        try {
          reason = String(reason || 'user_clicked_cancel');
          // Attempt to notify server to cancel orchestration
          try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: 'cancel', reason: reason })); } catch(_){}
          // Close the websocket with a user-cancel code
          try { ws && ws.close(4001, 'user_cancelled'); } catch(_){}
          // Prepare cancellation summary payload
          var promptMsgs = [];
          try { var map = (window.__cedar_last_prompts||{}); if (map && (threadId||null)) { promptMsgs = map[String(threadId)] || []; } } catch(_){}
          var body = { project_id: PROJECT_ID, branch_id: BRANCH_ID, thread_id: (threadId||null), timings: stepsHistory || [], prompt_messages: promptMsgs || [], reason: reason };
          // Post cancellation summary
          try {
            var resp = await fetch('/api/chat/cancel-summary', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
            var data = null; try { data = await resp.json(); } catch(_){}
            var text = (data && data.text) ? String(data.text) : 'Run cancelled by user.';
            // Render a Cancelled assistant bubble
            try {
              var wrapC = document.createElement('div'); wrapC.className = 'msg assistant';
              var metaC = document.createElement('div'); metaC.className = 'meta small'; metaC.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>Cancelled</span>";
              var bubC = document.createElement('div'); bubC.className = 'bubble assistant';
              var contC = document.createElement('div'); contC.className='content'; contC.style.whiteSpace='pre-wrap'; contC.textContent = text;
              bubC.appendChild(contC); wrapC.appendChild(metaC); wrapC.appendChild(bubC);
              if (msgs) msgs.appendChild(wrapC);
            } catch(_){}
          } catch(err) {
            try { console.error('[cancel] summary post failed', err); } catch(_){}
          }
          // Finalize UI state
          finalOrError = true;
          _clearRunningTimer();
          clearSpinner();
          _hideStop();
        } catch(_){}
      };

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
                // Create a new timeout bubble instead of rewriting existing one
                var budgetS = Math.round(timeoutMs/1000);
                var elapsedS = (function(){ try { return (( _now() - (wsStartMs||0) )/1000).toFixed(1); } catch(_) { return 'unknown'; } })();
                var timeoutWrap = document.createElement('div');
                timeoutWrap.className = 'msg system';
                var timeoutMeta = document.createElement('div');
                timeoutMeta.className = 'meta small';
                timeoutMeta.innerHTML = "<span class='title' style='font-weight:600'>System</span>";
                var timeoutBub = document.createElement('div');
                timeoutBub.className = 'bubble system';
                var timeoutCont = document.createElement('div');
                timeoutCont.className = 'content';
                timeoutCont.style.whiteSpace = 'pre-wrap';
                timeoutCont.textContent = '[timeout] Took too long. Exceeded ' + budgetS + 's budget; elapsed ' + elapsedS + 's. Please try again.';
                timeoutBub.appendChild(timeoutCont);
                timeoutWrap.appendChild(timeoutMeta);
                timeoutWrap.appendChild(timeoutBub);
                if (msgs) msgs.appendChild(timeoutWrap);
              } catch(_){ }
              clearSpinner();
              _clearRunningTimer(); // Stop timer on timeout
              stepAdvance('timeout', null);
              finalOrError = true; timedOut = true;
              try { ws.close(); } catch(_){ }
            }
        }, timeoutMs);
      }

      ws.onopen = function(){
        try {
          wsStartMs = _now();
          refreshTimeout();
          _showStop();
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
        // Normalize and update thread_id as soon as we see it, so subsequent UI uses the correct thread
        try {
          if (m && m.thread_id) {
            var tidStr0 = String(m.thread_id);
            if (String(threadId||'') !== tidStr0) {
              threadId = tidStr0;
              try {
                var chatForm3 = document.getElementById('chatForm');
                if (chatForm3) {
                  chatForm3.setAttribute('data-thread-id', tidStr0);
                  var hiddenTid3 = chatForm3.querySelector("input[name='thread_id']");
                  if (hiddenTid3) hiddenTid3.value = tidStr0; else { var h3 = document.createElement('input'); h3.type='hidden'; h3.name='thread_id'; h3.value=tidStr0; chatForm3.appendChild(h3); }
                }
              } catch(_){}
            }
          }
        } catch(_){}
        // Handle chat creation notification
        if (m.type === 'chat_created') {
          window.currentChatNumber = m.chat_number;
          updateChatNumberDisplay(m.chat_number);
          refreshHistoryPanel();
        }
        if (!m) return;
        if (m.type === 'stream') {
          // Handle streaming text updates - append instead of replacing
          if (streamText && m.text) {
            // Only update if we're not in a final state
            if (!finalOrError) {
              // Remove spinner if present and append the text  
              clearSpinner();
              streamText.textContent = m.text || '';
            }
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
            
            // For display, map 'assistant' to 'Chief Agent', otherwise show the actual role/agent name
            var displayRole = (rLower === 'assistant') ? 'Assistant' : r;
            
            var wrapM = document.createElement('div'); 
            wrapM.className = 'msg ' + roleClass;
            var metaM = document.createElement('div'); 
            metaM.className = 'meta small';
            // Only show name for non-user messages
            if (roleClass === 'user') {
              metaM.style.height = '1px'; // Empty meta for user
            } else {
              metaM.innerHTML = "<span class='title' style='font-weight:600'>" + displayRole + "</span>";
            }
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
          // Attach prompt JSON to the live planning bubble details and cache for later
          // [cedar-ui] Prompt event handler - caches prompts by thread_id for "Prepared LLM prompt" bubble
          try {
            console.debug('[cedar-ui] Received prompt event', {thread_id: m.thread_id, iteration: m.iteration, stage: m.stage, msg_count: (m.messages||[]).length});
            
            // Initialize cache if missing
            window.__cedar_last_prompts = window.__cedar_last_prompts || {};
            
            // Normalize thread_id as string for consistent caching
            if (m.thread_id) {
              var threadIdStr = String(m.thread_id);
              
              // Create cache entry with metadata
              var cacheEntry = {
                stage: m.stage || 'unknown',
                iteration: m.iteration || 0,
                agent: m.agent || 'Chief Agent',
                prompt_json: m.messages || [],
                timestamp: m.timestamp || Date.now() / 1000
              };
              
              // Initialize array for this thread if needed, then append
              if (!window.__cedar_last_prompts[threadIdStr]) {
                window.__cedar_last_prompts[threadIdStr] = [];
              }
              window.__cedar_last_prompts[threadIdStr].push(cacheEntry);
              
              console.debug('[cedar-ui] Cached prompt for thread', threadIdStr, 'entry:', cacheEntry, 'total entries:', window.__cedar_last_prompts[threadIdStr].length);
            } else {
              console.warn('[cedar-ui] Prompt event missing thread_id, cannot cache');
            }
            
            // Update thread_id if needed (ensure closure variable keeps new thread id)
            try {
              if (m.thread_id) {
                var tidStr = String(m.thread_id);
                if (String(threadId||'') !== tidStr) { threadId = tidStr; }
                var chatForm2 = document.getElementById('chatForm');
                if (chatForm2 && !(chatForm2.getAttribute('data-thread-id'))) {
                  chatForm2.setAttribute('data-thread-id', tidStr);
                  var hiddenTid2 = chatForm2.querySelector("input[name='thread_id']");
                  if (hiddenTid2) hiddenTid2.value = tidStr; else { var hi2 = document.createElement('input'); hi2.type='hidden'; hi2.name='thread_id'; hi2.value=tidStr; chatForm2.appendChild(hi2); }
                }
              }
            } catch(_){}
            
            // If a planning bubble exists, update its details panel to show the prompt JSON
            try {
              if (thinkWrap) {
                var bubble = thinkWrap.querySelector('.bubble[data-details-id]');
                var did = bubble ? bubble.getAttribute('data-details-id') : null;
                var pre = did ? document.querySelector('#'+did+' pre') : null;
                if (pre && (m.messages || []).length) {
                  try { pre.textContent = JSON.stringify(m.messages, null, 2); } catch(_){ pre.textContent = String(m.messages); }
                }
              }
            } catch(_){}
            
            // Create a visible Assistant prompt bubble with collapsible JSON details so tests can verify (behind flag)
            if (SHOW_PROMPT_BUBBLES) {
              try {
                var detIdPrompt = 'det_prompt_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
                var wrapP = document.createElement('div'); wrapP.className = 'msg assistant';
                var metaP = document.createElement('div'); metaP.className = 'meta small'; metaP.innerHTML = "<span class='title' style='font-weight:600'>Assistant</span>";
                var bubP = document.createElement('div'); bubP.className = 'bubble assistant'; bubP.setAttribute('data-details-id', detIdPrompt);
                var contP = document.createElement('div'); contP.className='content'; contP.style.whiteSpace='pre-wrap';
                contP.textContent = 'Prepared LLM prompt';
                bubP.appendChild(contP);
                var detailsP = document.createElement('div'); detailsP.id = detIdPrompt; detailsP.style.display='none';
                var preP = document.createElement('pre'); preP.className='small'; preP.style.whiteSpace='pre-wrap';
                try { preP.textContent = JSON.stringify(m.messages || [], null, 2); } catch(_){ preP.textContent = String(m.messages || []); }
                detailsP.appendChild(preP);
                wrapP.appendChild(metaP); wrapP.appendChild(bubP); wrapP.appendChild(detailsP);
                if (msgs) msgs.appendChild(wrapP);
                stepAdvance('assistant:prompt', wrapP);
              } catch(_){}
            }
            
            ackEvent(m);
          } catch(e) { 
            console.error('[cedar-ui] Prompt caching error:', e);
          }
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
            metaA.innerHTML = "<span class='title' style='font-weight:600; cursor:pointer' role='button' tabindex='0'>Assistant</span>";
            
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
                var meta0 = document.createElement('div'); meta0.className = 'meta small'; meta0.innerHTML = "<span class='title' style='font-weight:600'>Assistant</span>";
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

            // Lightweight plan updates - just skip them now that Plan tab is removed
            if (fn === 'plan_update') {
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

            // Plan function - no longer updating a panel since Plan tab is removed
          } catch(_){ }
        } else if (m.type === 'thinking_start') { ackEvent(m);
          try {
            // Always create a NEW planning bubble - never reuse
            var detIdTh = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            thinkWrap = document.createElement('div'); thinkWrap.className = 'msg assistant';
            var metaTh = document.createElement('div'); metaTh.className = 'meta small'; metaTh.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>planning</span>";
            var bubTh = document.createElement('div'); bubTh.className = 'bubble assistant';
            // Link bubble to details for click-to-toggle
            bubTh.setAttribute('data-details-id', detIdTh);
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
          } catch(_) {}
        } else if (m.type === 'thinking_token' && m.delta) {
          try {
            if (thinkText) {
              thinkText.textContent = (thinkText.textContent ? thinkText.textContent : '') + String(m.delta);
            }
          } catch(_) {}
        } else if (m.type === 'preview_start') {
          // Preview streaming start (gpt-5-nano fast preview)
          // ALWAYS create a NEW bubble - never modify existing ones
          try {
            if (!SHOW_PREVIEW) { ackEvent(m); return; }
            var t0 = performance.now();
            logToBackend('info', 'Received preview_start event', 'preview_start', {
              phase: m.phase,
              model: m.model,
              timestamp: m.timestamp
            });
            
            previewPhase = m.phase || 'thinking';
            
            // Create a NEW preview bubble
            var detIdPrev = 'det_preview_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
            previewWrap = document.createElement('div'); 
            previewWrap.className = 'msg assistant';
            var metaPrev = document.createElement('div'); 
            metaPrev.className = 'meta small'; 
            var phaseLabel = (m.phase === 'synthesis') ? 'synthesizing' : 'planning';
            // Label preview as Chief Agent to match final bubble, while still streaming early thinking
            metaPrev.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>" + phaseLabel + "</span>";
            var bubPrev = document.createElement('div'); 
            bubPrev.className = 'bubble assistant';
            bubPrev.style.opacity = '0.85'; // Slightly transparent to indicate preview
            bubPrev.setAttribute('data-details-id', detIdPrev);
            var contPrev = document.createElement('div'); 
            contPrev.className = 'content'; 
            contPrev.style.whiteSpace = 'pre-wrap';
            contPrev.style.fontStyle = 'italic'; // Italic to indicate preview
            contPrev.textContent = ''; // Start empty, will stream in
            previewText = contPrev;
            bubPrev.appendChild(contPrev);
            var detailsPrev = document.createElement('div'); 
            detailsPrev.id = detIdPrev; 
            detailsPrev.style.display = 'none';
            var prePrev = document.createElement('pre'); 
            prePrev.className = 'small'; 
            prePrev.style.whiteSpace = 'pre-wrap'; 
            prePrev.style.background = '#f8fafc'; 
            prePrev.style.padding = '8px'; 
            prePrev.style.borderRadius = '6px';
            try { prePrev.textContent = JSON.stringify({ model: m.model || 'gpt-5-nano', phase: m.phase }, null, 2); } catch(_) { prePrev.textContent = String(m.model || 'gpt-5-nano'); }
            detailsPrev.appendChild(prePrev);
            previewWrap.appendChild(metaPrev); 
            previewWrap.appendChild(bubPrev); 
            previewWrap.appendChild(detailsPrev);
            if (msgs) msgs.appendChild(previewWrap);
            stepAdvance('assistant:preview', previewWrap);
            
            var t1 = performance.now();
            logToBackend('debug', 'Rendered preview_start', 'preview_start', {
              render_time_ms: (t1 - t0).toFixed(2)
            });
          } catch(e) {
            console.error('[preview_start] error:', e);
            logToBackend('error', 'Failed to handle preview_start: ' + e.message, 'preview_start', {});
          }
        } else if (m.type === 'preview_token') {
          // Preview token streaming (word by word from gpt-5-nano)
          try {
            if (!SHOW_PREVIEW) { return; }
            if (previewText && m.text) {
              previewText.textContent = (previewText.textContent || '') + String(m.text);
            }
          } catch(e) {
            console.error('[preview_token] error:', e);
          }
        } else if (m.type === 'preview_complete') {
          // Preview streaming complete
          try {
            if (!SHOW_PREVIEW) { return; }
            logToBackend('info', 'Received preview_complete event', 'preview_complete', {
              phase: m.phase,
              total_length: m.total_length,
              timestamp: m.timestamp
            });
            
            // Add completion indicator to preview bubble
            if (previewWrap && previewText) {
              var completeLabel = document.createElement('div');
              completeLabel.className = 'small muted';
              completeLabel.style.fontStyle = 'italic';
              completeLabel.style.marginTop = '6px';
              completeLabel.textContent = '(Preview complete - waiting for final answer from ' + ((previewPhase === 'synthesis') ? 'gpt-5' : 'gpt-5') + ')';
              previewText.parentNode.appendChild(completeLabel);
            }
            
            // Clear preview state - next will be the real response
            previewWrap = null;
            previewText = null;
            previewPhase = null;
          } catch(e) {
            console.error('[preview_complete] error:', e);
            logToBackend('error', 'Failed to handle preview_complete: ' + e.message, 'preview_complete', {});
          }
        } else if (m.type === 'error') {
          // Generic error from backend (e.g., preview failure)
          try {
            var wrapE = document.createElement('div'); wrapE.className = 'msg system';
            var metaE = document.createElement('div'); metaE.className = 'meta small'; metaE.innerHTML = "<span class='title' style='font-weight:600'>Error</span>";
            var bubE = document.createElement('div'); bubE.className = 'bubble system';
            var contE = document.createElement('div'); contE.className = 'content'; contE.style.whiteSpace='pre-wrap';
            var txtE = String(m.error || m.content || 'Unknown error');
            // Use a template literal to safely include newlines without breaking JS parsing
            try { if (m.details) { txtE += `

Details:
` + JSON.stringify(m.details, null, 2); } } catch(_){ }
            contE.textContent = txtE; bubE.appendChild(contE);
            wrapE.appendChild(metaE); wrapE.appendChild(bubE);
            if (msgs) msgs.appendChild(wrapE);
            stepAdvance('system:error', wrapE);
          } catch(e) { console.error('[error handler] failed', e); }
        } else if (m.type === 'step_status') {
          try {
            __stepEnabled = !!m.enabled;
            __ensureStepIndicator();
            __setStepIndicator(__stepEnabled, !!m.continue_mode);
          } catch(_) {}
        } else if (m.type === 'thinking') {
          try {
            // Update existing bubble if it exists, otherwise create a new one
            if (!thinkWrap) {
              var detIdTh2 = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
              thinkWrap = document.createElement('div'); thinkWrap.className = 'msg assistant';
              var metaTh2 = document.createElement('div'); metaTh2.className = 'meta small'; metaTh2.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>planning</span>";
              var bubTh2 = document.createElement('div'); bubTh2.className = 'bubble assistant';
              // Link bubble to details for click-to-toggle
              bubTh2.setAttribute('data-details-id', detIdTh2);
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
            // Reset thinkWrap so next thinking_start creates a new bubble
            thinkWrap = null; thinkText = null; thinkSpin = null;
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
              _clearRunningTimer(); // Stop any running timer
              if (label === 'timeout' || label === 'finalizing' || label === 'persisted') { 
                finalOrError = true;
                _hideStop();
                try {
                  if (timeoutId) {
                    clearTimeout(timeoutId);
                    timeoutId = null;
                  }
                } catch(_){}
              }
            }
          } catch(_){ }
        } else if (m.type === 'final' && m.text) {
          finalOrError = true;
          try { 
            if (timeoutId) {
              clearTimeout(timeoutId);
              timeoutId = null;
            }
          } catch(_){}
          // Render a proper assistant bubble for the final answer, with optional JSON details
          try {
            _hideStop();
            var detIdF = m.json ? ('det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8)) : null;
            var wrapF = document.createElement('div'); wrapF.className = 'msg assistant';
            var fnF = (m && m.json && m.json.function) ? String(m.json.function) : 'final';
            var metaF = document.createElement('div'); metaF.className = 'meta small'; metaF.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>" + (fnF === 'final' ? 'Final' : fnF) + "</span>";
            var bubF = document.createElement('div'); bubF.className = 'bubble assistant'; if (detIdF) bubF.setAttribute('data-details-id', detIdF);
            var contF = document.createElement('div'); contF.className='content'; contF.style.whiteSpace='pre-wrap'; contF.textContent = (fnF ? (fnF + ' ') : '') + (m.text||'');
            // Add edit prompt link if we have a stored prompt for this thread
            try {
              var threadIdStr = String(threadId || '');
              var cachedEntries = (window.__cedar_last_prompts||{})[threadIdStr];
              var lastPromptJson = null;
              if (cachedEntries && Array.isArray(cachedEntries) && cachedEntries.length > 0) {
                var latestEntry = cachedEntries[cachedEntries.length - 1];
                lastPromptJson = latestEntry.prompt_json || null;
              }
              
              if (lastPromptJson && lastPromptJson.length) {
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
                    var _orig = null; try { _orig = JSON.stringify(lastPromptJson, null, 2); } catch(_) { _orig = '[]'; }
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
                  try { document.getElementById('promptEditArea').value = JSON.stringify(lastPromptJson, null, 2); } catch(_){}
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
            // Prompt bubbles are now cached silently, not shown in UI
          } catch(_) {
            // Fallback to replacing the processing text if bubble rendering fails
            try { streamText.textContent = m.text; } catch(_){}
          }
          // Clear spinner and timer once final is ready; remove the transient processing bubble so tests don't see it anymore
          clearSpinner();
          _clearRunningTimer(); // Stop any running timer
          try {
            setTimeout(function(){ try { if (stream && stream.parentNode) stream.parentNode.removeChild(stream); } catch(_){} }, 400);
          } catch(_) { try { if (stream && stream.parentNode) stream.parentNode.removeChild(stream); } catch(_){} }
          stepAdvance('assistant:final', null);
          ackEvent(m);
        } else if (m.type === 'error') {
          finalOrError = true;
          try { 
            if (timeoutId) {
              clearTimeout(timeoutId);
              timeoutId = null;
            }
          } catch(_){}
          _hideStop();
          // Check for error in both 'error' and 'content' fields (backend inconsistency)
          var errorMsg = m.error || m.content || m.text || 'Unknown error occurred';
          streamText.textContent = '[error] ' + errorMsg; ackEvent(m);
          clearSpinner();
          _clearRunningTimer(); // Stop any running timer on error
          try {
            // Also append a system bubble with error details for visibility in the thread
            var wrapE = document.createElement('div'); wrapE.className = 'msg system';
            var metaE = document.createElement('div'); metaE.className = 'meta small'; metaE.innerHTML = "<span class='pill'>system</span> <span class='title' style='font-weight:600'>Error Details</span>";
            var bubE = document.createElement('div'); bubE.className = 'bubble system';
            var contE = document.createElement('div'); contE.className = 'content'; contE.style.whiteSpace = 'pre-wrap'; 
            contE.textContent = 'Error: ' + String(errorMsg);
            // Add click handler to view full error details if available
            if (m.details || m.stack) {
              contE.style.cursor = 'pointer';
              contE.title = 'Click to view full error details';
              contE.addEventListener('click', function() {
                var details = '';
                if (m.details) details += 'Details: ' + m.details + '\\n\\n';
                if (m.stack) details += 'Stack:\\n' + m.stack;
                
                // Create a modal with copyable text instead of alert
                var modal = document.createElement('div');
                modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';
                
                var dialog = document.createElement('div');
                dialog.style.cssText = 'background:white;border-radius:8px;padding:20px;max-width:80%;max-height:80%;overflow:auto;';
                
                var title = document.createElement('h3');
                title.textContent = 'Error Details';
                title.style.marginTop = '0';
                dialog.appendChild(title);
                
                var textarea = document.createElement('textarea');
                textarea.value = details || 'No additional details available';
                textarea.style.cssText = 'width:500px;height:300px;font-family:monospace;font-size:12px;';
                textarea.readOnly = true;
                dialog.appendChild(textarea);
                
                var buttonDiv = document.createElement('div');
                buttonDiv.style.marginTop = '10px';
                
                var copyBtn = document.createElement('button');
                copyBtn.textContent = 'Copy to Clipboard';
                copyBtn.onclick = function() {
                  textarea.select();
                  document.execCommand('copy');
                  copyBtn.textContent = 'Copied!';
                  setTimeout(function() { copyBtn.textContent = 'Copy to Clipboard'; }, 2000);
                };
                buttonDiv.appendChild(copyBtn);
                
                var closeBtn = document.createElement('button');
                closeBtn.textContent = 'Close';
                closeBtn.style.marginLeft = '10px';
                closeBtn.onclick = function() { modal.remove(); };
                buttonDiv.appendChild(closeBtn);
                
                dialog.appendChild(buttonDiv);
                modal.appendChild(dialog);
                document.body.appendChild(modal);
                
                // Select all text for easy copying
                textarea.select();
              });
            }
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
      ws.onclose = function(){ 
        try { if (window.unsubscribeCedarLogs && logSub) window.unsubscribeCedarLogs(logSub); } catch(_){}; 
        try { 
          _clearRunningTimer(); // Ensure timer is stopped on websocket close
          _hideStop();
          if (currentStep && currentStep.node && !timedOut) { 
            annotateTime(currentStep.node, _now() - currentStep.t0); 
            currentStep = null; 
          } 
          if (!finalOrError && !timedOut) { 
            streamText.textContent = (streamText.textContent||'') + ' [closed]'; 
          } 
        } catch(_){} 
      };
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
    console.log('[startNewChat] Called with projectId=' + projectId + ', branchId=' + branchId);
    fetch(`/api/chat/new`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_id: projectId, branch_id: branchId})
    }).then(function(r) {
      console.log('[startNewChat] Response status:', r.status);
      if (!r.ok) {
        throw new Error('HTTP ' + r.status + ': ' + r.statusText);
      }
      return r.json();
    }).then(function(data) {
      console.log('[startNewChat] Chat created:', data.chat_number);
      window.currentChatNumber = data.chat_number;
      updateChatNumberDisplay(data.chat_number);
      // Clear current messages
      var msgs = document.getElementById('msgs');
      if (msgs) msgs.innerHTML = '<div class="muted small">Chat ' + data.chat_number + ' started</div>';
      // Refresh history panel
      refreshHistoryPanel();
    }).catch(function(e) {
      console.error('[startNewChat] Failed to create new chat:', e);
      // Show user-visible error
      var msgs = document.getElementById('msgs');
      if (msgs) {
        var err = document.createElement('div');
        err.className = 'muted small';
        err.style.color = '#ef4444';
        err.textContent = 'Error creating new chat. Check console for details.';
        msgs.appendChild(err);
      }
    });
  }
  
  window.loadChat = function(projectId, branchId, chatNumber) {
    // Load a specific chat's history
    window.currentChatNumber = chatNumber;
    updateChatNumberDisplay(chatNumber);
    // Ensure the Chat tab is active
    try {
      var chatTab = document.querySelector('.tabs .tab[data-target="main-chat"]');
      if (chatTab) { chatTab.click(); }
    } catch(_){}
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
            var roleLabel = (String(msg.role||'').toLowerCase() === 'assistant') ? 'Chief Agent' : String(msg.role||'');
            meta.innerHTML = '<span class="pill">' + roleLabel + '</span>';
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
    // This would typically reload the history items from the server
    // For now, we'll rely on page refresh or manual tab switching
    var histPanel = document.getElementById('right-history');
    if (histPanel) {
      // In a full implementation, this would fetch updated chat list
      // and re-render the history items with correct status indicators
    }
  }

  // Stop a running chat from the History panel
  window.stopChat = function(projectId, branchId, chatNumber) {
    try {
      fetch('/api/chat/stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ project_id: projectId, branch_id: branchId, chat_number: chatNumber, reason: 'Stopped by user via History' })
      }).then(function(r){ return r.json().catch(function(){ return {}; }); }).then(function(){
        // Update UI: replace spinner with warning icon and remove Stop button
        try {
          var spin = document.querySelector('.chat-history-item [data-chat-num="' + String(chatNumber) + '"]');
          if (spin && spin.parentElement) {
            var parent = spin.parentElement;
            var warn = document.createElement('span');
            warn.style.color = '#ef4444';
            warn.textContent = '⚠';
            parent.replaceChild(warn, spin);
            // Remove a following Stop button if present
            try {
              var btn = parent.querySelector('button');
              if (btn) btn.remove();
            } catch(_){ }
          }
        } catch(_){ }
      }).catch(function(e){ try { console.error('[stopChat] Failed to stop chat', e); } catch(_){} });
    } catch(e) { try { console.error('[stopChat] Error', e); } catch(_){} }
  }

  document.addEventListener('DOMContentLoaded', function(){
    try {
      var chatForm = document.getElementById('chatForm');

      // Upload auto-submit: submit the upload form as soon as a file is selected.
      try {
        var uploadForm = document.querySelector('[data-testid=upload-form]');
        var uploadInput = document.querySelector('[data-testid=upload-input]');
        var uploadButton = document.querySelector('[data-testid=upload-submit]');
        if (uploadInput && uploadForm) {
          uploadInput.addEventListener('change', function(){
            try {
              if (uploadInput.files && uploadInput.files.length > 0 && !uploadForm.getAttribute('data-autosubmitted')) {
                uploadForm.setAttribute('data-autosubmitted', '1');
                // Switch to Chat so processing is visible, but let browser handle redirect
                try { var chatTab = document.querySelector('.tabs .tab[data-target="main-chat"]'); if (chatTab) chatTab.click(); } catch(_){ }
                if (typeof uploadForm.requestSubmit === 'function') {
                  uploadForm.requestSubmit();
                } else if (uploadButton) {
                  try { uploadButton.click(); } catch(_){ uploadForm.submit(); }
                } else {
                  uploadForm.submit();
                }
              }
            } catch(_) {}
          });
          // Safety net: if change event listener didn't fire, submit shortly after a file is present
          setInterval(function(){
            try {
              if (uploadInput.files && uploadInput.files.length > 0 && uploadForm && !uploadForm.getAttribute('data-autosubmitted')) {
                uploadForm.setAttribute('data-autosubmitted', '1');
                if (typeof uploadForm.requestSubmit === 'function') { uploadForm.requestSubmit(); } else { uploadForm.submit(); }
              }
            } catch(_) {}
          }, 150);
        }
      } catch(_) {}

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
        var sp = new URLSearchParams(location.search || '');
        var msg = (sp.get('msg')||'').replace(/\\+/g,' ');
        var tid0 = sp.get('thread_id') || (chatForm && chatForm.getAttribute('data-thread-id')) || null;
        var fid0 = sp.get('file_id') || (chatForm && chatForm.getAttribute('data-file-id')) || null;
        var dsid0 = sp.get('dataset_id') || (chatForm && chatForm.getAttribute('data-dataset-id')) || null;
        console.log('[auto-chat] cfg=', UPLOAD_AUTOCHAT, 'msg=', msg, 'tid0=', tid0, 'fid0=', fid0, 'dsid0=', dsid0, 'started=', !!window.__uploadAutoChatStarted);
        if (UPLOAD_AUTOCHAT && !window.__uploadAutoChatStarted) {
          if (msg === 'File uploaded' && (tid0 || fid0)) {
            window.__uploadAutoChatStarted = true;
            // Build initial user message expected by tests: include details prefix and JSON
            var detailsTxt = String(FILE_DETAILS_JSON||'');
            var initialUserMsg = `User uploaded a file with the following details:\n\n${detailsTxt}`;
            console.log('[auto-chat] starting WS with initial message and context');
            // Render a compact "Uploaded <filename>" assistant bubble with details toggle containing metadata
            try {
              
              var fileName = '(file)';
              try { var _parsed = JSON.parse(detailsTxt||''); if (_parsed && _parsed.name) { fileName = String(_parsed.name); } } catch(_){ }
              var detIdUp = 'det_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
              var wrapUp = document.createElement('div'); wrapUp.className = 'msg assistant';
              var metaUp = document.createElement('div'); metaUp.className = 'meta small'; metaUp.innerHTML = "<span class='pill'>Chief Agent</span> <span class='title' style='font-weight:600'>File Uploaded</span>";
              var bubUp = document.createElement('div'); bubUp.className = 'bubble assistant'; bubUp.setAttribute('data-details-id', detIdUp);
              var contUp = document.createElement('div'); contUp.className='content'; contUp.style.whiteSpace='pre-wrap'; contUp.textContent = 'Uploaded ' + fileName;
              bubUp.appendChild(contUp);
              var detailsUp = document.createElement('div'); detailsUp.id = detIdUp; detailsUp.style.display='none';
              var preUp = document.createElement('pre'); preUp.className='small'; preUp.style.whiteSpace='pre-wrap'; preUp.style.background='#f8fafc'; preUp.style.padding='8px'; preUp.style.borderRadius='6px';
              preUp.textContent = detailsTxt || '(no details)';
              detailsUp.appendChild(preUp);
              wrapUp.appendChild(metaUp); wrapUp.appendChild(bubUp); wrapUp.appendChild(detailsUp);
              var msgsEl0 = document.getElementById('msgs'); if (msgsEl0) msgsEl0.appendChild(wrapUp);
            } catch(_){ }
            // Pass thread_id and file_id so the server can emit a processing bubble immediately
            startWS(initialUserMsg, tid0, fid0, dsid0);
          } else {
            console.log('[auto-chat] conditions not met; skipping');
          }
        } else if (!UPLOAD_AUTOCHAT) {
          console.log('[auto-chat] disabled by config');
        }
      } catch(e) { try { console.error('[auto-chat] exception', e); } catch(_) {} }


      // Load file content if file_id is in URL on page load
      try {
        var sp = new URLSearchParams(location.search || '');
        var fileId = sp.get('file_id');
        if (fileId && !window.__fileContentLoaded) {
          window.__fileContentLoaded = true;
          window.displayFileContent(fileId);
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
        // Wire Stop button
        try {
          var stopBtn2 = document.getElementById('stopChatBtn');
          if (stopBtn2) {
            stopBtn2.addEventListener('click', function(){ try { window.__cedar_cancel_current_run && window.__cedar_cancel_current_run('user_clicked_cancel'); } catch(_){} });
          }
        } catch(_){}
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

      // Function to display file extracted content
      window.displayFileContent = async function(fileId) {
        try {
          var response = await fetch('/api/files/' + fileId + '/extracted');
          if (!response.ok) throw new Error('Failed to fetch file content');
          var data = await response.json();
          
          // Find or create a content display area
          var contentPanel = document.getElementById('file-content-panel');
          if (!contentPanel) {
            // Create a new panel if it doesn't exist
            var chatPanel = document.getElementById('main-chat');
            if (!chatPanel) return;
            
            contentPanel = document.createElement('div');
            contentPanel.id = 'file-content-panel';
            contentPanel.className = 'card';
            contentPanel.style.cssText = 'margin-bottom:12px; padding:12px; background:#f8fafc; border-radius:8px; max-height:400px; overflow:auto;';
            
            // Insert before the messages
            var msgs = document.getElementById('msgs');
            if (msgs && msgs.parentNode) {
              msgs.parentNode.insertBefore(contentPanel, msgs);
            }
          }
          
          // Display the content
          var html = '<h4 style="margin:0 0 8px 0; font-size:14px; color:#1a2332">' + (data.ai_title || data.filename || 'File Content') + '</h4>';
          
          if (data.has_schema && data.data_schema) {
            // Display schema for structured data
            html += '<div class="small muted" style="margin-bottom:8px">Data Structure: ' + (data.data_schema.table_name || 'Table') + '</div>';
            html += '<div style="background:white; padding:8px; border-radius:4px; margin-bottom:8px">';
            html += '<table style="width:100%; font-size:13px">';
            html += '<thead><tr><th style="text-align:left; padding:4px; border-bottom:1px solid #e0e6ed">Column</th><th style="text-align:left; padding:4px; border-bottom:1px solid #e0e6ed">Type</th></tr></thead>';
            html += '<tbody>';
            if (data.data_schema.columns) {
              data.data_schema.columns.forEach(function(col) {
                html += '<tr><td style="padding:4px">' + (col.name || '') + '</td><td style="padding:4px; color:#6b7280">' + (col.type || '') + '</td></tr>';
              });
            }
            html += '</tbody></table>';
            if (data.data_schema.sql_create) {
              html += '<details style="margin-top:8px"><summary class="small muted" style="cursor:pointer">SQL Schema</summary>';
              html += '<pre style="margin-top:4px; padding:8px; background:#f1f5f9; border-radius:4px; font-size:12px; overflow:auto">' + data.data_schema.sql_create + '</pre>';
              html += '</details>';
            }
            html += '</div>';
          }
          
          if (data.has_content && data.extracted_content) {
            // Display extracted content
            html += '<div class="small" style="background:white; padding:8px; border-radius:4px">';
            html += '<div class="muted" style="margin-bottom:4px">Extracted Content:</div>';
            html += '<div style="white-space:pre-wrap; font-family:ui-monospace,monospace; font-size:12px; line-height:1.5; max-height:250px; overflow:auto">' + data.extracted_content + '</div>';
            html += '</div>';
          }
          
          contentPanel.innerHTML = html;
          contentPanel.style.display = 'block';
          
        } catch(e) {
          console.error('Failed to load file content:', e);
        }
      }

      // Intercept clicks on file/db links. For images, open a numbered Chat with context; otherwise use thread flow.
      document.addEventListener('click', function(ev){
        var a = ev.target && ev.target.closest ? ev.target.closest('a.thread-create') : null;
        if (!a) return;
        try { ev.preventDefault(); } catch(_){ }
        var isImage = false; try { isImage = !!a.dataset.isImage; } catch(_){ isImage = false; }
        var fid = a.getAttribute('data-file-id') || null;
        var dsid = a.getAttribute('data-dataset-id') || null;
        // If not present in attributes, try extracting from href
        if (!fid || !dsid) {
          try {
            var urlObj = new URL(a.getAttribute('href'), window.location.href);
            if (!fid) fid = urlObj.searchParams.get('file_id');
            if (!dsid) dsid = urlObj.searchParams.get('dataset_id');
          } catch(_){ }
        }
        if (isImage) {
          // New behavior for Images tab: open a numbered chat with image context
          (function(){
            try {
              // Switch to Chat tab
              try { var chatTab = document.querySelector('.tabs .tab[data-target="main-chat"]'); if (chatTab) chatTab.click(); } catch(_){ }
              // Start a new numbered chat
              try { if (window.startNewChat) window.startNewChat(PROJECT_ID, BRANCH_ID); } catch(_){ }
              // Update chat form with file context
              try {
                var f = document.getElementById('chatForm');
                if (f) {
                  f.setAttribute('data-thread-id', '');
                  f.setAttribute('data-file-id', fid||'');
                  try { f.setAttribute('data-file-name', (a.getAttribute('data-display-name')||'')); } catch(_){ }
                  f.setAttribute('data-dataset-id', dsid||'');
                  var hidT = f.querySelector("input[name='thread_id']"); if (hidT) { hidT.remove(); }
                  var hidF = f.querySelector("input[name='file_id']"); if (fid) { if (hidF) hidF.value = fid; else { var j=document.createElement('input'); j.type='hidden'; j.name='file_id'; j.value=fid; f.appendChild(j);} } else if (hidF) { hidF.remove(); }
                  var hidD = f.querySelector("input[name='dataset_id']"); if (dsid) { if (hidD) hidD.value = dsid; else { var k=document.createElement('input'); k.type='hidden'; k.name='dataset_id'; k.value=dsid; f.appendChild(k);} } else if (hidD) { hidD.remove(); }
                }
              } catch(_){ }
              // Render Image Context panel with preview and metadata
              try {
                var imgUrl = a.getAttribute('data-image-url') || '';
                var displayName = a.getAttribute('data-display-name') || '';
                var fileType = a.getAttribute('data-file-type') || '';
                var mimeType = a.getAttribute('data-mime-type') || '';
                var aiTitle = a.getAttribute('data-ai-title') || '';
                var aiCategory = a.getAttribute('data-ai-category') || '';
                var aiDesc = (function(){ try { var b=a.getAttribute('data-ai-desc-b64')||''; return b ? (new TextDecoder('utf-8')).decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0))) : ''; } catch(_){ return ''; } })();
                var size = a.getAttribute('data-size') || '';
                var createdAt = a.getAttribute('data-created-at') || '';
                // Create/replace panel
                var chatPanel = document.getElementById('main-chat');
                var msgs = document.getElementById('msgs');
                if (chatPanel && msgs) {
                  var panel = document.getElementById('image-context-panel');
                  if (!panel){ panel = document.createElement('div'); panel.id='image-context-panel'; panel.className='card'; panel.style.marginBottom='12px'; panel.style.padding='12px'; panel.style.background='#f8fafc'; panel.style.borderRadius='8px'; msgs.parentNode.insertBefore(panel, msgs); }
                  panel.innerHTML = '';
                  var h=document.createElement('h3'); h.textContent='Image Context'; panel.appendChild(h);
                  if (imgUrl) { var img=document.createElement('img'); img.src=imgUrl; img.alt=displayName||aiTitle||'image'; img.style.maxWidth='100%'; img.style.maxHeight='320px'; img.style.display='block'; img.style.border='1px solid var(--border)'; img.style.borderRadius='6px'; panel.appendChild(img); }
                  var tbl=document.createElement('table'); tbl.className='table'; var tbody=document.createElement('tbody');
                  function row(k,v){ var tr=document.createElement('tr'); var th=document.createElement('th'); th.textContent=k; var td=document.createElement('td'); td.textContent=v||''; tr.appendChild(th); tr.appendChild(td); tbody.appendChild(tr);} 
                  row('Title', aiTitle||displayName||''); row('Category', aiCategory||''); row('file_id', String(fid||'')); row('image_url', imgUrl||''); row('MIME', mimeType||''); row('Type', fileType||''); row('Size', String(size||'')); row('Created', createdAt||'');
                  tbl.appendChild(tbody); panel.appendChild(tbl);
                  if (aiDesc) { var pre=document.createElement('pre'); pre.className='small'; pre.style.whiteSpace='pre-wrap'; pre.style.background='#f1f5f9'; pre.style.padding='8px'; pre.style.borderRadius='6px'; pre.style.maxHeight='200px'; pre.style.overflow='auto'; pre.textContent=aiDesc; panel.appendChild(pre); }
                }
              } catch(_){ }
              // Prefill chat input with template including image details
              try {
                var t = document.getElementById('chatInput');
                if (t) {
                  var template = 'Image Context\\n' +
                                 'title: ' + (a.getAttribute('data-ai-title')||a.getAttribute('data-display-name')||'') + '\\n' +
                                 'file_id: ' + String(fid||'') + '\\n' +
                                 'image_url: ' + (a.getAttribute('data-image-url')||'') + '\\n' +
                                 'mime_type: ' + (a.getAttribute('data-mime-type')||'') + '\\n' +
                                 'file_type: ' + (a.getAttribute('data-file-type')||'') + '\\n' +
                                 'size_bytes: ' + (a.getAttribute('data-size')||'') + '\\n' +
                                 'created_at: ' + (a.getAttribute('data-created-at')||'') + '\\n' +
                                 'ai_category: ' + (a.getAttribute('data-ai-category')||'') + '\\n' +
                                 'ai_description: ' + (function(){ try { var b=a.getAttribute('data-ai-desc-b64')||''; return b ? (new TextDecoder('utf-8')).decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0))) : ''; } catch(_){ return ''; } })() + '\\n\\n' +
                                 '---\\n\\n' +
                                 'Prompt:\\n';
                  t.value = template; try { t.focus(); } catch(_){ }
                }
              } catch(_){ }
              // Clear messages panel for fresh chat
              try { var msgs2 = document.getElementById('msgs'); if (msgs2) { msgs2.innerHTML = "<div class='muted small'>(No messages yet)</div>"; } } catch(_){ }
              // Update URL without thread id (numbered chats)
              try { var url = `/project/${PROJECT_ID}?branch_id=${BRANCH_ID}` + (fid?`&file_id=${encodeURIComponent(fid)}`:''); if (history && history.pushState) { history.pushState({}, '', url); } } catch(_){ }
            } catch(e) { try { console.debug('[Image→Chat] error', e); } catch(_){} }
          })();
          return;
        }
        // Default behavior (non-image): create a thread and load file context
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
          // Load and display file content if file ID is present
          if (fid) { window.displayFileContent(fid); }
          // Clear messages panel to indicate a fresh thread
          try { var msgs = document.getElementById('msgs'); if (msgs) { msgs.innerHTML = "<div class='muted small'>(No messages yet)</div>"; } } catch(_){ }
          // Update URL with thread id
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
