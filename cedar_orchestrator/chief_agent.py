"""
Chief Agent Module

The ChiefAgent is responsible for:
- Reviewing agent results and making decisions
- Routing queries to appropriate specialized agents
- Synthesizing multi-agent outputs into coherent responses
- Managing iteration loops and convergence
"""

import os
import time
import json
import logging
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from fastapi import WebSocket

from .agents import AgentResult
from .preview_streamer import PreviewStreamer, PreviewConfig
from .logging_config import get_logger, log_function_entry, log_function_exit, log_step, log_success, log_error, log_warning

logger = get_logger(__name__)


class ChiefAgent:
    """Chief Agent that reviews all sub-agent responses and makes final decisions"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        log_function_entry(logger, "ChiefAgent.__init__", llm_client_present=llm_client is not None)
        self.llm_client = llm_client
        log_success(logger, "ChiefAgent initialized", f"LLM client: {'present' if llm_client else 'MISSING'}")
        log_function_exit(logger, "ChiefAgent.__init__")
        
        
    async def review_and_decide(self, user_query: str, agent_results: List[AgentResult], iteration: int = 0, max_iterations: int = 10, previous_context: str = "", resources: Optional[Dict[str, Any]] = None, conversation_history: Optional[str] = None, ws: Optional[WebSocket] = None, run_logs: Optional[List[str]] = None, thread_id: Optional[int] = None) -> Dict[str, Any]:
        """Review all agent results and make the final decision on what to do next.
        resources: Optional index of project assets (files, code, databases, notes, images).
        thread_id: Thread ID for WebSocket event correlation (will be converted to string for caching)."""
        log_function_entry(logger, "review_and_decide", 
                          query=user_query[:100],
                          agent_results_count=len(agent_results),
                          iteration=iteration,
                          max_iterations=max_iterations,
                          has_websocket=ws is not None,
                          thread_id=thread_id)
        
        start_time = time.time()
        remaining_loops = max_iterations - iteration - 1
        log_step(logger, f"Starting review (iteration {iteration}/{max_iterations}, {remaining_loops} loops remaining)")
        
        if not self.llm_client:
            log_error(logger, "No LLM client available")
            raise RuntimeError("ChiefAgent requires LLM client - cannot operate without it")
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            log_step(logger, f"Using LLM model: {model}")
            
            # Stream thinking start to UI
            # Differentiate between planning (no results) and synthesis (has results)
            log_step(logger, "Sending thinking/synthesis start event to UI")
            try:
                if ws is not None:
                    event_type = "thinking_start" if not agent_results else "synthesis_start"
                    phase = "Planning" if not agent_results else "Synthesis"
                    event_data = {
                        "type": event_type,
                        "phase": phase,
                        "model": model,
                        "iteration": iteration + 1
                    }
                    log_step(logger, f"Sending WebSocket event: {event_type}", f"phase={phase}")
                    await ws.send_json(event_data)
                    log_success(logger, "WebSocket event sent successfully")
                else:
                    log_warning(logger, "No WebSocket available, skipping UI event")
            except Exception as e:
                log_error(logger, "Failed to send WebSocket event", e)
            
            # Import prompt templates
            from .prompts.chief_prompts import get_system_prompt, get_validation_schema
            
            # Get the system prompt (includes all routing guidance)
            system_prompt = get_system_prompt(
                iteration=iteration,
                max_iterations=max_iterations,
                remaining_loops=remaining_loops,
                has_agent_results=bool(agent_results)
            )
            
            # Build messages for Chief Agent
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history if available
            if conversation_history:
                try:
                    messages.append({
                        "role": "user",
                        "content": f"Previous conversation context:\n{conversation_history[:2000]}"
                    })
                except Exception:
                    pass
            
            # Add resource index if available
            if resources:
                try:
                    res_str = json.dumps(resources, indent=2)
                    if len(res_str) > 8000:
                        res_str = res_str[:8000] + "\n... (truncated)"
                    messages.append({
                        "role": "user",
                        "content": f"Project Resources Index:\n```json\n{res_str}\n```"
                    })
                except Exception:
                    pass
            
            # Add agent results if we have them (synthesis phase)
            if agent_results:
                results_summary = "Agent Results:\n\n"
                for i, result in enumerate(agent_results, 1):
                    results_summary += f"**Agent {i}: {result.display_name}** (confidence: {result.confidence:.2f})\n"
                    results_summary += f"Summary: {result.summary}\n"
                    results_summary += f"Result:\n{result.result[:1000]}\n\n"
                messages.append({"role": "user", "content": results_summary})
            
            # Add the main user query
            messages.append({"role": "user", "content": f"User Query: {user_query}"})
            
            # Start preview streaming in parallel (non-blocking)
            # Only enable preview for synthesis phase - thinking phase takes too long with gpt-5 reasoning
            log_step(logger, "Checking preview streaming configuration")
            preview_task = None
            preview_enabled = PreviewConfig.is_enabled()
            has_ws = ws is not None
            is_synthesis = bool(agent_results)
            log_step(logger, f"Preview enabled: {preview_enabled}, WebSocket: {has_ws}, synthesis: {is_synthesis}")
            
            if preview_enabled and has_ws and is_synthesis:
                phase = "synthesis"
                log_step(logger, f"Starting preview task for {phase} phase")
                preview_task = PreviewStreamer.start_preview_task(
                    self.llm_client, messages, ws, phase
                )
                if preview_task:
                    log_success(logger, f"Preview task started for {phase} phase")
                else:
                    log_warning(logger, "Preview task creation returned None")
            else:
                log_warning(logger, f"Preview NOT started", f"enabled={preview_enabled}, ws={has_ws}, synthesis={is_synthesis}")
            
            # Call LLM (real model)
            log_step(logger, f"Calling LLM with {len(messages)} messages")
            # Note: gpt-5 only supports temperature=1 (default), don't set it
            response = await self.llm_client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=50000
            )
            log_success(logger, "LLM response received")
            
            # Cancel preview once real response arrives
            if preview_task:
                log_step(logger, "Cancelling preview task")
                await PreviewStreamer.cancel_preview(preview_task)
                log_success(logger, "Preview task cancelled")
            
            raw_content = response.choices[0].message.content
            log_step(logger, f"Got response: {len(raw_content)} chars")
            logger.debug(f"Raw JSON response:\n{raw_content[:500]}...")
            
            # Try to parse JSON
            def _validate_and_normalize(data: dict) -> dict:
                """Validate and normalize Chief Agent response"""
                if not isinstance(data, dict):
                    return {}
                
                # Ensure decision field
                if "decision" not in data:
                    data["decision"] = "loop"
                
                # Normalize decision values
                decision = str(data.get("decision", "")).lower().strip()
                if decision not in ("final", "loop", "clarify"):
                    data["decision"] = "loop"
                
                # Ensure agent_tasks is a list
                if "agent_tasks" not in data or not isinstance(data.get("agent_tasks"), list):
                    data["agent_tasks"] = []
                
                return data
            
            # Parse JSON (with repair attempts if needed)
            decision_data = {}
            max_retries = 3
            last_error = ""
            last_output = ""
            
            try:
                # Try direct parse first
                parsed = json.loads(raw_content)
                decision_data = _validate_and_normalize(parsed)
            except Exception as e:
                logger.warning(f"[ChiefAgent] Initial JSON parse failed: {e}")
                last_error = str(e)
                last_output = raw_content[:1500]
                
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_content, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1))
                        decision_data = _validate_and_normalize(parsed)
                    except Exception:
                        pass
                
                # If still no valid JSON, try repair with LLM
                if not decision_data:
                    for retries in range(1, max_retries + 1):
                        logger.info(f"[ChiefAgent] Attempting JSON repair (attempt {retries}/{max_retries})")
                        
                        repair_msgs = [
                            {"role": "system", "content": "You are a JSON repair assistant. Fix malformed JSON to be valid. Return ONLY valid JSON, no explanations."},
                            {"role": "user", "content": f"Fix this JSON:\n\n{raw_content[:4000]}"}
                        ]
                        
                        # Add run logs context for debugging
                        try:
                            if run_logs and len(run_logs) > 0:
                                logs_text = "\n".join(run_logs[-20:])
                                if len(logs_text) > 4000:
                                    logs_text = logs_text[-4000:]
                                repair_msgs.append({
                                    "role": "user",
                                    "content": "Run Logs (recent):\n" + logs_text
                                })
                        except Exception:
                            pass

                        try:
                            repair_resp = await self.llm_client.chat.completions.create(model=model, messages=repair_msgs, max_completion_tokens=50000)
                            repaired = repair_resp.choices[0].message.content
                            decision_data = _validate_and_normalize(json.loads(repaired))
                            break
                        except Exception as e2:
                            last_error = str(e2)
                            last_output = (repaired if 'repaired' in locals() else '')[:1500]
                            logger.warning(f"[ChiefAgent] Repair attempt {retries} failed: {e2}")
                            decision_data = {}

                if not decision_data:
                    # No fallback - raise error
                    raise RuntimeError(
                        f"Chief Agent failed to get valid JSON after {max_retries} repair attempts. "
                        f"Last error: {last_error}. Last output: {last_output[:200]}"
                    )

            # Log the assessment fields
            if "query_assessment" in decision_data:
                logger.info(f"[ChiefAgent] Query Assessment: {decision_data['query_assessment'][:200]}...")
            if "thinking_process" in decision_data:
                logger.info(f"[ChiefAgent] Thinking: {decision_data['thinking_process'][:200]}...")
            if "confidence_strategy" in decision_data:
                logger.info(f"[ChiefAgent] Confidence Strategy: {decision_data['confidence_strategy'][:100]}...")
            if "user_facing_message" in decision_data:
                logger.info(f"[ChiefAgent] User Message: {decision_data['user_facing_message'][:200]}...")

            logger.info(f"[ChiefAgent] Decision: {decision_data.get('decision')}, Selected: {decision_data.get('selected_agent')}")
            logger.info(f"[ChiefAgent] Agent Tasks: {decision_data.get('agent_tasks')}")
            logger.info(f"[ChiefAgent] Agent Tasks Count: {len(decision_data.get('agent_tasks', []))}")
            logger.info(f"[ChiefAgent] Completed in {time.time() - start_time:.3f}s")
            
            # Emit conversational thinking to UI (stream into the thinking bubble)
            try:
                if ws is not None:
                    user_msg = (decision_data.get('user_facing_message') or '').strip()
                    if user_msg:
                        await ws.send_json({
                            "type": "thinking",
                            "text": user_msg,
                            "model": model,
                            "elapsed_ms": int((time.time() - start_time) * 1000)
                        })
            except Exception:
                pass
            
            # Send completion event to stop spinner
            try:
                if ws is not None:
                    event_type = "thinking_complete" if not agent_results else "synthesis_complete"
                    await ws.send_json({
                        "type": event_type,
                        "elapsed_ms": int((time.time() - start_time) * 1000)
                    })
            except Exception:
                pass
            
            return decision_data
            
        except Exception as e:
            logger.error(f"[ChiefAgent] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Chief Agent failed: {str(e)}") from e
