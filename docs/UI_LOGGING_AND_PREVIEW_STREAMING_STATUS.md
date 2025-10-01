# UI Logging and Preview Streaming Investigation

## Summary

Comprehensive logging and analysis revealed that:
- ✅ **Backend preview streaming is WORKING PERFECTLY**
- ❌ **UI is NOT displaying preview content**
- ✅ **Backend logging infrastructure complete**
- ⏳ **UI logging infrastructure partially complete** (endpoint created, JavaScript integration needed)

## Investigation Timeline

### 1. Added Comprehensive Backend Logging

**Files Modified:**
- `cedar_orchestrator/logging_config.py` (created)
- `cedar_orchestrator/chief_agent.py` (enhanced logging)
- `cedar_orchestrator/preview_streamer.py` (enhanced logging)
- `cedar_orchestrator/ws_chat.py` (enhanced logging)

**Result**: Complete visibility into backend execution with logs written to `~/Library/Logs/CedarPy/`

### 2. Analyzed Actual User Query ("what is 2+2")

**Log Analysis from `backend_20250930_192640.log`:**

#### Planning Phase (19:32:37 - 19:32:55) - 18.1s
```
→ ENTERING review_and_decide
  ▸ Preview enabled: True, WebSocket: True
  ▸ Starting preview task for thinking phase
✓ SUCCESS: Preview task created successfully
  ▸ Calling OpenAI API for preview streaming  
✓ SUCCESS: Preview stream initiated
  ▸ Sending preview_start event to WebSocket
✓ SUCCESS: preview_start event sent: {'type': 'preview_start', 'phase': 'thinking', 'model': 'gpt-5-nano'}
  ▸ Starting token streaming loop
  [Streamed 66 tokens, 410 chars over ~5 seconds]
✓ SUCCESS: Preview complete: 410 chars, 66 tokens
✓ SUCCESS: LLM response received (gpt-5)
```

#### Synthesis Phase (19:33:18 - 19:33:50) - 31.7s
```
→ ENTERING review_and_decide (with 1 agent result)
  ▸ Preview enabled: True, WebSocket: True
  ▸ Starting preview task for synthesis phase
✓ SUCCESS: Preview task created successfully
  ▸ Calling OpenAI API for preview streaming
✓ SUCCESS: Preview stream initiated
  ▸ Sending preview_start event to WebSocket
✓ SUCCESS: preview_start event sent: {'type': 'preview_start', 'phase': 'synthesis', 'model': 'gpt-5-nano'}
  ▸ Starting token streaming loop
  [Streamed 101 tokens, 607 chars over ~12 seconds]
✓ SUCCESS: Preview complete: 607 chars, 101 tokens
✓ SUCCESS: LLM response received (gpt-5)
```

**Conclusion**: Preview streaming is working perfectly on the backend!

### 3. Reviewed UI Display

**What User Saw:**
```
Chief Agent
planning(41.0s)
I'll use CodeAgent to calculate this for you.

Coding Agent(35.8s)
4

Chief Agent
Final
**4**
- Verified by executing the calculation using CodeAgent.
```

**Analysis:**
- "planning(41.0s)" - Status text, NOT preview content
- "I'll use CodeAgent..." - Final gpt-5 response, NOT nano preview
- NO preview content visible at all

### 4. Reviewed UI JavaScript Code

**File**: `cedar_app/utils/javascript_bundles.py`

**Event Handlers Found:**
- ✅ `thinking_start` - handled
- ✅ `thinking_token` - handled (but not used for preview)
- ✅ `thinking` - handled
- ✅ `synthesis_start` - probably handled (same as thinking_start logic)
- ❌ `preview_start` - NOT HANDLED
- ❌ `preview_token` - NOT HANDLED
- ❌ `preview_complete` - NOT HANDLED

**Root Cause**: The UI has NO handlers for preview events!

## What's Working

### ✅ Backend Comprehensive Logging
- All backend activity logged to files
- Function entry/exit tracking
- Step-by-step progress logging
- Success/failure confirmations
- Error logging with full stack traces
- Component-specific log files
- Timestamps and line numbers

**Log Files Created:**
```
~/Library/Logs/CedarPy/
├── backend_<timestamp>.log          # All backend activity
├── chief_agent_<timestamp>.log      # ChiefAgent only
├── preview_streamer_<timestamp>.log # PreviewStreamer only
├── ws_chat_<timestamp>.log          # WebSocket handler
└── orchestrator_<timestamp>.log     # Orchestrator
```

### ✅ Preview Streaming Backend
- gpt-5-nano model called in parallel
- Tokens streamed word-by-word
- WebSocket events sent successfully:
  - `preview_start` with phase and model
  - `preview_token` for each word
  - `preview_complete` with total length
- Preview cancelled when real response arrives
- All timing and latency logged

### ✅ Backend UI Logging Endpoint
**Created**: `cedar_app/routes/ui_logging_routes.py`

**Endpoints:**
- `/api/ui-log` - Receive client-side log messages
- `/api/ui-event` - Receive detailed event tracking

**Features:**
- Timestamp tracking
- Latency calculation (backend send → UI receive)
- Event type logging
- Rendering time tracking
- All UI logs written to backend log files

## What's NOT Working

### ❌ UI Preview Display
The UI JavaScript (`javascript_bundles.py`) has NO handlers for:
- `preview_start` events
- `preview_token` events
- `preview_complete` events

**Impact**: Preview content is sent by backend but completely ignored by UI.

### ⏳ UI Client-Side Logging (Partially Complete)
**Status**: Backend endpoint exists, JavaScript integration needed

