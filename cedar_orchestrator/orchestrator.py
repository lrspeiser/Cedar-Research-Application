"""
Main Orchestrator Module
Coordinates all agents through the Chief Agent decision-making system

This module contains:
1. ChiefAgent - The decision-making agent that reviews and coordinates
2. ThinkerOrchestrator - Main orchestration class that manages all agents
"""

import os
import time
import json
import re
import logging
import asyncio
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import execution agents
from .execution_agents import AgentResult, ShellAgent, CodeAgent, SQLAgent

# Import specialized agents
from .specialized_agents import FormulaAgent, ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FileAgent, ImageCreationAgent, ImageAnalysisAgent

# Import file processing agents if available
try:
    from .file_processing_agents import FileProcessingOrchestrator
    FILE_PROCESSING_AVAILABLE = True
except ImportError:
    FILE_PROCESSING_AVAILABLE = False

# Import chief agent notes functionality if available
try:
    from .chief_agent_notes import ChiefAgentNoteTaker
    NOTES_AVAILABLE = True
except ImportError:
    NOTES_AVAILABLE = False

# Configure detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Also log to file for persistence
try:
    import sys
    log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")
    os.makedirs(log_dir, exist_ok=True)
    from datetime import datetime
    log_file = os.path.join(log_dir, f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.info(f"Orchestrator logging initialized to {log_file}")
except Exception as e:
    logger.warning(f"Could not set up file logging: {e}")


class ChiefAgent:
    """Chief Agent that reviews all sub-agent responses and makes final decisions"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
        
    async def review_and_decide(self, user_query: str, agent_results: List[AgentResult], iteration: int = 0, max_iterations: int = 10, previous_context: str = "", resources: Optional[Dict[str, Any]] = None, conversation_history: Optional[str] = None, ws: Optional[WebSocket] = None, run_logs: Optional[List[str]] = None, thread_id: Optional[int] = None) -> Dict[str, Any]:
        """Review all agent results and make the final decision on what to do next.
        resources: Optional index of project assets (files, code, databases, notes, images).
        thread_id: Thread ID for WebSocket event correlation (will be converted to string for caching)."""
        start_time = time.time()
        remaining_loops = max_iterations - iteration - 1
        logger.info(f"[ChiefAgent] Starting review of {len(agent_results)} agent results (iteration {iteration}/{max_iterations}, {remaining_loops} loops remaining)")
        
        if not self.llm_client:
            raise RuntimeError("ChiefAgent requires LLM client - cannot operate without it")
        
        try:
            # Build Chief Agent message without leaking orchestrator-internal content
            # Only include the system prompt, optional resource index, and the raw user query.
            
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ChiefAgent] Using LLM for decision making with model: {model}")
            
            # Stream thinking start to UI
            try:
                if ws is not None:
                    await ws.send_json({
                        "type": "thinking_start",
                        "model": model,
                        "iteration": iteration + 1
                    })
            except Exception:
                pass
            
            # Create the system prompt (shortened version for space)
            # NOTE: This prompt is dynamically extracted by agent_prompts.py - do NOT create manual copies elsewhere
            system_header = f"""You are the Chief Agent - an intelligent orchestrator who analyzes queries and deploys the right agents to get confident, accurate answers.

🎯 YOUR PRIMARY DIRECTIVE:
ALWAYS delegate work to specialized agents. NEVER answer directly, even for simple questions.
ASSESS the query complexity, then deploy the appropriate specialized agent(s) to achieve HIGH CONFIDENCE in the answer.

IMPORTANT:
- For simple calculations (2+2, sums, etc): Use CodeAgent to run the math (not you)
- For derivations/proofs from first principles: Use FormulaAgent (not you, not for simple arithmetic)
- For code generation/execution: Use CodeAgent (not you) 
- For research/citations: Use ResearchAgent (not you)
- For ALL tasks: Use the specialized agent, then return 'decision: final' with agents_to_use populated
- ONLY use 'decision: final' WITHOUT agents_to_use if you need to clarify the user's request first

CURRENT ITERATION STATUS:
- Iteration: {iteration + 1} of {max_iterations}
- Remaining loops: {remaining_loops}

You MUST respond ONLY with valid JSON in this EXACT format (no prose before or after):
"""

            # Different JSON format depending on whether we have agent results yet
            if agent_results:
                # SYNTHESIS PHASE: We have agent results, provide formatted final answer
                sample_json = """
{
  "decision": "final" or "loop" or "clarify",
  "final_answer": "Complete formatted text response with markdown. Include everything the user should see: answer, explanation, next steps, etc. YOU format it ALL - punchline first, then details.",
  "agent_tasks": [
    {
      "agent": "AgentName",
      "task": "Specific task/question to pass to this agent",
      "context": "Optional: Any specific context or parameters this agent needs"
    }
  ]
}

IMPORTANT FOR SYNTHESIS:
- final_answer should be COMPLETE formatted text ready to display
- Start with punchline/direct answer (1-2 sentences)
- Add brief explanation if needed
- Add any warnings/caveats if relevant
- Format with markdown (bold, bullets, code blocks as appropriate)
- Keep it CONCISE - don't repeat agent outputs verbatim
- Our code will display final_answer AS-IS, no manipulation
- If decision is 'loop', populate agent_tasks with specific tasks for each agent
- Each task should be a self-contained instruction that can be passed directly to the agent
"""
            else:
                # PLANNING PHASE: No agent results yet, explain routing decision
                sample_json = """
{
  "decision": "final" or "loop" or "clarify",
  "thinking_process": "Internal: 'User asks X. I will use [agents] because [reasons].'",
  "user_facing_message": "Brief formatted text explaining your routing decision. Keep it conversational and succinct. Example: 'I'll use CodeAgent to calculate this for you.'",
  "agent_tasks": [
    {
      "agent": "AgentName",
      "task": "Specific task/question to pass to this agent",
      "context": "Optional: Any specific context or parameters this agent needs"
    }
  ],
  "clarification_question": "ONLY if 'clarify' - formatted question text"
}

PLANNING PHASE RULES:
- user_facing_message is displayed to user while agents work
- Keep it SHORT - just explain what you're doing
- Our code displays it AS-IS, no parsing or manipulation
- agent_tasks: List of tasks to dispatch (one per agent)
- Each task must specify: agent name, specific task string, optional context
- Task string should be complete and self-contained - it will be passed directly to the agent
- If only one agent needed, agent_tasks will have one entry
- If multiple agents needed, agent_tasks will have multiple entries
"""

            examples = """

Examples (Routing Guidance):
- ResearchAgent (explanations with citations)
  • User: "Explain MOND at a high level and contrast it with the dark-matter paradigm; include 2–3 citations."
    Agents to use: [ResearchAgent]
  • User: "What are the main differences between L1 and L2 regularization in ML? Cite authoritative sources."
    Agents to use: [ResearchAgent]
  • User: "Summarize the latest (past 12 months) changes to Apple’s App Store policy and link to the official page."
    Agents to use: [ResearchAgent]

- FormulaAgent (mathematical derivations/proofs from first principles - NOT for simple arithmetic)
  • User: "Derive the closed-form solution of the logistic differential equation from dP/dt = rP(1 − P/K)."
    Agents to use: [FormulaAgent]
  • User: "Prove that the harmonic series diverges and include the reasoning steps."
    Agents to use: [FormulaAgent]
  • User: "From Maxwell's equations, derive the wave equation for E in vacuum and state the assumptions."
    Agents to use: [FormulaAgent]
  • User: "What is 2+2?" or "Calculate 15 * 23"
    Agents to use: [CodeAgent]  # Simple calculations use CodeAgent, NOT FormulaAgent

- CodeAgent (generate/run code, including simple calculations)
  • User: "Write a short Python script that reads every CSV in a folder and prints row counts per file (no third-party libs)."
    Agents to use: [CodeAgent]
  • User: "Simulate a simple random walk with 1,000,000 steps and report the mean and variance; print runtime too."
    Agents to use: [CodeAgent]
  • User: "Parse this nginx access log sample to extract unique IPs and counts, then output a sorted CSV."
    Agents to use: [CodeAgent]
  • User: "What is 2+2?" or "Calculate the sum of 1 through 100"
    Agents to use: [CodeAgent]  # Simple arithmetic uses CodeAgent to execute and verify

- ShellAgent (file search, grep, disk usage)
  • User: "Find all .py files changed in the last 24 hours under src/ and show the five largest."
    Agents to use: [ShellAgent]
  • User: "Search recursively under logs/ for the phrase 'rate limit exceeded' with 2 lines of context and count hits by hour."
    Agents to use: [ShellAgent]
  • User: "Show disk usage for ~/CedarPyData and list subfolders larger than 500MB."
    Agents to use: [ShellAgent]

- SQLAgent (DDL/DML/queries)
  • User: "Create a SQLite table daily_metrics (project_id INT, day DATE, requests INT), and add an index on (project_id, day)."
    Agents to use: [SQLAgent]
  • User: "Write a SQL query that lists the top 10 projects by total file size from the files table."
    Agents to use: [SQLAgent]
  • User: "Add a NOT NULL TEXT column ai_category to files with default 'uncategorized', and backfill existing nulls."
    Agents to use: [SQLAgent]

- StrategyAgent (plans & playbooks)
  • User: "Draft a 30‑day rollout plan to migrate our monolith to microservices: milestones, owners, risks, rollback."
    Agents to use: [StrategyAgent]
  • User: "Create an incident response playbook for our API (pager rotations, comms templates, decision tree)."
    Agents to use: [StrategyAgent]
  • User: "Design a partner onboarding plan for a new SDK: channels, KPIs, weekly milestones, assets needed."
    Agents to use: [StrategyAgent]

- DataAgent (schema analysis, reporting)
  • User: "Given users/sessions/purchases, propose indexes and write queries to compute weekly signup→first purchase conversion."
    Agents to use: [DataAgent]
  • User: "Detect and list orphaned purchases (user_id not in users), then propose a cleanup strategy."
    Agents to use: [DataAgent]
  • User: "Design a reporting table for daily LLM token usage cost per project, including schema and refresh cadence."
    Agents to use: [DataAgent]

- NotesAgent (create/merge notes)
  • User: "Turn these raw meeting bullets into structured notes with headings and tags; avoid duplicating existing notes."
    Agents to use: [NotesAgent]
  • User: "Merge these three short summaries into one actionable note with next steps and owners."
    Agents to use: [NotesAgent]
  • User: "Keep a running note for this thread and add a timestamped key-points section after each answer."
    Agents to use: [NotesAgent]

- FileAgent (download/analyze files)
  • User: "Download https://example.org/data/benchmarks.pdf into this project and extract title, page count, and a 2‑sentence abstract."
    Agents to use: [FileAgent]
  • User: "Analyze this image at /Users/me/Downloads/plot.png and detect the primary language of any text on it."
    Agents to use: [FileAgent]
  • User: "Fetch robots.txt from https://example.com, save it to the project, and report the Disallow rules."
    Agents to use: [FileAgent]
"""

            agent_guide = """

# CEDAR AGENT CAPABILITIES REFERENCE

If there are supporting files, images, or databases already in your project, prefer agents that can read/write those assets directly.

## Quick Role Summary:

**CodeAgent** (strongest): Python execution, calculations, simulations, data analysis (pandas/NumPy/ML), charts/plots (matplotlib), document extraction (CSV/PDF/HTML/OCR), can read/write databases, create/process images.
  - Returns: Formatted answer with code blocks, execution results, and explanations
  - Output includes: Generated Python code, execution output, artifacts (type: code, language: python, source)
  - Examples: Calculate "2+2?", parse PDF tables to CSV, train models, write to project DB.

**FormulaAgent**: Step-by-step derivations from first principles; formal proofs with assumptions.
  - Returns: Mathematical derivation with clear steps, assumptions, and final formula
  - NOT for simple calculations - use CodeAgent for arithmetic
  - Examples: Prove harmonic series diverges, derive wave equation from Maxwell's, prove 2+2=4 formally.

**ResearchAgent**: Web research with citations; use when external/current info needed.
  - Returns: List of sources with URLs, key findings, citations, and summarized answer
  - Output includes: Source titles, URLs, key content, and comprehensive summary
  - Examples: Explain MOND vs dark matter (cited), summarize policy changes with links, historical queries.

**StrategyAgent**: Multi-step planning; produces numbered plan with steps/inputs/outputs/agent assignments/dependencies.
  - Returns: Numbered action plan with step titles, agents to use per step, inputs/outputs, dependencies
  - Use for: Complex multi-step workflows, unclear dependencies, reusable orchestration plans
  - Examples: "Ingest PDFs → extract → load DB → charts → report"; incident playbooks; data product rollouts.

**SQLAgent**: Executable SQL only (SQLite-compatible); creates/updates tables, indexes, constraints, runs queries.
  - Returns: Raw SQL statements only (no explanations), ready to execute
  - Output: Pure SQL with CREATE/INSERT/UPDATE/DELETE/SELECT statements

**DataAgent**: Schema analysis, query guidance; reads DB metadata, proposes SQL to answer questions.
  - Returns: Table analysis, suggested SQL queries with explanations, expected results
  - Output includes: Relevant tables list, SQL with comments, JOIN clauses, aggregations

**NotesAgent**: Organized notes/summaries; turns bullets/JSON into clean notes with headings/tags/timestamps.
  - Returns: Structured note with title, timestamp, tags, key points (bullets), action items
  - Avoids duplication with existing notes in project

**ShellAgent**: System commands (non-interactive); file searches, grep, disk usage, package installs.
  - Returns: Command output, analysis, execution status, suggested follow-up commands
  - Output includes: stdout, stderr, exit codes, execution time

**FileAgent**: Downloads from URLs, manages files, records metadata; makes files available to other agents.
  - Returns: Saved file paths, metadata (size, MIME type), preview of content
  - Creates FileEntry records in database for project files

**ImageCreationAgent**: Text-to-image generation; creates diagrams/mockups, saves to project.
  - Returns: Saved image path, access URL, FileEntry ID
  - Requires: OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY

**ImageAnalysisAgent**: Image understanding/OCR; detects objects/tags/text, updates image metadata.
  - Returns: Title, detected objects list, tags, OCR text, metadata updates confirmation
  - Updates FileEntry.ai_* fields and metadata_json in database
  - Examples: Create `daily_metrics` with indexes, backfill columns, aggregations/joins.

**DataAgent**: Schema analysis, query guidance; reads DB metadata, proposes SQL to answer questions.
  - Examples: Conversion funnels with indexes, orphan detection, design reporting tables.

**NotesAgent**: Organized notes/summaries; turns bullets/JSON into clean notes with headings/tags/timestamps.
  - Examples: Meeting minutes, consolidate summaries, running investigation logs.

**ShellAgent**: System commands (non-interactive); file searches, grep, disk usage, package installs.
  - Examples: Find recently modified files, search logs, disk usage.

**FileAgent**: Downloads from URLs, manages files, records metadata; makes files available to other agents.
  - Examples: Download PDF/CSV with metadata, fetch robots.txt, register local files.

**ImageCreationAgent**: Text-to-image generation; creates diagrams/mockups, saves to project.
  - Examples: Concept art, storyboard frames.

**ImageAnalysisAgent**: Image understanding/OCR; detects objects/tags/text, updates image metadata.
  - Examples: OCR charts, auto-tag photos for search.

## Trigger Word Cheat Sheet:
- plan, roadmap, steps, orchestrate, dependencies → **StrategyAgent**
- calculate, simulate, analyze, plot, Python, parse tables → **CodeAgent**
- derive, prove, closed-form, theorem → **FormulaAgent**
- explain, summarize, cite, who/when/where → **ResearchAgent**
- SELECT, CREATE TABLE, ALTER, index, backfill → **SQLAgent**
- schema, tables, design reporting table → **DataAgent**
- summarize notes, structure bullets, tags → **NotesAgent**
- find files, grep, disk usage, install → **ShellAgent**
- download file, import URL, metadata → **FileAgent**
- generate image, concept art → **ImageCreationAgent**
- analyze image, OCR, detect objects → **ImageAnalysisAgent**

## Multi-Agent Patterns:
- Research-then-Analyze: ResearchAgent → CodeAgent (analyze/plot) → NotesAgent
- Ingest-Transform-Report: FileAgent → CodeAgent (extract/clean) → SQLAgent/DataAgent → NotesAgent
- Complex Orchestration: StrategyAgent (plan) → ChiefAgent (dispatch iteratively)

## Using Supporting Assets:
- If PDFs/CSVs/images in project: CodeAgent (parse/analyze), ImageAnalysisAgent (OCR), SQLAgent/DataAgent (DB), NotesAgent (document)
- Need new files: FileAgent (download first)
- CodeAgent can write outputs (CSV/plots) back to project files and DB

## When to Start with StrategyAgent:
- Prompt spans multiple modalities (files + web + DB + plots)
- Unclear dependencies or decision points ("if extraction fails, try OCR")
- Want reusable, auditable plan for ChiefAgent to execute step-by-step

## Agent Input Requirements (for agent_tasks):

When creating agent_tasks entries, the 'task' field should be a natural language string that will be passed directly to the agent. All agents accept plain text tasks.

**Basic format for all agents:**
```json
{"agent": "AgentName", "task": "Natural language description of what to do"}
```

**Special cases:**

- **ImageAnalysisAgent**: Requires file_id in context
  ```json
  {"agent": "ImageAnalysisAgent", "task": "Analyze this image", "context": {"file_id": 123}}
  ```

- **ImageCreationAgent**: Task is the image description
  ```json
  {"agent": "ImageCreationAgent", "task": "A sunset over mountains with snow"}
  ```

- **FileAgent**: Task should include URLs or file paths
  ```json
  {"agent": "FileAgent", "task": "Download https://example.com/data.pdf"}
  ```

- **DataAgent**: Include database context if available
  ```json
  {"agent": "DataAgent", "task": "Suggest queries for user conversion", "context": {"project_id": 1}}
  ```

- **NotesAgent**: Can include existing notes context
  ```json
  {"agent": "NotesAgent", "task": "Summarize these findings", "context": {"content_to_note": "..."}}
  ```

For most agents (CodeAgent, ShellAgent, SQLAgent, FormulaAgent, ResearchAgent, StrategyAgent), just provide a clear task description as a string.
"""

            system_prompt = system_header + sample_json + examples + agent_guide

            # Ask Chief Agent to review and decide
            # Build messages, including resource index if provided
            msgs = [
                {
                    "role": "system",
                    "content": system_prompt
                }
            ]
            try:
                if resources:
                    import json as _json
                    msgs.append({
                        "role": "user",
                        "content": "Resources Index:"
                    })
                    msgs.append({
                        "role": "user",
                        "content": _json.dumps(resources, ensure_ascii=False)
                    })
            except Exception:
                pass

            # Provide full conversation history if available
            if conversation_history:
                msgs.append({
                    "role": "user",
                    "content": f"Conversation History (verbatim):\n{conversation_history}"
                })

            # Provide full agent responses from this iteration
            try:
                if agent_results:
                    parts = []
                    for r in agent_results:
                        parts.append(f"Agent: {r.display_name}\nResponse (verbatim):\n{r.result}\n----")
                    msgs.append({
                        "role": "user",
                        "content": "Agent Responses (verbatim):\n" + "\n".join(parts)
                    })
            except Exception:
                pass

            msgs.append({
                "role": "user",
                "content": f"User Query: {user_query}"
            })

            # Attach recent run logs (always include, even on success)
            try:
                if run_logs:
                    # Limit to last 60 lines and 4000 chars to control prompt size
                    logs_tail = run_logs[-60:]
                    logs_text = "\n".join(logs_tail)
                    if len(logs_text) > 4000:
                        logs_text = logs_text[-4000:]
                    msgs.append({
                        "role": "user",
                        "content": "Run Logs (recent):\n" + logs_text
                    })
            except Exception:
                pass

            # Send prompt details for drilldown (clickable JSON in UI) after assembling all messages
            # See README "WebSocket Events" section for API key configuration and event payload documentation
            try:
                if ws is not None:
                    # Ensure thread_id is consistently a string for frontend caching
                    thread_id_str = str(thread_id) if thread_id is not None else ''
                    
                    prompt_payload = {
                        "type": "prompt",
                        "thread_id": thread_id_str,
                        "iteration": iteration,
                        "stage": "chief_first_pass" if not agent_results else "chief_synthesis",
                        "agent": "Chief Agent",
                        "messages": msgs,
                        "timestamp": time.time()
                    }
                    
                    logger.info(f"[ChiefAgent] EMIT prompt: thread_id={thread_id_str}, iteration={iteration}, stage={prompt_payload['stage']}, msg_count={len(msgs)}")
                    await ws.send_json(prompt_payload)
                    logger.info(f"[ChiefAgent] EMIT prompt: SUCCESS")
            except Exception as e:
                logger.warning(f"[ChiefAgent] EMIT prompt: FAILED: {e}")

            completion_params = {
                "model": model,
                "messages": msgs
            }
            
            # LLM API call with general retries (e.g., transient API/network issues)
            api_retries = 0
            api_max_retries = 3
            last_api_error = None
            # Per-call timeout (seconds)
            try:
                llm_timeout_s = int(os.getenv("CEDARPY_LLM_TIMEOUT_SECONDS", "45"))
            except Exception:
                llm_timeout_s = 45
            while True:
                try:
                    # Enforce a timeout on the LLM call
                    response = await asyncio.wait_for(
                        self.llm_client.chat.completions.create(**completion_params),
                        timeout=llm_timeout_s
                    )
                    break
                except asyncio.TimeoutError as api_e:
                    last_api_error = f"Timeout after {llm_timeout_s}s"
                    api_retries += 1
                    logger.warning(f"[ChiefAgent] LLM API timeout (attempt {api_retries}/{api_max_retries}): {last_api_error}")
                    # Inform UI
                    try:
                        if ws is not None:
                            await ws.send_json({"type": "info", "stage": f"planning.timeout.attempt_{api_retries}"})
                    except Exception:
                        pass
                    if api_retries >= api_max_retries:
                        raise
                    try:
                        msgs.append({
                            "role": "system",
                            "content": f"Previous API timeout: {last_api_error}. Please try again and return ONLY valid JSON."
                        })
                    except Exception:
                        pass
                except Exception as api_e:
                    last_api_error = str(api_e)
                    api_retries += 1
                    logger.warning(f"[ChiefAgent] LLM API error (attempt {api_retries}/{api_max_retries}): {api_e}")
                    # Inform UI
                    try:
                        if ws is not None:
                            await ws.send_json({"type": "info", "stage": f"planning.retry.attempt_{api_retries}", "message": last_api_error[:160]})
                    except Exception:
                        pass
                    if api_retries >= api_max_retries:
                        raise
                    # Nudge with a system note about previous API error
                    try:
                        msgs.append({
                            "role": "system",
                            "content": f"Previous API error: {last_api_error}. Please try again and return ONLY valid JSON."
                        })
                    except Exception:
                        pass
            
            # Log the full response object for debugging
            logger.info(f"[ChiefAgent] Raw API response object: {response}")
            logger.info(f"[ChiefAgent] Response choices count: {len(response.choices)}")
            logger.info(f"[ChiefAgent] Response finish_reason: {response.choices[0].finish_reason if response.choices else 'NO_CHOICES'}")
            
            chief_response = response.choices[0].message.content
            # Handle None/empty response
            if chief_response is None or chief_response == "":
                logger.error(f"[ChiefAgent] EMPTY RESPONSE from API! finish_reason={response.choices[0].finish_reason}")
                logger.error(f"[ChiefAgent] Full message object: {response.choices[0].message}")
                chief_response = ""
            
            # Log full response for debugging JSON issues
            if len(chief_response) <= 500:
                logger.info(f"[ChiefAgent] Response content: {chief_response}")
            else:
                logger.info(f"[ChiefAgent] Response content (truncated): {chief_response[:500]}...")
            
            # Parse JSON response with LLM repair retries on failure
            def _validate_and_normalize(d: Dict[str, Any]) -> Dict[str, Any]:
                if "decision" not in d:
                    raise ValueError("LLM response missing required 'decision' field")
                if d.get("decision") not in ["final", "loop", "clarify"]:
                    raise ValueError(f"Invalid decision value: {d.get('decision')} - must be 'final', 'loop', or 'clarify'")
                if d.get("decision") == "final" and "final_answer" not in d:
                    raise ValueError("LLM response has decision='final' but missing 'final_answer' field")
                return d

            decision_data: Dict[str, Any]
            try:
                decision_data = _validate_and_normalize(json.loads(chief_response))
            except json.JSONDecodeError as e1:
                logger.warning(f"[ChiefAgent] JSON parse failed: {e1}. Attempting repair retries…")
                retries = 0
                max_retries = 3
                last_error = str(e1)
                last_output = chief_response[:1500]
                decision_data = {}
                while retries < max_retries:
                    retries += 1
                    repair_system = (
                        "You previously returned invalid JSON. Return ONLY valid JSON matching the schema you were given. "
                        "Do NOT include any prose or code fences."
                    )
                    repair_user = (
                        f"Previous JSON parse error: {last_error}\n\n"
                        f"Your last output (truncated):\n{last_output}\n\n"
                        "Re-emit the same decision as valid JSON, including agents_to_use when appropriate."
                    )
                    repair_msgs = [
                        {"role": "system", "content": system_prompt},  # original instruction
                        {"role": "system", "content": repair_system},
                        {"role": "user", "content": repair_user},
                    ]
                    # Re-attach context for determinism
                    if conversation_history:
                        repair_msgs.append({"role": "user", "content": f"Conversation History (verbatim):\n{conversation_history}"})
                    if agent_results:
                        try:
                            parts = []
                            for r in agent_results:
                                parts.append(f"Agent: {r.display_name}\nResponse (verbatim):\n{r.result}\n----")
                            repair_msgs.append({"role": "user", "content": "Agent Responses (verbatim):\n" + "\n".join(parts)})
                        except Exception:
                            pass
                    repair_msgs.append({"role": "user", "content": f"User Query: {user_query}"})
                    # Include logs again in repair attempts
                    try:
                        if run_logs:
                            logs_tail = run_logs[-60:]
                            logs_text = "\n".join(logs_tail)
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
            
            return decision_data
            
        except Exception as e:
            logger.error(f"[ChiefAgent] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Chief Agent failed: {str(e)}") from e


class ThinkerOrchestrator:
    """The main orchestrator that coordinates all agents"""
    
    MAX_ITERATIONS = 10  # Maximum number of Chief Agent loop iterations
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.chief_agent = ChiefAgent(self.llm_client)  # Chief Agent is primary
        
        # Core execution agents
        self.code_agent = CodeAgent(self.llm_client)
        self.sql_agent = SQLAgent(self.llm_client)
        self.shell_agent = ShellAgent(self.llm_client)  # NEW: Full shell access
        
        # Specialized agents
        self.formula_agent = FormulaAgent(self.llm_client)
        self.research_agent = ResearchAgent(self.llm_client)
        self.strategy_agent = StrategyAgent(self.llm_client)
        self.data_agent = DataAgent(self.llm_client)
        self.notes_agent = NotesAgent(self.llm_client)
        self.file_agent = FileAgent(self.llm_client)  # Will get context during orchestration
        # Images
        self.image_creation_agent = ImageCreationAgent(self.llm_client)
        self.image_analysis_agent = ImageAnalysisAgent(self.llm_client)
        
        # Initialize file processing orchestrator if available
        if FILE_PROCESSING_AVAILABLE:
            self.file_processor = FileProcessingOrchestrator(self.llm_client)
        else:
            self.file_processor = None
        
    async def process_file(self, file_path: str, file_type: str, websocket: WebSocket) -> Dict[str, Any]:
        """Process uploaded file using file processing agents"""
        if not self.file_processor:
            await websocket.send_json({
                "type": "message",
                "role": "File Processing",
                "text": "File processing agents not available. Please install required libraries."
            })
            return {"error": "File processing not available"}
        
        return await self.file_processor.process_file(file_path, file_type, websocket)
    
        """Thinker phase: Assess query complexity and choose agents for confident answers"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": [],
            "selection_reasoning": "",
            "complexity": "simple",  # simple, moderate, or complex
            "confidence_strategy": "appropriate"  # appropriate, comprehensive, or exhaustive
        }
        
        # First: Assess query complexity
        # Simple arithmetic or basic questions - but still might benefit from multiple agents
        if any(pattern in message.lower() for pattern in ['2+2', '2 + 2', 'what is', 'calculate', 'compute']) and len(message) < 50:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "simple_calculation"
            thinking_process["analysis"] = f"Calculation query: {message}"
            thinking_process["agents_to_use"] = ["CodeAgent", "FormulaAgent"]  # Use both for validation
            thinking_process["selection_reasoning"] = f"User asks '{message}' - using Code and Formula agents for confident verification"
            thinking_process["confidence_strategy"] = "appropriate"
            return thinking_process
        
        # Analyze the message for research context
        import re
        has_url = bool(re.search(r'https?://[^\s]+', message))
        has_file_path = bool(re.search(r'(/[^\s]+\.[a-zA-Z]{2,4}|[A-Za-z]:\\[^\s]+|\./[^\s]+)', message))
        has_shell_command = bool(re.search(r'`[^`]+`', message)) or any(cmd in message.lower() for cmd in ['grep', 'find', 'ls', 'cat', 'brew install', 'pip install', 'npm install', 'apt-get', 'chmod', 'mkdir', 'rm', 'cp', 'mv'])
        # Image-related heuristics
        msg_lower = message.lower()
        has_image_word = any(w in msg_lower for w in ['image','images','picture','photo','plot','chart','visualize','render','thumbnail'])
        wants_create = any(w in msg_lower for w in ['create','generate','draw','render','visualize','plot','chart'])
        wants_analyze = any(w in msg_lower for w in ['analyz','describe','what\'s in','what is in'])
        file_ctx_present = bool((context or {}).get('file_id'))
        
        # CRITICAL: Check for file search keywords
        is_file_search = any(phrase in message.lower() for phrase in [
            'find files', 'find all files', 'search for files', 'files on my computer',
            'files on my machine', 'files related to', 'search my computer',
            'search my machine', 'look for files', 'locate files', 'where are',
            'list files', 'show files', 'what files', 'search for',
            'files containing', 'containing the word', 'grep', 'find'
        ])
        
        # Check for research-specific keywords
        is_data_task = any(word in message.lower() for word in ['data', 'dataset', 'csv', 'excel', 'json', 'analyze', 'statistics', 'correlation'])
        is_research_task = any(word in message.lower() for word in ['research', 'paper', 'study', 'literature', 'review', 'citation', 'reference', 'peer-review'])
        is_computation = any(word in message.lower() for word in ['calculate', 'compute', 'analyze', 'model', 'simulate', 'algorithm'])
        
        # FILE SEARCH ON USER'S COMPUTER
        if is_file_search or ('find' in message.lower() and 'file' in message.lower()):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "file_search"
            thinking_process["analysis"] = f"User wants to find files related to: {message}"
            thinking_process["agents_to_use"] = ["ShellAgent"]
            thinking_process["selection_reasoning"] = f"File search query - only Shell Agent needed with find/grep commands"
            return thinking_process
        # Simple SQL query
        elif any(word in message.lower() for word in ['sql', 'select', 'create table', 'database']):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "sql_query"
            thinking_process["analysis"] = f"SQL operation requested"
            thinking_process["agents_to_use"] = ["SQLAgent"]
            thinking_process["selection_reasoning"] = f"SQL query - only SQL Agent needed"
            return thinking_process
        # Data processing - moderate complexity
        elif is_data_task or (has_file_path and any(ext in message.lower() for ext in ['.csv', '.json', '.xlsx'])):
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "data_processing"
            thinking_process["analysis"] = f"Data processing task"
            thinking_process["agents_to_use"] = ["CodeAgent", "SQLAgent"]  # Only essential agents
            thinking_process["selection_reasoning"] = f"Data task - Coding Agent for analysis, SQL Agent for storage"
        # Complex mathematical derivation
        elif any(word in message.lower() for word in ['derive', 'proof', 'theorem', 'maxwell', 'equation']):
            thinking_process["complexity"] = "complex"
            thinking_process["identified_type"] = "mathematical_derivation"
            thinking_process["analysis"] = f"Complex derivation requested"
            thinking_process["agents_to_use"] = ["FormulaAgent", "CodeAgent"]
            thinking_process["selection_reasoning"] = f"Mathematical derivation - Formula Agent for theory, Coding Agent for verification"
        # Simple computation
        elif is_computation:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "computation"
            thinking_process["analysis"] = f"Computational task"
            thinking_process["agents_to_use"] = ["CodeAgent"]
            thinking_process["selection_reasoning"] = f"Computation - only Coding Agent needed"
        # Shell commands
        elif has_shell_command:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "shell_command"
            thinking_process["analysis"] = f"Shell command execution"
            thinking_process["agents_to_use"] = ["ShellAgent"]
            thinking_process["selection_reasoning"] = f"Shell command - only Shell Agent needed"
        # File download
        elif has_url:
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "file_download"
            thinking_process["analysis"] = f"File download from URL"
            thinking_process["agents_to_use"] = ["FileAgent"]
            thinking_process["selection_reasoning"] = f"URL download - only File Agent needed"
        # Image creation / visualization
        elif has_image_word and wants_create:
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "image_creation"
            thinking_process["analysis"] = "Image generation or visualization requested"
            thinking_process["agents_to_use"] = ["ImageCreationAgent"]
            thinking_process["selection_reasoning"] = "Use Image Creation to generate an image and save it to Files/Images"
        # Image analysis
        elif (has_image_word and wants_analyze) or (file_ctx_present and has_image_word):
            thinking_process["complexity"] = "simple"
            thinking_process["identified_type"] = "image_analysis"
            thinking_process["analysis"] = "Analyze an image and update metadata"
            thinking_process["agents_to_use"] = ["ImageAnalysisAgent"]
            thinking_process["selection_reasoning"] = "Use Image Analysis to describe and tag the image"
        # Default: Use minimal agents based on keywords
        else:
            # Try to be smart about the default
            thinking_process["complexity"] = "moderate"
            thinking_process["identified_type"] = "general_query"
            thinking_process["analysis"] = f"General query: {message[:100]}"
            # Default to just Coding Agent for most things
            thinking_process["agents_to_use"] = ["CodeAgent"]
            thinking_process["selection_reasoning"] = f"General query - starting with Coding Agent, can add more if needed"
            
        return thinking_process
        
    async def orchestrate(self, message: str, websocket, iteration: int = 0, previous_results: List[AgentResult] = None, project_id: int = None, branch_id: int = None, thread_id: int = None, db_session = None, conversation_history: Optional[str] = None):
        """Full orchestration process controlled by Chief Agent decisions with optional notes persistence"""
        orchestration_start = time.time()
        # Ensure optional context vars exist to avoid NameError
        file_id = None
        dataset_id = None
        # Structured run logs (always passed to the Chief Agent)
        run_logs: List[str] = []
        try:
            run_logs.append(f"Start: t={orchestration_start:.3f}s message={message[:120]}")
        except Exception:
            pass
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Starting orchestration for message: {message} (iteration: {iteration})")
        logger.info("="*80)
        
        # Check iteration limit
        if iteration >= self.MAX_ITERATIONS:
            # If we have previous results, use Chief Agent's last final_answer
            if previous_results:
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": f"**Note:** Maximum iterations ({self.MAX_ITERATIONS}) reached.\n\n{previous_results[0].result if previous_results else 'Processing limit reached. Please refine your request.'}"
                })
            else:
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": "Processing limit reached. Please try a more specific request."
                })
            return
        
        # Phase 1: Chief Agent planning (stream analysis before sub-agents) and selection
        logger.info("[ORCHESTRATOR] PHASE 1: Chief Agent Planning (stream)")
        try:
            run_logs.append("Phase: planning.start")
        except Exception:
            pass
        planning_decision = None
        try:
            planning_decision = await self.chief_agent.review_and_decide(
                user_query=message,
                agent_results=[],  # no agent results yet
                iteration=iteration,
                max_iterations=self.MAX_ITERATIONS,
                previous_context="",
                resources=None,
                conversation_history=conversation_history,
                ws=websocket,  # emit thinking_start + prompt + thinking
                run_logs=run_logs,
                thread_id=thread_id  # pass thread_id for WebSocket event correlation
            )
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Pre-analysis planning emit failed: {e}")
            try:
                run_logs.append(f"Error: planning.emit_failed: {type(e).__name__}: {e}")
            except Exception:
                pass
            planning_decision = {"decision": "loop", "agent_tasks": []}

        # Short-circuit only for clarifications - Chief Agent must NOT answer directly without agents
        try:
            if planning_decision.get('decision') == 'clarify':
                clarification_question = planning_decision.get('clarification_question', 'Could you please provide more details about your request?')
                thinking = planning_decision.get('thinking_process', 'Need more information from user')
                await websocket.send_json({
                    "type": "message",
                    "role": "The Chief Agent",
                    "text": f"""🤔 **Clarification Needed**\n\n{thinking}\n\n**Question:** {clarification_question}\n\nPlease provide this information so I can better assist you."""
                })
                return
            # REMOVED: Chief Agent should NEVER finalize without running agents first
            # All work must be delegated to specialized agents
        except Exception:
            pass

        # Parse agent_tasks from planning_decision
        agent_tasks_list = []
        try:
            if isinstance(planning_decision.get('agent_tasks'), list):
                agent_tasks_list = planning_decision.get('agent_tasks', [])
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Failed to parse agent_tasks: {e}")
            agent_tasks_list = []
        
        # Extract unique agent names from tasks
        agents_to_use = []
        agent_task_map = {}  # Map agent name to task string
        for task_entry in agent_tasks_list:
            try:
                agent_name = str(task_entry.get('agent', '')).strip()
                task_str = str(task_entry.get('task', '')).strip()
                context = task_entry.get('context', {})
                if agent_name and task_str:
                    if agent_name not in agents_to_use:
                        agents_to_use.append(agent_name)
                    # Store task and context for this agent
                    agent_task_map[agent_name] = {
                        'task': task_str,
                        'context': context
                    }
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to parse task entry: {e}")
        
        logger.info(f"[ORCHESTRATOR] Agents selected by Chief Agent: {agents_to_use}")
        logger.info(f"[ORCHESTRATOR] Agent tasks: {agent_task_map}")
        try:
            run_logs.append("Planning: agents=" + ",".join(agents_to_use))
        except Exception:
            pass

        # Phase 2: Parallel agent processing based on Chief Agent selection
        logger.info("[ORCHESTRATOR] PHASE 2: Parallel Agent Processing (from Chief selection)")
        agents = []
        # Helper to add agent if requested
        def _add(agent_name: str, agent_obj):
            nonlocal agents
            if agent_name in agents_to_use:
                agents.append(agent_obj)
                logger.info(f"[ORCHESTRATOR] Added {agent_name} to processing queue")
                try:
                    run_logs.append(f"Queue: {agent_name}")
                except Exception:
                    pass
        _add("CodeAgent", self.code_agent)
        _add("SQLAgent", self.sql_agent)
        _add("ShellAgent", self.shell_agent)
        _add("FormulaAgent", self.formula_agent)
        _add("ResearchAgent", self.research_agent)
        _add("StrategyAgent", self.strategy_agent)
        _add("DataAgent", self.data_agent)
        _add("NotesAgent", self.notes_agent)
        _add("ImageCreationAgent", self.image_creation_agent)
        _add("ImageAnalysisAgent", self.image_analysis_agent)
        if "FileAgent" in agents_to_use:
            if db_session and project_id and branch_id:
                self.file_agent.project_id = project_id
                self.file_agent.branch_id = branch_id
                self.file_agent.db_session = db_session
            agents.append(self.file_agent)
            logger.info("[ORCHESTRATOR] Added FileAgent to processing queue")

        # Process all agents in parallel
        logger.info(f"[ORCHESTRATOR] Starting parallel processing with {len(agents)} agents")
        parallel_start = time.time()
        
        # Track whether any agent error occurred
        had_errors = False
        
        # Don't send stream updates that would overwrite the Chief Agent analysis
        # The detailed analysis message is complete and should stand on its own
        
        # Create agent tasks - use specific task strings from agent_task_map
        agent_tasks = []
        for agent in agents:
            agent_class_name = agent.__class__.__name__
            
            # Get the specific task for this agent, fallback to user message
            task_info = agent_task_map.get(agent_class_name, {'task': message, 'context': {}})
            task_str = task_info.get('task', message)
            task_context = task_info.get('context', {})
            
            logger.info(f"[ORCHESTRATOR] Dispatching to {agent_class_name} with task: {task_str[:100]}...")
            
            if isinstance(agent, ShellAgent):
                conversation_context = f"User Query: {message}\nIteration: {iteration + 1}\nSpecific Task: {task_str}"
                agent_tasks.append(agent.process(task_str, conversation_context=conversation_context))
            elif agent is self.image_creation_agent:
                agent_tasks.append(agent.process(task_str, project_id=project_id, branch_id=branch_id, db_session=db_session))
            elif agent is self.image_analysis_agent:
                # ImageAnalysisAgent may need file_id from context
                file_id_for_analysis = task_context.get('file_id', file_id)
                agent_tasks.append(agent.process(task_str, project_id=project_id, branch_id=branch_id, db_session=db_session, file_id=file_id_for_analysis))
            elif agent is self.data_agent:
                # DataAgent may use project_id from context
                project_id_for_data = task_context.get('project_id', project_id)
                agent_tasks.append(agent.process(task_str, project_id=project_id_for_data))
            elif agent is self.notes_agent:
                # NotesAgent may have content_to_note in context
                content_to_note = task_context.get('content_to_note', '')
                existing_notes = task_context.get('existing_notes', [])
                agent_tasks.append(agent.process(task_str, content_to_note=content_to_note, existing_notes=existing_notes))
            else:
                # Default: just pass the task string
                agent_tasks.append(agent.process(task_str))
        
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        logger.info(f"[ORCHESTRATOR] Parallel processing completed in {time.time() - parallel_start:.3f}s")
        try:
            run_logs.append(f"Phase: agents.done dt={time.time() - parallel_start:.3f}s count={len(agents)}")
        except Exception:
            pass
        
        # Send agent results
        logger.info("[ORCHESTRATOR] Processing agent results")
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, AgentResult):
                logger.info(f"[ORCHESTRATOR] Result {i+1}: {result.agent_name} - Confidence: {result.confidence:.2f}, Method: {result.method}")
                logger.info(f"[ORCHESTRATOR] Result {i+1} UI label: {result.display_name}")
                logger.info(f"[ORCHESTRATOR] Result {i+1} content: {result.result[:200]}...")
                
                # Persist code artifacts even if not selected by Chief Agent
                try:
                    if db_session and project_id and branch_id and getattr(result, 'artifacts', None):
                        art = result.artifacts or {}
                        if str(art.get('type', '')).lower() == 'code' and str(art.get('source', '')).strip():
                            from main_models import SavedCode
                            name = (str(art.get('name') or '') or 'Generated Code')[:255]
                            desc = str(art.get('description') or '')
                            lang = str(art.get('language') or 'python')[:50]
                            src = str(art.get('source') or '')
                            sc = SavedCode(
                                project_id=int(project_id),
                                branch_id=int(branch_id),
                                name=name,
                                description=desc,
                                language=lang,
                                code=src,
                                agent_name=(result.display_name or result.agent_name)[:100]
                            )
                            db_session.add(sc)
                            db_session.commit()
                            logger.info(f"[ORCHESTRATOR] Saved code snippet id={getattr(sc, 'id', None)} lang={lang} name={name[:40]}")
                except Exception as e:
                    logger.warning(f"[ORCHESTRATOR] Failed to persist code artifact: {type(e).__name__}: {e}")
                
                # Send agent completion status with display name
                status_text = result.result  # Already formatted by the agent
                
                await websocket.send_json({
                    "type": "agent_result",
                    "agent_name": result.display_name,  # Use display name for UI
                    "text": status_text,
                    "summary": result.summary,  # Include summary for user visibility
                    "metadata": {
                        "agent": result.agent_name,
                        "confidence": result.confidence,
                        "method": result.method,
                        "needs_rerun": result.needs_rerun,
                        "summary": result.summary  # Also include in metadata
                    }
                })
                try:
                    short = (result.summary or (result.result or '').split('\n',1)[0] or '').strip()
                    if len(short) > 160: short = short[:160]
                    run_logs.append(f"AgentOK: {result.display_name} conf={result.confidence:.2f} sum={short}")
                except Exception:
                    pass
                valid_results.append(result)
                await asyncio.sleep(0.2)
            elif isinstance(result, Exception):
                logger.error(f"[ORCHESTRATOR] Agent {i+1} failed with exception: {result}")
                had_errors = True
                
                # Determine which agent failed based on index
                agent_name = "Unknown Agent"
                display_name = "Unknown Agent"
                if i < len(agents):
                    agent = agents[i]
                    agent_name = agent.__class__.__name__
                    # Map agent to display name
                    agent_display_names = {
                        "CodeAgent": "Coding Agent",
                        "ShellAgent": "Desktop Agent",
                        "SQLAgent": "SQL Agent",
                        "FormulaAgent": "Formula Agent",
                        "ResearchAgent": "Research Agent",
                        "StrategyAgent": "Strategy Agent",
                        "DataAgent": "Data Agent",
                        "NotesAgent": "Notes Agent",
                        "FileAgent": "File Manager",
                        "ImageCreationAgent": "Image Creation",
                        "ImageAnalysisAgent": "Image Analysis"
                    }
                    display_name = agent_display_names.get(agent_name, agent_name)
                
                # Create error report with detailed information
                error_type = type(result).__name__
                error_msg = str(result)
                
                # Check for common error patterns and provide specific guidance
                error_details = f"""Exception Type: {error_type}
Error Message: {error_msg}
Agent: {agent_name}
Task: {message[:200]}{'...' if len(message) > 200 else ''}"""
                
                suggested_fix = "Review the error details and check:"
                if "OPENAI_API_KEY" in error_msg or "api_key" in error_msg.lower():
                    suggested_fix += "\n- Ensure OPENAI_API_KEY is set in environment"
                    suggested_fix += "\n- Check the API key is valid and has proper permissions"
                elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                    suggested_fix += "\n- Check network connectivity"
                    suggested_fix += "\n- Verify firewall settings allow API access"
                elif "timeout" in error_msg.lower():
                    suggested_fix += "\n- The operation took too long to complete"
                    suggested_fix += "\n- Try a simpler query or break it into smaller parts"
                elif "module" in error_msg.lower() or "import" in error_msg.lower():
                    suggested_fix += "\n- Required Python modules may not be installed"
                    suggested_fix += "\n- Check if all dependencies are properly installed"
                else:
                    suggested_fix += "\n- Check the agent's configuration"
                    suggested_fix += "\n- Review the error message for specific issues"
                
                # Create an AgentResult for the exception
                error_result = AgentResult(
                    agent_name=agent_name,
                    display_name=display_name,
                    result=f"""**Agent Failure Report:**\n\n{display_name} encountered an unexpected error and could not complete the task.\n\n**Error Details:**\n```\n{error_details}\n```\n\n**Suggested Fix:**\n{suggested_fix}\n\n**What the Chief Agent should know:**\nThis agent crashed during execution. The error has been logged and detailed information is provided above for troubleshooting.""",
                    confidence=0.0,
                    method="Agent Exception",
                    explanation=f"Agent crashed: {error_type}",
                    summary=f"{display_name} failed with {error_type}: {error_msg[:100]}{'...' if len(error_msg) > 100 else ''}"
                )
                
                # Send the error as an agent result
                await websocket.send_json({
                    "type": "agent_result",
                    "agent_name": display_name,
                    "text": error_result.result,
                    "summary": error_result.summary,
                    "metadata": {
                        "agent": agent_name,
                        "confidence": 0.0,
                        "method": "Agent Exception",
                        "error": True,
                        "error_type": error_type,
                        "summary": error_result.summary
                    }
                })
                try:
                    run_logs.append(f"AgentERR: {display_name} type={error_type} msg={error_msg[:160]}")
                except Exception:
                    pass
                valid_results.append(error_result)
                await asyncio.sleep(0.2)
                
        # Phase 3: Chief Agent Review and Decision
        logger.info("[ORCHESTRATOR] PHASE 3: Chief Agent Review and Decision")
        logger.info(f"[ORCHESTRATOR] Chief Agent reviewing {len(valid_results)} valid results")
        
        # Don't send stream updates - let agent results speak for themselves
        
        # Do not pass previous iterations context to Chief Agent; keep input minimal
        previous_context = ""
        
        # Have Chief Agent review all results and make a decision
        # Build resource index for the Chief Agent (names + official IDs)
        resources_index: Optional[Dict[str, Any]] = None
        try:
            if db_session and project_id and branch_id:
                resources_index = {"files": [], "code": [], "databases": [], "notes": [], "images": []}
                # Files and Images from FileEntry
                try:
                    from main_models import FileEntry
                    files = db_session.query(FileEntry).filter(
                        FileEntry.project_id == int(project_id),
                        FileEntry.branch_id == int(branch_id)
                    ).order_by(FileEntry.created_at.desc()).limit(1000).all()
                    for f in files:
                        title = (getattr(f, 'ai_title', None) or f.display_name or '').strip() or f.filename
                        rec = {"id": f.id, "name": title, "structure": f.structure, "file_type": f.file_type}
                        resources_index["files"].append(rec)
                        # Basic image heuristic
                        ft = (f.file_type or '').lower()
                        if (f.structure or '').lower() == 'images' or ft in {"jpg","jpeg","png","gif","webp","bmp","tiff"}:
                            resources_index["images"].append({"id": f.id, "name": title})
                except Exception:
                    pass
                # Saved code snippets
                try:
                    from main_models import SavedCode
                    codes = db_session.query(SavedCode).filter(
                        SavedCode.project_id == int(project_id),
                        SavedCode.branch_id == int(branch_id)
                    ).order_by(SavedCode.created_at.desc()).limit(1000).all()
                    for sc in codes:
                        resources_index["code"].append({"id": sc.id, "name": (sc.name or '').strip() or f"Code {sc.id}"})
                except Exception:
                    pass
                # Databases
                try:
                    from main_models import Dataset
                    datasets = db_session.query(Dataset).filter(
                        Dataset.project_id == int(project_id),
                        Dataset.branch_id == int(branch_id)
                    ).order_by(Dataset.created_at.desc()).limit(1000).all()
                    for d in datasets:
                        resources_index["databases"].append({"id": d.id, "name": d.name})
                except Exception:
                    pass
                # Notes (include content)
                try:
                    from main_models import Note
                    notes = db_session.query(Note).filter(
                        Note.project_id == int(project_id),
                        Note.branch_id == int(branch_id)
                    ).order_by(Note.created_at.desc()).limit(1000).all()
                    for n in notes:
                        resources_index["notes"].append({
                            "id": n.id,
                            "title": (getattr(n, 'title', None) or '').strip() or f"Note {n.id}",
                            "content": n.content or ""
                        })
                except Exception:
                    pass
        except Exception:
            resources_index = None

        chief_decision = await self.chief_agent.review_and_decide(
            user_query=message,
            agent_results=valid_results,
            iteration=iteration,
            max_iterations=self.MAX_ITERATIONS,
            previous_context=previous_context,
            resources=None,
            conversation_history=conversation_history,
            ws=None,  # Do not emit thinking during the final review to avoid duplicate planning bubble
            run_logs=run_logs,
            thread_id=thread_id  # pass thread_id for WebSocket event correlation
        )
        logger.info(f"[ORCHESTRATOR] Chief Agent decision: {chief_decision.get('decision')}")
        
        # Log thinking process if available
        if chief_decision.get('thinking_process'):
            logger.info(f"[ORCHESTRATOR] Chief Agent thinking: {chief_decision['thinking_process'][:300]}...")
        
        # Chief Agent analysis is streamed from review_and_decide via 'thinking' event.
        # Always run Notes Agent to create structured notes for every Chief Agent processing step
        try:
            if self.notes_agent is not None:
                existing_notes_list = []
                # If DB session and context are available, fetch recent notes for de-duplication
                if db_session and project_id and branch_id and NOTES_AVAILABLE:
                    try:
                        note_taker_preview = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                        existing_notes_list = await note_taker_preview.get_existing_notes()
                    except Exception as e:
                        logger.warning(f"[ORCHESTRATOR-NOTES] Could not fetch existing notes for NotesAgent: {e}")
                # Prepare concise content for the notes agent: summarize Chief Agent decision only
                try:
                    decision = chief_decision or {}
                except Exception:
                    decision = {}
                try:
                    lines = []
                    lines.append(f"Decision: {decision.get('decision','')}")
                    tp = (decision.get('thinking_process') or '').strip()
                    if tp:
                        lines.append("Thinking Process:\n" + tp)
                    fa = (decision.get('final_answer') or '').strip()
                    if fa:
                        lines.append("Final Answer:\n" + fa)
                    ag = (decision.get('additional_guidance') or '').strip()
                    if ag:
                        lines.append("Additional Guidance:\n" + ag)
                    sel = (decision.get('selected_agent') or '').strip()
                    atu = decision.get('agents_to_use') or []
                    if atu:
                        lines.append("Agents To Use: " + ", ".join(atu))
                    elif sel:
                        lines.append("Selected Agent: " + sel)
                    rsn = (decision.get('reasoning') or '').strip()
                    if rsn:
                        lines.append("Reasoning:\n" + rsn)
                    content_to_note = "\n\n".join(lines)
                except Exception:
                    content_to_note = (chief_decision.get('final_answer') or '').strip() or 'Chief Agent summary'
                try:
                    notes_agent_result = await self.notes_agent.process(
                        task=message,
                        content_to_note=content_to_note,
                        existing_notes=existing_notes_list
                    )
                    if isinstance(notes_agent_result, AgentResult):
                        # Include in results for persistence and UI
                        valid_results.append(notes_agent_result)
                        try:
                            await websocket.send_json({
                                "type": "agent_result",
                                "agent_name": notes_agent_result.display_name,
                                "text": notes_agent_result.result,
                                "summary": getattr(notes_agent_result, 'summary', None),
                                "metadata": {
                                    "agent": "NotesAgent",
                                    "confidence": notes_agent_result.confidence,
                                    "method": notes_agent_result.method,
                                }
                            })
                        except Exception as e:
                            logger.warning(f"[ORCHESTRATOR-NOTES] Failed to send NotesAgent result to WS: {e}")
                except Exception as e:
                    logger.error(f"[ORCHESTRATOR-NOTES] NotesAgent processing failed: {e}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR-NOTES] Unexpected error in NotesAgent always-run block: {e}")
        
        # ALWAYS save notes after every agent response cycle (whether loop or final)
        # This ensures all intermediate findings are captured in the database
        logger.info(f"[ORCHESTRATOR-NOTES] " + "="*50)
        logger.info(f"[ORCHESTRATOR-NOTES] NOTES SAVE CHECK - ITERATION {iteration + 1}")
        logger.info(f"[ORCHESTRATOR-NOTES] " + "="*50)
        logger.info(f"[ORCHESTRATOR-NOTES] NOTES_AVAILABLE: {NOTES_AVAILABLE}")
        logger.info(f"[ORCHESTRATOR-NOTES] db_session exists: {db_session is not None}")
        logger.info(f"[ORCHESTRATOR-NOTES] db_session type: {type(db_session).__name__ if db_session else 'None'}")
        logger.info(f"[ORCHESTRATOR-NOTES] project_id: {project_id}")
        logger.info(f"[ORCHESTRATOR-NOTES] branch_id: {branch_id}")
        logger.info(f"[ORCHESTRATOR-NOTES] iteration: {iteration}")
        logger.info(f"[ORCHESTRATOR-NOTES] chief_decision type: {chief_decision.get('decision')}")
        logger.info(f"[ORCHESTRATOR-NOTES] valid_results count: {len(valid_results)}")
        for i, r in enumerate(valid_results):
            logger.info(f"[ORCHESTRATOR-NOTES]   Result {i}: {r.agent_name} - confidence: {r.confidence}")
        
        if NOTES_AVAILABLE and db_session and project_id and branch_id:
            logger.info(f"[ORCHESTRATOR-NOTES] ✓ All conditions met, attempting to save notes...")
            logger.info(f"[ORCHESTRATOR-NOTES] Using db_session of type: {type(db_session).__name__}")
            logger.info(f"[ORCHESTRATOR-NOTES] db_session bind: {db_session.bind if hasattr(db_session, 'bind') else 'No bind attribute'}")
            try:
                logger.info(f"[ORCHESTRATOR-NOTES] Creating ChiefAgentNoteTaker instance...")
                note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
                logger.info(f"[ORCHESTRATOR-NOTES] ChiefAgentNoteTaker created successfully")
                
                # Include iteration info in the notes
                enhanced_decision = dict(chief_decision)
                enhanced_decision['iteration'] = iteration
                enhanced_decision['is_final'] = chief_decision.get('decision') != 'loop'
                enhanced_decision['total_iterations'] = iteration + 1
                
                logger.info(f"[ORCHESTRATOR-NOTES] Enhanced decision prepared:")
                logger.info(f"[ORCHESTRATOR-NOTES]   iteration: {iteration}")
                logger.info(f"[ORCHESTRATOR-NOTES]   is_final: {enhanced_decision['is_final']}")
                logger.info(f"[ORCHESTRATOR-NOTES]   total_iterations: {enhanced_decision['total_iterations']}")
                
                logger.info(f"[ORCHESTRATOR-NOTES] Calling save_agent_notes...")
                logger.info(f"[ORCHESTRATOR-NOTES]   agent_results: {len(valid_results)} results")
                logger.info(f"[ORCHESTRATOR-NOTES]   user_query: {message[:100]}...")
                
                note_id = await note_taker.save_agent_notes(
                    agent_results=valid_results,
                    user_query=message, 
                    chief_decision=enhanced_decision
                )
                
                logger.info(f"[ORCHESTRATOR-NOTES] save_agent_notes returned: {note_id}")
                logger.info(f"[ORCHESTRATOR-NOTES] note_id type: {type(note_id).__name__}")
                
                if note_id:
                    logger.info(f"[ORCHESTRATOR-NOTES] ✅ SUCCESS: Saved iteration {iteration + 1} notes to database")
                    logger.info(f"[ORCHESTRATOR-NOTES] Note ID: {note_id}")
                    
                    # Send notification to websocket about note save
                    logger.info(f"[ORCHESTRATOR-NOTES] Sending note_saved notification to WebSocket...")
                    note_saved_msg = {
                        "type": "note_saved",
                        "note_id": note_id,
                        "iteration": iteration + 1,
                        "is_final": chief_decision.get('decision') != 'loop',
                        "message": f"Iteration {iteration + 1} analysis saved to Notes"
                    }
                    logger.info(f"[ORCHESTRATOR-NOTES] WebSocket message: {note_saved_msg}")
                    await websocket.send_json(note_saved_msg)
                    logger.info(f"[ORCHESTRATOR-NOTES] WebSocket notification sent successfully")
                else:
                    logger.warning(f"[ORCHESTRATOR-NOTES] ⚠️ WARNING: No note ID returned for iteration {iteration + 1}")
                    logger.warning(f"[ORCHESTRATOR-NOTES] save_agent_notes returned: {note_id}")
                    logger.warning(f"[ORCHESTRATOR-NOTES] This likely means the note was not saved")
            except Exception as e:
                logger.error(f"[ORCHESTRATOR-NOTES] ❌ ERROR: Failed to save notes for iteration {iteration + 1}")
                logger.error(f"[ORCHESTRATOR-NOTES] Exception type: {type(e).__name__}")
                logger.error(f"[ORCHESTRATOR-NOTES] Exception message: {str(e)}")
                import traceback
                logger.error(f"[ORCHESTRATOR-NOTES] Full traceback:\n{traceback.format_exc()}")
                # Don't fail the whole orchestration if notes fail to save
                # But make sure we log it prominently
        else:
            logger.warning(f"[ORCHESTRATOR-NOTES] ⚠️ SKIPPING NOTES SAVE - Missing requirements:")
            if not NOTES_AVAILABLE:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ NOTES_AVAILABLE is False")
            if not db_session:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ db_session is None")
            if not project_id:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ project_id is None or False: {project_id}")
            if not branch_id:
                logger.warning(f"[ORCHESTRATOR-NOTES]   ❌ branch_id is None or False: {branch_id}")
        
        # Handle clarification needs (still handled by individual agents)
        needs_clarification = any(r.needs_clarification for r in valid_results)
        
        if needs_clarification:
            # Find the agent needing clarification and format the question
            for result in valid_results:
                if result.needs_clarification:
                    clarification_text = f"**Clarification Needed**\n\n"
                    clarification_text += f"**Question:** {result.clarification_question}\n\n"
                    clarification_text += f"**Results So Far:** {result.result.split('Answer: ')[1].split('\n')[0] if 'Answer: ' in result.result else 'Processing incomplete'}\n\n"
                    clarification_text += f"**Next Steps:** Please provide more details to continue processing\n\n"
                    
                    await websocket.send_json({
                        "type": "message",
                        "role": result.display_name or "Agent",
                        "text": clarification_text
                    })
                    return
        
        # Handle Chief Agent's clarification request
        if chief_decision.get('decision') == 'clarify':
            clarification_question = chief_decision.get('clarification_question', 'Could you please provide more details about your request?')
            thinking = chief_decision.get('thinking_process', 'Need more information from user')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting clarification: {clarification_question}")
            
            await websocket.send_json({
                "type": "message",
                "role": "The Chief Agent",
                "text": f"""🤔 **Clarification Needed**

{thinking}

**Question:** {clarification_question}

**Why I'm asking:** {chief_decision.get('reasoning', 'This information will help me provide a more accurate and helpful response.')}

Please provide this information so I can better assist you."""
            })
            return
        
        # Chief Agent makes the final decision
        # Limit looping to 3 iterations if errors occurred; otherwise use MAX_ITERATIONS
        allowed_loops = 3 if 'had_errors' in locals() and had_errors else self.MAX_ITERATIONS
        if chief_decision.get('decision') == 'loop' and iteration < allowed_loops - 1:
            # Chief Agent wants another iteration
            guidance = (chief_decision.get('additional_guidance', '') or '').strip()
            thinking = chief_decision.get('thinking_process', 'Analyzing how to improve the answer...')
            logger.info(f"[ORCHESTRATOR] Chief Agent requesting iteration {iteration + 1} with guidance: {guidance}")

            # Do not synthesize guidance locally; keep decisions LLM-driven. If missing, proceed without guidance.
            if not guidance:
                logger.info("[ORCHESTRATOR] No additional_guidance provided by Chief Agent; proceeding without local synthesis.")

            await websocket.send_json({
                "type": "agent_result",
                "agent_name": "The Chief Agent",
                "text": f"""🔄 Refining Answer (Iteration {iteration + 2}/{self.MAX_ITERATIONS}, {self.MAX_ITERATIONS - iteration - 2} loops remaining)

🤔 Chief Agent's Analysis:
{thinking}

🎯 Next Approach:
{guidance}

⏳ Running additional analysis..."""
            })

            # Prepare enhanced message with Chief Agent's guidance
            # Check if the guidance contains a shell command (in backticks)
            if guidance and '`' in guidance:
                # Extract command from guidance if present
                cmd_match = re.search(r'`([^`]+)`', guidance)
                if cmd_match:
                    # Pass the command directly for Shell Agent
                    enhanced_message = f"Execute: `{cmd_match.group(1)}`\n\nOriginal request: {message}"
                else:
                    enhanced_message = f"{message}\n\nRefinement guidance: {guidance}"
            else:
                enhanced_message = f"{message}"

            # Brief delay for UI
            await asyncio.sleep(0.3)

            # Start next iteration with Chief Agent's guidance
            return await self.orchestrate(enhanced_message, websocket, iteration + 1, valid_results, project_id, branch_id, db_session)
        
        # Chief Agent has made final decision - extract JSON fields only
        final_answer = chief_decision.get('final_answer', '')
        selected_agent = chief_decision.get('selected_agent', 'The Chief Agent')
        reasoning = chief_decision.get('reasoning', '')
        
        logger.info(f"[ORCHESTRATOR] Chief Agent FINAL decision")
        logger.info(f"[ORCHESTRATOR] Selected approach: {selected_agent}")
        logger.info(f"[ORCHESTRATOR] Final answer: {final_answer[:200]}...")
        
        # Calculate total time
        total_time = time.time() - orchestration_start
        
        # Use the LLM's formatted answer directly - no parsing, no manipulation
        final_text = final_answer
        
        # Add metadata about processing
        if iteration > 0:
            final_text += f"\n_🔄 Resolved after {iteration + 1} iterations in {total_time:.1f}s_"
        else:
            final_text += f"\n_✅ Processed in {total_time:.1f}s_"
        
        # Send final response with Chief Agent attribution
        # Send as 'final' type to stop the frontend timer
        logger.info("[ORCHESTRATOR] Sending final message with type='final'")
        await websocket.send_json({
            "type": "final",
            "text": final_text,
            "json": {
                "role": 'The Chief Agent',
                "selected_agent": selected_agent,
                "chief_reasoning": reasoning,
                "confidence": max([r.confidence for r in valid_results]) if valid_results else 0.0,
                "method": "Chief Agent Decision",
                "orchestration_time": total_time,
                "metadata": {
                    "all_results": [
                        {
                            "agent": r.agent_name,
                            "result": r.result,
                            "summary": r.summary,
                            "confidence": r.confidence,
                            "method": r.method,
                            "explanation": r.explanation
                        } for r in valid_results
                    ]
                }
            }
        })
        logger.info("="*80)
        logger.info(f"[ORCHESTRATOR] Orchestration completed in {total_time:.3f}s")
        logger.info(f"[ORCHESTRATOR] Final answer: {final_answer[:100]}...")
        logger.info(f"[ORCHESTRATOR] Notes saved for all {iteration + 1} iteration(s)")
        logger.info("="*80)
        

# Export the advanced orchestrator
__all__ = ['ThinkerOrchestrator', 'ChiefAgent']