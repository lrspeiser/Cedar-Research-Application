# CedarPy User Story Flows and Agent Prompts

This document describes representative user flows through CedarPy and explains how the Chief Agent orchestrates specialized agents, including how parallel agent jobs are dispatched and results are synthesized. It also catalogs the core prompts and JSON schemas used by the Chief and execution agents.

If you need to configure keys or optional services (OpenAI, Redis/relay), see README sections referenced in ARCHITECTURE.md.


## 1) User Story Flows

The Chief Agent is the master orchestrator. For each user input, it plans which specialized agents to run, dispatches them (in parallel when appropriate), and then synthesizes the results into a concise final message. The examples below illustrate end‑to‑end behavior.

### Flow A: “Do a quick calculation and show the code”
- User submits: “What is the mean of [3, 10, 4, 9, 12]? Show the Python code.”
- System steps:
  1) Chief Agent (planning): decides to use CodeAgent with a simple task.
  2) Agent execution (parallel-ready but here only one agent): CodeAgent generates JSON with two fields — answer (markdown) and code (raw Python). The orchestrator executes the code and captures stdout and errors.
  3) Chief Agent (synthesis): formats a short TLDR + what was asked + what agents found + reasoning + next steps.
- Output: Final message with the result, the code snippet (from the agent’s own formatted markdown), and processing time.

### Flow B: Image upload → extract data → persist as tables → summarize
- Trigger: A user uploads an image (chart). Auto-chat message is created with structured file details (file_id, mime, size) and DB table listing.
- System steps:
  1) Chief Agent (planning): routes to ImageAnalysisAgent with context.file_id.
  2) Agent execution (parallel-ready): ImageAnalysisAgent returns structured JSON (chart type, axes, data_points).
  3) Chief Agent (synthesis): determines next step is to persist extracted data — plans a loop with SQLAgent.
  4) Agent execution (loop): SQLAgent generates DDL/DML in JSON; SQLRunner executes it against the per‑project SQLite DB.
  5) Chief Agent (synthesis): finalizes a concise summary with TLDR, what we saw in the chart, what we inserted into tables, and possible next steps (e.g., plot via CodeAgent).
- Output: Final message plus any intermediate bubbles (agent outputs) and a changelog entry.

### Flow C: Tabular import via file upload (CSV/TSV/Excel)
- Trigger: User uploads a CSV. The post‑processing pipeline classifies structure=tabular and runs the LLM codegen importer.
- System steps:
  1) Background: Cedar generates stdlib-only Python to import rows into the per‑project SQLite DB, capturing project_id and branch_id.
  2) Chat: Auto message shows completion details and suggests next steps.
  3) Optional: User asks, “What’s the average of column X?” Chief Agent routes to SQLAgent → SQLRunner or CodeAgent.
- Output: Persisted dataset + chat orchestration results.

### Flow D: “Search my repo for TODOs”
- User submits: “Find all TODO lines in this repo, and summarize the files.”
- System steps:
  1) Chief Agent (planning): dispatches ShellAgent to grep for TODO and may also dispatch CodeAgent to summarize results.
  2) Agent execution (parallel): ShellAgent extracts and runs a safe, non‑interactive command; CodeAgent produces a short roll‑up.
  3) Chief Agent (synthesis): combines outputs into a final brief overview with file counts and suggested next steps.
- Output: Final message with bullet summary and the shell output inlined or linked.

### Flow E: “Download this URL and analyze it”
- User submits: “Download https://example.com/file.csv and tell me the top 5 rows.”
- System steps:
  1) Chief Agent (planning): dispatches FileAgent (download) and CodeAgent (summarize/preview) in parallel.
  2) Agent execution: FileAgent saves into user data; CodeAgent prints a small preview; if needed, Chief schedules a loop to persist via SQLAgent.
  3) Chief Agent (synthesis): final summary, next steps (e.g., plotting, further filtering).
- Output: Final message with a structured preview, plus a note about where the file is stored.

