#!/usr/bin/env python3
"""
Migration script to add Notes database entry to existing projects.
This ensures all projects have a "Notes" entry in the datasets table.
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List, Tuple
from datetime import datetime, timezone

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

def add_notes_dataset(db_path: Path, project_id: int):
    """Add Notes database entry for a single project."""
    print(f"\nProcessing project {project_id}: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        
        # Check if datasets table exists
        if not table_exists(conn, "datasets"):
            print("  - Datasets table doesn't exist, skipping")
            conn.close()
            return
        
        # Check if Notes dataset already exists
        cursor = conn.execute(
            "SELECT id FROM datasets WHERE name = 'Notes' AND project_id = ?",
            (project_id,)
        )
        existing = cursor.fetchone()
        
        if existing:
            print(f"  - Notes database already exists (ID: {existing[0]})")
            conn.close()
            return
        
        # Get the main branch ID (usually 1, but let's be safe)
        cursor = conn.execute(
            "SELECT id FROM branches WHERE project_id = ? AND (is_default = 1 OR name = 'main' OR name = 'Main') ORDER BY id LIMIT 1",
            (project_id,)
        )
        branch_result = cursor.fetchone()
        
        if not branch_result:
            # Fallback: just use branch_id = 1
            branch_id = 1
            print(f"  ⚠ Could not find main branch, using branch_id = {branch_id}")
        else:
            branch_id = branch_result[0]
            print(f"  ✓ Found main branch ID: {branch_id}")
        
        # Insert Notes dataset
        created_at = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO datasets (project_id, branch_id, name, description, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            (
                project_id,
                branch_id,
                "Notes",
                "Project notes and documentation created by agents and users",
                created_at
            )
        )
        
        conn.commit()
        notes_id = cursor.lastrowid
        print(f"  ✅ Added Notes database entry (ID: {notes_id})")
        
        # Also check if we need to create an initialization note
        if table_exists(conn, "notes"):
            cursor = conn.execute("SELECT COUNT(*) FROM notes WHERE project_id = ?", (project_id,))
            note_count = cursor.fetchone()[0]
            
            if note_count == 0:
                # Add an initialization note
                cursor.execute(
                    """INSERT INTO notes 
                       (project_id, branch_id, content, title, note_type, agent_name, priority, tags, created_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        project_id,
                        branch_id,
                        f"📌 Project initialized. Notes database created on {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p %Z')}",
                        "Project Initialization",
                        "system",
                        "System",
                        0,
                        '["project-init", "system"]',
                        created_at
                    )
                )
                conn.commit()
                print(f"  ✅ Added initialization note")
            else:
                print(f"  - Project already has {note_count} note(s)")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"  ❌ Database error for project {project_id}: {e}")
    except Exception as e:
        print(f"  ❌ Unexpected error for project {project_id}: {e}")

def main():
    """Main migration function."""
    print("=" * 60)
    print("Cedar Notes Database Migration")
    print("=" * 60)
    print("\nThis script adds a 'Notes' database entry to all existing projects")
    print("so they appear properly in the Databases tab.")
    
    # Find all project databases
    databases = get_project_databases()
    
    if not databases:
        print("\nNo project databases found.")
        return
    
    print(f"\nFound {len(databases)} project database(s)")
    
    for project_id, db_path in databases:
        add_notes_dataset(db_path, project_id)
    
    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)
    print("\nAll projects should now have a 'Notes' database visible in the Databases tab.")

if __name__ == "__main__":
    main()