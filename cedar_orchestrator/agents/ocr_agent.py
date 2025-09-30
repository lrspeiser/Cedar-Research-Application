"""
OCRAgent - Extracted from file_processing_agents.py

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
from .file_processing_result import FileProcessingResult, PDF2IMAGE_AVAILABLE, TESSERACT_AVAILABLE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OCRAgent:
    """Agent for OCR processing of scanned PDFs and images"""
    
    def __init__(self):
        self.pdf2image_available = PDF2IMAGE_AVAILABLE
        self.tesseract_available = TESSERACT_AVAILABLE
        
    async def process(self, file_path: str) -> FileProcessingResult:
        """Perform OCR on file"""
        logger.info(f"[OCRAgent] Processing {file_path}")
        
        if not self.tesseract_available:
            return FileProcessingResult(
                agent_name="OCRAgent",
                success=False,
                data=None,
                metadata={},
                error="Tesseract not installed"
            )
        
        try:
            extracted_text = ""
            
            if file_path.lower().endswith('.pdf'):
                if not self.pdf2image_available:
                    return FileProcessingResult(
                        agent_name="OCRAgent",
                        success=False,
                        data=None,
                        metadata={},
                        error="pdf2image not installed"
                    )
                
                # Convert PDF to images
                images = convert_from_path(file_path, dpi=200)
                
                for i, image in enumerate(images):
                    text = pytesseract.image_to_string(image)
                    extracted_text += f"\n--- Page {i + 1} ---\n{text}"
                    
            else:
                # Direct image OCR
                from PIL import Image
                image = Image.open(file_path)
                extracted_text = pytesseract.image_to_string(image)
            
            # Save extracted text
            output_dir = Path(file_path).parent / f"{Path(file_path).stem}_ocr"
            output_dir.mkdir(exist_ok=True)
            
            text_file = output_dir / "ocr_text.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            
            metadata = {
                "text_length": len(extracted_text),
                "has_text": len(extracted_text.strip()) > 0,
                "output_file": str(text_file)
            }
            
            return FileProcessingResult(
                agent_name="OCRAgent",
                success=True,
                data=extracted_text[:5000],
                metadata=metadata,
                extracted_files=[str(text_file)]
            )
            
        except Exception as e:
            logger.error(f"[OCRAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="OCRAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )
