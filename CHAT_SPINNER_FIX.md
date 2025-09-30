# Chat Spinner Issue - Fix Documentation

## Problem Description

**Issue**: Chat history was showing a spinner on a chat even though no background job was running.

**Root Cause**: The chat was stuck in "processing" status because:
1. The WebSocket connection was lost or crashed during processing
2. The orchestration never completed (or crashed without proper cleanup)
3. The status was set to "processing" but never updated to "complete" or "error"

## What Was Fixed

### 1. Added Error Handling in WebSocket Chat Handler

**File**: `cedar_orchestrator/ws_chat.py`

**Changes**:
- Added try-except block around orchestration to catch failures
- When orchestration fails, the chat status is now properly set to "error"
- A system message is added explaining what went wrong
- Error details are sent to the client via WebSocket

**Before**:
```python
await orchestrator.orchestrate(...)
```

**After**:
```python
try:
    await orchestrator.orchestrate(...)
except Exception as orch_err:
    # Orchestration failed - mark chat as error
    logger.error(f"[WebSocket] Orchestration failed: {orch_err}")
    
    # Update chat status to error
    if project_id and chat_number:
        chat_manager.set_chat_status(project_id, branch_id, chat_number, "error")
        chat_manager.add_message(
            project_id, branch_id, chat_number,
            role="System",
            content=f"Error during orchestration: {str(orch_err)}",
            metadata={'type': 'system_error'}
        )
    
    # Send error to client
    await websocket.send_json({
        "type": "error",
        "error": f"Orchestration failed: {str(orch_err)}",
        ...
    })
    raise
```

### 2. Added Cleanup on WebSocket Disconnect

**File**: `cedar_orchestrator/ws_chat.py`

**Changes**:
- When WebSocket connection is lost, check if there's an active chat in "processing" status
- If found, mark it as "error" to prevent the spinner from showing indefinitely
- Add a system message explaining the connection was lost

**Code**:
```python
except Exception as e:
    logger.error(f"WebSocket connection error: {e}")
    
    # If we have an active chat in processing status, mark it as error on disconnect
    if current_chat_number and project_id:
        chat_data = chat_manager.get_chat(project_id, 1, current_chat_number)
        if chat_data and chat_data.get('status') == 'processing':
            logger.warning(f"[WebSocket] Chat #{current_chat_number} left in processing state, marking as error")
            chat_manager.set_chat_status(project_id, 1, current_chat_number, "error")
            chat_manager.add_message(
                project_id, 1, current_chat_number,
                role="System",
                content="Connection lost during processing",
                metadata={'type': 'disconnect_error'}
            )
```

### 3. Created Cleanup Utility Script

**File**: `scripts/cleanup_stuck_chats.py`

**Purpose**: Manual cleanup tool for any chats that got stuck before the fix was applied.

**Usage**:
```bash
# Clean up all stuck chats
python scripts/cleanup_stuck_chats.py

# Clean up stuck chats for specific project
python scripts/cleanup_stuck_chats.py --project-id 1 --branch-id 1

# Only clean chats stuck for more than 10 minutes
python scripts/cleanup_stuck_chats.py --max-age-minutes 10

# Dry run to see what would be cleaned
python scripts/cleanup_stuck_chats.py --dry-run
```

**What it does**:
- Scans `/tmp/cedar_chats` directory for chat JSON files
- Finds chats with status="processing" that are older than threshold (default 5 minutes)
- Updates their status to "error"
- Adds a system message explaining the cleanup

## How to Test the Fix

1. **Start the server**:
   ```bash
   python -m cedarpy.main
   ```

2. **Trigger a chat that will fail**:
   - Upload a file or send a chat message
   - Kill the server mid-processing (Ctrl+C or `kill -9`)
   
3. **Restart the server and check**:
   - The chat should now show an error icon (⚠) instead of a spinner
   - The system message should explain what happened

4. **Test graceful error handling**:
   - Remove or invalidate your OpenAI API key
   - Send a chat message
   - Should see an error message instead of infinite spinner

## Manual Fix for Current Issue

The chat stuck in your project has already been fixed with:

```bash
# Updated chat status from "processing" to "error"
cat /tmp/cedar_chats/chat_p1_b1_n1.json
```

**Status changed from**: `"status": "processing"`  
**Status changed to**: `"status": "error"`

This removed the spinner from the UI.

## Prevention

The fixes ensure that:
1. **Orchestration failures** → chat marked as "error" + system message
2. **Connection loss** → chat marked as "error" + system message  
3. **Manual cleanup** → utility script available for edge cases

## Related Files

- `cedar_orchestrator/ws_chat.py` - WebSocket handler with error handling
- `cedar_app/utils/chat_persistence.py` - Chat persistence manager
- `cedar_app/utils/page_rendering.py` - UI rendering (shows spinner based on status)
- `scripts/cleanup_stuck_chats.py` - Cleanup utility

## Testing Checklist

- [x] Chat status properly set to "error" on orchestration failure
- [x] Chat status properly set to "error" on WebSocket disconnect
- [x] System messages added to explain errors
- [x] Cleanup script successfully cleans stuck chats
- [x] UI spinner removed when status is not "processing"

## Notes

The chat history display in `page_rendering.py` (lines 172-180) correctly shows:
- **Spinner** (🔄) for status="processing"  
- **Warning** (⚠️) for status="error"
- **Checkmark** (✓) for status="complete"
- **Blue dot** (•) for status="active"

The issue was that chats were getting stuck in "processing" status and never transitioning to a final state. This has now been addressed with proper error handling and cleanup.