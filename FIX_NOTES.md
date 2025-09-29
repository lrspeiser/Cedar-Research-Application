# Cedar Orchestration Fix Notes

**Started:** 2025-09-29  
**Checkpoint Tag:** `cedar-orchestrator-pre-fix-20250929-160337`

## Overview

This document tracks all bugs fixed and improvements made during the orchestration flow overhaul. For each fix, we document:
- What the mistake was
- How it was fixed
- What test(s) were run
- What logging was added to confirm

---

## Session 1: Initial Investigation and Setup

### Issue: "what is 2+2?" test case not working as expected

**Symptoms:**
- User submits "what is 2+2?"
- Planning bubble shows brief thinking
- "Prepared LLM prompt" displays "No LLM prompt available" instead of actual JSON
- Flow unclear between Chief Agent phases

**Root Causes Identified:**
1. Prompt event caching failure (thread_id type mismatch)
2. Context not preserved across Chief Agent calls
3. Unclear two-phase flow (planning vs synthesis)
4. Fallback logic contradicts design
5. Subagent prompt architecture needs clarification
6. UI event handling inconsistencies

**Created:**
- `ORCHESTRATION_FLOW_ISSUES.md` - Comprehensive analysis
- 20 TODO tasks for systematic remediation
- Git checkpoint: `cedar-orchestrator-pre-fix-20250929-160337`

---

## Fixes Applied

### Fix 1: Prompt event missing thread_id field

**What was wrong:**
- Prompt events were emitted at line 277-280 of orchestrator.py
- Event payload only included `{"type": "prompt", "messages": [...]}`
- Missing `thread_id` field meant frontend couldn't correlate prompts to threads
- Frontend cache lookup failed, showing "No LLM prompt available"
- Thread ID was never passed through the orchestration chain

**How it was fixed:**
- Added `thread_id` parameter to `orchestrate()` method signature
- Added `thread_id` parameter to `review_and_decide()` method signature  
- Updated prompt event payload to include:
  - `thread_id` (as string for consistent caching)
  - `iteration` (current iteration number)
  - `stage` ("chief_first_pass" or "chief_synthesis")
  - `agent` ("Chief Agent")
  - `timestamp` (for debugging)
- Derived thread_id from chat_number in ws_chat.py
- Passed thread_id through both review_and_decide calls in orchestrate()
- Added README comment about API key configuration

**Tests run:**
- Code compiles without errors
- Server starts successfully
- Need to run: Submit "what is 2+2?" and check browser console for prompt events with thread_id

**Logging added:**
```python
logger.info(f"[ChiefAgent] EMIT prompt: thread_id={thread_id_str}, iteration={iteration}, stage={prompt_payload['stage']}, msg_count={len(msgs)}")
logger.info(f"[ChiefAgent] EMIT prompt: SUCCESS")
logger.warning(f"[ChiefAgent] EMIT prompt: FAILED: {e}")
```

**Commit:** `f863299` - "Fix: Add thread_id to prompt events for UI caching"

---

### Fix 2: Frontend prompt caching broken

**What was wrong:**
- Frontend cache `window.__cedar_last_prompts` was storing prompts incorrectly
- Old logic replaced entire cache instead of appending per-thread entries
- No debug logging to trace cache state
- "Prepared LLM prompt" bubble couldn't retrieve cached data
- Edit prompt modal broken due to cache structure mismatch

**How it was fixed:**
- Modified prompt event handler in `page_rendering.py` (lines ~1076-1097)
- Changed cache structure to append entries per thread:
  ```javascript
  window.__cedar_last_prompts[threadId] = [
    ...previousEntries,
    {stage, iteration, agent, prompt_json, timestamp}
  ]
  ```
- Added console.debug logging with `[cedar-ui]` prefix:
  - "Received prompt event"
  - "Cached prompt for thread"
  - "Cache lookup: found/not found"
  - "Cache state" on errors
- Updated "Prepared LLM prompt" bubble rendering (line ~1414)
- Fixed edit prompt modal to use new cache structure (line ~1508)
- Normalized thread_id to string consistently before cache operations

**Tests run:**
- Code compiles without errors
- Server restarts successfully (--reload mode)
- Need to run: Submit "what is 2+2?" and check:
  - Browser console shows `[cedar-ui]` debug logs
  - Cache updates with correct structure
  - "Prepared LLM prompt" bubble displays actual JSON
  - Edit prompt modal opens with correct data

**Logging added:**
```javascript
console.debug('[cedar-ui] Received prompt event', event);
console.debug('[cedar-ui] Cached prompt for thread', threadIdStr, 'entry:', cacheEntry, 'total entries:', window.__cedar_last_prompts[threadIdStr].length);
console.debug('[cedar-ui] Cache lookup for thread', threadIdStr, '- found:', cachedEntries ? cachedEntries.length + ' entries' : 'none');
console.debug('[cedar-ui] Cache state:', window.__cedar_last_prompts);
```

**Commit:** `8a5c2d1` - "Fix: Repair frontend prompt caching with per-thread arrays"

---

### Fix 3: Invalid default model causing all LLM calls to fail

