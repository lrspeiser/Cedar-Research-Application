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
            
            # Use gpt-5 for fast nano preview
            # Note: gpt-5 with responses.create uses nano by default for speed
            preview_model = os.getenv("CEDARPY_PREVIEW_MODEL", "gpt-5")
            # Display name for UI to distinguish from main model
            preview_model_display = "gpt-5-nano"
            log_step(logger, f"Using preview model: {preview_model} (display: {preview_model_display})")
            
            # Create a modified prompt for nano that asks it to think out loud
            # instead of returning JSON
            preview_messages = []
            
            # Import full agent capabilities glossary from chief prompts
            from .prompts.chief_prompts import get_agent_capabilities
            agent_glossary = get_agent_capabilities()
            
            # Override the system prompt to request thinking out loud
            # Different prompts for planning vs synthesis
            if phase == "thinking":
                # Planning phase: suggest which agents to use
                preview_system = f"""Think out loud how to solve this problem. Consider which agents you would send this problem to and describe what they could do to help. Focus on the ones that would give you the fastest answer, then focus on the ones that would give you the most accurate answer. Suggest we start with the ones that meet both criteria first.

We also provided notes, files and databases that your agents can use that might help.

Available agents:

{agent_glossary}

Do NOT return JSON. Just explain your thought process in plain English as if you're talking through the problem. Do not repeat these instructions back to the user, just follow them."""
            else:
                # Synthesis phase: review what agents did and what's next
                preview_system = f"""Review the agent results provided and think out loud about what we learned. Consider:
- Did the agents answer the question? 
- Is the answer complete or do we need more work?
- If more work is needed, which agents should we use next?

Do NOT repeat what you already suggested in the planning phase. Focus on the NEW information from the agent results.

Do NOT return JSON. Just explain your synthesis in plain English. Do not repeat these instructions back to the user, just follow them."""
            
            
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
            
            # Start streaming response
            log_step(logger, "Calling OpenAI API for preview streaming")
            
            # Convert messages format for responses API
            # responses.create expects "input" with role/content structure
            input_messages = []
            for msg in preview_messages:
                input_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Use responses.create for gpt-5 (nano by default)
            # Only include required fields per API docs
            log_step(logger, f"Using responses.create API for {preview_model}")
            stream = await llm_client.responses.create(
                model=preview_model,
                input=input_messages,
                stream=True
            )
            log_success(logger, "Preview stream initiated")
            
            # Send preview start event
            log_step(logger, "Sending preview_start event to WebSocket")
            event_data = {
                "type": "preview_start",
                "phase": phase,
                "model": preview_model_display,  # Use display name for UI
                "timestamp": time.time() * 1000  # milliseconds since epoch
            }
            await websocket.send_json(event_data)
            log_success(logger, f"preview_start event sent: {event_data}")
            
            # Stream word by word
            log_step(logger, "Starting token streaming loop")
            full_text = ""
            word_buffer = ""
            token_count = 0
            
            # responses.create returns ResponseTextDeltaEvent objects with delta field
            event_count = 0
            delta_count = 0
            async for event in stream:
                event_count += 1
                if event_count == 1:
                    logger.debug(f"First event received: type={type(event)}")
                
                # Handle different event types from responses API
                if hasattr(event, 'type'):
                    event_type = event.type
                    
                    # Log all event types for first few events
                    if event_count <= 5:
                        logger.debug(f"Event {event_count}: type={event_type}")
                    
                    # Only process text delta events
                    if event_type != 'response.output_text.delta':
                        continue
                    
                    delta_count += 1
                    if delta_count == 1:
                        logger.debug("First delta event received")
                    
                    # Extract text content from delta field
                    if not hasattr(event, 'delta'):
                        logger.debug("Delta event missing delta field")
                        continue
                    
                    content = event.delta
                    
                    if not content:
                        logger.debug("Delta event has empty content")
                        continue
                    
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
            
            log_step(logger, f"Stream ended: {event_count} events, {delta_count} deltas, {token_count} tokens sent")
            
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
                "total_length": len(full_text),
                "timestamp": time.time() * 1000  # milliseconds since epoch
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
