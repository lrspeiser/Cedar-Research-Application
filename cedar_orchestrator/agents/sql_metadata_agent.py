"""
SQLMetadataAgent - Extracted from file_processing_agents.py

Individual agent file created during Phase 3 refactoring.
"""

"""
File Processing Agents for extracting and analyzing uploaded files
Includes PDF processing, image extraction, text analysis, and metadata generation
"""

import os
import json
import asyncio
import logging
import hashlib
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, BinaryIO
from dataclasses import dataclass
from pathlib import Path
import tempfile
import shutil

# Import shared file processing utilities
from .file_processing_result import FileProcessingResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SQLMetadataAgent:
    """Agent for creating SQL metadata tables from extracted data"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(
            os.path.expanduser("~"), "CedarPyData", "file_metadata.db"
        )
        self._init_db()
        
    def _init_db(self):
        """Initialize metadata database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            file_name TEXT,
            file_type TEXT,
            file_size INTEGER,
            hash TEXT,
            processed_date TEXT,
            
            -- Extracted metadata
            title TEXT,
            summary TEXT,
            language TEXT,
            page_count INTEGER,
            word_count INTEGER,
            has_images BOOLEAN,
            image_count INTEGER,
            
            -- Analysis results
            key_topics TEXT,  -- JSON array
            entities TEXT,    -- JSON array
            document_type TEXT,
            confidence REAL,
            
            -- Processing details
            agents_used TEXT,  -- JSON array
            processing_time REAL,
            extracted_files TEXT,  -- JSON array
            
            raw_metadata TEXT  -- Full JSON metadata
        )
        """)
        
        conn.commit()
        conn.close()
        
    async def process(self, file_path: str, all_results: List[FileProcessingResult]) -> FileProcessingResult:
        """Store metadata in SQL database"""
        logger.info(f"[SQLMetadataAgent] Storing metadata for {file_path}")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Aggregate metadata from all agents
            metadata = {}
            extracted_files = []
            agents_used = []
            
            for result in all_results:
                if result.success:
                    metadata.update(result.metadata)
                    if result.extracted_files:
                        extracted_files.extend(result.extracted_files)
                    agents_used.append(result.agent_name)
            
            # Calculate file hash
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            # Prepare data for insertion
            from datetime import datetime
            
            insert_data = {
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "file_type": metadata.get("file_type", "unknown"),
                "file_size": os.path.getsize(file_path),
                "hash": file_hash,
                "processed_date": datetime.now().isoformat(),
                
                "title": metadata.get("title", ""),
                "summary": metadata.get("summary", ""),
                "language": metadata.get("primary_language", ""),
                "page_count": metadata.get("page_count", 0),
                "word_count": len(metadata.get("text", "").split()) if "text" in metadata else 0,
                "has_images": metadata.get("image_count", 0) > 0,
                "image_count": metadata.get("image_count", 0),
                
                "key_topics": json.dumps(metadata.get("key_topics", [])),
                "entities": json.dumps(metadata.get("entities", [])),
                "document_type": metadata.get("document_type", ""),
                "confidence": metadata.get("confidence", 0),
                
                "agents_used": json.dumps(agents_used),
                "processing_time": 0,  # TODO: Calculate actual time
                "extracted_files": json.dumps(extracted_files),
                
                "raw_metadata": json.dumps(metadata)
            }
            
            # Insert or update
            cursor.execute("""
            INSERT OR REPLACE INTO file_metadata (
                file_path, file_name, file_type, file_size, hash, processed_date,
                title, summary, language, page_count, word_count, has_images, image_count,
                key_topics, entities, document_type, confidence,
                agents_used, processing_time, extracted_files, raw_metadata
            ) VALUES (
                :file_path, :file_name, :file_type, :file_size, :hash, :processed_date,
                :title, :summary, :language, :page_count, :word_count, :has_images, :image_count,
                :key_topics, :entities, :document_type, :confidence,
                :agents_used, :processing_time, :extracted_files, :raw_metadata
            )
            """, insert_data)
            
            conn.commit()
            
            # Get the inserted row ID
            row_id = cursor.lastrowid
            
            conn.close()
            
            return FileProcessingResult(
                agent_name="SQLMetadataAgent",
                success=True,
                data={"row_id": row_id, "table": "file_metadata"},
                metadata={
                    "database": self.db_path,
                    "row_id": row_id,
                    "file_hash": file_hash
                }
            )
            
        except Exception as e:
            logger.error(f"[SQLMetadataAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="SQLMetadataAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )
