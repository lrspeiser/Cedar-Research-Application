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

# PDF and image processing libraries
try:
    import fitz  # PyMuPDF for digital PDFs
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    from PIL import Image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# For language extraction
try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

from openai import AsyncOpenAI
from fastapi import WebSocket

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class FileProcessingResult:
    """Result from a file processing agent"""
    agent_name: str
    success: bool
    data: Any
    metadata: Dict[str, Any]
    error: Optional[str] = None
    extracted_files: List[str] = None  # Paths to extracted files

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
            
            # Handle GPT-5 parameters
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1000
            else:
                completion_params["max_tokens"] = 1000
                completion_params["temperature"] = 0.3
            
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

class PDFExtractionAgent:
    """Agent for extracting content from PDFs using PyMuPDF"""
    
    def __init__(self):
        self.available = PYMUPDF_AVAILABLE
        
    async def process(self, file_path: str) -> FileProcessingResult:
        """Extract text and images from PDF"""
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

class LangExtractAgent:
    """Agent for language detection and extraction"""
    
    def __init__(self):
        self.available = LANGDETECT_AVAILABLE
        
    async def process(self, text: str) -> FileProcessingResult:
        """Detect languages in text"""
        logger.info(f"[LangExtractAgent] Processing text of length {len(text)}")
        
        if not self.available:
            # Fallback to simple detection
            metadata = {"detected_languages": ["unknown"], "confidence": 0}
            return FileProcessingResult(
                agent_name="LangExtractAgent",
                success=True,
                data=None,
                metadata=metadata
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

class ImageAnalysisAgent:
    """Agent for analyzing extracted images with GPT Vision"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, image_paths: List[str]) -> FileProcessingResult:
        """Analyze images with GPT Vision"""
        logger.info(f"[ImageAnalysisAgent] Processing {len(image_paths)} images")
        
        if not self.llm_client:
            return FileProcessingResult(
                agent_name="ImageAnalysisAgent",
                success=False,
                data=None,
                metadata={},
                error="No LLM client available"
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
            
            image_analyses = []
            
            for img_path in image_paths[:5]:  # Limit to first 5 images
                # Read image and encode to base64
                import base64
                with open(img_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Analyze with GPT Vision
                completion_params = {
                    "model": model if "gpt-5" not in model else "gpt-4o",  # Fallback for vision
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Analyze this image and describe: 1) What it shows, 2) Key elements visible, 3) Any text present, 4) What it implies or represents"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                }
                
                # Handle GPT-5 parameters
                if "gpt-5" in model or "gpt-4.1" in model:
                    completion_params["max_completion_tokens"] = 500
                else:
                    completion_params["max_tokens"] = 500
                
                try:
                    response = await self.llm_client.chat.completions.create(**completion_params)
                    analysis = response.choices[0].message.content
                    
                    image_analyses.append({
                        "image": os.path.basename(img_path),
                        "analysis": analysis
                    })
                except Exception as e:
                    logger.warning(f"Failed to analyze {img_path}: {e}")
                    image_analyses.append({
                        "image": os.path.basename(img_path),
                        "analysis": f"Analysis failed: {str(e)}"
                    })
            
            metadata = {
                "images_analyzed": len(image_analyses),
                "total_images": len(image_paths),
                "analyses": image_analyses
            }
            
            return FileProcessingResult(
                agent_name="ImageAnalysisAgent",
                success=True,
                data=image_analyses,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"[ImageAnalysisAgent] Error: {e}")
            return FileProcessingResult(
                agent_name="ImageAnalysisAgent",
                success=False,
                data=None,
                metadata={},
                error=str(e)
            )

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

class FileProcessingOrchestrator:
    """Orchestrator for coordinating all file processing agents"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.file_reader = FileReaderAgent(llm_client)
        self.pdf_extractor = PDFExtractionAgent()
        self.ocr_agent = OCRAgent()
        self.lang_extractor = LangExtractAgent()
        self.image_analyzer = ImageAnalysisAgent(llm_client)
        self.sql_metadata = SQLMetadataAgent()
        
    async def process_file(self, file_path: str, file_type: str, websocket: Optional[WebSocket] = None) -> Dict[str, Any]:
        """Process uploaded file through all relevant agents"""
        logger.info(f"[FileProcessingOrchestrator] Processing {file_path}")
        
        results = []
        extracted_images = []
        extracted_text = ""
        
        # Send initial status
        if websocket:
            await websocket.send_json({
                "type": "action",
                "function": "processing",
                "text": f"Processing file: {os.path.basename(file_path)}"
            })
        
        # 1. Basic file analysis with GPT
        if websocket:
            await websocket.send_json({
                "type": "action",
                "function": "status",
                "text": "Analyzing file content with AI..."
            })
        
        file_result = await self.file_reader.process(file_path, file_type)
        results.append(file_result)
        
        # 2. PDF-specific processing
        if file_type == "application/pdf" or file_path.lower().endswith('.pdf'):
            if websocket:
                await websocket.send_json({
                    "type": "action",
                    "function": "status",
                    "text": "Extracting PDF content and images..."
                })
            
            pdf_result = await self.pdf_extractor.process(file_path)
            results.append(pdf_result)
            
            if pdf_result.success:
                if pdf_result.extracted_files:
                    extracted_images = [f for f in pdf_result.extracted_files if f.endswith('.png')]
                if pdf_result.data:
                    extracted_text = pdf_result.data
                    
                # Check if it's a scanned PDF
                if pdf_result.metadata.get("is_scanned"):
                    if websocket:
                        await websocket.send_json({
                            "type": "action",
                            "function": "status",
                            "text": "Performing OCR on scanned document..."
                        })
                    
                    ocr_result = await self.ocr_agent.process(file_path)
                    results.append(ocr_result)
                    if ocr_result.success and ocr_result.data:
                        extracted_text = ocr_result.data
        
        # 3. Language detection
        if extracted_text:
            if websocket:
                await websocket.send_json({
                    "type": "action",
                    "function": "status",
                    "text": "Detecting language..."
                })
            
            lang_result = await self.lang_extractor.process(extracted_text)
            results.append(lang_result)
        
        # 4. Image analysis
        if extracted_images:
            if websocket:
                await websocket.send_json({
                    "type": "action",
                    "function": "status",
                    "text": f"Analyzing {len(extracted_images)} extracted images..."
                })
            
            image_result = await self.image_analyzer.process(extracted_images)
            results.append(image_result)
        
        # 5. Store in SQL metadata
        if websocket:
            await websocket.send_json({
                "type": "action",
                "function": "status",
                "text": "Storing metadata in database..."
            })
        
        sql_result = await self.sql_metadata.process(file_path, results)
        results.append(sql_result)
        
        # Compile final response
        success_count = sum(1 for r in results if r.success)
        
        summary = {
            "file": os.path.basename(file_path),
            "type": file_type,
            "agents_run": len(results),
            "successful": success_count,
            "extracted_files": [],
            "metadata": {}
        }
        
        # Aggregate all extracted files
        for result in results:
            if result.extracted_files:
                summary["extracted_files"].extend(result.extracted_files)
            if result.metadata:
                summary["metadata"].update(result.metadata)
        
        # Send final summary
        if websocket:
            final_text = f"""**File Processing Complete**

**File:** {os.path.basename(file_path)}
**Type:** {file_type}

**Processing Results:**
- Agents Run: {len(results)}
- Successful: {success_count}
- Extracted Files: {len(summary["extracted_files"])}

**Key Findings:**
"""
            
            if "title" in summary["metadata"]:
                final_text += f"- Title: {summary['metadata']['title']}\n"
            if "summary" in summary["metadata"]:
                final_text += f"- Summary: {summary['metadata']['summary'][:200]}...\n"
            if "primary_language" in summary["metadata"]:
                final_text += f"- Language: {summary['metadata']['primary_language']}\n"
            if "page_count" in summary["metadata"]:
                final_text += f"- Pages: {summary['metadata']['page_count']}\n"
            if "image_count" in summary["metadata"]:
                final_text += f"- Images: {summary['metadata']['image_count']}\n"
            
            if summary["extracted_files"]:
                final_text += f"\n**Extracted Files:**\n"
                for f in summary["extracted_files"][:10]:
                    final_text += f"- {os.path.basename(f)}\n"
            
            await websocket.send_json({
                "type": "message",
                "role": "File Processing",
                "text": final_text,
                "metadata": summary
            })
        
        return summary

# Export the main orchestrator
__all__ = ['FileProcessingOrchestrator', 'FileProcessingResult']