# Prompt Management System

## Date: 2025-09-30

## ZERO DUPLICATES POLICY

**Every prompt exists in EXACTLY ONE place in the codebase.**

## How It Works

### 1. Prompts Live in Agent Implementation Files

All agent prompts are defined ONLY in these files:
- `cedar_orchestrator/specialized_agents.py` - FormulaAgent, ResearchAgent, DataAgent, NotesAgent, StrategyAgent
- `cedar_orchestrator/execution_agents.py` - CodeAgent, ShellAgent, SQLAgent
- `cedar_orchestrator/orchestrator.py` - ChiefAgent

### 2. Dynamic Extraction for Documentation

The file `cedar_orchestrator/agent_prompts.py` does NOT contain any actual prompts. Instead, it:
- Uses regex to read agent source files at runtime
- Extracts the `"content": """..."""` from system messages
- Provides these to the `/agents` documentation page

**Key Point:** If you change a prompt in an agent implementation, the `/agents` page automatically shows the new prompt. No manual updates needed.

## Verification

### Current State (Verified 2025-09-30)

```bash
# Each prompt appears exactly ONCE in the codebase:

$ rg -c "You are a data analysis expert" --type py
cedar_orchestrator/specialized_agents.py:1

$ rg -c "You are a research assistant" --type py
cedar_orchestrator/specialized_agents.py:1

$ rg -c "You are a note-taking expert" --type py
cedar_orchestrator/specialized_agents.py:1
```

## Architecture

```
┌─────────────────────────────────────┐
│  Agent Implementation Files         │
│  (specialized_agents.py, etc.)      │
│                                     │
│  - Contains ACTUAL prompts          │
│  - Used by runtime execution        │
│  - SINGLE SOURCE OF TRUTH           │
└──────────────┬──────────────────────┘
               │
               │ (extracted at runtime)
               │
               ▼
┌─────────────────────────────────────┐
│  agent_prompts.py                   │
│                                     │
│  - NO hardcoded prompts             │
│  - Uses regex extraction            │
│  - Provides to /agents page         │
└──────────────┬──────────────────────┘
               │
               │ (displays)
               │
               ▼
┌─────────────────────────────────────┐
│  /agents Documentation Page         │
│                                     │
│  - Shows what's actually running    │
│  - Always in sync with code         │
│  - Never out of date                │
└─────────────────────────────────────┘
```

## Rules

1. **NEVER copy prompts** - If you need to show a prompt somewhere, extract it dynamically
2. **NEVER create backup prompt files** - The git history is the backup
3. **If extraction fails** - Fix the extraction logic, don't create a manual copy
4. **One source of truth** - Agent implementation files are the ONLY place prompts live

## Recent Changes (2025-09-30)

### What Was Wrong
- Old `agent_prompts.py` had 500+ lines of manually copied prompts
- Prompts were duplicated between implementation and documentation
- Documentation showed OLD prompts that didn't match actual implementation
- DataAgent, ResearchAgent, NotesAgent had JSON schemas in code but plain text in docs

### What Was Fixed
1. **Deleted** old `agent_prompts.py` entirely (commit 4d4eb35)
2. **Created** new `agent_prompts.py` with dynamic extraction (commit 114f1af)
3. **Verified** each prompt appears exactly once in codebase

### Test Results
```python
from cedar_orchestrator.agent_prompts import get_data_agent_prompt

# Extracts ACTUAL prompt from specialized_agents.py:
print(get_data_agent_prompt()[:300])
# Output: "You are a data analysis expert. Based on the available 
# database schema and the user's query, provide analysis.
# You must respond ONLY with valid JSON matching this schema:
# {
#     "relevant_tables": [..."
```

## Maintenance

### Adding a New Agent
1. Create agent class in appropriate file (e.g., `specialized_agents.py`)
2. Add system prompt in the `completion_params` messages
3. Add extraction function to `agent_prompts.py`:
   ```python
   def get_new_agent_prompt() -> str:
       file_path = ORCHESTRATOR_DIR / "specialized_agents.py"
       return extract_prompt_from_agent(str(file_path), "NewAgent", "process")
   ```
4. Add to `AGENTS_METADATA` list

### Changing an Agent Prompt
1. Edit the prompt ONLY in the agent implementation file
2. Nothing else needed - extraction happens automatically
3. Restart server to see changes on `/agents` page

### Debugging Extraction
If extraction fails with `[Could not find class ...]`:
1. Check class name spelling matches exactly
2. Verify class definition format (with/without parentheses)
3. Check system prompt is in format: `"role": "system", "content": """..."""`
4. Fix regex in `extract_prompt_from_agent()` if needed

## Related Commits

- `4d4eb35` - DELETE agent_prompts.py - removing ALL duplicate/backup prompts
- `114f1af` - CREATE new agent_prompts.py with DYNAMIC prompt extraction from source code
- `170dd01` - Fix agent_prompts.py - update DataAgent, ResearchAgent, NotesAgent to show JSON schemas
- `2bc74ea` - Remove JSON fallback logic from ResearchAgent, DataAgent, and NotesAgent - fail fast instead

## Philosophy

> "Code should be the source of truth. Documentation should extract from code, not duplicate it."

When prompts are duplicated:
- ❌ They drift out of sync
- ❌ Changes get missed
- ❌ Users see wrong information
- ❌ Debugging is harder

When prompts are extracted dynamically:
- ✅ Always accurate
- ✅ Single point of maintenance  
- ✅ Impossible to be out of sync
- ✅ Clear what's actually running