# Chief Agent Automatic Note-Taking Feature

## Overview
The Chief Agent has been enhanced with automatic note-taking capabilities. Every time the multi-agent orchestration processes a user query, the Chief Agent automatically creates comprehensive notes in the SQL database that capture:

- The original user query
- Analysis from each participating agent
- The Chief Agent's decision-making process
- Key findings and final answers
- Automatically generated tags for categorization

## How It Works

### 1. During Orchestration
When the `ThinkerOrchestrator` processes a message:
- Multiple specialized agents analyze the query in parallel
- The Chief Agent reviews all results and makes a decision
- After the decision, if database context is available, notes are automatically saved

### 2. Note Structure
Each automatically generated note contains:
```markdown
## Query Analysis - [timestamp]
**User Query:** [original query]

### Structured Notes
[Notes Agent content if available]

### Chief Agent Analysis
**Decision:** [loop/direct]
**Selected Agent:** [chosen agent]
**Reasoning:** [decision reasoning]

### Agent Findings
#### [Agent Name]
- **Confidence:** [score]
- **Method:** [approach used]  
- **Key Finding:** [main result]

### Final Answer
[The final response provided]
```

### 3. Automatic Tagging
Notes are automatically tagged based on:
- Query type (math, code, database, research, strategy, explanation)
- Selected agents (agent:code_agent, agent:math_agent, etc.)
- Decision type (iterative, direct)
- Date (date:YYYY-MM-DD)

## Implementation Details

### Files Modified
1. **`cedar_orchestrator/chief_agent_notes.py`** (NEW)
   - `ChiefAgentNoteTaker` class for managing notes
   - Methods for building comprehensive notes
   - Tag generation logic
   - Database interaction for notes persistence

2. **`cedar_orchestrator/advanced_orchestrator.py`**
   - Added import for `ChiefAgentNoteTaker`
   - Modified `orchestrate()` method to accept database parameters
   - Added automatic note saving after Chief Agent decision

3. **`cedar_orchestrator/ws_chat.py`**  
   - Modified to pass database session to orchestrator
   - Handles database session lifecycle

## Database Schema
Notes are stored in the existing `notes` table:
```sql
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,  -- JSON array of tags
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Usage

### Automatic Operation
Notes are created automatically when:
1. A WebSocket chat connection has a project context
2. A database session is available
3. The orchestration completes successfully

### Viewing Notes
Notes appear automatically in the Notes tab of the Cedar UI for the relevant project and branch.

### Example Flow
1. User sends query: "Calculate the square root of 144"
2. Multiple agents process (MathAgent, CodeAgent, etc.)
3. Chief Agent reviews and decides on best answer
4. **Automatically**: Note is created with:
   - Full analysis from all agents
   - Chief Agent's reasoning
   - Tags: ["math", "agent:math_agent", "direct", "date:2024-12-20"]
5. Note appears in Notes tab immediately

## Benefits

1. **Knowledge Persistence**: All agent analyses are automatically preserved
2. **Learning System**: Notes serve as training data for future improvements
3. **Audit Trail**: Complete record of decision-making process
4. **Searchable History**: Tagged notes enable efficient retrieval
5. **No Manual Effort**: Happens automatically without user intervention

## Configuration

### Enabling/Disabling
The feature is automatically enabled when:
- The `chief_agent_notes` module is available
- A database session can be established
- Project and branch IDs are provided

To disable, you can set `NOTES_AVAILABLE = False` in `advanced_orchestrator.py`

### Customizing Tags
Edit the `_generate_tags()` method in `ChiefAgentNoteTaker` to add custom tag logic.

### Adjusting Note Content
Modify the `_build_comprehensive_notes()` method to change what information is captured.

## Error Handling
- If note saving fails, a warning is logged but orchestration continues
- Database rollback is attempted on failures
- The feature fails gracefully without affecting the main chat functionality

## Future Enhancements
- [ ] Add note templates for different query types
- [ ] Implement note summarization for long analyses  
- [ ] Add cross-referencing between related notes
- [ ] Enable note export in various formats
- [ ] Add note analytics dashboard
- [ ] Implement note-based learning feedback loop

## Testing
To test the automatic note-taking:
1. Start a WebSocket chat with a project context
2. Send any query to the orchestrator
3. Check the Notes tab - a new note should appear
4. Verify the note contains all agent analyses and tags