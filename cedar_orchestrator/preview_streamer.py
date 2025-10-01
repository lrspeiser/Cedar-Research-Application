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

logger = logging.getLogger(__name__)


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
        if not websocket or not llm_client:
            return
        
        try:
            logger.info(f"[PreviewStreamer] Starting preview stream ({phase})")
            logger.info(f"[PreviewStreamer] WebSocket: {websocket is not None}")
            logger.info(f"[PreviewStreamer] Messages count: {len(messages)}")
            
            # Use gpt-5-nano for fast preview
            preview_model = os.getenv("CEDARPY_PREVIEW_MODEL", "gpt-5-nano")
            logger.info(f"[PreviewStreamer] Using model: {preview_model}")
            
            # Start streaming response
            stream = await llm_client.chat.completions.create(
                model=preview_model,
                messages=messages,
                stream=True,
                max_completion_tokens=2000  # Limit preview length
            )
            
            # Send preview start event
            logger.info(f"[PreviewStreamer] Sending preview_start event")
            await websocket.send_json({
                "type": "preview_start",
                "phase": phase,
                "model": preview_model
            })
            logger.info(f"[PreviewStreamer] preview_start event sent")
            
            # Stream word by word
            full_text = ""
            word_buffer = ""
            
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
                    logger.debug(f"[PreviewStreamer] Sending token: {word_buffer[:20]}...")
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
                await websocket.send_json({
                    "type": "preview_token",
                    "text": word_buffer,
                    "phase": phase
                })
            
            # Send preview complete
            await websocket.send_json({
                "type": "preview_complete",
                "phase": phase,
                "total_length": len(full_text)
            })
            
            logger.info(f"[PreviewStreamer] Preview complete ({len(full_text)} chars)")
            
        except asyncio.CancelledError:
            logger.info("[PreviewStreamer] Preview cancelled (real response arrived)")
        except Exception as e:
            logger.warning(f"[PreviewStreamer] Preview streaming failed: {e}")
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
        if not websocket:
            logger.info("[PreviewStreamer] No WebSocket, skipping preview")
            return None
        
        if not llm_client:
            logger.info("[PreviewStreamer] No LLM client, skipping preview")
            return None
        
        try:
            task = asyncio.create_task(
                PreviewStreamer.stream_preview(
                    llm_client, messages, websocket, phase
                )
            )
            logger.info("[PreviewStreamer] Preview task started")
            return task
        except Exception as e:
            logger.warning(f"[PreviewStreamer] Failed to start preview task: {e}")
            return None
    
    @staticmethod
    async def cancel_preview(task: Optional[asyncio.Task]) -> None:
        """Cancel preview task if it's still running"""
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("[PreviewStreamer] Preview task cancelled")


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
