"""
WebSocket Chat with Advanced Thinker-Orchestrator Implementation
This module provides the real multi-agent orchestration system.
"""

import os
import logging
import json
import time
import traceback
from typing import Optional
from fastapi import WebSocket, FastAPI
from cedar_orchestrator.orchestrator import ThinkerOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WSDeps:
    """Dependencies container for WebSocket chat"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def register_ws_chat(app: FastAPI, deps: WSDeps, route_path: str = "/ws/chat/{project_id}"):
    """
    Register WebSocket chat routes with advanced orchestrator.
    
    Args:
        app: FastAPI application instance
        deps: Dependencies container
        route_path: WebSocket route path pattern
    """
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY") or ""
    
    if not api_key:
        logger.warning("No OpenAI API key found. Some features will be limited.")
        print("[startup] WARNING: No OpenAI API key configured. LLM features will be limited.")
    else:
        print("[startup] OpenAI API key configured. Full orchestration enabled.")
    
    # Create the advanced orchestrator
    orchestrator = ThinkerOrchestrator(api_key)
    
    # Register route WITH project_id for compatibility
    if "{project_id}" in route_path:
        @app.websocket(route_path)
        async def ws_chat_with_project(websocket: WebSocket, project_id: int):
            """WebSocket endpoint with project context"""
            await handle_ws_chat(websocket, orchestrator, project_id, deps)
    
    # Also register a simple route WITHOUT project_id
    simple_path = "/ws/chat"
    @app.websocket(simple_path)
    async def ws_chat_simple(websocket: WebSocket):
        """WebSocket endpoint without project context"""
        await handle_ws_chat(websocket, orchestrator, None, deps)
    
    logger.info(f"Registered advanced WebSocket routes: {route_path} and {simple_path}")
    print(f"[startup] Advanced thinker-orchestrator WebSocket routes registered")
    print(f"[startup]   - {route_path} (with project context)")
    print(f"[startup]   - {simple_path} (general chat)")

async def handle_ws_chat(
    websocket: WebSocket, 
    orchestrator: ThinkerOrchestrator, 
    project_id: Optional[int],
    deps: WSDeps
):
    """
    Handle WebSocket chat connection with advanced orchestration.
    
    Args:
        websocket: WebSocket connection
        orchestrator: ThinkerOrchestrator instance
        project_id: Optional project ID for context
        deps: Dependencies container
    """
    try:
        await websocket.accept()
        
        # Import chat manager for persistence
        from cedar_app.utils.chat_persistence import get_chat_manager
        chat_manager = get_chat_manager()
        current_chat_number = None
        
        logger.info(f"WebSocket connected: project_id={project_id}")
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                
                # Support both formats: {"type": "message"} and {"action": "chat"}
                message_type = data.get("type")
                action = data.get("action")
                
                if message_type == "message" or action == "chat":
                    content = data.get("content", "").strip()
                    branch_id = data.get("branch_id", 1)  # Default to branch 1
                    chat_number = data.get("chat_number", current_chat_number)
                    file_id = data.get("file_id")
                    dataset_id = data.get("dataset_id")
                    
                    # Create or get chat
                    if not chat_number and project_id:
                        # Create a new chat if none specified
                        chat_data = chat_manager.create_chat(
                            project_id=project_id,
                            branch_id=branch_id,
                            title=f"Chat {content[:30]}..." if content else "New Chat"
                        )
                        chat_number = chat_data['chat_number']
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Created new chat #{chat_number}")
                        
                        # Notify client about new chat
                        await websocket.send_json({
                            "type": "chat_created",
                            "chat_number": chat_number,
                            "title": chat_data['title']
                        })
                    elif chat_number and project_id:
                        current_chat_number = chat_number
                        logger.info(f"[WebSocket] Using existing chat #{chat_number}")
                    
                    logger.info("*"*80)
                    logger.info(f"[WebSocket] New message received from client")
                    logger.info(f"[WebSocket] Project ID: {project_id}, Chat #{chat_number}")
                    logger.info(f"[WebSocket] Message content: {content}")
                    logger.info(f"[WebSocket] Message length: {len(content)} characters")
                    logger.info("*"*80)
                    
                    if not content:
                        logger.warning("[WebSocket] Empty message received, sending error")
                        await websocket.send_json({
                            "type": "error",
                            "error": "Empty message received",
                            "content": "Empty message received"  # Keep both for backward compatibility
                        })
                        continue
                    
                    # Save user message to chat
                    if project_id and chat_number:
                        chat_manager.add_message(
                            project_id=project_id,
                            branch_id=branch_id,
                            chat_number=chat_number,
                            role="user",
                            content=content
                        )
                        chat_manager.set_chat_status(project_id, branch_id, chat_number, "processing")
                    
                    logger.info(f"[WebSocket] Initiating orchestration for: {content[:100]}...")
                    orchestration_start = time.time()
                    
                    # Create a wrapper to capture messages sent to WebSocket
                    class PersistentWebSocket:
                        def __init__(self, ws, chat_mgr, proj_id, br_id, chat_num):
                            self.ws = ws
                            self.chat_mgr = chat_mgr
                            self.proj_id = proj_id
                            self.br_id = br_id
                            self.chat_num = chat_num
                        
                        async def send_json(self, data):
                            # Send to client
                            await self.ws.send_json(data)
                            
                            # Persist certain message types
                            if self.proj_id and self.chat_num:
                                msg_type = data.get('type', '')
                                if msg_type == 'message':
                                    self.chat_mgr.add_message(
                                        self.proj_id, self.br_id, self.chat_num,
                                        role=data.get('role', 'Chief Agent'),
                                        content=data.get('text', ''),
                                        metadata={'type': 'agent_response'}
                                    )
                                elif msg_type == 'final':
                                    self.chat_mgr.add_message(
                                        self.proj_id, self.br_id, self.chat_num,
                                        role='Chief Agent',
                                        content=data.get('text', ''),
                                        metadata={'type': 'final_answer'}
                                    )
                                    self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "complete")
                                elif msg_type == 'error':
                                    self.chat_mgr.set_chat_status(self.proj_id, self.br_id, self.chat_num, "error")
                    
                    # Use wrapper if we have persistence context
                    ws_to_use = websocket
                    if project_id and chat_number:
                        ws_to_use = PersistentWebSocket(websocket, chat_manager, project_id, branch_id, chat_number)
                    
                    # Get per-project database session for persistence (notes, saved code, etc.)
                    db_session = None
                    logger.info(f"[WebSocket-DB] Attempting to create project DB session...")
                    logger.info(f"[WebSocket-DB]   project_id: {project_id}")
                    logger.info(f"[WebSocket-DB]   has deps: {deps is not None}")
                    logger.info(f"[WebSocket-DB]   has get_project_engine: {hasattr(deps, 'get_project_engine') if deps else False}")
                    
                    try:
                        if project_id and hasattr(deps, 'get_project_engine'):
                            logger.info(f"[WebSocket-DB] Getting project engine...")
                            from sqlalchemy.orm import sessionmaker
                            eng = deps.get_project_engine(project_id)
                            logger.info(f"[WebSocket-DB] Got engine: {eng}")
                            logger.info(f"[WebSocket-DB] Engine URL: {eng.url if hasattr(eng, 'url') else 'No URL'}")
                            SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
                            db_session = SessionLocal()
                            logger.info(f"[WebSocket-DB] ✅ Created project DB session")
                            logger.info(f"[WebSocket-DB]   Session type: {type(db_session).__name__}")
                            logger.info(f"[WebSocket-DB]   Session bind: {db_session.bind}")
                        else:
                            if not project_id:
                                logger.warning(f"[WebSocket-DB] ⚠️ No project_id provided")
                            if not hasattr(deps, 'get_project_engine'):
                                logger.warning(f"[WebSocket-DB] ⚠️ deps missing get_project_engine")
                    except Exception as e:
                        logger.error(f"[WebSocket-DB] ❌ Failed to create project DB session")
                        logger.error(f"[WebSocket-DB]   Error: {e}")
                        import traceback
                        logger.error(f"[WebSocket-DB]   Traceback:\n{traceback.format_exc()}")
                    
                    # Emit immediate processing bubble if a file context is present (upload auto-chat)
                    try:
                        if project_id and db_session is not None and file_id:
                            from main_models import FileEntry
                            rec = db_session.query(FileEntry).filter(FileEntry.id == int(file_id), FileEntry.project_id == int(project_id)).first()
                            if rec:
                                await websocket.send_json({
                                    "type": "action",
                                    "function": "processing",
                                    "text": f"Processing {rec.display_name}…",
                                    "call": {
                                        "event": "upload_autochat",
                                        "file_id": int(rec.id),
                                        "filename": rec.display_name,
                                        "size_bytes": rec.size_bytes,
                                        "mime_type": rec.mime_type
                                    }
                                })
                                logger.info(f"[WebSocket] Emitted processing bubble for file_id={rec.id}")
                    except Exception as e:
                        logger.warning(f"[WebSocket] Failed to emit processing bubble: {e}")
                    
                    # Build conversation history from chat manager (full messages)
                    conversation_history = None
                    try:
                        if project_id and chat_number:
                            chat_data = chat_manager.get_chat(project_id, branch_id, chat_number)
                            if chat_data:
                                parts = []
                                for m in (chat_data.get('messages') or []):
                                    role = str(m.get('role') or '').strip()
                                    text = str(m.get('content') or '').strip()
                                    parts.append(f"{role}: {text}")
                                # Optionally include prior agent_results text for richer context
                                for ar in (chat_data.get('agent_results') or []):
                                    try:
                                        an = str(ar.get('agent_name') or 'Agent')
                                        tx = str(ar.get('text') or '')
                                        parts.append(f"{an}: {tx}")
                                    except Exception:
                                        pass
                                conversation_history = "\n".join(parts)
                    except Exception as e:
                        logger.warning(f"[WebSocket] Failed to build conversation history: {e}")
                    
                    # Process with advanced orchestrator (with optional notes persistence)
                    try:
                        # Derive thread_id from chat_number for event correlation
                        # Chat numbers map to threads in this implementation
                        derived_thread_id = chat_number if chat_number else None
                        
                        # If file_id is present and this looks like auto-upload message, provide helpful default prompt
                        query_to_send = content
                        is_file_upload_message = (
                            file_id and (
                                not content or 
                                len(content.strip()) < 20 or 
                                content.strip().startswith("Uploaded ") or
                                content.strip() in ["Uploaded file", "File uploaded"]
                            )
                        )
                        if is_file_upload_message:
                            # Get file metadata from database
                            file_rec = None
                            try:
                                if db_session and file_id:
                                    from main_models import FileEntry
                                    file_rec = db_session.query(FileEntry).filter(
                                        FileEntry.id == int(file_id),
                                        FileEntry.project_id == int(project_id)
                                    ).first()
                            except Exception as e:
                                logger.warning(f"[WebSocket] Could not fetch file metadata: {e}")
                            
                            # Get database metadata for context
                            db_metadata = ""
                            try:
                                if db_session:
                                    # Get list of existing tables
                                    from sqlalchemy import inspect
                                    inspector = inspect(db_session.bind)
                                    table_names = inspector.get_table_names()
                                    if table_names:
                                        db_metadata = f"\n\n**Existing Database Tables:**\n" + "\n".join([f"- {t}" for t in table_names[:20]])
                                        if len(table_names) > 20:
                                            db_metadata += f"\n- ... and {len(table_names) - 20} more tables"
                            except Exception as e:
                                logger.warning(f"[WebSocket] Could not fetch database metadata: {e}")
                            
                            # Build file-type-specific prompt based on mime_type
                            if file_rec:
                                mime = (file_rec.mime_type or "").lower()
                                ext = (file_rec.file_type or "").lower()
                                filename = file_rec.display_name or file_rec.name or f"file_{file_id}"
                                size_kb = file_rec.size_bytes / 1024 if file_rec.size_bytes else 0
                                
                                # File metadata header (used in all prompts)
                                file_info = f"""**Uploaded File:**
- Filename: {filename}
- Type: {mime} (.{ext})
- Size: {size_kb:.1f} KB
- File ID: {file_id}"""
                                
                                if "image" in mime or ext in ["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"]:
                                    # IMAGE-SPECIFIC PROMPT
                                    query_to_send = f"""{file_info}

**Task:** Extract and store chart/image data in database

**Step 1 (This iteration):** Use ImageAnalysisAgent to:
- Identify image type (chart/diagram/photo/screenshot)
- Extract chart data: type, axes, data points, series
- Perform OCR on any text
- Extract metadata

**Step 2 (Next iteration):** Use SQLAgent to:
- CREATE tables: chart_data, chart_metadata, image_text
- INSERT extracted data with file_id={file_id} as foreign key
- Return row counts and table names
{db_metadata}

**IMPORTANT:** Start by analyzing the image with ImageAnalysisAgent."""
                                    logger.info(f"[WebSocket] Using image-specific prompt for {filename}")
                                
                                elif "pdf" in mime or ext == "pdf":
                                    # PDF-SPECIFIC PROMPT
                                    query_to_send = f"""{file_info}

**Task:** Extract PDF content and store in database

**Step 1 (This iteration):** Use PDFExtractionAgent to:
- Extract text from all pages
- Extract tables (convert to structured data)
- Extract embedded images
- Get metadata (author, title, page count)

**Step 2 (Next iteration):** Use SQLAgent to:
- CREATE tables: pdf_pages, pdf_tables, pdf_metadata
- INSERT extracted content with file_id={file_id}
- Return summary of what was stored
{db_metadata}

**IMPORTANT:** Start by extracting PDF content with PDFExtractionAgent."""
                                    logger.info(f"[WebSocket] Using PDF-specific prompt for {filename}")
                                
                                elif any(x in mime for x in ["csv", "json", "excel", "spreadsheet"]) or ext in ["csv", "json", "xlsx", "xls"]:
                                    # STRUCTURED DATA-SPECIFIC PROMPT
                                    query_to_send = f"""{file_info}

**Task:** Parse structured data and load into database

**Step 1 (This iteration):** Use CodeAgent to:
- Read file from storage path
- Infer schema (column names, types, constraints)
- Detect issues (nulls, duplicates, outliers)
- Generate summary statistics

**Step 2 (Next iteration):** Use SQLAgent to:
- CREATE TABLE with appropriate types
- Add constraints (NOT NULL, UNIQUE, PRIMARY KEY)
- INSERT all rows
- Add indexes on key columns
- Return table name and row count
{db_metadata}

**IMPORTANT:** Start by parsing the file with CodeAgent."""
                                    logger.info(f"[WebSocket] Using structured-data prompt for {filename}")
                                
                                else:
                                    # GENERIC FALLBACK PROMPT (for text, markdown, unknown types)
                                    query_to_send = f"""{file_info}

**Task:** Process file and integrate into database
{db_metadata}

**Action Required:**
1. Analyze file content using appropriate agent
2. Extract structured data where possible
3. Store in database with file_id={file_id} as foreign key
4. Provide confirmation of what was stored

**IMPORTANT:** Start by determining the best approach for this file type."""
                                    logger.info(f"[WebSocket] Using generic prompt for {filename} (mime={mime})")
                            else:
                                # Fallback if file metadata couldn't be fetched
                                query_to_send = f"""I uploaded a file (file_id: {file_id}). Please process it and integrate into our database system:

**DATABASE SYSTEM:** SQLite with SQLAlchemy ORM
**How to write to database:** Use SQLAgent to execute SQL CREATE TABLE and INSERT statements
{db_metadata}

**ACTION REQUIRED BY FILE TYPE:**

**For structured data files (CSV, JSON, Excel, SQL):**
1. Analyze the data structure and identify columns/schema
2. **Generate SQL code** to CREATE TABLE (or ALTER existing table)
3. **Generate SQL code** to INSERT/UPDATE the data into the table
4. Execute the SQL code using SQLAgent
5. Provide summary of rows inserted and any data transformations applied
6. Suggest which existing tables this could augment (if applicable)

**For unstructured files (PDFs, text documents, markdown):**
1. **Extract key findings** → Create/update a 'findings' or 'notes' table with structured data
2. **Extract citations/references** → Create/update a 'citations' table (author, title, year, url, etc.)
3. **Extract embedded images** → Save to image library and record in 'images' table
4. **Extract tables** → Convert to structured data and insert into appropriate database tables
5. Generate SQL code for all extractions and execute with SQLAgent
6. Provide summary of what was extracted and where it was stored

**For images (charts, plots, diagrams, photos):**
1. Describe what's shown in the image
2. **Extract data from charts/graphs** → Create table with the data points
3. **Perform OCR** on any text present → Store in 'image_text' table
4. **Save to image library** → Record metadata in 'images' table (file_id, description, extracted_data_table)
5. If chart data extracted, offer to recreate the visualization
6. Generate and execute SQL for all data storage

**IMPORTANT:** 
- Actually execute the SQL code (don't just suggest it)
- Use existing table names from the database metadata when appropriate
- Create new tables with descriptive names if no suitable table exists
- Include the file_id as a foreign key in created tables for traceability
- Provide clear confirmation of what was stored where

Please start by analyzing the file and executing the appropriate data integration steps."""
                            logger.info(f"[WebSocket] File upload detected, using database-focused analysis prompt for file_id={file_id}")
                        
                        await orchestrator.orchestrate(
                            query_to_send,
                            ws_to_use,
                            iteration=0,
                            previous_results=None,
                            project_id=project_id,
                            branch_id=branch_id,
                            thread_id=derived_thread_id,  # pass for WebSocket event correlation
                            db_session=db_session,
                            conversation_history=conversation_history
                        )
                    except Exception as orch_err:
                        # Orchestration failed - mark chat as error
                        logger.error(f"[WebSocket] Orchestration failed: {orch_err}")
                        logger.error(traceback.format_exc())
                        
                        # Update chat status to error
                        if project_id and chat_number:
                            try:
                                chat_manager.set_chat_status(project_id, branch_id, chat_number, "error")
                                chat_manager.add_message(
                                    project_id, branch_id, chat_number,
                                    role="System",
                                    content=f"Error during orchestration: {str(orch_err)}",
                                    metadata={'type': 'system_error'}
                                )
                            except Exception as status_err:
                                logger.error(f"[WebSocket] Failed to update error status: {status_err}")
                        
                        # Send error to client
                        try:
                            await websocket.send_json({
                                "type": "error",
                                "error": f"Orchestration failed: {str(orch_err)}",
                                "content": f"Orchestration failed: {str(orch_err)}",
                                "details": str(orch_err),
                                "stack": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
                            })
                        except:
                            pass
                        raise
                    finally:
                        # Clean up database session
                        if db_session:
                            try:
                                db_session.close()
                            except:
                                pass
                    
                    orchestration_time = time.time() - orchestration_start
                    logger.info("*"*80)
                    logger.info(f"[WebSocket] Orchestration completed in {orchestration_time:.3f}s")
                    logger.info("*"*80)
                    
                    # Log to changelog if we have the necessary deps
                    if project_id and hasattr(deps, 'record_changelog'):
                        try:
                            # Get a database session
                            if hasattr(deps, 'RegistrySessionLocal'):
                                db = deps.RegistrySessionLocal()
                                try:
                                    branch_id = 1  # Default branch
                                    deps.record_changelog(
                                        db=db,
                                        project_id=project_id,
                                        branch_id=branch_id,
                                        action="ws_chat",
                                        input_payload={"message": content},
                                        output_payload={"processed": True}
                                    )
                                finally:
                                    db.close()
                        except Exception as e:
                            logger.error(f"Failed to record changelog: {e}")
                    
                elif data.get("type") == "ping":
                    # Handle ping/pong for connection keepalive
                    await websocket.send_json({"type": "pong"})
                    
                elif data.get("type") == "close":
                    # Clean close requested
                    break
                    
                else:
                    # Unknown message type
                    msg_info = f"type={data.get('type')}, action={data.get('action')}"
                    logger.warning(f"Unknown message format: {msg_info}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Unknown message format: {msg_info}",
                        "content": f"Unknown message format: {msg_info}"  # Keep both for backward compatibility
                    })
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": f"Error processing message: {str(e)}",
                    "content": f"Error processing message: {str(e)}",  # Keep both for backward compatibility
                    "details": str(e),
                    "stack": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
                })
                
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        logger.error(traceback.format_exc())
        
        # If we have an active chat in processing status, mark it as error on disconnect
        if current_chat_number and project_id:
            try:
                from cedar_app.utils.chat_persistence import get_chat_manager
                chat_manager = get_chat_manager()
                chat_data = chat_manager.get_chat(project_id, 1, current_chat_number)  # Default branch 1
                if chat_data and chat_data.get('status') == 'processing':
                    logger.warning(f"[WebSocket] Chat #{current_chat_number} left in processing state, marking as error")
                    chat_manager.set_chat_status(project_id, 1, current_chat_number, "error")
                    chat_manager.add_message(
                        project_id, 1, current_chat_number,
                        role="System",
                        content="Connection lost during processing",
                        metadata={'type': 'disconnect_error'}
                    )
            except Exception as cleanup_err:
                logger.error(f"[WebSocket] Failed to clean up chat status: {cleanup_err}")
    finally:
        try:
            await websocket.close()
            logger.info(f"WebSocket disconnected: project_id={project_id}")
        except:
            pass

# Export public interface
__all__ = ['register_ws_chat', 'WSDeps']