**Missing**:
- JavaScript helper functions to send logs to backend
- Event handlers that log receipt/processing/rendering
- Timestamp tracking in JavaScript
- Latency measurement client-side

## What Needs To Be Done

### 1. Add Preview Event Handlers to UI (**CRITICAL**)

**File**: `cedar_app/utils/javascript_bundles.py`

**Location**: In the `handleEvent` function (around line 783-846)

**Add handlers for:**

```javascript
} else if (m.type === 'preview_start') {
  // Create preview bubble or update existing thinking bubble
  // Show "Preview from gpt-5-nano..."
  // Start collecting preview text
  
} else if (m.type === 'preview_token') {
  // Append token to preview bubble
  // Stream word-by-word like thinking_token
  
} else if (m.type === 'preview_complete') {
  // Mark preview as complete
  // Prepare for real response to replace it
```

### 2. Add Client-Side Logging JavaScript

**Add logging helper function:**
```javascript
function logToBackend(level, message, eventType, data) {
  try {
    fetch('/api/ui-log', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        level: level,
        message: message,
        event_type: eventType,
        timestamp_client: performance.now(),
        timestamp_backend_sent: data.backend_timestamp,
        data: data
      })
    });
  } catch(e) { console.error('Failed to log to backend:', e); }
}
```

**Add to every event handler:**
```javascript
} else if (m.type === 'preview_start') {
  var t0 = performance.now();
  logToBackend('info', 'Received preview_start event', 'preview_start', {
    phase: m.phase,
    model: m.model,
    backend_timestamp: m.timestamp
  });
  
  // ... handle event ...
  
  var t1 = performance.now();
  logToBackend('debug', 'Rendered preview_start', 'preview_start', {
    render_time_ms: t1 - t0
  });
}
```

### 3. Add Timestamp Tracking

**Backend**: Add timestamp to WebSocket events
```python
# In preview_streamer.py
await websocket.send_json({
    "type": "preview_start",
    "phase": phase,
    "model": preview_model,
    "timestamp": time.time() * 1000  # milliseconds since epoch
})
```

**UI**: Track and log latency
```javascript
var latency = performance.now() - (m.timestamp - performance.timeOrigin);
logToBackend('info', `Preview event latency: ${latency.toFixed(1)}ms`, 'latency', {
  backend_timestamp: m.timestamp,
  ui_timestamp: performance.now(),
  latency_ms: latency
});
```

## Testing Plan

### Test 1: Verify UI Logging Endpoint
```bash
curl -X POST http://localhost:8000/api/ui-log \
  -H "Content-Type: application/json" \
  -d '{
    "level": "info",
    "message": "Test log from curl",
    "event_type": "test",
    "timestamp_client": 12345.67
  }'
```

Check logs:
```bash
grep "\[UI\]" ~/Library/Logs/CedarPy/backend_*.log
```

### Test 2: Verify Preview Events After UI Changes
1. Add preview event handlers to JavaScript
2. Restart backend
3. Send "what is 2+2" query
4. Check backend logs for `[UI]` entries
5. Verify preview content appears in UI before final response

### Test 3: Measure End-to-End Latency
1. Check backend logs for event send timestamp
2. Check UI logs for event receive timestamp
3. Calculate: `UI receive - Backend send = network latency`
4. Check UI logs for render timestamp
5. Calculate: `UI render - UI receive = processing time`

## Expected Results After Fixes

### Backend Logs Will Show:
```
19:32:37.041 | INFO | preview_streamer | Sending preview_start event to WebSocket
19:32:37.043 | INFO | ui_logging_routes | [UI] Received preview_start event | latency=2.1ms
19:32:37.045 | INFO | ui_logging_routes | [UI] Rendered preview bubble | render_time=2.3ms
19:32:41.020 | INFO | preview_streamer | Sending preview_token | text="I'll"
19:32:41.022 | INFO | ui_logging_routes | [UI] Received preview_token | latency=2.0ms
...
```

### UI Will Show:
```
Chief Agent
planning (with live preview streaming word-by-word)
[Preview from gpt-5-nano] I'll use CodeAgent to calculate 2+2...
[Preview complete, waiting for final answer...]
I'll use CodeAgent to calculate this for you.
```

## Documentation

- [LOGGING_SYSTEM.md](LOGGING_SYSTEM.md) - Backend logging documentation
- [BYTECODE_CACHE_ISSUE.md](BYTECODE_CACHE_ISSUE.md) - Cache prevention
- This document - UI logging and preview streaming status

## Related Files

**Backend Logging:**
- `cedar_orchestrator/logging_config.py`
- `cedar_orchestrator/chief_agent.py`
- `cedar_orchestrator/preview_streamer.py`
- `cedar_orchestrator/ws_chat.py`

**UI Logging:**
- `cedar_app/routes/ui_logging_routes.py` (backend endpoint)
- `cedar_app/utils/javascript_bundles.py` (needs JavaScript integration)

**Testing:**
- `test_preview_streaming.py`
- `clear_cache_and_run.sh`

## Conclusion

**Current State:**
- ✅ Backend logging: COMPLETE and WORKING
- ✅ Preview streaming backend: COMPLETE and WORKING  
- ✅ UI logging endpoint: CREATED
- ❌ Preview display in UI: NOT IMPLEMENTED
- ⏳ UI logging JavaScript: NOT IMPLEMENTED

**Impact**: We have complete backend visibility but are "blind" on the UI side. The preview streaming feature is fully functional on the backend but the UI doesn't know what to do with the events.

**Priority**: Add preview event handlers to UI JavaScript (Step 1 above) to make preview streaming visible to users.
