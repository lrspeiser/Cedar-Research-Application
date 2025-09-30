# LLM Output Principle

## Core Rule: LLM Formats, Code Extracts

**Our code NEVER parses or manipulates LLM text output.** The only exception is when we need to execute specific commands from the LLM (SQL queries, Python code, shell commands, URLs to scrape, file paths to read, etc.).

## Why This Matters

1. **Simplicity**: No complex regex, no brittle parsing logic
2. **Flexibility**: LLM can change output format without breaking code
3. **Maintainability**: All formatting decisions in one place (the prompt)
4. **Reliability**: No "trying to detect sections" or "guessing structure"

## What We Do Instead

### ✅ Correct Approach

```python
# Extract JSON fields
final_answer = chief_decision.get('final_answer', '')

# Display AS-IS - no parsing
final_text = final_answer
```

The LLM's prompt explicitly states:
```
"final_answer": "Complete formatted text response with markdown. Include everything the user should see: answer, explanation, next steps, etc. YOU format it ALL - punchline first, then details."

IMPORTANT:
- Our code displays final_answer AS-IS, no parsing or manipulation
```

### ❌ Wrong Approach

```python
# DON'T DO THIS - parsing LLM output
answer_match = re.search(r'Answer:\s*(.+?)(?=\n\n|$)', result_text, re.DOTALL)
why_match = re.search(r'Why:\s*(.+?)(?=\n\n|$)', result_text, re.DOTALL)

if answer_match:
    answer = answer_match.group(1).strip()
    # ... more parsing logic
```

## The Exception: Executable Commands

We DO parse/extract when we need to **execute** something:

```python
# ✅ These are OK - we're extracting commands to execute
sql_query = agent_response.get('sql')  # Extract SQL to run
code_to_run = agent_response.get('code')  # Extract Python to execute
shell_command = agent_response.get('command')  # Extract shell command
file_path = agent_response.get('file_path')  # Extract file to read
url = agent_response.get('url')  # Extract URL to scrape
```

## JSON Schema Design

Our JSON schemas have two types of fields:

### 1. Display Fields (LLM formats)
- `final_answer` - Complete formatted text for user
- `user_facing_message` - Brief formatted explanation
- `clarification_question` - Formatted question text

**Code behavior**: Display AS-IS, no parsing

### 2. Action Fields (Code processes)
- `decision` - "final" | "loop" | "clarify" (routing logic)
- `agents_to_use` - List of agent names (agent dispatch)
- `sql` - SQL statement (execute query)
- `code` - Python code (run in sandbox)
- `command` - Shell command (execute)
- `file_path` - File path (read/write)

**Code behavior**: Parse, validate, execute

### 3. Metadata Fields (Code logs/tracks)
- `reasoning` - Why this decision (for logging)
- `thinking_process` - Internal thought process (for logging)
- `confidence` - Numeric confidence score (for ranking)

**Code behavior**: Log, track, compare - never display to user

## Examples

### Chief Agent JSON (Synthesis Phase)

```json
{
  "decision": "final",
  "final_answer": "**The answer is 4.**\n\nI used CodeAgent to calculate 2+2, which executed Python and verified the result. This is mathematically correct.\n\n**Why this matters**: While simple, using code execution ensures accuracy and demonstrates the workflow.\n\n**Next steps**: Try more complex calculations or ask about mathematical derivations.",
  "selected_agent": "CodeAgent",
  "reasoning": "Simple arithmetic - CodeAgent executed and verified"
}
```

**Our code does**:
- Checks `decision` field → routes to "final" handler
- Extracts `final_answer` → displays AS-IS
- Logs `reasoning` → not displayed to user

**Our code does NOT do**:
- Parse "**The answer is 4.**" to extract the number
- Detect "Why this matters:" section
- Try to find "Next steps:" section
- Manipulate the markdown formatting

### CodeAgent JSON (Execution)

```json
{
  "answer": "The sum is 100",
  "code": "result = sum(range(1, 11))\nprint(f'The sum is {result}')",
  "why": "Using Python's sum() and range() to calculate efficiently"
}
```

**Our code does**:
- Extracts `code` field → **executes in sandbox**
- Extracts `answer` → displays AS-IS
- Logs `why` → for context

**Our code does NOT do**:
- Parse "The sum is 100" to extract the number
- Modify the answer text
- Try to detect code blocks in the answer

## Updating Prompts

When you want to change output format:

1. **Update the prompt** to describe the new format
2. **Update the JSON schema** in the prompt
3. **Code changes**: Usually none needed!

Example: Want to add a "confidence level" to final answers?

```json
{
  "decision": "final",
  "final_answer": "4\n\n**Confidence**: High - verified by code execution"
}
```

Just update the prompt instruction:
```
"final_answer": "Direct answer, then on a new line add '**Confidence**: High/Medium/Low' with brief explanation"
```

No code changes needed - we display `final_answer` AS-IS.

## Checklist

Before adding any text parsing logic, ask:

- [ ] Am I parsing to **display** differently? → ❌ Update the prompt instead
- [ ] Am I parsing to **execute** a command? → ✅ OK, extract and execute
- [ ] Am I parsing to **route/decide**? → Use JSON field, not text parsing
- [ ] Am I parsing to **validate**? → Add validation rules to prompt

## Summary

- **LLM formats** → user-facing text with markdown, structure, sections
- **Code extracts** → JSON fields for routing, commands for execution
- **No parsing** → display text AS-IS, let LLM handle formatting
- **Exception** → only parse when extracting executable commands (SQL, code, shell, URLs, paths)