"""
Preview Streamer Module

Runs a fast preview model (gpt-5-nano) in parallel with the main model to provide
instant word-by-word streaming feedback while waiting for the real response.
"""

import os
import asyncio
import logging
import time
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from fastapi import WebSocket

from .logging_config import get_logger, log_function_entry, log_function_exit, log_step, log_success, log_error, log_warning
from .step_controller import StepController
from .cedar_product_preamble import get_cedar_product_preamble

logger = get_logger(__name__)


class PreviewStreamer:
    """Handles streaming preview responses from fast model"""
    
    @staticmethod
    async def stream_preview(
        llm_client: AsyncOpenAI,
        messages: List[Dict[str, Any]],
        websocket: Optional[WebSocket] = None,
        phase: str = "thinking",
        thread_id: Optional[str] = None,
        server_received_ms: Optional[int] = None
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
            
            # Use configured preview model (defaults to gpt-5-nano)
            from .preview_streamer import PreviewConfig as _PC  # type: ignore
            preview_model = _PC.MODEL
            preview_model_display = preview_model
            log_step(logger, f"Using preview model: {preview_model}")
            
            # Create a modified prompt for nano that asks it to think out loud
            # instead of returning JSON
            preview_messages = []
            
# Override the system prompt to request thinking out loud
            # Different prompts for planning vs synthesis
            cedar_intro = get_cedar_product_preamble()
            if phase == "thinking":
                # Planning phase: compressed, focused instruction
                preview_system = (
                    cedar_intro + "\n\n" +
                    "Think out loud about the user prompt. "
                    "First, explain what the prompt or file is asking. "
                    "Second, briefly list the data, files, or code you would need. "
                    "Third, propose which agent(s) to use and why. "
                    "You may reference any provided notes, files, or database context. "
                    "Keep it short and actionable. Do NOT return JSON."
                )
            else:
                # Synthesis phase: concise follow-up
                preview_system = (
                    cedar_intro + "\n\n" +
                    "Think out loud about what the agent results show. "
                    "What’s done, what’s missing, and which agent(s) should run next? "
                    "Do NOT repeat planning guidance. Keep it concise. Do NOT return JSON."
                )
            
            
            preview_messages.append({"role": "system", "content": preview_system})
            
            # Extract notes/resources context from original messages
            # Look for messages that contain project resources or notes
            notes_context = ""
            resources_context = ""
            
            for msg in messages:
                if msg["role"] == "user":
                    content = msg.get("content", "")
                    # Check if this is a project resources message
                    if "Project Resources Index" in content:
                        resources_context = content
                    # Check if this is conversation history (notes about the project)
                    elif "Previous conversation context" in content:
                        notes_context = content
            
            # Add notes context to preview system prompt if available
            if notes_context:
                preview_messages.append({
                    "role": "user",
                    "content": f"""The following are notes about what else the user has done in this project, to give you context on what they are trying to accomplish:

{notes_context}"""
                })
            
            # Add resources context if available
            if resources_context:
                preview_messages.append({"role": "user", "content": resources_context})
            
            # Add the actual user messages (skip system prompts and context we already extracted)
            for msg in messages:
                if msg["role"] != "system":
                    content = msg.get("content", "")
                    # Skip if we already added it as notes or resources context
                    if content != notes_context and content != resources_context:
                        preview_messages.append(msg)
            
            log_step(logger, f"Built preview messages: {len(preview_messages)} messages")
            
            # Debug: log first 500 chars of each message for troubleshooting
            for i, msg in enumerate(preview_messages):
                content_preview = str(msg.get('content', ''))[:500]
                logger.debug(f"Preview message {i} ({msg.get('role')}): {content_preview}...")
            
            # Send preview start event BEFORE opening the API stream to ensure immediate UI feedback
            now_ms = int(time.time() * 1000)
            log_step(logger, "Sending preview_start event to WebSocket (pre-stream)")
            event_data = {
                "type": "preview_start",
                "phase": phase,
                "model": preview_model_display,
                "timestamp": now_ms,
                "server_emitted_ms": now_ms,
                "server_received_ms": int(server_received_ms) if server_received_ms else None,
                "thread_id": str(thread_id) if thread_id is not None else None
            }
            await websocket.send_json(event_data)
            log_success(logger, f"preview_start event sent: {event_data}")

            # Optional step pause after preview_start
            if thread_id is not None:
                await StepController.wait_next(str(thread_id), "sent_preview_start")

            # Start streaming response
            log_step(logger, "Calling OpenAI API for preview streaming")
            # Use chat.completions for instant streaming (no reasoning delay)
            stream = await llm_client.chat.completions.create(
                model=preview_model,
                messages=preview_messages,
                stream=True,
                max_completion_tokens=PreviewConfig.MAX_TOKENS
            )
            log_success(logger, "Preview stream initiated")
            
            # Stream word by word
            log_step(logger, "Starting token streaming loop")
            full_text = ""
            word_buffer = ""
            token_count = 0
            tokens_emitted = 0  # number of preview_token events actually sent
            
            # Optional step pause right before reading the first token
            if thread_id is not None:
                await StepController.wait_next(str(thread_id), "first_token")

            # chat.completions.create returns chunks with delta.content
            chunk_count = 0
            delta_count = 0
            async for chunk in stream:
                chunk_count += 1
                if chunk_count == 1:
                    logger.debug(f"First chunk received: type={type(chunk)}")
                
                # Handle chat completions format
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                if not delta.content:
                    continue
                
                delta_count += 1
                if delta_count == 1:
                    logger.debug(f"First delta content received after {chunk_count} chunks")
                
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
                        "phase": phase,
                        "timestamp": int(time.time() * 1000),
                        "thread_id": str(thread_id) if thread_id is not None else None
                    })
                    tokens_emitted += 1
                    word_buffer = ""
                
                # Small delay for readability (streaming effect)
                await asyncio.sleep(0.01)
            
            log_step(logger, f"Stream ended: {chunk_count} chunks, {delta_count} deltas, {token_count} tokens sent")
            
            # Send any remaining text
            if word_buffer:
                log_step(logger, "Sending remaining buffer text")
                await websocket.send_json({
                    "type": "preview_token",
                    "text": word_buffer,
                    "phase": phase,
                    "timestamp": int(time.time() * 1000),
                    "thread_id": str(thread_id) if thread_id is not None else None
                })
                tokens_emitted += 1
            
            # Send preview complete
            log_step(logger, "Sending preview_complete event")
            await websocket.send_json({
                "type": "preview_complete",
                "phase": phase,
                "total_length": len(full_text),
                "timestamp": int(time.time() * 1000),
                "thread_id": str(thread_id) if thread_id is not None else None,
                "canceled": False
            })
            
            # Enforce: if no preview text was streamed, emit an error event to surface the failure
            if tokens_emitted == 0:
                try:
                    await websocket.send_json({
                        "type": "preview_warning",
                        "warning": "Preview streaming produced no text",
                        "content": "Preview model returned no delta content; proceeding without preview text.",
                        "details": {
                            "phase": phase,
                            "model": preview_model_display,
                            "chunk_count": chunk_count,
                            "delta_count": delta_count,
                            "thread_id": str(thread_id) if thread_id is not None else None
                        }
                    })
                except Exception:
                    pass
            
            log_success(logger, f"Preview complete: {len(full_text)} chars, {token_count} tokens (events: {tokens_emitted})")
            log_function_exit(logger, "stream_preview")
            
        except asyncio.CancelledError:
            log_warning(logger, "Preview cancelled (real response arrived)")
            try:
                # Inform UI that preview completed due to cancellation so it can annotate the bubble
                await websocket.send_json({
                    "type": "preview_complete",
                    "phase": phase,
                    "total_length": 0,
                    "timestamp": int(time.time() * 1000),
                    "thread_id": str(thread_id) if thread_id is not None else None,
                    "canceled": True
                })
                # If no tokens were streamed at all, emit an error per no-fallback policy
                if 'tokens_emitted' in locals() and tokens_emitted == 0:
                    await websocket.send_json({
                        "type": "preview_warning",
                        "warning": "Preview streaming produced no text (cancelled)",
                        "content": "Preview model produced no text before cancellation; this is not an error.",
                        "details": {
                            "phase": phase,
                            "model": preview_model_display,
                            "thread_id": str(thread_id) if thread_id is not None else None
                        }
                    })
            except Exception:
                pass
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
        phase: str = "thinking",
        thread_id: Optional[str] = None,
        server_received_ms: Optional[int] = None
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
                    llm_client, messages, websocket, phase, thread_id, server_received_ms
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
