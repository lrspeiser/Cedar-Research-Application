"""
PDFExtractionAgent - Extracted from file_processing_agents.py

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
from .file_processing_result import FileProcessingResult, PYMUPDF_AVAILABLE

# Import fitz (PyMuPDF) if available
if PYMUPDF_AVAILABLE:
    import fitz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFExtractionAgent:
    """Agent for extracting content from PDFs using PyMuPDF"""
    
    def __init__(self):
        self.available = PYMUPDF_AVAILABLE
        
    async def process(self, file_path: str, project_id: Optional[int] = None, branch_id: Optional[int] = None, file_id: Optional[int] = None) -> FileProcessingResult:
        """Extract text and images from PDF with optional db_update for persistence"""
        logger.info(f"[PDFExtractionAgent] Processing {file_path}")
        
        if not self.available:
            return FileProcessingResult(
                agent_name="PDFExtractionAgent",
                success=False,
                data=None,
                metadata={},
                error="PyMuPDF not installed"
            )
        
        try:
            extracted_files = []
            output_dir = Path(file_path).parent / f"{Path(file_path).stem}_extracted"
            output_dir.mkdir(exist_ok=True)
            
            doc = fitz.open(file_path)
            
            # Extract text
            full_text = ""
            page_texts = []
            for page_num, page in enumerate(doc):
                text = page.get_text()
                page_texts.append(text)
                full_text += f"\n--- Page {page_num + 1} ---\n{text}"
            
            # Save extracted text
            text_file = output_dir / "extracted_text.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(full_text)
            extracted_files.append(str(text_file))
            
            # Extract images
            image_count = 0
            for page_num, page in enumerate(doc):
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        img_path = output_dir / f"page{page_num + 1}_img{img_index + 1}.png"
                        pix.save(str(img_path))
                        extracted_files.append(str(img_path))
                        image_count += 1
                    else:  # CMYK
                        pix1 = fitz.Pixmap(fitz.csRGB, pix)
                        img_path = output_dir / f"page{page_num + 1}_img{img_index + 1}.png"
                        pix1.save(str(img_path))
                        extracted_files.append(str(img_path))
                        image_count += 1
                        pix1 = None
                    
                    pix = None
            
            metadata = {
                "page_count": len(doc),
                "text_length": len(full_text),
                "image_count": image_count,
                "output_directory": str(output_dir),
                "has_text": len(full_text.strip()) > 0,
                "is_scanned": len(full_text.strip()) < 100 and image_count > 0
            }
            
            doc.close()
            
            return FileProcessingResult(
                agent_name="PDFExtractionAgent",
                success=True,
                data=full_text[:5000],  # Preview
                metadata=metadata,
                extracted_files=extracted_files
            )
            
        except Exception as e:
            logger.error(f"[PDFExtractionAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="PDFExtractionAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )
