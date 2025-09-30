"""
Specialized Agents Module
Contains domain-specific agents for specialized tasks

These agents handle:
1. FormulaAgent - Mathematical derivations from first principles
2. ResearchAgent - Web research and citations
3. StrategyAgent - Strategic planning and coordination
4. DataAgent - Database schema analysis
5. NotesAgent - Documentation and note-taking
6. FileAgent - File downloads and management
"""

import os
import time
import json
import re
import sqlite3
import logging
import urllib.request
import tempfile
import mimetypes
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

# Import AgentResult from execution_agents
from .execution_agents import AgentResult

# Configure logging
logger = logging.getLogger(__name__)

class ImageCreationAgent:
    """Agent that generates images (via OpenAI Images) and saves them into the project files store.
    Keys: OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY must be set. See README: "Images tab and image agents".
    """
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
    
    async def process(self, task: str, *, project_id: Optional[int] = None, branch_id: Optional[int] = None, db_session=None) -> AgentResult:
        start_time = time.time()
        logger.info(f"[ImageCreationAgent] Starting image creation task: {task[:120]}...")
        if not self.llm_client:
            return AgentResult(
                agent_name="ImageCreationAgent",
                display_name="Image Creation",
                result="Image creation unavailable: missing OpenAI client (no API key)",
                confidence=0.0,
                method="images.generate",
                explanation="Set OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY",
                summary="Image creation skipped (no API key)"
            )
        try:
            import base64, uuid, os
            from datetime import datetime
            from cedar_app.db_utils import _project_dirs
            from main_models import FileEntry, Project, Branch
            
            model = os.getenv("CEDARPY_IMAGE_MODEL") or "gpt-image-1"
            prompt = (task or "Create an illustrative image").strip()
            logger.info(f"[ImageCreationAgent] Using model={model}")
            
            # Generate image (base64)
            # Note: AsyncOpenAI supports images.generate returning data[].b64_json
            resp = await self.llm_client.images.generate(model=model, prompt=prompt, size="1024x1024")
            b64 = resp.data[0].b64_json  # type: ignore[attr-defined]
            img_bytes = base64.b64decode(b64)
            
            # Save to project files storage
            if not project_id or not branch_id or db_session is None:
                raise RuntimeError("project_id, branch_id, and db_session are required to save image")
            dirs = _project_dirs(int(project_id))
            images_dir = os.path.join(dirs["files_root"], "images")
            os.makedirs(images_dir, exist_ok=True)
            fname = f"img_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.png"
            fpath = os.path.join(images_dir, fname)
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            size_bytes = len(img_bytes)
            
            # DB row
            fe = FileEntry(
                project_id=int(project_id),
                branch_id=int(branch_id),
                filename=fname,
                display_name=fname,
                file_type="png",
                structure="images",
                mime_type="image/png",
                size_bytes=size_bytes,
                storage_path=fpath,
                ai_title="Generated Image",
                ai_description=prompt
            )
            try:
                db_session.add(fe)
                db_session.commit()
                db_session.refresh(fe)
            except Exception as e:
                try: db_session.rollback()
                except Exception: pass
                raise
            
            url_rel = f"/uploads/{project_id}/images/{fname}"
            elapsed = time.time() - start_time
            result_text = (
                f"Answer: Created image saved as {fname} ({size_bytes} bytes).\n\n"
                f"Where: {url_rel}\n"
                f"What: {prompt}\n"
                f"Note: The new image is available in the Images tab and in the Files list."
            )
            return AgentResult(
                agent_name="ImageCreationAgent",
                display_name="Image Creation",
                result=result_text,
                confidence=0.8,
                method="images.generate",
                explanation=f"Saved to project files store in ~{elapsed:.1f}s",
                summary=f"Generated an image and saved it as {fname}"
            )
        except Exception as e:
            logger.error(f"[ImageCreationAgent] Failed: {e}")
            return AgentResult(
                agent_name="ImageCreationAgent",
                display_name="Image Creation",
                result=f"Answer: Failed to create image: {type(e).__name__}: {e}",
                confidence=0.0,
                method="images.generate",
                explanation="Exception during image generation",
                summary="Image creation failed"
            )

