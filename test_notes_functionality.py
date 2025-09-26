#!/usr/bin/env python3
"""
Comprehensive test for notes functionality - saving to database and retrieval
"""

import os
import sys
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Add the project to path
sys.path.insert(0, '/Users/leonardspeiser/Projects/cedarpy')

def test_notes_database():
    """Test notes saving and retrieval from main cedarpy database"""
    
    print("Notes Functionality Test")
    print("=" * 60)
    
    # The notes are in the main cedarpy.db, not individual project databases!
    data_dir = Path.home() / "CedarPyData"
    db_path = data_dir / "cedarpy.db"
    
    if not db_path.exists():
        print(f"❌ Main database not found at {db_path}")
        return
    
    print(f"Using database: {db_path}")
    print("-" * 40)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Step 1: Check if notes table exists
    print("\n1. Checking for notes table...")
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='notes'
    """)
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("   ❌ Notes table does not exist!")
        # Try alternative table names
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE '%note%'
        """)
        similar_tables = cursor.fetchall()
        if similar_tables:
            print(f"   Found similar tables: {[t[0] for t in similar_tables]}")
    else:
        print("   ✅ Notes table exists")
    
    # Step 2: Check notes table schema
    print("\n2. Checking notes table schema...")
    try:
        cursor.execute("PRAGMA table_info(notes)")
        columns = cursor.fetchall()
        if columns:
            print("   Columns found:")
            for col in columns:
                print(f"     - {col[1]} ({col[2]})")
        else:
            print("   ❌ Could not get table schema")
    except sqlite3.Error as e:
        print(f"   ❌ Error checking schema: {e}")
    
    # Step 3: Check if there are any notes
    print("\n3. Checking for existing notes...")
    try:
        cursor.execute("SELECT COUNT(*) FROM notes")
        count = cursor.fetchone()[0]
        print(f"   Found {count} notes in database")
        
        if count > 0:
            # Get sample notes
            cursor.execute("""
                SELECT id, title, content, created_at, branch_id 
                FROM notes 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            notes = cursor.fetchall()
            print("\n   Recent notes:")
            for note in notes:
                note_id, title, content, created_at, branch_id = note
                # Truncate content for display
                content_preview = content[:100] + "..." if len(content) > 100 else content
                print(f"     ID: {note_id}")
                print(f"     Title: {title}")
                print(f"     Content: {content_preview}")
                print(f"     Created: {created_at}")
                print(f"     Branch: {branch_id}")
                print("     " + "-" * 30)
    except sqlite3.Error as e:
        print(f"   ❌ Error querying notes: {e}")
    
    # Step 4: Test inserting a note
    print("\n4. Testing note insertion...")
    test_note = {
        "title": "Test Note from Script",
        "content": json.dumps({
            "test": True,
            "timestamp": datetime.now().isoformat(),
            "message": "This is a test note to verify database functionality"
        }),
        "branch_id": 1  # Assuming main branch
    }
    
    try:
        cursor.execute("""
            INSERT INTO notes (title, content, branch_id, project_id, created_at)
            VALUES (?, ?, ?, 
                    (SELECT id FROM projects LIMIT 1),
                    ?)
        """, (
            test_note["title"],
            test_note["content"],
            test_note["branch_id"],
            datetime.now().isoformat()
        ))
        conn.commit()
        note_id = cursor.lastrowid
        print(f"   ✅ Successfully inserted test note with ID: {note_id}")
        
        # Verify it was saved
        cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        saved_note = cursor.fetchone()
        if saved_note:
            print("   ✅ Note verified in database")
        else:
            print("   ❌ Note not found after insertion")
            
    except sqlite3.Error as e:
        print(f"   ❌ Error inserting note: {e}")
    
    # Step 5: Check how notes are retrieved for display
    print("\n5. Testing note retrieval query (as used by UI)...")
    try:
        # This query mimics what the UI should use
        cursor.execute("""
            SELECT id, title, content, created_at, branch_id
            FROM notes
            WHERE project_id = (SELECT id FROM projects LIMIT 1)
            ORDER BY created_at DESC
            LIMIT 10
        """)
        ui_notes = cursor.fetchall()
        print(f"   Retrieved {len(ui_notes)} notes for UI display")
        
        if ui_notes:
            print("\n   Notes that should appear in UI:")
            for note in ui_notes[:3]:  # Show first 3
                note_id, title, content, created_at, branch_id = note
                print(f"     - {title} (created: {created_at})")
    except sqlite3.Error as e:
        print(f"   ❌ Error retrieving notes: {e}")
    
    # Step 6: Check if notes are branch-aware
    print("\n6. Checking branch awareness...")
    try:
        cursor.execute("""
            SELECT DISTINCT branch_id, COUNT(*) as count
            FROM notes
            GROUP BY branch_id
        """)
        branch_counts = cursor.fetchall()
        if branch_counts:
            print("   Notes per branch:")
            for branch_id, count in branch_counts:
                print(f"     Branch {branch_id}: {count} notes")
        else:
            print("   No notes found across branches")
    except sqlite3.Error as e:
        print(f"   ❌ Error checking branches: {e}")
    
    # Close connection
    conn.close()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("-" * 60)
    
    # Check what might be wrong
    print("\nPossible issues if notes aren't showing:")
    print("1. Notes table might not exist (check step 1)")
    print("2. Notes might not be saved with correct project_id")
    print("3. UI might be querying wrong table/columns")
    print("4. Branch filtering might be excluding notes")
    print("5. Chief Agent notes might not be saving correctly")
    
    return True

def test_chief_agent_notes():
    """Test if Chief Agent notes are being saved"""
    
    print("\n\nChief Agent Notes Test")
    print("=" * 60)
    
    # Check if chief_agent_notes module exists
    try:
        from cedar_orchestrator.chief_agent_notes import ChiefAgentNoteTaker
        print("✅ ChiefAgentNoteTaker module found")
    except ImportError as e:
        print(f"❌ ChiefAgentNoteTaker not found: {e}")
        return
    
    # Find the Notes table structure in models
    try:
        from cedar_app.db_models.models import Note
        print("✅ Note model found")
        
        # Check model attributes
        print("\nNote model attributes:")
        for attr in dir(Note):
            if not attr.startswith('_'):
                print(f"  - {attr}")
    except ImportError as e:
        print(f"❌ Note model not found: {e}")
    
    print("\nTo test Chief Agent note saving:")
    print("1. Run a query through the chat interface")
    print("2. Check if notes appear in the Notes tab")
    print("3. Look for 'Saved notes to database' in the logs")

def check_ui_rendering():
    """Check how notes are rendered in the UI"""
    
    print("\n\nUI Rendering Check")
    print("=" * 60)
    
    # Check page_rendering.py for notes display
    rendering_file = Path("/Users/leonardspeiser/Projects/cedarpy/cedar_app/utils/page_rendering.py")
    
    if rendering_file.exists():
        with open(rendering_file) as f:
            content = f.read()
            
        # Check for notes rendering code
        if "notes_panel" in content or "Notes tab" in content:
            print("✅ Notes rendering code found in page_rendering.py")
            
            # Look for the specific query
            import re
            query_pattern = r"db\.query\(Note\).*\.filter.*\.order_by"
            matches = re.findall(query_pattern, content)
            if matches:
                print(f"   Found {len(matches)} note queries in UI code")
        else:
            print("❌ No notes rendering code found")
    else:
        print("❌ page_rendering.py not found")
    
    # Check web_ui.py for notes endpoints
    web_ui_file = Path("/Users/leonardspeiser/Projects/cedarpy/cedar_app/web_ui.py")
    if web_ui_file.exists():
        with open(web_ui_file) as f:
            content = f.read()
        
        if "Note" in content:
            print("✅ Note handling found in web_ui.py")
            # Count note-related queries
            import re
            note_queries = re.findall(r"db\.query\(Note\)", content)
            print(f"   Found {len(note_queries)} Note queries in web_ui.py")

if __name__ == "__main__":
    # Run all tests
    test_notes_database()
    test_chief_agent_notes()
    check_ui_rendering()
    
    print("\n" + "=" * 60)
    print("Test complete! Check the output above for issues.")
    print("\nIf notes aren't showing in the UI:")
    print("1. Make sure notes are being saved to the correct project/branch")
    print("2. Check that the UI is querying the right table")
    print("3. Verify the Notes tab is refreshing after operations")
    print("4. Check browser console for JavaScript errors")