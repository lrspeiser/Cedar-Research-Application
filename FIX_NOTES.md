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

### Fix 1: [Placeholder - will be updated as fixes are applied]

**What was wrong:**

**How it was fixed:**

**Tests run:**

**Logging added:**

**Commit:**

---

## Testing Log

### Test Case: "what is 2+2?"

**Baseline (before fixes):**
- [ ] Planning bubble appears
- [ ] Thinking text streams
- [ ] Math/Code agents execute
- [ ] Agent results visible
- [ ] Final answer correct
- [ ] Prepared LLM prompt shows JSON
- [ ] No fallback logic triggered

**After fixes:**
- [ ] Planning bubble appears
- [ ] Thinking text streams
- [ ] Math/Code agents execute
- [ ] Agent results visible
- [ ] Final answer correct
- [ ] Prepared LLM prompt shows JSON
- [ ] No fallback logic triggered

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