class ImageAnalysisAgent:
    """Agent that analyzes an image (vision) and updates FileEntry AI metadata.
    Keys: OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY must be set. See README: "Images tab and image agents".
    """
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
    
    async def process(self, task: str, *, project_id: Optional[int] = None, branch_id: Optional[int] = None, db_session=None, file_id: Optional[int] = None) -> AgentResult:
        start_time = time.time()
        logger.info(f"[ImageAnalysisAgent] Starting image analysis task for file_id={file_id}...")
        if not self.llm_client:
            return AgentResult(
                agent_name="ImageAnalysisAgent",
                display_name="Image Analysis",
                result="Image analysis unavailable: missing OpenAI client (no API key)",
                confidence=0.0,
                method="vision",
                explanation="Set OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY",
                summary="Image analysis skipped (no API key)"
            )
        try:
            import base64, json, os
            from cedar_app.db_utils import _project_dirs
            from main_models import FileEntry
            
            if not (project_id and branch_id and db_session and file_id):
                raise RuntimeError("project_id, branch_id, db_session, and file_id are required for analysis")
            rec = db_session.query(FileEntry).filter(FileEntry.id==int(file_id), FileEntry.project_id==int(project_id)).first()
            if not rec or not rec.storage_path or not os.path.isfile(rec.storage_path):
                raise FileNotFoundError("Image file not found on disk")
            
            with open(rec.storage_path, 'rb') as f:
                img_b = f.read()
            b64 = base64.b64encode(img_b).decode('ascii')
            mime = (rec.mime_type or 'image/png')
            url_data = f"data:{mime};base64,{b64}"
            
            model = os.getenv("CEDARPY_VISION_MODEL") or os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-4o-mini"
            sys_prompt = """You are a computer vision analyst.
            
            You MUST respond ONLY with valid JSON matching this EXACT schema:
            {
                "title": "short descriptive title",
                "description": "1-2 sentence description",
                "objects": ["object1", "object2"],
                "text": ["text detected in image"],
                "tags": ["tag1", "tag2"],
                "summary": "brief summary for logging"
            }
            
            No extra keys. No prose outside JSON. ONLY valid JSON."""
            user_text = (task or "Analyze this image").strip()
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": url_data}}
                ]}
            ]
            logger.info(f"[ImageAnalysisAgent] Using model={model}")
            resp = await self.llm_client.chat.completions.create(model=model, messages=messages)
            content = (resp.choices[0].message.content or "").strip()
            
            # Parse JSON response - fail fast if invalid
            data = json.loads(content)
            
            title = str(data.get("title") or "").strip()[:100]
            desc = str(data.get("description") or "").strip()[:350]
            tags = data.get("tags") if isinstance(data.get("tags"), list) else []
            objects = data.get("objects") if isinstance(data.get("objects"), list) else []
            text_in_image = data.get("text") if isinstance(data.get("text"), list) else []
            summary = data.get("summary", "Analyzed image")
            
            # Update DB metadata
            rec.ai_title = title or rec.ai_title
            rec.ai_description = desc or rec.ai_description
            # Merge into metadata_json
            meta = dict(rec.metadata_json or {})
            meta.update({
                "vision": {
                    "objects": objects,
                    "text": text_in_image,
                    "tags": tags,
                    "model": model,
                }
            })
            rec.metadata_json = meta
            try:
                db_session.add(rec)
                db_session.commit()
            except Exception:
                try: db_session.rollback()
                except Exception: pass
                raise
            
            elapsed = time.time() - start_time
            result_text = (
                f"Answer: Analyzed image id={rec.id}.\n\n"
                f"Title: {title or '(unchanged)'}\n"
                f"Objects: {', '.join([str(o) for o in objects[:10]]) if objects else '(none)'}\n"
                f"Tags: {', '.join([str(t) for t in tags[:10]]) if tags else '(none)'}\n"
                f"Detected text: {', '.join([str(t) for t in text_in_image[:10]]) if text_in_image else '(none)'}\n"
                f"Stored updates to FileEntry.ai_* and metadata_json."
            )
            return AgentResult(
                agent_name="ImageAnalysisAgent",
                display_name="Image Analysis",
                result=result_text,
                confidence=0.85,
                method="vision",
                explanation=f"Updated DB metadata in ~{elapsed:.1f}s",
                summary=summary
            )
        except Exception as e:
            logger.error(f"[ImageAnalysisAgent] Failed: {e}")
            return AgentResult(
                agent_name="ImageAnalysisAgent",
                display_name="Image Analysis",
                result=f"Answer: Failed to analyze image: {type(e).__name__}: {e}",
                confidence=0.0,
                method="vision",
                explanation="Exception during vision analysis",
                summary="Image analysis failed"
            )

