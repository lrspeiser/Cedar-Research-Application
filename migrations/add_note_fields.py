#!/usr/bin/env python3
"""
Migration script to add new fields to the notes table.
Run this script to update existing project databases with the new Note model fields.
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List, Tuple

# Add the parent directory to path to import from main modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_project_databases() -> List[Tuple[int, Path]]:
    """Find all project SQLite databases."""
    projects_dir = Path.home() / ".cedar" / "projects"
    databases = []
    
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                try:
                    project_id = int(project_dir.name)
                    db_path = project_dir / "cedar.db"
                    if db_path.exists():
                        databases.append((project_id, db_path))
                except ValueError:
                    # Skip non-numeric directories
                    continue
    
    return databases

def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None

def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_def: str):
    """Add a column to a table if it doesn't exist."""
    if not column_exists(conn, table_name, column_name):
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            print(f"  ✓ Added column {column_name}")
        except sqlite3.Error as e:
            print(f"  ✗ Failed to add column {column_name}: {e}")
    else:
        print(f"  - Column {column_name} already exists")

def migrate_notes_table(db_path: Path, project_id: int):
    """Migrate the notes table for a single project database."""
    print(f"\nMigrating project {project_id}: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        
        # Check if notes table exists
        if not table_exists(conn, "notes"):
            print("  - Notes table doesn't exist, skipping")
            conn.close()
            return
        
        # Add new columns if they don't exist
        columns_to_add = [
            ("chat_id", "INTEGER"),
            ("thread_id", "INTEGER"),
            ("agent_name", "VARCHAR(100)"),
            ("user_query", "TEXT"),
            ("note_type", "VARCHAR(50) DEFAULT 'general'"),
            ("title", "VARCHAR(255)"),
            ("priority", "INTEGER DEFAULT 0"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ]
        
        for column_name, column_def in columns_to_add:
            add_column_if_missing(conn, "notes", column_name, column_def)
        
        # Create new indexes if they don't exist
        indexes_to_create = [
            ("ix_notes_chat_thread", "CREATE INDEX IF NOT EXISTS ix_notes_chat_thread ON notes(chat_id, thread_id)"),
            ("ix_notes_type", "CREATE INDEX IF NOT EXISTS ix_notes_type ON notes(note_type)"),
        ]
        
        for index_name, index_sql in indexes_to_create:
            try:
                conn.execute(index_sql)
                print(f"  ✓ Created or verified index {index_name}")
            except sqlite3.Error as e:
                print(f"  ✗ Failed to create index {index_name}: {e}")
        
        conn.commit()
        conn.close()
        print(f"  ✅ Migration completed for project {project_id}")
        
    except sqlite3.Error as e:
        print(f"  ❌ Database error for project {project_id}: {e}")
    except Exception as e:
        print(f"  ❌ Unexpected error for project {project_id}: {e}")

def migrate_registry_database():
    """Migrate the registry database if needed."""
    registry_path = Path.home() / ".cedar" / "cedar.db"
    
    if not registry_path.exists():
        print("Registry database not found, skipping")
        return
    
    print(f"\nMigrating registry database: {registry_path}")
    
    try:
        conn = sqlite3.connect(str(registry_path))
        
        # Check if notes table exists in registry (unlikely, but let's be thorough)
        if table_exists(conn, "notes"):
            columns_to_add = [
                ("chat_id", "INTEGER"),
                ("thread_id", "INTEGER"),
                ("agent_name", "VARCHAR(100)"),
                ("user_query", "TEXT"),
                ("note_type", "VARCHAR(50) DEFAULT 'general'"),
                ("title", "VARCHAR(255)"),
                ("priority", "INTEGER DEFAULT 0"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ]
            
            for column_name, column_def in columns_to_add:
                add_column_if_missing(conn, "notes", column_name, column_def)
        
        conn.commit()
        conn.close()
        print("  ✅ Registry migration completed")
        
    except sqlite3.Error as e:
        print(f"  ❌ Registry database error: {e}")

def main():
    """Main migration function."""
    print("=" * 60)
    print("Cedar Notes Table Migration")
    print("=" * 60)
    
    # First migrate the registry database
    migrate_registry_database()
    
    # Find and migrate all project databases
    databases = get_project_databases()
    
    if not databases:
        print("\nNo project databases found.")
        return
    
    print(f"\nFound {len(databases)} project database(s)")
    
    for project_id, db_path in databases:
        migrate_notes_table(db_path, project_id)
    
    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()