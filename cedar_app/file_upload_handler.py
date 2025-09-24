"""
File upload handler for processing documents through the orchestrator
"""

import os
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import shutil
from pathlib import Path
import mimetypes

logger = logging.getLogger(__name__)

def register_file_upload_routes(app: FastAPI):
    """Register file upload routes for document processing"""
    
    @app.post("/api/upload/process")
    async def process_uploaded_file(file: UploadFile = File(...)):
        """
        Process uploaded file through the orchestrator
        """
        try:
            # Create upload directory
            upload_dir = Path(os.path.expanduser("~")) / "CedarPyData" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Save uploaded file
            file_path = upload_dir / file.filename
            
            # Write file to disk
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Detect file type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = file.content_type
            
            logger.info(f"Uploaded file: {file.filename}, Type: {mime_type}, Path: {file_path}")
            
            return JSONResponse({
                "success": True,
                "file_path": str(file_path),
                "file_name": file.filename,
                "file_type": mime_type,
                "message": f"File uploaded successfully. Use WebSocket to process it."
            })
            
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return JSONResponse({
                "success": False,
                "error": str(e)
            }, status_code=500)
    
    @app.websocket("/ws/process-file")
    async def websocket_file_processor(websocket: WebSocket):
        """
        WebSocket endpoint for processing files with real-time updates
        """
        await websocket.accept()
        
        try:
            while True:
                # Receive file processing request
                data = await websocket.receive_json()
                
                if data.get("action") == "process_file":
                    file_path = data.get("file_path")
                    file_type = data.get("file_type")
                    
                    if not file_path or not os.path.exists(file_path):
                        await websocket.send_json({
                            "type": "error",
                            "content": "File not found"
                        })
                        continue
                    
                    # Import orchestrator
                    try:
                        from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator
                        
                        # Get API key
                        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
                        if not api_key:
                            await websocket.send_json({
                                "type": "error",
                                "content": "OpenAI API key not configured"
                            })
                            continue
                        
                        # Create orchestrator
                        orchestrator = ThinkerOrchestrator(api_key)
                        
                        # Process file
                        result = await orchestrator.process_file(file_path, file_type, websocket)
                        
                    except Exception as e:
                        logger.error(f"File processing error: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "content": f"Processing failed: {str(e)}"
                        })
                
                elif data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "content": str(e)
                })
            except:
                pass

# Export the registration function
__all__ = ['register_file_upload_routes']