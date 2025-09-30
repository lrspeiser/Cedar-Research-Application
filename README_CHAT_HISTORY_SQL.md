# Chat History SQL Storage

## Overview

The chat history system stores all chat conversations in SQL with each message as a separate database record. This enables:

- **Efficient querying**: Search across all chat messages, filter by role, agent, or content
- **Guaranteed ordering**: Messages are ordered by sequence_number within each chat
- **Rich metadata**: Store structured data with each message for analysis
- **Scalability**: No file I/O bottlenecks, all data in indexed SQL tables
- **Analytics**: Generate statistics and insights from chat data

## Database Schema

### `chats` Table

Stores chat session metadata.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-incrementing primary key |
| `project_id` | Integer (FK) | Reference to projects table |
| `branch_id` | Integer (FK) | Reference to branches table |
| `chat_number` | Integer | Sequential number within project/branch (1, 2, 3...) |
| `thread_id` | Integer (FK, nullable) | Optional link to threads table |
| `title` | String(255) | Chat title (defaults to "Chat N") |
| `status` | String(20) | Chat status: active, processing, complete, error |
| `created_at` | DateTime (UTC) | When chat was created |
| `updated_at` | DateTime (UTC) | When chat was last modified |
| `metadata_json` | JSON | Additional metadata |

**Indexes:**
- Unique constraint on `(project_id, branch_id, chat_number)`
- Index on `(project_id, branch_id, created_at)` for listing
- Index on `status` for filtering

### `chat_messages` Table

Stores individual chat messages. **Each message is a separate record.**

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-incrementing primary key |
| `chat_id` | Integer (FK) | Reference to chats table |
| `project_id` | Integer | Denormalized for fast queries |
| `branch_id` | Integer | Denormalized for fast queries |
| `sequence_number` | Integer | Order within chat (1, 2, 3...) |
| `role` | String(20) | Message role: user, assistant, system, agent |
| `content` | Text | Message content |
| `metadata_json` | JSON | Structured data (prompts, results, etc.) |
| `agent_name` | String(100) | Which agent generated this message |
| `created_at` | DateTime (UTC) | When message was created |

**Indexes:**
- Unique constraint on `(chat_id, sequence_number)`
- Index on `(chat_id, sequence_number)` for ordering
- Index on `(project_id, branch_id, created_at)` for queries
- Index on `role` for filtering
- Index on `agent_name` for agent analysis

## Usage Examples

### Creating a Chat

```python
from cedar_app.database import get_project_db
from cedar_app.chat_db_utils import create_chat, add_message_to_chat

# Get database session (using dependency injection in FastAPI routes)
project_id = 1
branch_id = 1

for db in get_project_db(project_id):
    # Create new chat
    chat = create_chat(
        db=db,
        project_id=project_id,
        branch_id=branch_id,
        title="Debug Session",
        status='active'
    )
    
    print(f"Created chat #{chat.chat_number}")
```

### Adding Messages

```python
# Add user message
user_msg = add_message_to_chat(
    db=db,
    chat_id=chat.id,
    role='user',
    content='How do I fix this error?',
    metadata={'timestamp': '2025-09-30T16:51:00Z'}
)

# Add assistant message
assistant_msg = add_message_to_chat(
    db=db,
    chat_id=chat.id,
    role='assistant',
    content='Here is the fix...',
    agent_name='code_agent',
    metadata={
        'code_changes': ['file1.py', 'file2.py'],
        'test_results': 'passed'
    }
)
```

### Retrieving Chat History

```python
from cedar_app.chat_db_utils import get_chat_by_number, get_chat_messages

# Get a specific chat with all messages
chat = get_chat_by_number(db, project_id, branch_id, chat_number=5)

if chat:
    print(f"Chat: {chat.title}")
    print(f"Status: {chat.status}")
    print(f"Messages: {len(chat.messages)}")
    
    # Messages are ordered by sequence_number
    for msg in chat.messages:
        print(f"[{msg.sequence_number}] {msg.role}: {msg.content[:50]}...")
```

### Listing All Chats

```python
from cedar_app.chat_db_utils import list_chats

# Get recent chats
chats = list_chats(
    db=db,
    project_id=project_id,
    branch_id=branch_id,
    limit=10,
    status='active'  # Optional filter
)

for chat_summary in chats:
    print(f"Chat #{chat_summary['chat_number']}: {chat_summary['title']}")
    print(f"  Messages: {chat_summary['message_count']}")
    print(f"  Updated: {chat_summary['updated_at']}")
```

### Searching Messages

```python
from cedar_app.chat_db_utils import search_chat_messages

# Search for messages containing specific text
results = search_chat_messages(
    db=db,
    project_id=project_id,
    branch_id=branch_id,
    search_text='error',
    role='user',  # Optional: filter by role
    limit=20
)

for chat, message in results:
    print(f"Chat #{chat.chat_number}: {message.content}")
```

### Getting Chat Statistics

```python
from cedar_app.chat_db_utils import get_chat_statistics

stats = get_chat_statistics(db, project_id, branch_id)

print(f"Total chats: {stats['total_chats']}")
print(f"Total messages: {stats['total_messages']}")
print(f"Status breakdown: {stats['status_counts']}")
print(f"Role breakdown: {stats['role_counts']}")
```