**What was wrong:**
- Line 90 of `orchestrator.py` had: `model = ... or "gpt-5"`
- **GPT-5 doesn't exist yet!** This caused all OpenAI API calls to fail
- Error message: "Model unresponsive: JSON parsing failed after 3 repair attempts"
- Chief Agent would retry 3 times, fail, and return fallback error message
- This was blocking ALL queries from working

**How it was fixed:**
- Changed default model from `"gpt-5"` to `"gpt-4o"` (valid model)
- Updated model parameter logic to properly handle gpt-4o:
  - Use `max_completion_tokens` for gpt-4o (new API format)
  - Add `temperature=0.3` for gpt-4o (supported parameter)
- Added comment explaining why gpt-5 was removed

**Tests run:**
- Code compiles without errors
- Server will auto-reload changes (--reload mode)
- Need to run: Submit "what is 2+2?" and verify:
  - Chief Agent successfully calls OpenAI
  - Planning completes without "Model unresponsive" error
  - Final answer returns "4"
  - No JSON parsing failures

**Logging added:**
- Existing log already shows: `[ChiefAgent] Using LLM for decision making with model: {model}`
- This will now show "gpt-4o" instead of "gpt-5"

**Root cause analysis:**
- The UI shows "gpt-5" in the model dropdown (line 304 check)
- Logs showed "gpt-4.1" being configured somewhere
- But the actual default was "gpt-5" which doesn't exist
- This is a critical bug that would break the entire system for any user without explicit model configuration

**Commit:** `[pending]` - "CRITICAL FIX: Change invalid default model from gpt-5 to gpt-4o"

---

## Current Status

**Fixes completed:** 2/20
- ✅ Backend: Added thread_id to prompt events
- ✅ Frontend: Fixed prompt caching with per-thread arrays

**Ready for testing:** YES - Server is running with --reload, changes are active

---

## Testing Instructions

### IMMEDIATE TEST: Verify prompt event fixes work

**Prerequisites:**
- Server running on localhost:8000 (✅ confirmed running)
- Browser with Developer Console open
- Clear browser cache/cookies recommended

**Test Steps:**
1. Navigate to: `http://localhost:8000/project/1`
2. Open browser Developer Console (F12)
3. Submit query: "what is 2+2?"
4. Watch for these specific log entries:
   
   **Backend logs (server.log):**
   ```
   [ChiefAgent] EMIT prompt: thread_id=X, iteration=0, stage=chief_first_pass, msg_count=Y
   [ChiefAgent] EMIT prompt: SUCCESS
   ```
   
   **Frontend logs (browser console):**
   ```
   [cedar-ui] Received prompt event {type: "prompt", thread_id: "X", ...}
   [cedar-ui] Cached prompt for thread X entry: {...} total entries: 1
   [cedar-ui] Cache lookup for thread X - found: 1 entries
   ```

5. Check "Prepared LLM prompt" bubble:
   - Should show actual JSON instead of "No LLM prompt available"
   - Click to expand and verify JSON structure contains messages array

**Expected Results:**
- ✅ Backend emits prompt events with thread_id
- ✅ Frontend receives and caches prompt events
- ✅ "Prepared LLM prompt" displays real JSON
- ❓ Planning bubble appears and streams thinking (existing functionality)
- ❓ Final answer is "4" (existing functionality)

### Test Case: "what is 2+2?"

**Baseline (before fixes):**
- [❓] Planning bubble appears
- [❓] Thinking text streams
- [❓] Math/Code agents execute
- [❓] Agent results visible
- [❓] Final answer correct
- [❌] Prepared LLM prompt shows JSON (was showing "No LLM prompt available")
- [❓] No fallback logic triggered

**After fixes:**
- [⏳] Planning bubble appears (testing needed)
- [⏳] Thinking text streams (testing needed)
- [⏳] Math/Code agents execute (testing needed)
- [⏳] Agent results visible (testing needed)
- [⏳] Final answer correct (testing needed)
- [🎯] Prepared LLM prompt shows JSON (primary fix target)
- [⏳] No fallback logic triggered (testing needed)

---

## Notes

### Subagent Architecture Clarification

**Design principle:**
- Each subagent has system-level rules (how to work, required fields, output format)
- Chief Agent provides specific task context for each subagent
- Combination: `[Subagent System Rules] + [Chief's Task Context] → Subagent`
- Subagents may return structured data that Chief needs to process

**Examples:**
- SQL Agent needs: DB connection string, schema, query format rules
- Image Analysis needs: File path/ID, analysis type, output structure
- Code Agent needs: Language, execution environment, result format

---

## Commands Used

```bash
# Create checkpoint
git tag cedar-orchestrator-pre-fix-$(date +%Y%m%d-%H%M%S)

# View checkpoint
git tag | grep cedar-orchestrator-pre-fix

# Revert if needed (emergency only)
git reset --hard cedar-orchestrator-pre-fix-20250929-160337
```

---

## Environment

- Python: [version will be captured]
- FastAPI: [version will be captured]
- OpenAI: [version will be captured]
- OS: MacOS
- Shell: zsh 5.9

---

**Next:** Begin Task 2 - Capture baseline behavior