class FormulaAgent:
    """Agent that derives mathematical formulas from first principles"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Derive mathematical formulas from first principles and walk through derivations"""
        start_time = time.time()
        logger.info(f"[FormulaAgent] Starting mathematical derivation for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: FormulaAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=f"**Agent Failure Report:**\n\nThe Formula Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to derive mathematical formulas from first principles. Without it, no derivation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot derive formulas",
                summary="Formula Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[FormulaAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a mathematical expert who derives formulas from first principles.

You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted derivation with steps, explanations, and final formula. Use markdown with LaTeX for equations. This is displayed AS-IS.",
  "final_formula": "The derived formula in LaTeX or plaintext",
  "assumptions": ["assumption 1", "assumption 2"],
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format with markdown, show ALL steps clearly, displayed AS-IS
- Start from fundamental axioms and definitions
- Show each transformation step with explanation
- Use proper mathematical notation (LaTeX in markdown)
- 'final_formula' field: Just the result formula
- 'assumptions' field: List any assumptions or constraints
- No text outside the JSON object

Example response:
{
  "answer": "**Derivation of Quadratic Formula**\n\nStarting from ax² + bx + c = 0...\n\n**Final Formula:** x = (-b ± √(b²-4ac))/(2a)",
  "final_formula": "x = (-b ± √(b²-4ac))/(2a)",
  "assumptions": ["a ≠ 0", "coefficients are real numbers"],
  "summary": "Derived quadratic formula from first principles"
}"""
                    },
                    {"role": "user", "content": f"Derive from first principles: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            full_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                response_data = json.loads(full_response)
            except json.JSONDecodeError as e:
                logger.error(f"[FormulaAgent] Failed to parse JSON: {e}")
                return AgentResult(
                    agent_name="FormulaAgent",
                    display_name="Formula Agent",
                    result=f"**JSON Parse Error:**\n\nLLM returned invalid JSON.\n\n**Error:** {e}",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse response"
                )
            
            # Extract fields
            answer = response_data.get('answer', '').strip()
            final_formula = response_data.get('final_formula', '').strip()
            assumptions = response_data.get('assumptions', [])
            summary = response_data.get('summary', '').strip()
            
            if not answer:
                return AgentResult(
                    agent_name="FormulaAgent",
                    display_name="Formula Agent",
                    result="**Missing Answer:**\n\nLLM response missing 'answer' field.",
                    confidence=0.1,
                    method="Missing answer",
                    explanation="No derivation provided",
                    summary="No answer generated"
                )
            
            if not summary:
                summary = f"Derived formula for: {task[:100]}"
            
            logger.info(f"[FormulaAgent] Completed derivation in {time.time() - start_time:.3f}s")
            logger.info(f"[FormulaAgent] Final formula: {final_formula[:100]}")
            
            # Display LLM's answer AS-IS
            formatted_output = answer
            
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=formatted_output,
                confidence=0.85,
                method="First principles derivation",
                explanation="Mathematical derivation from axioms",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[FormulaAgent] Error: {e}")
            return AgentResult(
                agent_name="FormulaAgent",
                display_name="Formula Agent",
                result=f"Answer: Unable to complete derivation\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Derivation failed"
            )

class ResearchAgent:
    """Agent that performs web searches using GPT's web search capabilities"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Run web search and return relevant sites and content"""
        start_time = time.time()
        logger.info(f"[ResearchAgent] Starting web research for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: ResearchAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=f"**Agent Failure Report:**\n\nThe Research Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to perform web research. Without it, no research is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot perform research",
                summary="Research Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ResearchAgent] Using model: {model}")
            
            # Research using structured JSON schema
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a research assistant with web search capabilities.
                        You must respond ONLY with valid JSON matching this schema:
                        {
                            "sources": [
                                {
                                    "title": "source title",
                                    "url_or_reference": "URL or citation",
                                    "key_findings": "main findings from this source",
                                    "relevance": "why this source matters"
                                }
                            ],
                            "synthesis": "comprehensive summary integrating all sources",
                            "key_insights": ["insight 1", "insight 2"],
                            "confidence_notes": "any limitations or caveats",
                            "summary": "brief executive summary for logging"
                        }
                        
                        Provide at least 3-5 relevant sources with concrete findings."""
                    },
                    {"role": "user", "content": f"Research this topic and find relevant sources: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            research_data = json.loads(raw_content)
            
            logger.info(f"[ResearchAgent] Completed research in {time.time() - start_time:.3f}s")
            
            # Format sources
            sources_text = ""
            if research_data.get("sources"):
                sources_text = "\n\n**Sources:**\n"
                for idx, source in enumerate(research_data["sources"], 1):
                    sources_text += f"{idx}. **{source.get('title', 'Unknown')}**\n"
                    if source.get('url_or_reference'):
                        sources_text += f"   - Reference: {source['url_or_reference']}\n"
                    sources_text += f"   - Findings: {source.get('key_findings', 'N/A')}\n"
                    if source.get('relevance'):
                        sources_text += f"   - Relevance: {source['relevance']}\n"
                    sources_text += "\n"
            
            # Format key insights
            insights_text = ""
            if research_data.get("key_insights"):
                insights_text = "\n**Key Insights:**\n"
                for insight in research_data["key_insights"]:
                    insights_text += f"- {insight}\n"
            
            synthesis = research_data.get("synthesis", "No synthesis available")
            confidence_notes = research_data.get("confidence_notes", "")
            summary = research_data.get("summary", "Research completed")
            
            formatted_output = f"""Answer: Web Research Results

{synthesis}
{insights_text}
{sources_text}
{f'**Caveats:** {confidence_notes}' if confidence_notes else ''}

Why: Conducted web research to find relevant sources and synthesize information"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=formatted_output,
                confidence=0.75,
                method="Web search and research",
                explanation="Found and analyzed relevant web sources",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Error: {e}")
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=f"Answer: Research failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Research error"
            )

