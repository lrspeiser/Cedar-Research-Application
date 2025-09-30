"""
File Processing Orchestrator
Coordinates all file processing agents to analyze uploaded files
"""

import os
import logging
from typing import Any, Dict, Optional
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import all file processing agents from the agents package
from .agents import (
    FileReaderAgent,
    PDFExtractionAgent,
    OCRAgent,
    LangExtractAgent,
    ImageAnalysisAgent,
    SQLMetadataAgent
)
from .agents.file_processing_result import FileProcessingResult

# Configure logging
logger = logging.getLogger(__name__)


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