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
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

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
            
            # Build enhanced analysis prompt with schema requirements
            # Read schema documentation for reference
            schema_instruction = f"""
**CRITICAL: Return your analysis as a single, valid JSON object matching this exact structure:**

```json
{{
  "file_id": {file_id},
  "metadata": {{
    "image_type": "chart|diagram|photo|screenshot|mixed",
    "chart_type": "line|scatter|bar|histogram|heatmap|pie|etc (null if not a chart)",
    "title": "extracted title text",
    "width": <pixel width>,
    "height": <pixel height>,
    "color_palette": ["#hex1", "#hex2"],
    "has_annotations": true|false,
    "has_legend": true|false,
    "has_gridlines": true|false
  }},
  "purpose": {{
    "purpose_type": "data_visualization|comparison|trend_analysis|distribution|relationship|composition|documentation|illustration",
    "primary_message": "What is the main takeaway or message this image communicates?",
    "audience": "Who is the intended audience? (e.g., researchers, students, general public)",
    "context": "What domain or field does this relate to? (e.g., astronomy, finance, medical)",
    "confidence": 0.0-1.0
  }},
  "conclusions": [
    {{
      "conclusion_text": "A specific conclusion that can be drawn from this image",
      "evidence": "Observable evidence in the image that supports this conclusion (be specific)",
      "reasoning": "Logical reasoning that connects the evidence to the conclusion",
      "confidence": 0.0-1.0,
      "conclusion_type": "trend|correlation|anomaly|pattern|relationship|comparison",
      "order_index": 0
    }}
  ],
  "axes": [
    {{
      "axis_name": "x|y|z|color|size",
      "label": "axis label",
      "units": "units",
      "scale_type": "linear|log|log10|symlog|date",
      "min_value": <number>,
      "max_value": <number>,
      "tick_values": [tick1, tick2, ...],
      "gridlines": true|false
    }}
  ],
  "series": [
    {{
      "series_name": "series name",
      "legend_label": "legend text",
      "color": "#hexcolor",
      "marker_style": "circle|square|triangle|none",
      "line_style": "solid|dashed|dotted|none",
      "series_type": "line|scatter|bar|area|error_bars",
      "order_index": 0
    }}
  ],
  "data_points": [
    {{
      "series_name": "series name",
      "x_value": <number>,
      "y_value": <number>,
      "z_value": <number or null>,
      "error_x": <number or null>,
      "error_y": <number or null>,
      "label": "point label or null",
      "order_index": 0
    }}
  ],
  "text_extractions": [
    {{
      "text_content": "extracted text",
      "text_type": "title|subtitle|axis_label|legend|annotation|caption|table|equation|body",
      "bbox_x0": <int or null>,
      "bbox_y0": <int or null>,
      "bbox_x1": <int or null>,
      "bbox_y1": <int or null>,
      "confidence": 0.0-1.0,
      "order_index": 0
    }}
  ]
}}
```

**INSTRUCTIONS:**
1. **Metadata**: Identify image type and basic properties
2. **Purpose**: Assess what this image is trying to communicate and why it was created
3. **Conclusions**: Draw 1-3 specific conclusions from the data/content with evidence and reasoning
4. **Technical Details**: Extract axes, series, data points for charts; or relevant structures for other image types
5. **Text**: OCR all visible text with context about its role
6. **Format**: Return ONLY the JSON object, no markdown, no extra text

For the **purpose** section, think about:
- What story is this image telling?
- What should the viewer learn or understand?
- What decision or insight might this support?

For **conclusions**, follow this pattern:
- State the conclusion clearly
- Cite specific visual evidence (e.g., "Data points show X decreasing from A to B")
- Explain the reasoning (e.g., "This pattern suggests...because...")
- Assess your confidence (higher if evidence is clear and unambiguous)
"""
            
            analysis_prompt = f"{task}\n\n{schema_instruction}"
            
            completion_params = {
                "model": vision_model,
                "messages": [
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "ImageAnalysisAgent",
                            AGENT_ROLES.get("ImageAnalysisAgent", "to analyze images and extract structured data"),
                            """You are an expert image analyst specializing in scientific visualization, data extraction, and visual reasoning.

Your task is to:
1. Analyze images comprehensively (charts, diagrams, photos, screenshots)
2. Extract structured data (axes, series, data points for charts)
3. Assess the PURPOSE: What is this image trying to communicate?
4. Draw CONCLUSIONS: What insights can be derived from this image?
5. Provide REASONING: Why do these conclusions follow from the visual evidence?
6. Return results as valid JSON matching the exact schema provided. Additionally include a 'db_update' object with SQL to persist results.

IMPORTANT:
- Return ONLY valid JSON, no markdown code fences, no explanatory text
- Be specific and quantitative in evidence and reasoning
- Assess confidence honestly (0.0 = uncertain, 1.0 = certain)
- For charts: extract as many data points as visible
- For conclusions: connect observable evidence to logical inferences
- For 'db_update'.sql, provide SQLite-compatible DDL/DML and use {{project_id}}, {{branch_id}}, {{file_id}} placeholders for context"""
                        )
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
                
                # Try to parse as JSON and format nicely
                try:
                    # Clean response - remove markdown code fences if present
                    cleaned_response = analysis_text.strip()
                    if cleaned_response.startswith("```json"):
                        cleaned_response = cleaned_response[7:]
                    if cleaned_response.startswith("```"):
                        cleaned_response = cleaned_response[3:]
                    if cleaned_response.endswith("```"):
                        cleaned_response = cleaned_response[:-3]
                    cleaned_response = cleaned_response.strip()
                    
                    # Parse JSON
                    analysis_data = json.loads(cleaned_response)
                    logger.info(f"[ImageAnalysisAgent] Successfully parsed JSON response")
                    
                    # Format as human-readable text + preserve JSON
                    purpose = analysis_data.get('purpose', {})
                    conclusions = analysis_data.get('conclusions', [])
                    metadata = analysis_data.get('metadata', {})

                    # Capture db_update if present
                    db_update = analysis_data.get('db_update') if isinstance(analysis_data, dict) else None
                    
                    result_text = f"""## Image Analysis Complete

**File:** {file_metadata.get('filename', 'Unknown')}
**Type:** {file_metadata.get('mime_type', 'Unknown')}
**Size:** {file_metadata.get('size_bytes', 0):,} bytes

---

### Purpose
**Type:** {purpose.get('purpose_type', 'Unknown')}
**Message:** {purpose.get('primary_message', 'Not specified')}
**Context:** {purpose.get('context', 'Not specified')}
**Audience:** {purpose.get('audience', 'Not specified')}

### Conclusions
"""
                    
                    for i, conclusion in enumerate(conclusions, 1):
                        result_text += f"""
**{i}. {conclusion.get('conclusion_text', 'Unknown conclusion')}**
- **Evidence:** {conclusion.get('evidence', 'Not provided')}
- **Reasoning:** {conclusion.get('reasoning', 'Not provided')}
- **Confidence:** {conclusion.get('confidence', 0.5):.0%}
- **Type:** {conclusion.get('conclusion_type', 'unknown')}
"""
                    
                    result_text += f"""

### Structured Data (JSON)

```json
{json.dumps(analysis_data, indent=2)}
```

**Note:** This JSON can be passed directly to SQLAgent for database storage using the schema defined in `IMAGE_ANALYSIS_SCHEMA.md`.
"""
                    
                    duration = time.time() - start_time
                    logger.info(f"[ImageAnalysisAgent] Completed successfully in {duration:.2f}s")
                    
                    return AgentResult(
                        agent_name="ImageAnalysisAgent",
                        display_name="Image Analysis Agent",
                        result=result_text,
                        confidence=0.9,
                        method=f"GPT Vision ({vision_model}) + Structured Analysis",
                        explanation=f"Analyzed image with purpose assessment, conclusions, and reasoning. Extracted structured data in JSON format.",
                        summary=f"Analyzed {file_metadata.get('filename', 'image')}: {purpose.get('primary_message', 'No summary')[:100]}",
                        artifacts={
                            "file_metadata": file_metadata,
                            "analysis_json": analysis_data,  # Store full JSON for SQLAgent
                            **({"db_update": db_update} if db_update else {})
                        }
                    )
                    
                except json.JSONDecodeError as e:
                    # NEVER CREATE A FALLBACK - Fail loudly so we can fix the root cause
                    logger.error(f"[ImageAnalysisAgent] FATAL: Could not parse response as JSON: {e}")
                    logger.error(f"[ImageAnalysisAgent] Raw response: {analysis_text}")
                    logger.error(f"[ImageAnalysisAgent] This indicates the LLM did not follow the JSON schema in its prompt")
                    logger.error(f"[ImageAnalysisAgent] Fix the prompt or LLM model - DO NOT add fallback logic")
                    raise ValueError(
                        f"ImageAnalysisAgent failed to return valid JSON. "
                        f"Error: {e}. "
                        f"Raw response (first 1000 chars): {analysis_text[:1000]}"
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
