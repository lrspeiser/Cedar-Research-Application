# Agent JSON Schema Update Summary

## Date: 2025-01-29

## Overview
Updated four specialized agents (FormulaAgent, ResearchAgent, DataAgent, NotesAgent) to use structured JSON schema responses instead of free-form text. This improves consistency, parseability, and integration with the ChiefAgent and UI.

---

## Updated Agents

### 1. **FormulaAgent**
**Purpose:** Derives mathematical formulas from first principles with step-by-step reasoning.

**JSON Schema:**
```json
{
  "answer": "step-by-step derivation in markdown with LaTeX formulas",
  "final_formula": "the theorem or formula in LaTeX or text",
  "assumptions": ["assumption 1", "assumption 2"],
  "summary": "brief summary for logging"
}
```

**Key Changes:**
- Structured derivation output with clear separation of steps, final formula, and assumptions
- LaTeX formula support for mathematical notation
- Improved logging with summary field

---

### 2. **ResearchAgent**
**Purpose:** Performs web research and synthesizes information from multiple sources.

**JSON Schema:**
```json
{
  "sources": [
    {
      "title": "source title",
      "url_or_reference": "URL or citation",
      "key_findings": "main findings from this source",
      "relevance": "why this source matters"
    }
  ],
  "synthesis": "comprehensive summary integrating all sources",
  "key_insights": ["insight 1", "insight 2"],
  "confidence_notes": "any limitations or caveats",
  "summary": "brief executive summary for logging"
}
```

**Key Changes:**
- Structured sources with clear metadata (title, URL, findings, relevance)
- Separate synthesis section for integrated analysis
- Key insights extraction for quick reference
- Confidence notes for transparency about limitations

---

### 3. **DataAgent**
**Purpose:** Analyzes database schemas and suggests SQL queries.

**JSON Schema:**
```json
{
  "relevant_tables": [
    {
      "table_name": "table_name",
      "purpose": "what this table contains",
      "relevance": "why it matters for the query"
    }
  ],
  "suggested_queries": [
    {
      "sql": "SELECT ... FROM ...",
      "purpose": "what this query does",
      "expected_result": "what the result tells us"
    }
  ],
  "analysis": "overall analysis of how to approach the data question",
  "transformations_needed": ["transformation 1", "transformation 2"],
  "summary": "brief summary for logging"
}
```

**Key Changes:**
- Structured table analysis with purpose and relevance
- Executable SQL queries with explanations
- Analysis of data approach strategy
- Recommended transformations for data processing

---

### 4. **NotesAgent**
**Purpose:** Creates structured notes from findings and research.

**JSON Schema:**
```json
{
  "title": "clear note title",
  "timestamp": "current date/time or 'auto'",
  "tags": ["tag1", "tag2", "tag3"],
  "category": "main category (e.g., research, code, meeting)",
  "key_points": ["key point 1", "key point 2"],
  "details": "detailed notes in markdown with headings, bullets, code, formulas",
  "action_items": ["action 1", "action 2"],
  "sources": ["source 1", "source 2"],
  "new_content_only": true,
  "summary": "brief summary for logging"
}
```

**Key Changes:**
- Structured note format with title, timestamp, tags, and category
- Separation of key points from detailed content
- Action items tracking
- Source citations
- Duplicate detection support

---

## Benefits

### 1. **Consistency**
- All agents now return predictable, structured data
- Easier to process programmatically
- Standardized error handling

### 2. **Parseability**
- JSON format enables direct integration with UI components
- ChiefAgent can easily extract specific fields
- Better support for downstream processing

### 3. **Error Handling**
- Each agent includes JSON parsing with fallback to raw text
- Graceful degradation if LLM doesn't return valid JSON
- Warning logs for debugging

### 4. **Logging & Debugging**
- Summary fields provide concise logging
- Structured data makes it easier to trace issues
- Better visibility into agent outputs

### 5. **User Experience**
- Formatted output in UI is more readable
- Key information is highlighted
- Sources and citations are clearly displayed

---

## Implementation Details

### Common Pattern
All updated agents follow this pattern:

1. **System Prompt:** Explicitly requests JSON response matching a specific schema
2. **LLM Call:** Gets response from OpenAI API
3. **JSON Parsing:** Attempts to parse response as JSON
4. **Fallback:** If parsing fails, wraps raw text in minimal JSON structure
5. **Formatting:** Converts JSON to human-readable markdown for display
6. **Return:** AgentResult with formatted output and summary

### Error Handling Example
```python
try:
    agent_data = json.loads(raw_content)
except json.JSONDecodeError:
    logger.warning(f"[AgentName] Response was not valid JSON, using raw text")
    agent_data = {"fallback_field": raw_content, "summary": "Agent completed (raw text)"}
```

---

## Next Steps

### Remaining Agents to Update
1. **StrategyAgent** - Planning and orchestration
2. **FileAgent** - Already has some structure but could benefit from JSON schema
3. **SQLAgent** - Already structured but could formalize schema
4. **CodeAgent** - Consider JSON schema for execution results
5. **ShellAgent** - Consider JSON schema for command outputs
6. **ImageCreationAgent** - Could use JSON for metadata
7. **ImageAnalysisAgent** - Could use JSON for detection results

### Future Enhancements
- Add JSON schema validation using `jsonschema` library
- Create TypeScript/Python type definitions for schemas
- Implement schema versioning for backwards compatibility
- Add schema documentation to API docs
- Consider using Pydantic for runtime validation

---

## Testing

### Manual Testing
```bash
# Test import
python -c "import cedar_orchestrator.specialized_agents as sa; print('Successfully imported')"

# Test server startup
python main.py
```

### Integration Testing
- Test each agent through the UI
- Verify JSON parsing works correctly
- Confirm fallback behavior when JSON is malformed
- Check that summaries appear in logs

---

## Related Files
- `cedar_orchestrator/specialized_agents.py` - Main implementation
- `main.py` - Server that uses the agents
- `cedar_orchestrator/orchestrator.py` - ChiefAgent that dispatches to specialized agents

---

## Commit Info
- **Commit Hash:** 1bc1589
- **Message:** "Update ResearchAgent, DataAgent, and NotesAgent to use JSON schema for structured responses"
- **Files Changed:** 1 file (specialized_agents.py)
- **Insertions:** 257 lines
- **Deletions:** 58 lines