class StrategyAgent:
    """Agent that creates detailed strategic plans for addressing queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Create a detailed strategic plan for addressing the user's query"""
        start_time = time.time()
        logger.info(f"[StrategyAgent] Creating strategic plan for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: StrategyAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=f"**Agent Failure Report:**\n\nThe Strategy Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to create strategic plans. Without it, no planning is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot create strategy",
                summary="Strategy Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[StrategyAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a strategic planning expert. Create detailed action plans that include:
                        1. Breaking down the problem into manageable steps
                        2. Identifying which specialized agents should be used
                        3. Determining the sequence of operations
                        4. Specifying how to gather source material
                        5. How to analyze data and compile results
                        6. How to write the final report
                        
                        Format as a numbered step-by-step plan with:
                        - Step number and title
                        - Agent(s) to use
                        - Input/output for each step
                        - Dependencies between steps
                        
                        # AVAILABLE AGENTS AND THEIR CAPABILITIES:
                        
                        **CodeAgent** (strongest): Python execution, calculations, simulations, data analysis (pandas/NumPy/ML), charts/plots (matplotlib), document extraction (CSV/PDF/HTML/OCR), can read/write databases, create/process images.
                        
                        **FormulaAgent**: Step-by-step derivations from first principles; formal proofs with assumptions.
                        
                        **ResearchAgent**: Web research with citations; use when external/current info needed.
                        
                        **StrategyAgent**: Multi-step planning (you can recursively suggest your own use for complex orchestration).
                        
                        **SQLAgent**: Executable SQL only (SQLite-compatible); creates/updates tables, indexes, constraints, runs queries.
                        
                        **DataAgent**: Schema analysis, query guidance; reads DB metadata, proposes SQL to answer questions.
                        
                        **NotesAgent**: Organized notes/summaries; turns bullets/JSON into clean notes with headings/tags/timestamps.
                        
                        **ShellAgent**: System commands (non-interactive); file searches, grep, disk usage, package installs.
                        
                        **FileAgent**: Downloads from URLs, manages files, records metadata; makes files available to other agents.
                        
                        **ImageCreationAgent**: Text-to-image generation; creates diagrams/mockups, saves to project.
                        
                        **ImageAnalysisAgent**: Image understanding/OCR; detects objects/tags/text, updates image metadata.
                        
                        # MULTI-AGENT PATTERNS:
                        - Research-then-Analyze: ResearchAgent → CodeAgent (analyze/plot) → NotesAgent
                        - Ingest-Transform-Report: FileAgent → CodeAgent (extract/clean) → SQLAgent/DataAgent → NotesAgent
                        - Complex Orchestration: StrategyAgent (plan) → ChiefAgent (dispatch iteratively)
                        
                        # USING SUPPORTING ASSETS:
                        - If PDFs/CSVs/images in project: CodeAgent (parse/analyze), ImageAnalysisAgent (OCR), SQLAgent/DataAgent (DB), NotesAgent (document)
                        - Need new files: FileAgent (download first)
                        - CodeAgent can write outputs (CSV/plots) back to project files and DB"""
                    },
                    {"role": "user", "content": f"Create a strategic plan to address: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            strategic_plan = response.choices[0].message.content
            
            logger.info(f"[StrategyAgent] Completed strategic planning in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Strategic Action Plan

{strategic_plan}

Why: Created a comprehensive strategic plan with specific steps and agent assignments"""
            
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=formatted_output,
                confidence=0.80,
                method="Strategic planning",
                explanation="Developed detailed execution strategy"
            )
            
        except Exception as e:
            logger.error(f"[StrategyAgent] Error: {e}")
            return AgentResult(
                agent_name="StrategyAgent",
                display_name="Strategy Agent",
                result=f"Answer: Strategic planning failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Planning error"
            )

