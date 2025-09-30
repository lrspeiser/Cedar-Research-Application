"""
LangExtractAgent - Extracted from file_processing_agents.py

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
from .file_processing_result import FileProcessingResult, LANGDETECT_AVAILABLE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LangExtractAgent:
    """Agent for language detection and extraction"""
    
    def __init__(self):
        self.available = LANGDETECT_AVAILABLE
        
    async def process(self, text: str) -> FileProcessingResult:
        """Detect languages in text"""
        logger.info(f"[LangExtractAgent] Processing text of length {len(text)}")
        
        if not self.available:
            # NEVER CREATE A FALLBACK - Fail loudly so dependencies are properly installed
            logger.error(f"[LangExtractAgent] FATAL: langdetect library not available")
            logger.error(f"[LangExtractAgent] Install it with: pip install langdetect")
            logger.error(f"[LangExtractAgent] DO NOT return fake 'unknown' data - fail the operation")
            raise RuntimeError(
                "LangExtractAgent requires langdetect library. Install with: pip install langdetect"
            )
        
        try:
            from langdetect import detect_langs
            
            # Detect languages
            languages = detect_langs(text[:5000])  # Use first 5000 chars
            
            lang_results = []
            for lang in languages:
                lang_results.append({
                    "language": lang.lang,
                    "confidence": lang.prob
                })
            
            metadata = {
                "detected_languages": lang_results,
                "primary_language": lang_results[0]["language"] if lang_results else "unknown"
            }
            
            return FileProcessingResult(
                agent_name="LangExtractAgent",
                success=True,
                data=None,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"[LangExtractAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="LangExtractAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )
