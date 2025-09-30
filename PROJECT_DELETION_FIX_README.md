# Project Deletion Fix

## Problem

When deleting projects, we were not thoroughly cleaning up all associated data before removing the project directory. This caused two major issues:

1. **Ghost Data**: Data from deleted projects would appear in new projects, especially when project IDs were reused
2. **ID Reuse**: SQLite was reusing project IDs after deletion, causing deleted project data to appear associated with new projects

## Root Causes

### 1. Incomplete Database Cleanup

The `delete_project()` function in `cedar_app/utils/project_management.py` was:
- Only deleting the project and branches from the registry database
- Removing the entire project directory (including the database) without first cleaning records from the per-project database
- Not deleting related data like threads, files, datasets, notes, changelog entries, etc.

This meant that if the database deletion failed for any reason, orphaned records could remain and appear in other projects.

### 2. Project ID Reuse

The `projects` table in the registry database was not using `AUTOINCREMENT`:
```sql
CREATE TABLE projects (
    id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE (title)
)
```

Without `AUTOINCREMENT`, SQLite will reuse IDs from deleted rows, meaning:
- Project with ID 1 deleted → new project could get ID 1
- If any data wasn't properly cleaned from the first project, it would appear in the new project with the same ID

## Solutions Implemented

### 1. Thorough Database Cleanup Before Directory Removal

Enhanced `delete_project()` to properly clean all records from the per-project database **before** removing the directory:

```python
# New cleanup order (respects foreign key constraints):
1. ThreadMessages (references threads)
2. Threads
3. FileEntries
4. Datasets
5. Notes
6. ChangelogEntries
7. SQLUndoLog
8. Branches (from per-project DB)
9. Project record (from per-project DB)
```

Each step includes:
- Error handling with rollback
- Detailed logging for debugging
- Counts of deleted items

### 2. Added AUTOINCREMENT to Projects Table

Updated `main_models.py`:
```python
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)  # Added autoincrement=True
    # ... rest of fields
```

This ensures:
- Project IDs are never reused after deletion
- Each project gets a unique, monotonically increasing ID
- No possibility of data collision between projects

### 3. Migration Script

Created `migrations/add_autoincrement_to_projects.py` to:
- Find the registry database (checks multiple possible locations)
- Create a new table with AUTOINCREMENT
- Copy all data from the old table
- Drop the old table and rename the new one
- Verify data integrity

The migration is idempotent - it checks if AUTOINCREMENT is already present and skips if so.

## What Was Fixed

### Before
```
1. User deletes Project A (ID: 1)
   - Registry record deleted ✓
   - Directory removed ✓
   - Per-project DB records... maybe deleted, maybe not ✗

2. User creates new Project B
   - Gets ID 1 (reused) ✗
   - If Project A's data wasn't fully cleaned, it appears in Project B ✗
```

### After
```
1. User deletes Project A (ID: 1)
   - Close database connections ✓
   - Delete from registry ✓
   - Clean ALL per-project database records (threads, files, notes, etc.) ✓
   - Log each deletion step ✓
   - Remove chat history ✓
   - Remove project directory ✓

2. User creates new Project B
   - Gets ID 2 (never reuses IDs) ✓
   - No ghost data possible ✓
   - Complete data isolation ✓
```

## Testing the Fix

### To Verify Thorough Deletion

1. Create a test project with various data (files, threads, notes, datasets)
2. Check the logs when deleting:
   ```
   [INFO] Deleted project 'Test Project' (ID: 42) from registry
   [INFO] Deleted 10 thread messages for project 42
   [INFO] Deleted 5 threads for project 42
   [INFO] Deleted 3 file entries for project 42
   [INFO] Deleted 2 datasets for project 42
   [INFO] Deleted 7 notes for project 42
   [INFO] Deleted 15 changelog entries for project 42
   [INFO] Deleted 8 undo log entries for project 42
   [INFO] Deleted 2 branches from project DB for project 42
   [INFO] Deleted project record from project DB for project 42
   [INFO] Deleted 3 chats for project 42
   [INFO] Removed project directory: /path/to/projects/42
   ```

### To Verify No ID Reuse

1. Create Project A - note its ID (e.g., 1)
2. Delete Project A
3. Create Project B - verify it gets a different ID (e.g., 2)
4. Verify Project B has no data from Project A

### To Run the Migration

```bash
python3 migrations/add_autoincrement_to_projects.py
```

The script will:
- Find your registry database automatically
- Check if migration is needed
- Apply the AUTOINCREMENT change safely
- Verify data integrity

## Files Changed

1. **cedar_app/utils/project_management.py**
   - Enhanced `delete_project()` with thorough database cleanup
   - Added detailed logging for each deletion step
   - Proper error handling and rollback

2. **main_models.py**
   - Added `autoincrement=True` to Project.id column

3. **migrations/add_autoincrement_to_projects.py**
   - Created migration script to update existing databases
   - Handles multiple database locations
   - Idempotent and safe

## Additional Notes

- The fix maintains backward compatibility - existing projects continue to work
- The migration must be run on existing installations to get AUTOINCREMENT
- New installations automatically get AUTOINCREMENT from the model definition
- All deletions are logged for debugging and verification
- The fix respects foreign key constraints by deleting in proper order

## Logging Output Example

When deleting a project, you'll now see comprehensive logging:

```
[INFO] Disposed database engine for project 42
[INFO] Deleted project 'My Test Project' (ID: 42) from registry
[INFO] Deleted 5 chats for project 42
[INFO] Deleted 15 thread messages for project 42
[INFO] Deleted 3 threads for project 42
[INFO] Deleted 2 file entries for project 42
[INFO] Deleted 1 datasets for project 42
[INFO] Deleted 4 notes for project 42
[INFO] Deleted 10 changelog entries for project 42
[INFO] Deleted 5 undo log entries for project 42
[INFO] Deleted 2 branches from project DB for project 42
[INFO] Deleted project record from project DB for project 42
[INFO] Removed project directory: /Users/user/CedarPyData/projects/42
[INFO] Project deletion complete - My Test Project (ID: 42)
[INFO] Deleted: {'branches': 2, 'files': 2, 'threads': 3, 'datasets': 1, 'notes': 4, 'chats': 5}
```

This comprehensive logging helps verify that all data was properly cleaned up.