class DataAgent:
    """Agent that analyzes available databases and suggests SQL queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.project_id = None  # Will be set during processing
        
    async def process(self, task: str, project_id: Optional[int] = None) -> AgentResult:
        """Get database metadata and suggest relevant SQL queries"""
        start_time = time.time()
        logger.info(f"[DataAgent] Analyzing databases for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: DataAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=f"**Agent Failure Report:**\n\nThe Data Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to analyze data and suggest SQL queries. Without it, no data analysis is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot analyze data",
                summary="Data Agent failed: No LLM configured"
            )
        
        try:
            # Get database metadata if project_id is provided
            db_metadata = "No specific database context available"
            if project_id:
                try:
                    from cedar_app.db_utils import _project_dirs, _get_project_engine
                    db_path = _project_dirs(project_id)["db_path"]
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Get all tables
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = cursor.fetchall()
                        
                        db_metadata = "Available tables:\n"
                        for table in tables:
                            table_name = table[0]
                            cursor.execute(f"PRAGMA table_info({table_name})")
                            columns = cursor.fetchall()
                            db_metadata += f"\n- {table_name}: "
                            db_metadata += ", ".join([f"{col[1]} ({col[2]})" for col in columns])
                        
                        conn.close()
                except Exception as e:
                    logger.warning(f"[DataAgent] Could not get database metadata: {e}")
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[DataAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a data analysis expert. Based on the available database schema and the user's query, provide analysis.
                        You must respond ONLY with valid JSON matching this schema:
                        {
                            "relevant_tables": [
                                {
                                    "table_name": "table_name",
                                    "purpose": "what this table contains",
                                    "relevance": "why it matters for the query"
                                }
                            ],
                            "suggested_queries": [
                                {
                                    "sql": "SELECT ... FROM ...",
                                    "purpose": "what this query does",
                                    "expected_result": "what the result tells us"
                                }
                            ],
                            "analysis": "overall analysis of how to approach the data question",
                            "transformations_needed": ["transformation 1", "transformation 2"],
                            "summary": "brief summary for logging"
                        }
                        
                        Provide at least 1-3 concrete SQL queries that can be executed."""
                    },
                    {"role": "user", "content": f"Database Schema:\n{db_metadata}\n\nUser Query: {task}\n\nSuggest relevant SQL queries."}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            data_analysis = json.loads(raw_content)
            
            logger.info(f"[DataAgent] Completed data analysis in {time.time() - start_time:.3f}s")
            
            # Format relevant tables
            tables_text = ""
            if data_analysis.get("relevant_tables"):
                tables_text = "\n**Relevant Tables:**\n"
                for table in data_analysis["relevant_tables"]:
                    tables_text += f"- **{table.get('table_name', 'Unknown')}**: {table.get('purpose', 'N/A')}\n"
                    if table.get('relevance'):
                        tables_text += f"  _Relevance: {table['relevance']}_\n"
            
            # Format suggested queries
            queries_text = ""
            if data_analysis.get("suggested_queries"):
                queries_text = "\n**Suggested SQL Queries:**\n"
                for idx, query in enumerate(data_analysis["suggested_queries"], 1):
                    queries_text += f"\n{idx}. {query.get('purpose', 'Query')}\n"
                    queries_text += f"```sql\n{query.get('sql', 'N/A')}\n```\n"
                    if query.get('expected_result'):
                        queries_text += f"_Expected Result: {query['expected_result']}_\n"
            
            # Format transformations
            transformations_text = ""
            if data_analysis.get("transformations_needed"):
                transformations_text = "\n**Recommended Transformations:**\n"
                for transform in data_analysis["transformations_needed"]:
                    transformations_text += f"- {transform}\n"
            
            analysis = data_analysis.get("analysis", "No analysis available")
            summary = data_analysis.get("summary", "Data analysis completed")
            
            formatted_output = f"""Answer: Database Analysis and SQL Suggestions

{analysis}
{tables_text}
{queries_text}
{transformations_text}

Why: Analyzed available databases and suggested relevant SQL queries"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=formatted_output,
                confidence=0.70,
                method="Database analysis and SQL generation",
                explanation="Analyzed schema and suggested queries",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[DataAgent] Error: {e}")
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=f"Answer: Data analysis failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Analysis error"
            )

class FileAgent:
    """Agent that downloads files from the web or manages user-provided files"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI], project_id: int = None, branch_id: int = None, db_session = None):
        self.llm_client = llm_client
        self.project_id = project_id
        self.branch_id = branch_id
        self.db_session = db_session
        
    async def process(self, task: str) -> AgentResult:
        """Download files or process file paths and save with metadata"""
        start_time = time.time()
        logger.info(f"[FileAgent] Starting file processing for: {task[:100]}...")
        
        # Import required modules at the start
        import re
        import urllib.request
        import tempfile
        import mimetypes
        
        # Check if task contains URLs or file paths
        url_pattern = r'https?://[^\s]+'
        file_path_pattern = r'(/[^\s]+|[A-Za-z]:\\[^\s]+|\./[^\s]+)'
        
        urls = re.findall(url_pattern, task)
        file_paths = re.findall(file_path_pattern, task)
        
        results = []
        
        # Handle URL downloads
        if urls:
            logger.info(f"[FileAgent] Found {len(urls)} URLs to download")
            for url in urls:
                try:
                    # Create temp directory for downloads
                    download_dir = os.path.join(os.path.expanduser("~"), "CedarDownloads")
                    os.makedirs(download_dir, exist_ok=True)
                    
                    # Extract filename from URL
                    url_path = url.split('?')[0]
                    filename = os.path.basename(url_path) or 'download'
                    
                    # Download file
                    logger.info(f"[FileAgent] Downloading from {url}")
                    with urllib.request.urlopen(url, timeout=30) as response:
                        content = response.read()
                        
                    # Save file
                    timestamp = time.strftime('%Y%m%d_%H%M%S')
                    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
                    full_filename = f"{timestamp}_{safe_filename}"
                    file_path = os.path.join(download_dir, full_filename)
                    
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    # Get file metadata
                    file_size = len(content)
                    mime_type, _ = mimetypes.guess_type(filename)
                    
                    # Read first lines for description
                    first_lines = ""
                    try:
                        if mime_type and 'text' in mime_type:
                            first_lines = content[:500].decode('utf-8', errors='ignore')
                    except:
                        first_lines = "[Binary file]"
                    
                    # Save to database if available
                    file_id = None
                    if self.db_session and self.project_id and self.branch_id:
                        try:
                            from main_models import FileEntry
                            
                            # Generate AI description if LLM available
                            ai_description = None
                            if self.llm_client and first_lines and len(first_lines) > 10:
                                try:
                                    model = os.getenv("CEDARPY_OPENAI_MODEL") or "gpt-5"
                                    completion_params = {
                                        "model": model,
                                        "messages": [
                                            {
                                                "role": "system",
                                                "content": """You are a file analyzer. You MUST respond ONLY with valid JSON:
                                                {
                                                    "description": "brief 1-2 sentence description of file content"
                                                }
                                                No extra text. ONLY JSON."""
                                            },
                                            {"role": "user", "content": f"File: {filename}\nContent preview: {first_lines[:500]}"}
                                        ]
                                    }
                                    if "gpt-5" in model:
                                        completion_params["max_completion_tokens"] = 50000
                                    else:
                                        completion_params["max_tokens"] = 50000
                                    
                                    response = await self.llm_client.chat.completions.create(**completion_params)
                                    content_json = json.loads(response.choices[0].message.content.strip())
                                    ai_description = content_json.get("description", "").strip()
                                except:
                                    pass
                            
                            file_entry = FileEntry(
                                project_id=self.project_id,
                                branch_id=self.branch_id,
                                filename=full_filename,
                                display_name=filename,
                                file_type=os.path.splitext(filename)[1][1:] if '.' in filename else 'unknown',
                                structure='sources' if 'text' in (mime_type or '') else 'binary',
                                mime_type=mime_type or 'application/octet-stream',
                                size_bytes=file_size,
                                storage_path=file_path,
                                ai_title=f"Downloaded: {filename}",
                                ai_description=ai_description or f"Downloaded from {url}",
                                ai_category="downloaded",
                                metadata_json={"source_url": url, "download_time": time.time()}
                            )
                            self.db_session.add(file_entry)
                            self.db_session.commit()
                            file_id = file_entry.id
                            logger.info(f"[FileAgent] Saved file to database with ID: {file_id}")
                        except Exception as e:
                            logger.warning(f"[FileAgent] Failed to save to database: {e}")
                    
                    results.append({
                        "action": "downloaded",
                        "url": url,
                        "path": file_path,
                        "filename": full_filename,
                        "size": file_size,
                        "mime_type": mime_type or 'application/octet-stream',
                        "preview": first_lines[:200],
                        "file_id": file_id
                    })
                    
                except Exception as e:
                    logger.error(f"[FileAgent] Download failed for {url}: {e}")
                    results.append({
                        "action": "error",
                        "url": url,
                        "error": str(e)
                    })
        
        # Handle local file paths
        elif file_paths:
            logger.info(f"[FileAgent] Found {len(file_paths)} file paths to process")
            for path in file_paths:
                try:
                    if os.path.exists(path):
                        file_size = os.path.getsize(path)
                        mime_type, _ = mimetypes.guess_type(path)
                        
                        # Read first lines
                        first_lines = ""
                        try:
                            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                first_lines = f.read(500)
                        except:
                            first_lines = "[Binary file]"
                        
                        results.append({
                            "action": "analyzed",
                            "path": path,
                            "filename": os.path.basename(path),
                            "size": file_size,
                            "mime_type": mime_type or 'unknown',
                            "preview": first_lines[:200]
                        })
                    else:
                        results.append({
                            "action": "error",
                            "path": path,
                            "error": "File not found"
                        })
                except Exception as e:
                    results.append({
                        "action": "error",
                        "path": path,
                        "error": str(e)
                    })
        else:
            # No files or URLs found - provide guidance
            return AgentResult(
                agent_name="FileAgent",
                display_name="File Manager",
                result="""Answer: No files or URLs detected in your request

Why: To use the File Agent, please provide either:
- A URL to download (e.g., https://example.com/file.pdf)
- A file path to analyze (e.g., /Users/you/document.txt)

Suggested Next Steps: Include a specific URL or file path in your request""",
                confidence=0.3,
                method="No files detected",
                explanation="Awaiting file information"
            )
        
        # Format results
        if results:
            answer_lines = []
            for r in results:
                if r["action"] == "downloaded":
                    answer_lines.append(f"✓ Downloaded {r['filename']} ({r['size']} bytes) to {r['path']}")
                elif r["action"] == "analyzed":
                    answer_lines.append(f"✓ Analyzed {r['filename']} ({r['size']} bytes)")
                elif r["action"] == "error":
                    answer_lines.append(f"✗ Error: {r['error']}")
            
            formatted_output = f"""Answer: {chr(10).join(answer_lines)}

Why: Files have been processed and saved with metadata

File Details:
{json.dumps(results, indent=2)}

Suggested Next Steps: Files are ready for further processing or analysis"""
            
            return AgentResult(
                agent_name="FileAgent",
                display_name="File Manager",
                result=formatted_output,
                confidence=0.9 if all(r["action"] != "error" for r in results) else 0.6,
                method="File download and analysis",
                explanation=f"Processed {len(results)} file(s)"
            )
        
        return AgentResult(
            agent_name="FileAgent",
            display_name="File Manager",
            result="No files processed",
            confidence=0.1,
            method="No action taken",
            explanation="No files to process"
        )

