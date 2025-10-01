"""
FileAgent - Extracted from specialized_agents.py

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
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
                                                "content": build_agent_system_prompt(
                                                    "FileAgent",
                                                    AGENT_ROLES.get("FileAgent", "to download and manage files"),
                                                    """You are a file analyzer. You MUST respond ONLY with valid JSON:
                                                {
                                                    "description": "brief 1-2 sentence description of file content"
                                                }
                                                No extra text. ONLY JSON."""
                                                )
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
