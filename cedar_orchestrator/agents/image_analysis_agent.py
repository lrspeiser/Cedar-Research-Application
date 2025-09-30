"""
ImageAnalysisAgent - Extracted from file_processing_agents.py

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

# Import AgentResult for orchestrator compatibility
from .agent_result import AgentResult

class ImageAnalysisAgent:
    """Agent for analyzing images with GPT Vision (orchestrator-compatible)"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str, project_id: Optional[int] = None, branch_id: Optional[int] = None, 
                      db_session = None, file_id: Optional[int] = None) -> AgentResult:
        """Analyze image using GPT Vision with orchestrator integration
        
        Args:
            task: Task description from Chief Agent
            project_id: Project ID for database access
            branch_id: Branch ID for file lookup
            db_session: SQLAlchemy session for database queries
            file_id: File ID to analyze (from context)
        """
        import time
        start_time = time.time()
        logger.info(f"[ImageAnalysisAgent] Starting task: {task[:100]}...")
        logger.info(f"[ImageAnalysisAgent] Context: project_id={project_id}, branch_id={branch_id}, file_id={file_id}")
        
        if not self.llm_client:
            return AgentResult(
                agent_name="ImageAnalysisAgent",
                display_name="Image Analysis Agent",
                result="**Agent Failure:** No LLM client configured for image analysis.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available",
                summary="Image Analysis failed: No LLM configured"
            )
        
        try:
            # Step 1: Look up the file in the database if file_id provided
            image_path = None
            file_metadata = {}
            
            if file_id and db_session and project_id:
                logger.info(f"[ImageAnalysisAgent] Looking up file_id={file_id} in database...")
                try:
                    from main_models import FileEntry
                    file_entry = db_session.query(FileEntry).filter(
                        FileEntry.id == int(file_id),
                        FileEntry.project_id == int(project_id)
                    ).first()
                    
                    if file_entry and file_entry.storage_path and os.path.exists(file_entry.storage_path):
                        image_path = file_entry.storage_path
                        file_metadata = {
                            "filename": file_entry.display_name or file_entry.name,
                            "mime_type": file_entry.mime_type,
                            "size_bytes": file_entry.size_bytes,
                            "file_id": file_entry.id
                        }
                        logger.info(f"[ImageAnalysisAgent] Found file: {file_metadata['filename']} at {image_path}")
                    else:
                        logger.warning(f"[ImageAnalysisAgent] File entry not found or path doesn't exist for file_id={file_id}")
                except Exception as e:
                    logger.error(f"[ImageAnalysisAgent] Database lookup failed: {e}")
            
            if not image_path:
                return AgentResult(
                    agent_name="ImageAnalysisAgent",
                    display_name="Image Analysis Agent",
                    result=f"**File Not Found:** Could not locate image file (file_id={file_id}) in database or filesystem.\n\n**Task:** {task}",
                    confidence=0.0,
                    method="File lookup failed",
                    explanation="Image file not accessible",
                    summary="Image analysis failed: File not found"
                )
            
            # Step 2: Read and encode image to base64
            logger.info(f"[ImageAnalysisAgent] Reading image from {image_path}...")
            import base64
            try:
                with open(image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                logger.info(f"[ImageAnalysisAgent] Image encoded, size={len(base64_image)} chars")
            except Exception as e:
                logger.error(f"[ImageAnalysisAgent] Failed to read image: {e}")
                return AgentResult(
                    agent_name="ImageAnalysisAgent",
                    display_name="Image Analysis Agent",
                    result=f"**Read Error:** Could not read image file: {e}\n\n**Path:** {image_path}",
                    confidence=0.0,
                    method="File read error",
                    explanation=str(e),
                    summary="Image analysis failed: Could not read file"
                )
            
            # Step 3: Analyze with GPT Vision
            model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
            vision_model = "gpt-4o" if "gpt-5" in model else model  # gpt-5 doesn't support vision yet
            logger.info(f"[ImageAnalysisAgent] Analyzing with vision model: {vision_model}")
            
            # Build analysis prompt based on task
            analysis_prompt = task if task else "Analyze this image comprehensively and describe what it shows."
            
            completion_params = {
                "model": vision_model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an expert image analyst. Provide detailed, structured analysis.

For charts/plots: Identify chart type, axes, legend, data series, and extract visible data points.
For diagrams: Describe structure, flow, and key components.
For text-heavy images: Perform OCR and extract all readable text.
For photos: Describe scene, objects, composition.

Format your response with markdown headings and bullet points for clarity."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": analysis_prompt
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
            
            try:
                logger.info(f"[ImageAnalysisAgent] Calling vision API...")
                response = await self.llm_client.chat.completions.create(**completion_params)
                analysis_text = response.choices[0].message.content
                logger.info(f"[ImageAnalysisAgent] Analysis complete, response length={len(analysis_text)} chars")
                
                # Format the result
                result_text = f"""## Image Analysis Complete

**File:** {file_metadata.get('filename', 'Unknown')}
**Type:** {file_metadata.get('mime_type', 'Unknown')}
**Size:** {file_metadata.get('size_bytes', 0):,} bytes

---

{analysis_text}
"""
                
                duration = time.time() - start_time
                logger.info(f"[ImageAnalysisAgent] Completed successfully in {duration:.2f}s")
                
                return AgentResult(
                    agent_name="ImageAnalysisAgent",
                    display_name="Image Analysis Agent",
                    result=result_text,
                    confidence=0.9,
                    method=f"GPT Vision ({vision_model})",
                    explanation=f"Analyzed image using {vision_model} with vision API",
                    summary=f"Analyzed {file_metadata.get('filename', 'image')} using GPT Vision",
                    metadata=file_metadata
                )
                
            except Exception as e:
                logger.error(f"[ImageAnalysisAgent] Vision API call failed: {e}")
                import traceback
                logger.error(f"[ImageAnalysisAgent] Traceback:\n{traceback.format_exc()}")
                return AgentResult(
                    agent_name="ImageAnalysisAgent",
                    display_name="Image Analysis Agent",
                    result=f"**Analysis Failed:** Vision API error: {e}\n\nFile: {file_metadata.get('filename', 'Unknown')}",
                    confidence=0.1,
                    method="Vision API Error",
                    explanation=str(e),
                    summary="Image analysis failed due to API error"
                )
            
        except Exception as e:
            logger.error(f"[ImageAnalysisAgent] Unexpected error: {e}")
            import traceback
            logger.error(f"[ImageAnalysisAgent] Traceback:\n{traceback.format_exc()}")
            return AgentResult(
                agent_name="ImageAnalysisAgent",
                display_name="Image Analysis Agent",
                result=f"**Unexpected Error:** {e}\n\n**Task:** {task}",
                confidence=0.0,
                method="Exception",
                explanation=str(e),
                summary="Image analysis failed with unexpected error"
            )
