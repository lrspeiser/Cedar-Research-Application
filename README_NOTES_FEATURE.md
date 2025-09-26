# Cedar Notes Feature Documentation

## Overview
The Notes feature in Cedar has been enhanced to provide persistent, database-backed note storage with rich metadata tracking and integration with the Chief Agent orchestration system.

## Key Features

### 1. **Automatic Project Initialization Notes**
- When a new project is created, a system note is automatically added with the creation timestamp
- Uses friendly date/time formatting (e.g., "December 20, 2024 at 3:45 PM UTC")
- Tagged as a "system" note for easy filtering

### 2. **Enhanced Note Model**
The Note model now includes comprehensive metadata fields:

#### Core Fields
- `id`: Primary key
- `project_id`: Associated project
- `branch_id`: Associated branch
- `content`: Note content (text or JSON)
- `tags`: JSON array of string tags

#### Source Tracking
- `chat_id`: Chat number where the note was created
- `thread_id`: Thread ID if created in a thread context
- `agent_name`: Name of the agent that created the note
- `user_query`: Original user query that triggered the note

#### Metadata
- `note_type`: Type of note ('general', 'system', 'agent_finding', 'user_note')
- `title`: Optional title for the note
- `priority`: Priority level (0=normal, 1=high, 2=critical)

#### Timestamps
- `created_at`: Creation timestamp (UTC)
- `updated_at`: Last update timestamp (UTC)

### 3. **Improved UI Display**

The Notes tab now features:

- **Rich Formatting**: Support for JSON structured content, markdown-style text, and plain text
- **Priority Indicators**: Visual indicators for high (🟡) and critical (🔴) priority notes
- **Metadata Display**: Shows note type, creating agent, and associated chat number
- **Tag Pills**: Visual tags for easy categorization
- **System Notes**: Special styling for system-generated notes
- **Friendly Timestamps**: Human-readable date/time format

### 4. **Database Integration**

Notes are now persisted in the SQLite database with:

- Proper indexing for efficient queries
- Support for filtering by project, branch, chat, and thread
- Type-based categorization for different note sources

## Usage

### Creating Notes Programmatically

```python
from main_models import Note
from datetime import datetime, timezone

# Create a note
note = Note(
    project_id=project.id,
    branch_id=branch.id,
    content="Important finding about the codebase",
    title="Code Analysis Result",
    note_type="agent_finding",
    agent_name="Code Analyzer",
    chat_id=current_chat_id,
    priority=1,  # High priority
    tags=["analysis", "important"]
)
db.add(note)
db.commit()
```

### Note Content Formats

#### Plain Text
```python
note.content = "This is a simple text note"
```

#### Structured JSON (Themes)
```python
note.content = json.dumps({
    "themes": [
        {
            "name": "Key Findings",
            "notes": [
                "Found security vulnerability in auth module",
                "Performance bottleneck in data processing"
            ]
        }
    ]
})
```

#### Structured JSON (Sections)
```python
note.content = json.dumps({
    "sections": [
        {
            "title": "Security Analysis",
            "text": "Detailed security findings..."
        },
        {
            "title": "Performance Review",
            "text": "Performance metrics and recommendations..."
        }
    ]
})
```

## Chief Agent Integration

The Chief Agent can now:

1. **Create Notes**: Automatically create notes during task execution
2. **Update Notes**: Modify existing notes with new information
3. **Query Notes**: Access notes for context during decision-making
4. **Tag Notes**: Apply appropriate tags for categorization

### Example Chief Agent Prompt Extension

```python
# In the Chief Agent orchestration payload
notes_context = db.query(Note).filter(
    Note.project_id == project_id,
    Note.branch_id == branch_id
).order_by(Note.created_at.desc()).limit(10).all()

# Include in prompt
prompt += f"""
Recent Notes:
{format_notes_for_prompt(notes_context)}

You can create or update notes using SQL:
INSERT INTO notes (project_id, branch_id, content, title, note_type, agent_name) 
VALUES (?, ?, ?, ?, ?, ?);
"""
```

## Migration

For existing projects, run the migration script to add new fields:

```bash
python migrations/add_note_fields.py
```

This script will:
1. Find all existing project databases
2. Add new columns to the notes table
3. Create necessary indexes
4. Preserve existing note data

## API Endpoints

### View Notes
- **GET** `/project/{project_id}?branch_id={branch_id}#main-notes`
- Displays all notes for the current project/branch

### Add Note (future enhancement)
- **POST** `/project/{project_id}/notes/add`
- Allows manual note creation through the UI

### Refresh Notes
- **GET** `/project/{project_id}?branch_id={branch_id}&refresh_notes=1`
- Forces a refresh of the notes display

## Best Practices

1. **Use Appropriate Note Types**
   - `system`: For automated system events
   - `agent_finding`: For AI-generated insights
   - `user_note`: For manual user notes
   - `general`: For uncategorized notes

2. **Apply Meaningful Tags**
   - Use consistent tag naming conventions
   - Include context-specific tags (e.g., "security", "performance", "bug")

3. **Set Priority Levels**
   - Use priority=2 for critical issues requiring immediate attention
   - Use priority=1 for important but non-critical items
   - Use priority=0 for general information

4. **Include Source Context**
   - Always set `chat_id` when notes are created from chat
   - Include `agent_name` to track the source of automated notes
   - Store `user_query` to maintain context

## Future Enhancements

- [ ] Manual note creation UI
- [ ] Note editing capabilities
- [ ] Advanced filtering and search
- [ ] Note templates
- [ ] Export functionality
- [ ] Note attachments
- [ ] Collaborative notes with user attribution
- [ ] Note versioning and history