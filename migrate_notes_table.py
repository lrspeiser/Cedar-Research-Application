#!/usr/bin/env python
"""
Migration script to add missing columns to the notes table.

The Note model expects the following columns that are missing from the database:
- chat_id (Integer, nullable)
- thread_id (Integer, nullable)
- agent_name (String(100), nullable)
- user_query (Text, nullable)
- note_type (String(50), default='general')
- title (String(255), nullable)
- priority (Integer, default=0)
- updated_at (DateTime, default=now, onupdate=now)

This script will add these columns and associated indexes.
"""

import sqlite3
from pathlib import Path
import logging
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def migrate_notes_table():
    """Add missing columns to notes table"""
    
    # Database paths
    main_db = "/Users/leonardspeiser/CedarPyData/cedarpy.db"
    
    logging.info(f"Migrating database: {main_db}")
    
    # Connect to database
    conn = sqlite3.connect(main_db)
    cursor = conn.cursor()
    
    try:
        # Check current schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='notes'")
        current_schema = cursor.fetchone()
        if current_schema:
            logging.info(f"Current notes table schema:\n{current_schema[0]}")
        
        # List of columns to add with their SQL definitions
        columns_to_add = [
            ("chat_id", "INTEGER"),
            ("thread_id", "INTEGER"),
            ("agent_name", "VARCHAR(100)"),
            ("user_query", "TEXT"),
            ("note_type", "VARCHAR(50) DEFAULT 'general'"),
            ("title", "VARCHAR(255)"),
            ("priority", "INTEGER DEFAULT 0"),
            ("updated_at", "DATETIME")
        ]
        
        # Check which columns already exist
        cursor.execute("PRAGMA table_info(notes)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        logging.info(f"Existing columns: {existing_columns}")
        
        # Add missing columns
        for col_name, col_def in columns_to_add:
            if col_name not in existing_columns:
                logging.info(f"Adding column: {col_name}")
                try:
                    cursor.execute(f"ALTER TABLE notes ADD COLUMN {col_name} {col_def}")
                    conn.commit()
                    logging.info(f"✅ Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    logging.warning(f"⚠️ Could not add column {col_name}: {e}")
            else:
                logging.info(f"✓ Column {col_name} already exists")
        
        # Create new indexes if they don't exist
        indexes_to_create = [
            ("ix_notes_chat_thread", "chat_id, thread_id"),
            ("ix_notes_type", "note_type")
        ]
        
        # Check existing indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notes'")
        existing_indexes = {row[0] for row in cursor.fetchall()}
        logging.info(f"Existing indexes: {existing_indexes}")
        
        for idx_name, idx_cols in indexes_to_create:
            if idx_name not in existing_indexes:
                logging.info(f"Creating index: {idx_name}")
                try:
                    cursor.execute(f"CREATE INDEX {idx_name} ON notes ({idx_cols})")
                    conn.commit()
                    logging.info(f"✅ Created index: {idx_name}")
                except sqlite3.OperationalError as e:
                    logging.warning(f"⚠️ Could not create index {idx_name}: {e}")
            else:
                logging.info(f"✓ Index {idx_name} already exists")
        
        # Update existing rows to set updated_at if null
        logging.info("Setting updated_at for existing rows...")
        cursor.execute("""
            UPDATE notes 
            SET updated_at = created_at 
            WHERE updated_at IS NULL
        """)
        rows_updated = cursor.rowcount
        conn.commit()
        logging.info(f"✅ Updated {rows_updated} rows with updated_at values")
        
        # Verify final schema
        cursor.execute("PRAGMA table_info(notes)")
        final_columns = cursor.fetchall()
        logging.info("\n=== FINAL NOTES TABLE SCHEMA ===")
        for col in final_columns:
            logging.info(f"  {col[1]:20} {col[2]:20} {'NOT NULL' if col[3] else 'NULL':10} default={col[4]}")
        
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
    
    logging.info("\n✅ Migration completed successfully!")


def migrate_project_databases():
    """Also migrate notes tables in project-specific databases"""
    import os
    
    data_dir = Path("/Users/leonardspeiser/CedarPyData")
    
    # Find all project databases
    for db_file in data_dir.glob("project_*.db"):
        logging.info(f"\n{'='*50}")
        logging.info(f"Migrating project database: {db_file}")
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        try:
            # Check if notes table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes'")
            if not cursor.fetchone():
                logging.info("No notes table in this database, skipping...")
                continue
            
            # List of columns to add with their SQL definitions
            columns_to_add = [
                ("chat_id", "INTEGER"),
                ("thread_id", "INTEGER"),
                ("agent_name", "VARCHAR(100)"),
                ("user_query", "TEXT"),
                ("note_type", "VARCHAR(50) DEFAULT 'general'"),
                ("title", "VARCHAR(255)"),
                ("priority", "INTEGER DEFAULT 0"),
                ("updated_at", "DATETIME")
            ]
            
            # Check which columns already exist
            cursor.execute("PRAGMA table_info(notes)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            # Add missing columns
            for col_name, col_def in columns_to_add:
                if col_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE notes ADD COLUMN {col_name} {col_def}")
                        conn.commit()
                        logging.info(f"✅ Added column: {col_name}")
                    except sqlite3.OperationalError as e:
                        logging.warning(f"⚠️ Could not add column {col_name}: {e}")
            
            # Create new indexes if they don't exist
            indexes_to_create = [
                ("ix_notes_chat_thread", "chat_id, thread_id"),
                ("ix_notes_type", "note_type")
            ]
            
            # Check existing indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notes'")
            existing_indexes = {row[0] for row in cursor.fetchall()}
            
            for idx_name, idx_cols in indexes_to_create:
                if idx_name not in existing_indexes:
                    try:
                        cursor.execute(f"CREATE INDEX {idx_name} ON notes ({idx_cols})")
                        conn.commit()
                        logging.info(f"✅ Created index: {idx_name}")
                    except sqlite3.OperationalError as e:
                        logging.warning(f"⚠️ Could not create index {idx_name}: {e}")
            
            # Update existing rows to set updated_at if null
            cursor.execute("""
                UPDATE notes 
                SET updated_at = created_at 
                WHERE updated_at IS NULL AND created_at IS NOT NULL
            """)
            rows_updated = cursor.rowcount
            conn.commit()
            logging.info(f"✅ Updated {rows_updated} rows with updated_at values")
            
        except Exception as e:
            logging.error(f"Failed to migrate {db_file}: {e}")
            conn.rollback()
        finally:
            conn.close()


if __name__ == "__main__":
    logging.info("Starting notes table migration...")
    
    # Migrate main database
    migrate_notes_table()
    
    # Migrate project databases
    logging.info("\n" + "="*50)
    logging.info("Migrating project-specific databases...")
    migrate_project_databases()
    
    logging.info("\n🎉 All migrations completed!")