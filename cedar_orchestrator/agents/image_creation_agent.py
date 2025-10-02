"""
ImageCreationAgent - Extracted from specialized_agents.py

Individual agent file created during Phase 3 refactoring.
"""

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
from .agent_result import AgentResult

# Configure logging
import logging
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
                # NEVER CREATE A FALLBACK - Let rollback exceptions propagate
                logger.error(f"[ImageCreationAgent] Database commit failed: {e}")
                db_session.rollback()  # If this fails, let it raise
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
