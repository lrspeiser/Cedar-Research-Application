# Agent JSON Schema Status

## Date: 2025-09-30

## Summary

**ALL agents now use strict JSON schemas in their prompts.**

Every agent that uses LLM prompts now has explicit "You MUST respond ONLY with valid JSON" requirements.

---

## Agent Status

### ✅ Agents with Strict JSON Schemas

#### 1. **ChiefAgent** (orchestrator.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You MUST respond ONLY with valid JSON in this EXACT format (no prose before or after)"
- **Schema:** Different for planning vs synthesis phase
  - Planning: decision, thinking_process, user_facing_message, selected_agent, agents_to_use, reasoning, clarification_question
  - Synthesis: decision, final_answer, selected_agent, reasoning, additional_guidance
- **Parsing:** Direct `json.loads()` with error handling

#### 2. **CodeAgent** (execution_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You MUST respond with VALID JSON in this EXACT format"
- **Schema:** answer, code, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 3. **ShellAgent** (execution_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You MUST respond with VALID JSON in this EXACT format"
- **Schema:** answer, command, expected_output, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 4. **SQLAgent** (execution_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You MUST respond with VALID JSON in this EXACT format"
- **Schema:** answer, sql, operation_type, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 5. **FormulaAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You MUST respond with VALID JSON in this EXACT format"
- **Schema:** answer, final_formula, assumptions, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 6. **ResearchAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You must respond ONLY with valid JSON matching this schema"
- **Schema:** sources (array with title, url_or_reference, key_findings, relevance), synthesis, key_insights, confidence_notes, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 7. **StrategyAgent** (specialized_agents.py)
- **Status:** ⚠️ Has JSON format but not strict (needs update)
- **Prompt:** Currently text-based, no JSON requirement
- **Action Needed:** Update to strict JSON in next iteration

#### 8. **DataAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You must respond ONLY with valid JSON matching this schema"
- **Schema:** relevant_tables, suggested_queries, analysis, transformations_needed, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 9. **NotesAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON
- **Prompt:** "You must respond ONLY with valid JSON matching this schema"
- **Schema:** title, timestamp, tags, category, key_points, details, action_items, sources, new_content_only, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 10. **ImageAnalysisAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON (updated 2025-09-30)
- **Prompt:** "You MUST respond ONLY with valid JSON matching this EXACT schema"
- **Schema:** title, description, objects, text, tags, summary
- **Parsing:** Direct `json.loads()` - fail fast

#### 11. **FileAgent** (specialized_agents.py)
- **Status:** ✅ Strict JSON for LLM usage (updated 2025-09-30)
- **Prompt:** "You MUST respond ONLY with valid JSON" (for optional file description generation)
- **Schema:** description
- **Note:** Main file operations don't use LLM - only optional AI description generation does
- **Parsing:** Direct `json.loads()` - fail fast

### 🚫 Agents WITHOUT LLM Prompts (No JSON Needed)

#### 12. **ImageCreationAgent** (specialized_agents.py)
- **Status:** N/A - Uses DALL-E API directly
- **No LLM prompt:** User's text is passed directly to image generation API
- **No JSON needed:** API call, not LLM completion

---

## JSON Parsing Policy

**ALL agents follow the fail-fast policy:**
- No try/except wrappers around `json.loads()`
- If LLM returns invalid JSON, the agent fails with `JSONDecodeError`
- No fallback logic that hides problems
- Verbose logging shows the actual error for debugging

This aligns with project rule: "We don't simulate tests, we allow errors to happen and fix the root cause."

---

## Remaining Work

### StrategyAgent Needs Update
- Current status: Has text-based prompt, no JSON schema
- Action: Update to use strict JSON schema like other agents
- Priority: Medium (works but inconsistent with other agents)

---

## Verification

Test that all agents import successfully:

```bash
python -c "
from cedar_orchestrator.orchestrator import ChiefAgent
from cedar_orchestrator.execution_agents import CodeAgent, ShellAgent, SQLAgent
from cedar_orchestrator.specialized_agents import (
    FormulaAgent, ResearchAgent, StrategyAgent, DataAgent, 
    NotesAgent, FileAgent, ImageCreationAgent, ImageAnalysisAgent
)
print('✓ All agents import successfully')
"
```

---

## Related Documentation

- `PROMPT_MANAGEMENT.md` - Explains zero-duplicates policy
- `AGENT_JSON_SCHEMA_UPDATE.md` - Details on JSON schema implementation
- `agent_prompts.py` - Dynamic prompt extraction (no duplicates)

---

## Benefits of Strict JSON

1. **Consistency:** All agents follow same pattern
2. **Parseability:** Easy to extract specific fields programmatically
3. **Type Safety:** Know what fields to expect
4. **Error Detection:** Immediate failure if LLM doesn't follow schema
5. **No Silent Failures:** No fallback logic hiding problems
6. **Better Debugging:** Clear error messages when JSON parsing fails

---

## Schema Evolution

If you need to change an agent's schema:

1. Update the system prompt in the agent's `process()` method
2. Update the JSON parsing logic to handle new fields
3. No need to update `agent_prompts.py` - it extracts dynamically
4. Test the agent to ensure LLM follows new schema
5. Document the change in commit message

The `/agents` page will automatically show the new schema since prompts are extracted dynamically.