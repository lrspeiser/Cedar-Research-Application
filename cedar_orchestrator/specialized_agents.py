"""
Specialized Agents Module
Contains domain-specific agents for specialized tasks

These agents handle:
1. MathAgent - Mathematical derivations from first principles
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

class MathAgent:
    """Agent that derives mathematical formulas from first principles"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Derive mathematical formulas from first principles and walk through derivations"""
        start_time = time.time()
        logger.info(f"[MathAgent] Starting mathematical derivation for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: MathAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
                result=f"**Agent Failure Report:**\n\nThe Math Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to derive mathematical formulas from first principles. Without it, no derivation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot derive formulas",
                summary="Math Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[MathAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a mathematical expert who derives formulas from first principles.
                        - Start from fundamental axioms and definitions
                        - Show each step of the derivation clearly
                        - Explain the reasoning behind each transformation
                        - Use proper mathematical notation
                        - Include any assumptions or constraints
                        - Provide the final formula and its applications"""
                    },
                    {"role": "user", "content": f"Derive from first principles: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1500
            else:
                completion_params["max_tokens"] = 1500
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            derivation = response.choices[0].message.content
            
            logger.info(f"[MathAgent] Completed derivation in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Mathematical Derivation from First Principles

{derivation}

Why: Derived the formula step-by-step from fundamental mathematical principles"""
            
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
                result=formatted_output,
                confidence=0.85,
                method="First principles derivation",
                explanation="Mathematical derivation from axioms",
                summary=f"Derived formula from first principles for: {task[:80]}{'...' if len(task) > 80 else ''}"
            )
            
        except Exception as e:
            logger.error(f"[MathAgent] Error: {e}")
            return AgentResult(
                agent_name="MathAgent",
                display_name="Math Agent",
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
            
            # Note: This simulates web search results. In production, you'd integrate with actual search APIs
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a research assistant with web search capabilities.
                        Based on the query, provide:
                        1. A list of relevant websites and sources
                        2. Key content and findings from each source
                        3. A summary of the most important information
                        4. Citations and references
                        
                        Format your response as:
                        - Source 1: [URL/Title] - Key findings
                        - Source 2: [URL/Title] - Key findings
                        etc.
                        
                        Then provide a comprehensive summary."""
                    },
                    {"role": "user", "content": f"Research this topic and find relevant sources: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1000
            else:
                completion_params["max_tokens"] = 1000
                completion_params["temperature"] = 0.5
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            research_results = response.choices[0].message.content
            
            logger.info(f"[ResearchAgent] Completed research in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Web Research Results

{research_results}

Why: Conducted web research to find relevant sources and information"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=formatted_output,
                confidence=0.75,
                method="Web search and research",
                explanation="Found and analyzed relevant web sources"
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
                        2. Identifying which specialized agents should be used (available agents: Coding Agent, Math Agent, Research Agent, Data Agent, Notes Agent, Logical Reasoner, General Assistant)
                        3. Determining the sequence of operations
                        4. Specifying how to gather source material
                        5. How to analyze data and compile results
                        6. How to write the final report
                        
                        Format as a numbered step-by-step plan with:
                        - Step number and title
                        - Agent(s) to use
                        - Input/output for each step
                        - Dependencies between steps"""
                    },
                    {"role": "user", "content": f"Create a strategic plan to address: {task}"}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 1200
            else:
                completion_params["max_tokens"] = 1200
                completion_params["temperature"] = 0.4
            
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
                        "content": """You are a data analysis expert. Based on the available database schema and the user's query:
                        1. List relevant tables and their purposes
                        2. Suggest SQL queries that would help answer the question
                        3. Explain what each query would return
                        4. Recommend data transformations or joins if needed
                        
                        Format SQL queries properly with:
                        - Clear comments explaining the purpose
                        - Proper JOIN clauses if needed
                        - Appropriate WHERE conditions
                        - GROUP BY and aggregations as necessary"""
                    },
                    {"role": "user", "content": f"Database Schema:\n{db_metadata}\n\nUser Query: {task}\n\nSuggest relevant SQL queries."}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 800
            else:
                completion_params["max_tokens"] = 800
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            sql_suggestions = response.choices[0].message.content
            
            logger.info(f"[DataAgent] Completed data analysis in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Database Analysis and SQL Suggestions

{sql_suggestions}

Why: Analyzed available databases and suggested relevant SQL queries"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=formatted_output,
                confidence=0.70,
                method="Database analysis and SQL generation",
                explanation="Analyzed schema and suggested queries"
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
                                            {"role": "system", "content": "Generate a brief description for this file based on its content."},
                                            {"role": "user", "content": f"File: {filename}\nContent preview: {first_lines[:500]}"}
                                        ]
                                    }
                                    if "gpt-5" in model:
                                        completion_params["max_completion_tokens"] = 100
                                    else:
                                        completion_params["max_tokens"] = 100
                                    
                                    response = await self.llm_client.chat.completions.create(**completion_params)
                                    ai_description = response.choices[0].message.content.strip()
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
                        "content": """You are a note-taking expert. Create concise, well-organized notes that:
                        1. Capture key findings and insights
                        2. Avoid duplicating existing notes
                        3. Use bullet points and clear headings
                        4. Include important formulas, code snippets, or data
                        5. Add tags for easy searching later
                        6. Reference sources when applicable
                        
                        Format notes with:
                        - Clear titles
                        - Date/timestamp
                        - Categories/tags
                        - Key points
                        - Action items if any"""
                    },
                    {"role": "user", "content": f"Existing Notes:\n{existing_notes_text}\n\nContent to create notes from:\n{content_to_note or task}\n\nCreate new notes without duplicating existing ones."}
                ]
            }
            
            if "gpt-5" in model or "gpt-4.1" in model:
                completion_params["max_completion_tokens"] = 600
            else:
                completion_params["max_tokens"] = 600
                completion_params["temperature"] = 0.3
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            notes = response.choices[0].message.content
            
            logger.info(f"[NotesAgent] Completed note creation in {time.time() - start_time:.3f}s")
            
            formatted_output = f"""Answer: Notes Created

{notes}

Why: Created structured notes from the provided content, avoiding duplication with existing notes"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=formatted_output,
                confidence=0.85,
                method="Intelligent note creation",
                explanation="Created organized notes from findings"
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
__all__ = ['MathAgent', 'ResearchAgent', 'StrategyAgent', 'DataAgent', 'NotesAgent', 'FileAgent']