### Flow F: “Create or modify a table and then query it”
- User submits: “Create a notes_by_tag table and materialize counts per tag; then list the top 10 tags.”
- System steps:
  1) Chief Agent (planning): schedules SQLAgent to create the schema and insert/update.
  2) Agent execution: SQLAgent returns JSON containing DDL/DML; SQLRunner executes it; if needed, schedules a second step to query top 10.
  3) Chief Agent (synthesis): returns the results and next steps.
- Output: Final message; if data is large, the message includes a short preview.

Notes on concurrency
- The Chief Agent can assign multiple agent_tasks in a single loop (e.g., ShellAgent + CodeAgent). The Agent Dispatcher executes them concurrently and returns structured AgentResult objects used in synthesis.


## 2) Orchestration internals: parallel dispatch and loop synthesis

- Agent selection and dispatch (parallel):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/agent_dispatcher.py start=98
# Execute all agents in parallel
results = await asyncio.gather(*agent_tasks, return_exceptions=True)
logger.info(f"[AgentDispatcher] All {len(results)} agents completed")

return results
```

- Orchestrate: planning → dispatch → synthesis (and loop if needed):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/orchestrator.py start=196
if agent_tasks_list:
    agents, agent_task_map = AgentDispatcher.select_agents(agent_tasks_list, self)
    if agents:
        results = await AgentDispatcher.dispatch_agents(
            agents, agent_task_map, message, iteration,
            project_id, branch_id, file_id, db_session
        )
        valid_results, had_errors = await AgentResultProcessor.process_results(
            results, agents, message, websocket, run_logs,
            db_session, project_id, branch_id, thread_id, file_id
        )

# Chief Agent synthesis
chief_decision = await self.chief_agent.review_and_decide(
    user_query=message,
    agent_results=valid_results,
    iteration=iteration,
    max_iterations=self.MAX_ITERATIONS,
    previous_context="",
    resources=resources_index,
    conversation_history=conversation_history,
    ws=websocket,
    run_logs=run_logs,
    thread_id=thread_id
)
```

- Iteration loop (when decision="loop"):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/orchestrator.py start=275
if chief_decision.get('decision') == 'loop' and iteration < allowed_loops - 1:
    await self._handle_iteration(
        websocket, chief_decision, iteration, message,
        valid_results, project_id, branch_id, thread_id,
        db_session, conversation_history, file_id, dataset_id
    )
    return
```


## 3) Chief Agent prompts and schemas

System header (excerpt):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/prompts/chief_prompts.py start=12
def get_system_header(iteration: int, max_iterations: int, remaining_loops: int) -> str:
    """Get the main system header for Chief Agent"""
    cedar_intro = get_cedar_product_preamble()
    return f"""{cedar_intro}

You are the Chief Agent, the primary orchestrator that analyzes user queries, delegates tasks to specialized agents, reviews their responses, and synthesizes the final answer.
...
You MUST respond ONLY with valid JSON in this EXACT format (no prose before or after):
"""
```

Planning schema (no agent results yet):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/prompts/chief_prompts.py start=93
def get_planning_schema() -> str:
    return """
{
  "decision": "loop",
  "thinking_process": "Internal: 'User asks X. I will use [agents] because [reasons].'",
  "user_facing_message": "Brief formatted text explaining your routing decision...",
  "agent_tasks": [
    { "agent": "AgentName", "task": "...", "context": "..." }
  ]
}
... (rules about planning phase) ...
"""
```

Synthesis schema (with agent results):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/prompts/chief_prompts.py start=47
def get_synthesis_schema() -> str:
    return """
{
  "decision": "final" or "loop" or "clarify",
  "thinking_process": "Internal reasoning: ...",
  "additional_guidance": "...",
  "final_answer": "Complete, user-facing response...",
  "agent_tasks": [ { "agent": "AgentName", "task": "...", "context": "..." } ]
}
... (rules about synthesis and example) ...
"""
```

