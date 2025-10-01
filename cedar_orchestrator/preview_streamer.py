"""
Preview Streamer Module

Runs a fast preview model (gpt-5-nano) in parallel with the main model to provide
instant word-by-word streaming feedback while waiting for the real response.
"""

import os
import asyncio
import logging
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from fastapi import WebSocket

from .logging_config import get_logger, log_function_entry, log_function_exit, log_step, log_success, log_error, log_warning

logger = get_logger(__name__)


class PreviewStreamer:
    """Handles streaming preview responses from fast model"""
    
    @staticmethod
    async def stream_preview(
        llm_client: AsyncOpenAI,
        messages: List[Dict[str, Any]],
        websocket: Optional[WebSocket] = None,
        phase: str = "thinking"
    ) -> None:
        """
        Stream a preview response using gpt-5-nano in parallel with main call.
        
        This is fire-and-forget - it runs in the background and doesn't block.
        
        Args:
            llm_client: OpenAI client
            messages: Same messages being sent to main model
            websocket: WebSocket for streaming
            phase: "thinking" or "synthesis" for UI labeling
        """
        log_function_entry(logger, "stream_preview", 
                          phase=phase,
                          has_websocket=websocket is not None,
                          has_client=llm_client is not None,
                          message_count=len(messages) if messages else 0)
        
        if not websocket or not llm_client:
            log_warning(logger, "Missing websocket or client, aborting preview", 
                       f"ws={websocket is not None}, client={llm_client is not None}")
            return
        
        try:
            log_step(logger, f"Starting preview stream for {phase} phase")
            log_step(logger, f"Messages to send: {len(messages)}")
            
            # Use gpt-5-nano for fast preview
            preview_model = os.getenv("CEDARPY_PREVIEW_MODEL", "gpt-5-nano")
            log_step(logger, f"Using preview model: {preview_model}")
            
            # Start streaming response
            log_step(logger, "Calling OpenAI API for preview streaming")
            stream = await llm_client.chat.completions.create(
                model=preview_model,
                messages=messages,
                stream=True,
                max_completion_tokens=2000  # Limit preview length
            )
            log_success(logger, "Preview stream initiated")
            
            # Send preview start event
            log_step(logger, "Sending preview_start event to WebSocket")
            event_data = {
                "type": "preview_start",
                "phase": phase,
                "model": preview_model
            }
            await websocket.send_json(event_data)
            log_success(logger, f"preview_start event sent: {event_data}")
            
            # Stream word by word
            log_step(logger, "Starting token streaming loop")
            full_text = ""
            word_buffer = ""
            token_count = 0
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                if not delta.content:
                    continue
                
                content = delta.content
                full_text += content
                word_buffer += content
                
                # Send complete words (split on spaces)
                if ' ' in word_buffer or '\n' in word_buffer:
                    token_count += 1
                    if token_count % 10 == 0:  # Log every 10 tokens
                        logger.debug(f"Streamed {token_count} tokens, {len(full_text)} chars total")
                    await websocket.send_json({
                        "type": "preview_token",
                        "text": word_buffer,
                        "phase": phase
                    })
                    word_buffer = ""
                
                # Small delay for readability (streaming effect)
                await asyncio.sleep(0.01)
            
            # Send any remaining text
            if word_buffer:
                log_step(logger, "Sending remaining buffer text")
                await websocket.send_json({
                    "type": "preview_token",
                    "text": word_buffer,
                    "phase": phase
                })
            
            # Send preview complete
            log_step(logger, "Sending preview_complete event")
            await websocket.send_json({
                "type": "preview_complete",
                "phase": phase,
                "total_length": len(full_text)
            })
            
            log_success(logger, f"Preview complete: {len(full_text)} chars, {token_count} tokens")
            log_function_exit(logger, "stream_preview")
            
        except asyncio.CancelledError:
            log_warning(logger, "Preview cancelled (real response arrived)")
            log_function_exit(logger, "stream_preview", result="CANCELLED")
        except Exception as e:
            log_error(logger, "Preview streaming failed", e)
            log_function_exit(logger, "stream_preview", result="ERROR")
            # Don't raise - this is just a preview, failure is OK
    
    @staticmethod
    def start_preview_task(
        llm_client: AsyncOpenAI,
        messages: List[Dict[str, Any]],
        websocket: Optional[WebSocket] = None,
        phase: str = "thinking"
    ) -> Optional[asyncio.Task]:
        """
        Start preview streaming as a background task.
        
        Returns the task so it can be cancelled if real response arrives quickly.
        """
        log_function_entry(logger, "start_preview_task",
                          phase=phase,
                          has_websocket=websocket is not None,
                          has_client=llm_client is not None)
        
        if not websocket:
            log_warning(logger, "No WebSocket, skipping preview")
            log_function_exit(logger, "start_preview_task", result=None)
            return None
        
        if not llm_client:
            log_warning(logger, "No LLM client, skipping preview")
            log_function_exit(logger, "start_preview_task", result=None)
            return None
        
        try:
            log_step(logger, "Creating preview task")
            task = asyncio.create_task(
                PreviewStreamer.stream_preview(
                    llm_client, messages, websocket, phase
                )
            )
            log_success(logger, "Preview task created successfully")
            log_function_exit(logger, "start_preview_task", result="TASK_CREATED")
            return task
        except Exception as e:
            log_error(logger, "Failed to start preview task", e)
            log_function_exit(logger, "start_preview_task", result=None)
            return None
    
    @staticmethod
    async def cancel_preview(task: Optional[asyncio.Task]) -> None:
        """Cancel preview task if it's still running"""
        log_function_entry(logger, "cancel_preview", task_present=task is not None)
        
        if task and not task.done():
            log_step(logger, "Cancelling preview task")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log_success(logger, "Preview task cancelled successfully")
        else:
            log_step(logger, "Preview task already done or None, no cancellation needed")
        
        log_function_exit(logger, "cancel_preview")


class PreviewConfig:
    """Configuration for preview streaming"""
    
    # Enable/disable preview streaming
    ENABLED = os.getenv("CEDARPY_PREVIEW_ENABLED", "true").lower() == "true"
    
    # Model to use for preview
    MODEL = os.getenv("CEDARPY_PREVIEW_MODEL", "gpt-5-nano")
    
    # Delay before starting preview (to avoid if real response is instant)
    START_DELAY_MS = int(os.getenv("CEDARPY_PREVIEW_DELAY", "100"))
    
    # Max tokens for preview
    MAX_TOKENS = int(os.getenv("CEDARPY_PREVIEW_MAX_TOKENS", "2000"))
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if preview streaming is enabled"""
        return cls.ENABLED
    
    @classmethod
    def should_start_preview(cls, estimated_duration_ms: int = 5000) -> bool:
        """
        Decide if preview should be started based on estimated duration.
        
        Only start preview if we expect the real call to take a while.
        """
        return cls.ENABLED and estimated_duration_ms > cls.START_DELAY_MS
