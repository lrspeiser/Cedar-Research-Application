# Cedar Orchestration Flow - Issues Analysis and Remediation Plan

**Created:** 2025-09-29  
**Status:** Investigation Complete - Ready for Implementation

## Executive Summary

The Cedar orchestrator is not following the intended flow described by the user. Several critical issues have been identified in how the Chief Agent coordinates with subagents, handles context, and streams results to the UI.

## Expected Flow (User's Design Intent)

1. **User submits prompt** → System assembles ALL context:
   - Original user prompt (preserved verbatim)
   - Thread history (full, untruncated)
   - Notes history
   - Chief Agent system prompt
   - Subagent usage guide

2. **Chief Agent first pass** → Streams thinking:
   - Analyzes what user wants
   - Determines what needs to be done
   - Identifies required subagents
   - Streams this analysis to UI (planning bubble)

3. **Chief Agent crafts subagent prompts**:
   - Original content + thinking → creates specific prompts for each subagent
   - Each subagent gets tailored instructions based on Chief's analysis

4. **Subagents execute in parallel** → Return results to Chief

5. **Chief Agent synthesis**:
   - Appends subagent results to original prompt (NEVER truncates)
   - Attempts to solve the problem

6. **Notes Agent runs** → Tracks conversation/decisions

7. **Chief Agent decision**:
   - Final answer, OR
   - Clarification question, OR
   - Another iteration with subagents

8. **Error handling**:
   - Logs + original thread passed back to Chief (up to 3 retries)
   - NO FALLBACKS
   - After 3 failures → "Sorry, your request failed."

## Current Issues Identified

### 1. Prompt Event Not Being Cached Properly

**File:** `cedar_orchestrator/orchestrator.py` line ~278  
**Issue:** The "prompt" event is emitted but may not include thread_id consistently, or the payload structure doesn't match what the UI expects.

**Evidence:** In the screenshot, "Prepared LLM prompt" shows "No LLM prompt available" even though the system ran successfully.

**Root Cause:**
- Inconsistent thread_id type (int vs string) between backend emit and frontend cache key
- Missing or incomplete prompt event payload
- UI cache lookup failing due to key mismatch

### 2. Message Assembly Not Preserving Full Context

**File:** `cedar_orchestrator/orchestrator.py` lines 214-272  
**Issue:** Multiple message assembly paths exist, leading to inconsistent context inclusion.

**Problems Found:**
- Original user prompt may get replaced instead of preserved
- Subagent results are passed but original context might be truncated
- No single source of truth for message assembly
- Conversation history passed separately instead of as part of unified context

### 3. Chief Agent Called Twice But Purpose Unclear

**Current Flow:**
```
Line 704: chief_agent.review_and_decide()  # First call - planning
Line 1056: chief_agent.review_and_decide() # Second call - synthesis?
```

**Issue:** 
- First call (line 704) runs with empty agent_results
- Second call (line 1056) runs with ws=None (doesn't emit thinking)
- The two-phase intent (first-pass planning → synthesis) is not explicit
- No clear "subagent prompt crafting" step between the two calls

### 4. Fallback Logic Exists Despite "No Fallbacks" Rule

**File:** `cedar_orchestrator/orchestrator.py` lines 80-82, 436-451, 482-492  
**Issue:** Multiple fallback paths that return "best available result" when errors occur.

**User's Rule:** NO FALLBACKS. If something fails and the LLM cannot fix it after 3 retries, show "Sorry, your request failed."

### 5. Subagent Architecture Needs Clarification

**File:** Various agent files  
**Issue:** Current implementation mixes agent-specific rules with task instructions.

**Expected Architecture:**
- Each subagent maintains its own system-level rules (how to work, required fields, output format)
- Chief Agent crafts the specific task/context for each subagent
- The combination is: [Subagent System Rules] + [Chief's Task Context] → Subagent
- Subagents may return structured data that the Chief needs to process (e.g., SQL results, image analysis metadata)

### 6. UI Event Handling Inconsistencies

**File:** `cedar_app/utils/page_rendering.py` lines 869-1514  
**Issue:**
- "prompt" event handler exists but may not normalize thread_id before caching
- Cache lookup at line 1474 may use different thread_id representation
- No debug logging to trace cache state
- "Prepared LLM prompt" bubble logic has multiple fallback paths that mask the real issue

## Remediation Plan

See the TODO list for 20 specific tasks that address these issues systematically:

### Phase 1: Foundation (Tasks 1-5)
- Create checkpoint and enable debugging
- Capture baseline of current behavior
- Fix prompt event emission
- Repair UI prompt caching
- Guarantee thinking streaming works

### Phase 2: Core Architecture (Tasks 6-11)
- Refactor message assembly (single source of truth)
- Implement explicit first-pass planning phase
- Ensure Chief crafts all subagent prompts
- Execute subagents with proper error handling
- Chief synthesis with full context
- Run Notes Agent consistently

### Phase 3: Reliability (Tasks 12-14)
- Remove all fallback logic
- Add structured retry mechanism
- Standardize UI event handling
- Verify token window handling

### Phase 4: Quality & Observability (Tasks 15-20)
- Automated tests (unit, integration, E2E)
- Structured logging
- Documentation updates
- Remove obsolete code
- Commit to main
- Final verification

## Key Principles to Enforce

1. **Full Context Always:** Original prompt NEVER truncated, always at the top
2. **No Fallbacks:** Errors bubble up with full context for retry or final failure
3. **Chief Drives Everything:** Subagents are tools; Chief crafts their prompts
4. **Explicit State Machine:** Planning → Subagents → Synthesis → Notes → Decision
5. **Transparency:** All prompts, errors, and logs visible for debugging
6. **Single Source of Truth:** One message assembly function, no legacy paths

## Next Steps

1. Start with Task 1 (Create checkpoint)
2. Work through tasks sequentially
3. Commit each logical change to main with clear messages
4. Run tests continuously
5. Update FIX_NOTES.md with findings as we go

## Success Criteria

When we run "what is 2+2?":
- ✅ Planning bubble shows Chief Agent thinking
- ✅ Math/Code agents execute (visible as cards)
- ✅ Chief synthesizes with full context
- ✅ Final answer shows "4" with brief reasoning
- ✅ "Prepared LLM prompt" bubble displays actual JSON (not "No LLM prompt available")
- ✅ No fallback logic triggered
- ✅ All WebSocket events fire in correct order

## Files to Modify

Primary:
- `cedar_orchestrator/orchestrator.py` (core flow)
- `cedar_app/utils/page_rendering.py` (UI events)
- `cedar_orchestrator/ws_chat.py` (WebSocket handling)

Secondary:
- Individual agent files (for prompt crafting)
- Test files (new tests)
- README.md, FIX_NOTES.md (documentation)

## Timeline Estimate

- Foundation: 2-3 hours
- Core Architecture: 4-6 hours
- Reliability: 2-3 hours
- Quality & Observability: 3-4 hours

**Total: 11-16 hours** (spread over 2-3 work sessions)

---

**Note:** All commits will go directly to `main` per user's workflow. No branches will be used.