Routing examples and patterns:
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/prompts/chief_prompts.py start=123
def get_routing_examples() -> str:
    return """
Trigger Word Map:
- plan, roadmap, steps, orchestrate, playbook → StrategyAgent
- calculate, simulate, analyze, plot → CodeAgent
- derive, prove → FormulaAgent
- explain, summarize, cite → ResearchAgent
- SELECT, CREATE TABLE → SQLAgent
- schema, tables → DataAgent
- find files, grep → ShellAgent
- download file → FileAgent
- execute SQL generated by SQLAgent → SQLRunner
- generate image → ImageCreationAgent
- analyze image → ImageAnalysisAgent
...
"""
```


## 4) Agent prompt formats (expected JSON)

The execution agents return structured JSON that the orchestrator validates and uses directly. Below are the core prompt formats enforced by each agent.

CodeAgent (JSON contract excerpt):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/agents/code_agent.py start=80
"""You are a Python code generator.

You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted response ... (markdown)",
  "code": "executable_python_code_here_without_markdown_fences",
  "summary": "Brief 1-sentence description",
  "db_update": { ... optional SQL to persist artifacts ... }
}
... IMPORTANT rules ...
"""
```

SQLAgent (JSON contract excerpt):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/agents/sql_agent.py start=90
"""You are a SQL expert.
You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Markdown explanation of what the SQL does",
  "sql": "executable SQL statements",
  "operation_type": "CREATE_TABLE|SELECT|INSERT|UPDATE|DELETE|ALTER_TABLE|CREATE_INDEX|CREATE_DATABASE",
  "summary": "Brief 1-sentence description"
}
... IMPORTANT rules ...
"""
```

ShellAgent (JSON contract excerpt):
```python path=/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/agents/shell_agent.py start=78
"""You are a shell command expert.
You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Markdown explanation...",
  "command": "exact_shell_command_to_execute",
  "expected_output": "...",
  "summary": "Brief 1-sentence description"
}
... IMPORTANT rules (non-interactive, single line, etc.) ...
"""
```

Additional agents
- FileAgent: Uses structured behavior for URL downloads and optional brief description via LLM; stores files into per‑project storage and saves metadata to the DB.
- ImageAnalysisAgent: Returns structured JSON matching IMAGE_ANALYSIS_SCHEMA (metadata, axes, series, data_points, OCR text). Requires context.file_id.
- StrategyAgent, ResearchAgent, DataAgent, NotesAgent, FormulaAgent: Each has focused responsibilities; the Chief Agent chooses them via routing examples and task phrasing.


## 5) Chief Agent: master-then-parallel-then-synthesis pattern

- Master planning: The Chief Agent’s system prompt enforces a two‑phase loop — planning (decision="loop") then synthesis (decision="final" or another loop). In planning, it produces agent_tasks; in synthesis, it reviews agent results, decides if more work is needed, and optionally schedules the next minimal set of tasks.
- Parallel execution: The Agent Dispatcher gathers the selected agents and runs them concurrently using asyncio.gather, with per‑agent parameters (e.g., passing file_id for ImageAnalysisAgent or db_session for SQLRunner).
- Recollection: AgentResult objects feed into synthesis; the Chief Agent condenses the findings into a concise final_answer with a consistent structure (TLDR → Recap → What came back → Reasoning → Next steps).
- Looping: If more work is required, the Chief provides additional_guidance plus the next agent_tasks only (iterative planning by design). The orchestrator then re‑enters agent execution using the provided task list.


## 6) Operational clarity

- No silent fallbacks: Agent and Chief errors are surfaced as structured bubbles; logs include [agent], [preview], [ws] prefixes. JSON parse errors are explicitly handled with repair attempts (ChiefAgent) or error messages (agents).
- Key usage: See README “LLM classification on file upload” and “Where to put your OpenAI key (.env) when packaged”. Code paths contain comments pointing to these sections.
- Parallelism and limits: Agents are run with timeouts; the Chief enforces iteration limits and provides finalization guidance when limits are reached.