## Advanced Queries

### Messages by Agent

```python
from main_models import ChatMessage

# Query all messages from a specific agent
agent_messages = db.query(ChatMessage).filter(
    ChatMessage.project_id == project_id,
    ChatMessage.branch_id == branch_id,
    ChatMessage.agent_name == 'code_agent'
).order_by(ChatMessage.created_at.desc()).limit(100).all()
```

### Recent User Questions

```python
# Get the last 50 user messages
user_questions = db.query(ChatMessage).filter(
    ChatMessage.project_id == project_id,
    ChatMessage.branch_id == branch_id,
    ChatMessage.role == 'user'
).order_by(ChatMessage.created_at.desc()).limit(50).all()
```

### Chat Message Count by Day

```python
from sqlalchemy import func, cast, Date

# Group messages by date
daily_counts = db.query(
    cast(ChatMessage.created_at, Date).label('date'),
    func.count(ChatMessage.id).label('count')
).filter(
    ChatMessage.project_id == project_id,
    ChatMessage.branch_id == branch_id
).group_by('date').order_by('date').all()

for date, count in daily_counts:
    print(f"{date}: {count} messages")
```

### Longest Chats

```python
from main_models import Chat

# Find chats with most messages
chats_with_counts = db.query(
    Chat,
    func.count(ChatMessage.id).label('msg_count')
).join(ChatMessage).filter(
    Chat.project_id == project_id,
    Chat.branch_id == branch_id
).group_by(Chat.id).order_by(desc('msg_count')).limit(10).all()

for chat, msg_count in chats_with_counts:
    print(f"Chat #{chat.chat_number}: {msg_count} messages")
```

## Migration from File-Based Storage

If you have existing file-based chats (JSON files), migrate them to SQL:

```python
from cedar_app.chat_db_utils import migrate_file_based_chat_to_sql
from pathlib import Path

chat_dir = Path("/tmp/cedar_chats")
for chat_file in chat_dir.glob("chat_p1_b1_*.json"):
    migrated_chat = migrate_file_based_chat_to_sql(
        db=db,
        project_id=1,
        branch_id=1,
        chat_file_path=str(chat_file)
    )
    
    if migrated_chat:
        print(f"Migrated chat #{migrated_chat.chat_number}")
```

## Integration with Existing Code

### Updating Chat Status

```python
from cedar_app.chat_db_utils import update_chat_status

# Mark chat as complete when processing finishes
update_chat_status(db, chat_id=chat.id, status='complete')
```

### Getting Active Chat

```python
from cedar_app.chat_db_utils import get_active_chat

# Get the currently active chat (if any)
active = get_active_chat(db, project_id, branch_id)
if active:
    print(f"Resuming chat #{active.chat_number}")
```

## Benefits Over File-Based Storage

1. **Atomic Operations**: Database transactions ensure data consistency
2. **Concurrent Access**: Multiple processes can safely read/write
3. **Efficient Queries**: SQL indexes make searches fast
4. **Data Integrity**: Foreign keys and constraints prevent orphaned data
5. **Scalability**: No file system limitations
6. **Backup/Recovery**: Standard database backup tools work
7. **Analytics**: Easy to generate insights and statistics

## Performance Considerations

- Messages are denormalized with `project_id` and `branch_id` for faster queries
- Indexes on commonly queried columns (role, agent_name, timestamps)
- Use `joinedload` for eager loading when fetching chats with messages
- Pagination supported via limit/offset in query functions

## Notes Integration

The `notes` table already includes a `chat_id` column, allowing notes to reference specific chats:

```python
from main_models import Note

# Create a note linked to a chat
note = Note(
    project_id=project_id,
    branch_id=branch_id,
    chat_id=chat.chat_number,  # Link to chat
    content="Important finding from this conversation",
    note_type='agent_finding'
)
db.add(note)
db.commit()
```

## Testing

To test the chat storage system:

```python
# Test chat creation and messaging
for db in get_project_db(1):
    # Create test chat
    chat = create_chat(db, 1, 1, title="Test Chat")
    
    # Add test messages
    for i in range(5):
        add_message_to_chat(
            db, chat.id, 
            role='user' if i % 2 == 0 else 'assistant',
            content=f"Test message {i+1}"
        )
    
    # Verify retrieval
    retrieved = get_chat_by_number(db, 1, 1, chat.chat_number)
    assert len(retrieved.messages) == 5
    print(f"✓ Chat {chat.chat_number} created with 5 messages")
```

## Error Handling

All database operations include error handling with logging:

```python
try:
    chat = create_chat(db, project_id, branch_id, title="My Chat")
except Exception as e:
    print(f"[chat-error] Failed to create chat: {e}")
    # Handle error appropriately
```

## Future Enhancements

Possible future improvements:

- Full-text search using database FTS capabilities
- Message threading/replies within a chat
- Export chat to various formats (PDF, Markdown, HTML)
- Chat templates and cloning
- Message reactions/annotations
- Chat sharing and collaboration features

## See Also

- `main_models.py` - Database model definitions
- `cedar_app/database.py` - Database connection and migration management
- `cedar_app/chat_db_utils.py` - Chat utility functions
- `cedar_app/utils/chat_persistence.py` - Legacy file-based chat manager (still available for compatibility)
