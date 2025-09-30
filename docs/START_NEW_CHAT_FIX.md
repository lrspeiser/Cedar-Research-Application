# Start New Chat Link Fix

## Problem

The "Start New Chat" link on the project page was not opening a new chat window. When users clicked the link, nothing happened.

## Root Cause

The issue was a **JavaScript variable scope problem**:

1. In `cedar_app/utils/page_rendering.py` (line 828), the link's onclick handler referenced `PROJECT_ID` and `BRANCH_ID`:
   ```html
   <a href="#" onclick="startNewChat(PROJECT_ID, BRANCH_ID); return false;">Start New Chat</a>
   ```

2. These JavaScript variables were defined inside a self-executing anonymous function in `cedar_app/utils/javascript_bundles.py`:
   ```javascript
   (function(){
     var PROJECT_ID = __PID__;
     var BRANCH_ID = __BID__;
     // ... rest of the code
   })();
   ```

3. Because the variables were declared with `var` inside the function scope, they were **not accessible** from the inline onclick handler in the HTML, which executes in the global scope.

## Solution

Changed the inline onclick handler to use Python f-string interpolation to inject the actual values:

**Before:**
```html
<a href="#" onclick="startNewChat(PROJECT_ID, BRANCH_ID); return false;">Start New Chat</a>
```

**After:**
```html
<a href="#" onclick="startNewChat({project.id}, {current.id}); return false;">Start New Chat</a>
```

This way, the actual numeric IDs are embedded directly in the HTML at server-side render time, eliminating the dependency on JavaScript variables.

## Additional Improvements

### 1. Enhanced Logging
Added defensive console logging to the `startNewChat` function to help diagnose future issues:

```javascript
window.startNewChat = function(projectId, branchId) {
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
    // ... rest of success handling
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
```

### 2. User-Visible Error Messages
Now if chat creation fails, the user sees a visible error message in the chat area instead of silent failure.

### 3. Regression Test
Created `tests/test_playwright_start_new_chat.py` to verify:
- The "Start New Chat" link is visible and clickable
- Clicking it makes a successful API call to `/api/chat/new`
- The new chat number is displayed
- The messages area is cleared and shows "Chat N started"
- The "New Chat" button in the History panel also works

## Files Changed

1. **cedar_app/utils/page_rendering.py**
   - Line 828: Fixed onclick handler to use inlined project/branch IDs

2. **cedar_app/utils/javascript_bundles.py**
   - Lines 1097-1130: Added logging and error handling to `startNewChat` function

3. **tests/test_playwright_start_new_chat.py** (NEW)
   - Comprehensive Playwright test for the link functionality

4. **docs/START_NEW_CHAT_FIX.md** (NEW)
   - This documentation file

## Verification

To verify the fix works:

1. **Manual Testing:**
   - Start the server: `python run_cedarpy.py`
   - Navigate to any project page
   - Click "Start New Chat" in the Chat tab header
   - Verify a new chat is created and the chat number is displayed
   - Switch to the History tab
   - Click the "New Chat" button
   - Verify it also creates a new chat

2. **Automated Testing:**
   ```bash
   pytest tests/test_playwright_start_new_chat.py -v -s
   ```

## Prevention

To avoid similar issues in the future:

1. **Avoid inline onclick handlers when possible** - use event listeners instead
2. **When using inline handlers, always inline the actual values** using server-side templating
3. **Add defensive logging** to help diagnose issues
4. **Write Playwright tests** for critical UI interactions

## Related Files

- Chat API implementation: `cedar_app/routes/chat_api.py`
- Chat persistence: `cedar_app/utils/chat_persistence.py`
- WebSocket chat: `cedar_orchestrator/ws_chat.py`
- Main JavaScript bundle: `cedar_app/utils/javascript_bundles.py`
- Page rendering: `cedar_app/utils/page_rendering.py`

## API Endpoint

The link calls this API endpoint:

**POST /api/chat/new**

Request body:
```json
{
  "project_id": 1,
  "branch_id": 1,
  "title": "Optional chat title"
}
```

Response:
```json
{
  "chat_number": 1,
  "title": "Chat 1",
  "created_at": "2025-01-15T10:30:00"
}
```

This endpoint is registered in `main.py` via `register_chat_api_routes()`.