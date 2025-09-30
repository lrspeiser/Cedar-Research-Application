#!/usr/bin/env python3
"""
Migration script to add AUTOINCREMENT to the projects table in the registry database.

This ensures that project IDs are never reused after deletion, preventing data
from deleted projects from appearing in new projects with recycled IDs.

SQLite doesn't support ALTER TABLE to add AUTOINCREMENT, so we need to:
1. Create a new table with AUTOINCREMENT
2. Copy data from old table
3. Drop old table
4. Rename new table to old name
"""

import sqlite3
from pathlib import Path
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def migrate_projects_table_autoincrement():
    """Add AUTOINCREMENT to projects table in registry database."""
    
    # Find the registry database
    # Check multiple possible locations
    possible_paths = [
        Path.home() / "CedarPyData" / "cedarpy.db",
        Path.home() / ".cedar" / "registry.db",
    ]
    
    registry_db = None
    for path in possible_paths:
        if path.exists():
            registry_db = path
            break
    
    if not registry_db:
        logging.warning(f"Registry database not found at any of: {[str(p) for p in possible_paths]}")
        return
    
    logging.info(f"Migrating registry database: {registry_db}")
    
    # Connect to database
    conn = sqlite3.connect(str(registry_db))
    cursor = conn.cursor()
    
    try:
        # Check if projects table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
        if not cursor.fetchone():
            logging.info("Projects table doesn't exist yet, skipping migration")
            conn.close()
            return
        
        # Check current schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='projects'")
        current_schema = cursor.fetchone()
        if current_schema:
            logging.info(f"Current projects table schema:\\n{current_schema[0]}")
            
            # Check if AUTOINCREMENT is already there
            if "AUTOINCREMENT" in current_schema[0].upper():
                logging.info("✓ Projects table already has AUTOINCREMENT, no migration needed")
                conn.close()
                return
        
        logging.info("Starting migration to add AUTOINCREMENT...")
        
        # Begin transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Create new table with AUTOINCREMENT
        cursor.execute("""
            CREATE TABLE projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME
            )
        """)
        logging.info("✓ Created new projects_new table with AUTOINCREMENT")
        
        # 2. Copy all data from old table to new table
        cursor.execute("""
            INSERT INTO projects_new (id, title, created_at)
            SELECT id, title, created_at FROM projects
        """)
        rows_copied = cursor.rowcount
        logging.info(f"✓ Copied {rows_copied} rows from projects to projects_new")
        
        # 3. Drop old table
        cursor.execute("DROP TABLE projects")
        logging.info("✓ Dropped old projects table")
        
        # 4. Rename new table to old name
        cursor.execute("ALTER TABLE projects_new RENAME TO projects")
        logging.info("✓ Renamed projects_new to projects")
        
        # 5. Recreate indexes if they existed
        # The UNIQUE constraint on title is already in the table definition
        # but let's add an index on created_at for performance
        try:
            cursor.execute("CREATE INDEX ix_projects_created_at ON projects (created_at)")
            logging.info("✓ Created index on created_at")
        except sqlite3.OperationalError:
            logging.info("Index on created_at already exists or not needed")
        
        # Commit transaction
        conn.commit()
        logging.info("✓ Transaction committed successfully")
        
        # Verify final schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='projects'")
        final_schema = cursor.fetchone()
        if final_schema:
            logging.info(f"\\nFinal projects table schema:\\n{final_schema[0]}")
        
        # Verify data integrity
        cursor.execute("SELECT COUNT(*) FROM projects")
        final_count = cursor.fetchone()[0]
        logging.info(f"\\nFinal row count: {final_count}")
        
        if final_count != rows_copied:
            logging.error(f"⚠️ WARNING: Row count mismatch! Copied {rows_copied}, but found {final_count}")
        else:
            logging.info("✓ Data integrity verified")
        
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
        logging.info("Transaction rolled back")
        raise
    finally:
        conn.close()
    
    logging.info("\\n✅ Migration completed successfully!")
    logging.info("Project IDs will now never be reused after deletion.")


if __name__ == "__main__":
    logging.info("="*60)
    logging.info("Cedar Projects Table AUTOINCREMENT Migration")
    logging.info("="*60)
    logging.info("")
    
    try:
        migrate_projects_table_autoincrement()
    except Exception as e:
        logging.error(f"\\n❌ Migration failed with error: {e}")
        sys.exit(1)
    
    logging.info("\\n🎉 All migrations completed successfully!")
