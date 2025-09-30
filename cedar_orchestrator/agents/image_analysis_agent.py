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