class NotesAgent:
    """Agent that creates and manages structured notes from findings"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.existing_notes = []  # Will be populated with existing notes
        
    async def process(self, task: str, content_to_note: str = "", existing_notes: List[str] = None) -> AgentResult:
        """Create notes from content while avoiding duplication"""
        start_time = time.time()
        logger.info(f"[NotesAgent] Creating notes for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: NotesAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=f"**Agent Failure Report:**\n\nThe Notes Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to create structured notes. Without it, no note creation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot create notes",
                summary="Notes Agent failed: No LLM configured"
            )
        
        try:
            if existing_notes:
                self.existing_notes = existing_notes
            
            existing_notes_text = "\n".join(self.existing_notes) if self.existing_notes else "No existing notes"
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[NotesAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a note-taking expert. Create concise, well-organized notes.
                        You must respond ONLY with valid JSON matching this schema:
                        {
                            "title": "clear note title",
                            "timestamp": "current date/time or 'auto'",
                            "tags": ["tag1", "tag2", "tag3"],
                            "category": "main category (e.g., research, code, meeting, etc.)",
                            "key_points": [
                                "key point 1",
                                "key point 2"
                            ],
                            "details": "detailed notes in markdown format with headings, bullet points, code blocks, formulas",
                            "action_items": ["action 1", "action 2"],
                            "sources": ["source 1", "source 2"],
                            "new_content_only": true,
                            "summary": "brief summary for logging"
                        }
                        
                        Ensure notes avoid duplicating existing content and focus on new insights."""
                    },
                    {"role": "user", "content": f"Existing Notes:\n{existing_notes_text}\n\nContent to create notes from:\n{content_to_note or task}\n\nCreate new notes without duplicating existing ones."}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            notes_data = json.loads(raw_content)
            
            logger.info(f"[NotesAgent] Completed note creation in {time.time() - start_time:.3f}s")
            
            # Format notes output
            title = notes_data.get("title", "Notes")
            timestamp = notes_data.get("timestamp", time.strftime('%Y-%m-%d %H:%M:%S'))
            tags = notes_data.get("tags", [])
            category = notes_data.get("category", "general")
            key_points = notes_data.get("key_points", [])
            details = notes_data.get("details", "No details available")
            action_items = notes_data.get("action_items", [])
            sources = notes_data.get("sources", [])
            summary = notes_data.get("summary", "Notes created")
            
            # Build formatted output
            notes_output = f"# {title}\n\n"
            notes_output += f"**Date:** {timestamp}\n"
            notes_output += f"**Category:** {category}\n"
            if tags:
                notes_output += f"**Tags:** {', '.join(tags)}\n"
            notes_output += "\n---\n\n"
            
            if key_points:
                notes_output += "## Key Points\n"
                for point in key_points:
                    notes_output += f"- {point}\n"
                notes_output += "\n"
            
            notes_output += "## Details\n\n"
            notes_output += f"{details}\n\n"
            
            if action_items:
                notes_output += "## Action Items\n"
                for item in action_items:
                    notes_output += f"- [ ] {item}\n"
                notes_output += "\n"
            
            if sources:
                notes_output += "## Sources\n"
                for source in sources:
                    notes_output += f"- {source}\n"
            
            formatted_output = f"""Answer: Notes Created

{notes_output}

Why: Created structured notes from the provided content, avoiding duplication with existing notes"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=formatted_output,
                confidence=0.85,
                method="Intelligent note creation",
                explanation="Created organized notes from findings",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[NotesAgent] Error: {e}")
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=f"Answer: Note creation failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Note creation error"
            )

# Export the specialized agents
__all__ = ['FormulaAgent', 'ResearchAgent', 'StrategyAgent', 'DataAgent', 'NotesAgent', 'FileAgent']
