"""
FileReaderAgent - Extracted from file_processing_agents.py

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
from openai import AsyncOpenAI

# Import shared file processing utilities
from .file_processing_result import FileProcessingResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileReaderAgent:
    """Agent that reads files and sends content to GPT for analysis"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, file_path: str, file_type: str) -> FileProcessingResult:
        """Read file and analyze with GPT"""
        logger.info(f"[FileReaderAgent] Processing {file_path} of type {file_type}")
        
        if not self.llm_client:
            return FileProcessingResult(
                agent_name="FileReaderAgent",
                success=False,
                data=None,
                metadata={},
                error="No LLM client available"
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
            
            # Read file content based on type
            content = ""
            if file_type in ["text/plain", "text/csv", "application/json", "text/markdown"]:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()[:10000]  # Limit to 10k chars
            else:
                # For binary files, get basic info
                file_size = os.path.getsize(file_path)
                content = f"Binary file: {os.path.basename(file_path)}, Size: {file_size} bytes, Type: {file_type}"
            
            # Analyze with GPT
            prompt = f"""Analyze this file and extract structured metadata.
File type: {file_type}
Content preview: {content[:5000]}

Provide a JSON response with:
- title: document title if found
- summary: brief summary of content
- key_topics: list of main topics
- language: primary language
- entities: important names, dates, locations mentioned
- document_type: classification (report, article, data, etc)
- confidence: confidence score 0-1
"""
            
            completion_params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a document analysis expert. Analyze files and extract structured metadata."},
                    {"role": "user", "content": prompt}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            result = response.choices[0].message.content
            
            # Try to parse as JSON
            metadata = {}
            try:
                import json
                metadata = json.loads(result)
            except:
                metadata = {"raw_analysis": result}
            
            return FileProcessingResult(
                agent_name="FileReaderAgent",
                success=True,
                data=content[:5000],
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"[FileReaderAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="FileReaderAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )
