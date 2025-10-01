"""
WebSocket Chat with Advanced Thinker-Orchestrator Implementation
This module provides the real multi-agent orchestration system.
"""

import os
import logging
import json
import time
import traceback
from cedar_orchestrator.step_controller import StepController
from typing import Optional
from fastapi import WebSocket, FastAPI
from cedar_orchestrator.orchestrator import ThinkerOrchestrator
from cedar_orchestrator.logging_config import get_logger, log_function_entry, log_function_exit, log_step, log_success, log_error, log_warning

logger = get_logger(__name__)

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
    log_function_entry(logger, "register_ws_chat", route_path=route_path)
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY") or ""
    
    if not api_key:
        log_warning(logger, "No OpenAI API key found", "Some features will be limited")
        print("[startup] WARNING: No OpenAI API key configured. LLM features will be limited.")
    else:
        log_success(logger, "OpenAI API key configured", "Full orchestration enabled")
        print("[startup] OpenAI API key configured. Full orchestration enabled.")
    
    # Create the advanced orchestrator
    log_step(logger, "Creating ThinkerOrchestrator instance")
    orchestrator = ThinkerOrchestrator(api_key)
    log_success(logger, "ThinkerOrchestrator created")
    
    # Register route WITH project_id for compatibility
    if "{project_id}" in route_path:
        log_step(logger, f"Registering WebSocket route: {route_path}")
        @app.websocket(route_path)
        async def ws_chat_with_project(websocket: WebSocket, project_id: int):
            """WebSocket endpoint with project context"""
            await handle_ws_chat(websocket, orchestrator, project_id, deps)
    
    # Also register a simple route WITHOUT project_id
    simple_path = "/ws/chat"
    log_step(logger, f"Registering WebSocket route: {simple_path}")
    @app.websocket(simple_path)
    async def ws_chat_simple(websocket: WebSocket):
        """WebSocket endpoint without project context"""
        await handle_ws_chat(websocket, orchestrator, None, deps)
    
    log_success(logger, f"WebSocket routes registered: {route_path} and {simple_path}")
    print(f"[startup] Advanced thinker-orchestrator WebSocket routes registered")
    print(f"[startup]   - {route_path} (with project context)")
    print(f"[startup]   - {simple_path} (general chat)")
    log_function_exit(logger, "register_ws_chat")

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
    log_function_entry(logger, "handle_ws_chat", project_id=project_id)
    
    try:
        log_step(logger, "Accepting WebSocket connection")
        await websocket.accept()
        log_success(logger, "WebSocket connection accepted")
        
        # Import chat manager for persistence
        log_step(logger, "Initializing chat manager")
        from cedar_app.utils.chat_persistence import get_chat_manager
        chat_manager = get_chat_manager()
        current_chat_number = None
        log_success(logger, f"Chat manager initialized, project_id={project_id}")
        
        # Main message loop
        log_step(logger, "Entering WebSocket message loop")
        while True:
            try:
                # Receive message from client
                log_step(logger, "Waiting for message from client")
                data = await websocket.receive_json()
                log_success(logger, "Message received from client", f"data keys: {list(data.keys())}")
                
                # Support both formats: {"type": "message"} and {"action": "chat"}
                message_type = data.get("type")
                action = data.get("action")
                log_step(logger, f"Message type: {message_type}, action: {action}")
                
                if message_type == "step_control":
                    # Developer step-through controls for preview
                    try:
                        target = str(data.get("target") or "preview").lower()
                        cmd = str(data.get("cmd") or "").lower().strip()
                        t_id = data.get("thread_id")
                        # Fallback to current chat number for correlation if thread_id missing
                        t_id = str(t_id) if t_id is not None else (str(current_chat_number) if current_chat_number else None)
                        if target == "preview":
                            if cmd == "enable":
                                StepController.enable(t_id)
                            elif cmd == "disable":
                                StepController.disable(t_id)
                            elif cmd == "next":
                                StepController.next(t_id)
                            elif cmd in ("cont", "continue"):
                                StepController.cont(t_id)
                        await websocket.send_json({
                            "type": "step_status",
                            "target": target,
                            "enabled": StepController._get(t_id).enabled,
                            "continue_mode": StepController._get(t_id).continue_mode,
                            "thread_id": t_id
                        })
                    except Exception as e:
                        logger.error(f"[WebSocket] step_control handling failed: {e}")
                    continue

                if message_type == "message" or action == "chat":
                    content = data.get("content", "").strip()
                    branch_id = data.get("branch_id", 1)  # Default to branch 1
                    chat_number = data.get("chat_number", current_chat_number)
                    file_id = data.get("file_id")
                    dataset_id = data.get("dataset_id")
                    log_step(logger, f"Processing chat message", f"content_length={len(content)}, chat_number={chat_number}")
                    
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
                    
                    logger.info("="*80)
                    log_step(logger, "Processing new user message")
                    log_step(logger, f"Project ID: {project_id}, Chat #{chat_number}")
                    log_step(logger, f"Message: {content[:200]}..." if len(content) > 200 else f"Message: {content}")
                    log_step(logger, f"Length: {len(content)} characters")
                    logger.info("="*80)
                    
                    if not content:
                        log_warning(logger, "Empty message received")
                        await websocket.send_json({
                            "type": "error",
                            "error": "Empty message received",
                            "content": "Empty message received"  # Keep both for backward compatibility
                        })
                        log_step(logger, "Error event sent to client")
                        continue
                    
                    # Save user message to chat
                    if project_id and chat_number:
                        log_step(logger, "Saving user message to chat")
                        chat_manager.add_message(
                            project_id=project_id,
                            branch_id=branch_id,
                            chat_number=chat_number,
                            role="user",
                            content=content
                        )
                        chat_manager.set_chat_status(project_id, branch_id, chat_number, "processing")
                        log_success(logger, "User message saved and status set to processing")
                    
                    log_step(logger, f"Initiating orchestration")
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
                            db_tables = []
                            try:
                                if db_session:
                                    from sqlalchemy import inspect
                                    inspector = inspect(db_session.bind)
                                    db_tables = inspector.get_table_names()
                            except Exception as e:
                                logger.warning(f"[WebSocket] Could not fetch database metadata: {e}")
                            
                            # Build minimal data-only prompt - let Chief Agent decide what to do
                            if file_rec:
                                filename = file_rec.display_name or file_rec.name or f"file_{file_id}"
                                mime = (file_rec.mime_type or "").lower()
                                ext = (file_rec.file_type or "").lower()
                                size_kb = file_rec.size_bytes / 1024 if file_rec.size_bytes else 0
                                storage_path = file_rec.storage_path or "(path unknown)"
                                
                                # DATA-ONLY prompt - no instructions, just facts
                                query_to_send = f"""User uploaded a file:

**File Details:**
- Filename: {filename}
- Type: {mime} (.{ext})
- Size: {size_kb:.1f} KB
- File ID: {file_id}
- Storage Path: {storage_path}

**Database Context:**
- Existing tables: {', '.join(db_tables[:30]) if db_tables else 'none'}
{f'- ... and {len(db_tables) - 30} more' if len(db_tables) > 30 else ''}

Please analyze and process this file."""
                                logger.info(f"[WebSocket] File upload: {filename} ({mime}, {size_kb:.1f}KB, file_id={file_id})")
                            else:
                                # Fallback if file metadata couldn't be fetched
                                query_to_send = f"""User uploaded a file (file_id: {file_id}).

**Database Context:**
- Existing tables: {', '.join(db_tables[:30]) if db_tables else 'none'}
{f'- ... and {len(db_tables) - 30} more' if len(db_tables) > 30 else ''}

Please analyze and process this file."""
                            logger.info(f"[WebSocket] File upload detected for file_id={file_id}")
                        
                        await orchestrator.orchestrate(
                            query_to_send,
                            ws_to_use,
                            iteration=0,
                            previous_results=None,
                            project_id=project_id,
                            branch_id=branch_id,
                            thread_id=derived_thread_id,  # pass for WebSocket event correlation
                            db_session=db_session,
                            conversation_history=conversation_history,
                            file_id=file_id,  # Pass file_id for image/file processing agents
                            dataset_id=dataset_id  # Pass dataset_id if present
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
                    
                elif data.get("type") == "cancel":
                    # User requested cancellation; mark chat as error and close
                    try:
                        cancel_reason = str(data.get("reason") or "user_cancelled")
                    except Exception:
                        cancel_reason = "user_cancelled"
                    if project_id and current_chat_number:
                        try:
                            chat_manager.set_chat_status(project_id, 1, current_chat_number, "error")
                            chat_manager.add_message(
                                project_id, 1, current_chat_number,
                                role="System",
                                content=f"Run cancelled: {cancel_reason}",
                                metadata={'type': 'user_cancel'}
                            )
                        except Exception as e:
                            logger.error(f"[WebSocket] Failed to mark chat cancelled: {e}")
                    try:
                        await websocket.close(code=4001)
                    except Exception:
                        pass
                    break
                
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