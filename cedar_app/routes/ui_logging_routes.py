"""
UI Logging Routes

Receives logs from client-side JavaScript and writes them to backend log files.
This allows complete visibility into UI behavior, rendering, and event handling.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from cedar_orchestrator.logging_config import get_logger, log_step, log_success

router = APIRouter()
logger = get_logger(__name__)

class UILogEntry(BaseModel):
    """Model for client-side log entries"""
    level: str  # 'info', 'debug', 'warn', 'error'
    message: str
    event_type: Optional[str] = None
    timestamp_client: float  # Client-side timestamp (performance.now())
    timestamp_backend_sent: Optional[float] = None  # When backend sent the event
    data: Optional[Dict[str, Any]] = None  # Additional data


@router.post("/api/ui-log")
async def receive_ui_log(entry: UILogEntry, request: Request):
    """
    Receive a log entry from the client-side JavaScript.
    
    This endpoint allows the frontend to send logs back to the backend,
    providing complete visibility into:
    - What events the UI receives
    - When events are received
    - How events are rendered
    - Latency between backend send and UI receive
    """
    
    try:
        # Calculate latency if we have backend timestamp
        latency_ms = None
        if entry.timestamp_backend_sent:
            # Backend timestamp is in seconds since epoch
            # Client timestamp is performance.now() in milliseconds
            # We need to convert to comparable units
            server_time_ms = datetime.now().timestamp() * 1000
            latency_ms = server_time_ms - entry.timestamp_backend_sent
        
        # Format the log message
        log_msg = f"[UI] {entry.message}"
        
        # Add event type if present
        if entry.event_type:
            log_msg += f" | event_type={entry.event_type}"
        
        # Add latency if calculated
        if latency_ms is not None:
            log_msg += f" | latency={latency_ms:.1f}ms"
        
        # Add any additional data
        if entry.data:
            # Truncate data if too long
            data_str = str(entry.data)
            if len(data_str) > 200:
                data_str = data_str[:200] + "..."
            log_msg += f" | data={data_str}"
        
        # Log at appropriate level
        level = entry.level.lower()
        if level == 'debug':
            logger.debug(log_msg)
        elif level == 'warn' or level == 'warning':
            logger.warning(log_msg)
        elif level == 'error':
            logger.error(log_msg)
        else:  # 'info' or default
            logger.info(log_msg)
        
        return {"status": "logged"}
        
    except Exception as e:
        logger.error(f"Failed to process UI log: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/api/ui-event")
async def receive_ui_event(request: Request):
    """
    Receive a UI event with full details.
    
    This is for more detailed event tracking including:
    - Event receipt timestamp
    - Event processing timestamp  
    - Rendering timestamp
    - DOM manipulation details
    """
    
    try:
        data = await request.json()
        
        event_type = data.get('event_type', 'unknown')
        action = data.get('action', 'unknown')
        timestamp_received = data.get('timestamp_received')
        timestamp_processed = data.get('timestamp_processed')
        timestamp_rendered = data.get('timestamp_rendered')
        backend_timestamp = data.get('backend_timestamp')
        
        log_msg = f"[UI_EVENT] {event_type} | action={action}"
        
        # Calculate latencies
        if timestamp_received and backend_timestamp:
            receive_latency = timestamp_received - backend_timestamp
            log_msg += f" | receive_latency={receive_latency:.1f}ms"
        
        if timestamp_processed and timestamp_received:
            process_time = timestamp_processed - timestamp_received
            log_msg += f" | process_time={process_time:.1f}ms"
        
        if timestamp_rendered and timestamp_processed:
            render_time = timestamp_rendered - timestamp_processed
            log_msg += f" | render_time={render_time:.1f}ms"
        
        if timestamp_rendered and timestamp_received:
            total_time = timestamp_rendered - timestamp_received
            log_msg += f" | total_ui_time={total_time:.1f}ms"
        
        # Add any other data
        other_data = {k: v for k, v in data.items() 
                     if k not in ['event_type', 'action', 'timestamp_received', 
                                  'timestamp_processed', 'timestamp_rendered', 'backend_timestamp']}
        if other_data:
            data_str = str(other_data)
            if len(data_str) > 200:
                data_str = data_str[:200] + "..."
            log_msg += f" | {data_str}"
        
        logger.info(log_msg)
        
        return {"status": "logged"}
        
    except Exception as e:
        logger.error(f"Failed to process UI event: {e}")
        return {"status": "error", "message": str(e)}
