# CedarPy Architecture

This document provides an overview of the CedarPy architecture, a tour of folders and key files, the main data flows, configuration and packaging notes, and a complete “Technologies and Libraries” section describing what we use, why, where, and how to configure each component.

If you are configuring API keys or system-level dependencies, see the README sections referenced throughout (we add explicit pointers so you know exactly where to look).

## Table of Contents
- 1) High-level overview
- 2) Directory and key files
- 3) Runtime data flows
- 4) Configuration and secrets
- 5) CI/CD and packaging
- 6) Technologies and Libraries
- 7) Operational notes and gotchas
- 8) Where to start when making changes
- 9) User story flows (end-to-end)
- 10) Agents and prompts (planning, routing, contracts)
- 11) Document index and source map
- 12) Academic Paper PDF workflow — the ultimate research tool
- 13) Full inlined references (single-document source of truth)
  - USER_FLOWS_AND_AGENTS.md
  - README.md (full)
  - COMPREHENSIVE_README.md
  - IMAGE_ANALYSIS_SCHEMA.md
  - CEDAR_AGENT_GUIDE.md
  - PROMPT_MANAGEMENT.md
  - PROMPT_IMPROVEMENT_GUIDE.md
  - ORCHESTRATOR_REFACTORING_PLAN.md
  - ORCHESTRATION_FLOW_ISSUES.md
  - AGENT_FLOW_IMPROVEMENTS.md
  - README_CHAT_HISTORY_SQL.md
  - README_NOTES_FEATURE.md
  - GitHub Workflows: ci.yml, tests.yml, macos-dmg.yml, macos-dmg-release.yml

## 1) High-level overview

- Purpose: Desktop/web research and data management app with LLM-driven workflows (projects/branches/threads, file uploads and AI classification, branch-aware SQL workspace, chat orchestration, and code/data tools).
- Desktop shell: PySide6 (QtWebEngine) embedding the web UI (cedarqt.py) so the app has a Dock icon, proper Quit behavior, and integrated logging.
- Backend: FastAPI + SQLAlchemy with a central registry database (default SQLite, can be MySQL) and one SQLite database per project.
- LLM: OpenAI for file classification, tabular import codegen, summaries; deterministic test mode exists for CI.
- Packaging: PyInstaller-based macOS bundle and DMG; GitHub Actions builds/testing; optional Redis/Valkey + Node SSE relay for incremental UI updates.


## 2) Directory and key files

Root level
- main.py — FastAPI application (imports configuration, DB utilities, LLM helpers, unified logging, wrappers for changelog/versioning, shell integration).
- main_models.py — SQLAlchemy models shared by the registry and per-project DBs (Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Setting, Version, ChangelogEntry, SQLUndoLog, Note, SavedCode, Chat, ChatMessage).
- main_helpers.py — Shared utilities: Redis SSE relay publish; in-memory ack registry with timeouts; branch roll-up logic; file extension mapping; lightweight versioning helper.
- run_cedarpy.py — Launcher that logs early, selects the app module (main or a minimal variant if present), starts Uvicorn, and includes diagnostic “doctor” helpers.
- server_manager.py — Development helper to avoid multiple server instances (PID files, port checks); can start/stop/restart.
- cedarqt.py — PySide6 Qt desktop shell. Handles single-instance lock with stale-lock recovery, loads .env in packaged mode, and forwards console logs to ~/Library/Logs/CedarPy.
- cedar_langextract.py — LangExtract integration: ensures tables and FTS index in per-project DB; file-to-text conversion; chunking; retrieval.
- cedar_tools.py — Tool registry/entry pairing with cedar_tools/ package tools.
- tests (test_*.py) — Pytest/Playwright tests for tools, chat, SQL, uploads, and embedded browser.
- pyproject.toml — Ruff lint configuration (focused on syntax/undefined names; excludes build artifacts).
- requirements*.txt — Dependency lists (core, dev, and file-processing specific).
- README.md and many focused docs — Authoritative operational docs for LLM keys, uploads, tabular import, Redis/relay, embedded UI testing, stale-lock fix, etc.

Core application: cedar_app/
- config.py — Loads .env from current dir, ~/CedarPyData/.env, and packaged Resources/.env (when applicable). Initializes data directories, feature flags, log directories, shell API settings.
- database.py & db_utils.py — Central registry engine/session; per-project engine cache; helpers for project directories (files/threads), lightweight migrations, ensure_project_initialized, and thread snapshotting.
- api_routes.py — Extracted API handlers (settings page/save; model change; chat ack; file serving bound to the project’s file root with path validation).
- route_handlers.py — Extracted heavy handlers (e.g., SQL execution + undo snapshot).
- routes/ — Modular route registration (main routes, project/thread routes, file routes, shell routes, SQL routes, WebSocket routes, log routes).
- llm/ — OpenAI client wrapper and tabular import codegen (stdlib-only execution sandbox).
- utils/ — Business logic modules (upload processing and classification, page rendering, branch/project ops, SQL helpers, logging, thread chat, WebSocket chat, etc.). Includes page_rendering_v2.py and backups of older versions.
- templates/components/ — Python-driven UI components used by server-rendered templates (alerts, tables).
- tools/ — Tool adapter(s) (e.g., shell tool) used by orchestrations.
- scripts/ — Utilities (e.g., extract_sql_routes.py).

LLM orchestration: cedar_orchestrator/
- Orchestrator and agents (file/code/data/image/pdf/notes/SQL/shell, etc.), prompts, resource indexer, ws_chat entry point. Backups of older orchestrator files are kept (marked .backup/.bak) for reference.

Tools and utilities
- cedar_tools/ — Legacy tool implementations (code, db, download, extract, image, notes, shell, tabular_import, web).
- cedar_utils/ — Reusable utilities (ports.py for robust port selection used by run_cedarpy launcher).

Build and distribution
- build-macos/ — PyInstaller intermediates for macOS packaging (not source; can be cleaned/rebuilt).
- dist-macos/ — Packaged app output (CedarPy app with bundled Qt frameworks and plugins).

Dev/test artifacts
- .ci_artifacts/ — Test logs, junit reports, playwright logs, env snapshots from CI.
- .logs/ and cedar_server.log — Runtime logs while developing.
- .testdata_shell/ — Local test data/logs for shell runs.

Legacy parallel agent folder
- agents/ — A simpler/older agent system parallel to cedar_orchestrator/agents. Prefer the cedar_orchestrator versions. If both contain similar functions, consolidate and move unused ones to a clearly marked _legacy folder with “DO NOT USE” comments to prevent confusion.


## 3) Runtime data flows

File upload
1) File saved to ~/CedarPyData/projects/<project_id>/files/<branchName>/...
2) Background post-processing:
   - LLM classification: structure (images|sources|code|tabular), ai_title, ai_description, ai_category.
   - Tabular import (for structure=tabular): generate stdlib-only Python code, import into per-project SQLite, create Dataset entries.
   - LangExtract chunking/FTS for retrieval.
3) UI auto-opens chat for the upload’s thread and posts a structured initial message. Errors are not hidden; logs include [upload-api], [llm-*], [tabular-*] lines.

WebSocket chat orchestration
- cedar_orchestrator generates prompts, calls tools, streams planning/actions/finals, and relies on client acks (/api/chat/ack) so the backend knows bubbles rendered.
- Optional Redis/Valkey + Node SSE relay streams incremental updates; WS remains for control and fallback.

Branch-aware SQL
- SQL executes on the per-project SQLite DB (with undo snapshots for mutations). Rendering helpers display SELECT results; changelog entries are recorded for actions.

Shell API (dangerous; local-only by default)
- When enabled, runs supervised shell jobs with token guard and WebSocket streaming. Logs are persisted under ~/CedarPyData/logs/shell.


## 4) Configuration and secrets

Where keys live
- For desktop/packaged runs: put keys in ~/CedarPyData/.env. Finder-launched apps do not inherit your shell environment.
- For CLI/dev runs: .env in the repo root is read as well. Keys: OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY.

References in README
- “LLM classification on file upload” — detailed configuration for models/keys.
- “Where to put your OpenAI key (.env) when packaged” — guidance for packaged app.
- “Shell window and API (WebSockets-only)” — enabling and securing shell execution.
- “Redis + Node relay (SSE) for reliable incremental updates” — how to run the relay in dev/CI.

Security and logging principles
- Do not hardcode API keys; environment only. No silent fallbacks; failures are logged verbosely.
- Client-side console logs are proxied to the server (capturing UI actions and errors for troubleshooting).


## 5) CI/CD and packaging

- GitHub Actions workflows: CI (tests), macOS DMG packaging, and release.
- PyInstaller packaging: build-macos intermediates; dist-macos packaged app with bundled Qt frameworks.
- Embedded UI testing: Playwright connects to QtWebEngine via CDP (configure CEDARPY_QT_DEVTOOLS_PORT).


## 6) Technologies and Libraries

Below are the libraries and technologies used by CedarPy, how we use them, configuration notes, and relevant README pointers.

FastAPI
- What/Why: ASGI web framework used for HTTP routes and WebSockets.
- Where: main.py and cedar_app/routes/*.
- Config: Standard FastAPI app; WebSockets used for chat and shell. See README: “WebSocket handshake and client acks”.

Starlette (transitive via FastAPI)
- What/Why: Underpins FastAPI routing and WebSocket support.
- Where: starlette.websockets used in main.py.

Uvicorn
- What/Why: ASGI server for FastAPI.
- Where: run_cedarpy.py starts uvicorn; CLI usage in README (uvicorn main:app --reload).
- Config: Default development server; logging routed to Unified Logging buffers.

Pydantic (transitive via FastAPI)
- What/Why: Data validation/models for request/response.
- Where: Imported in main.py (BaseModel) for typed payloads.

SQLAlchemy
- What/Why: ORM/SQL toolkit for registry and per-project DBs.
- Where: main_models.py (ORM models), cedar_app/database.py and db_utils.py (engines/sessions), SQL helpers in cedar_app/utils/sql_utils.py.
- Config: Registry DB (REGISTRY_DATABASE_URL) defaults to SQLite; per-project DBs are SQLite files under ~/CedarPyData/projects/<id>/database.db.

SQLite
- What/Why: Default datastore for registry (if not MySQL) and for all per-project databases.
- Where: cedar_app/database.py & db_utils.py create SQLite engines.
- Config: No server required; stored under ~/CedarPyData/projects.

MySQL + PyMySQL
- What/Why: Optional registry DB backend.
- Where: README “Run the server in a normal browser” shows sample DSN; main.py includes registry migrations compatible with MySQL.
- Config: Set CEDARPY_MYSQL_URL (or similar) per README; install PyMySQL via requirements.

python-multipart
- What/Why: File upload form parsing for FastAPI.
- Where: Required for multipart form endpoints (/files/upload).

PySide6 (Qt, QtWebEngine)
- What/Why: Desktop shell; embeds the app UI in a Chromium-based window with a Dock icon and menu.
- Where: cedarqt.py, dist-macos/ packaged frameworks and plugins.
- Config: CEDARPY_QT_DEVTOOLS_PORT for CDP; CEDARPY_QT_HEADLESS=1 for CI headless; single-instance lock at ~/Library/Logs/CedarPy/cedarqt.lock with stale-lock recovery. See README “Embedded UI testing via Playwright + CDP” and “Single-instance lock and stale lock recovery”.

OpenAI (openai SDK)
- What/Why: LLM calls for file classification, tabular import codegen, and summaries.
- Where: cedar_app/llm/client.py and related utilities; invoked from upload and orchestrator flows.
- Config: OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY via .env; model name via CEDARPY_OPENAI_MODEL. Deterministic CI mode with CEDARPY_TEST_MODE=1. See README sections “LLM classification on file upload”, “Tabular import via LLM codegen”, and “Where to put your OpenAI key (.env) when packaged)”.
- Important: Never hardcode secrets; code comments point back to README sections for key config (as required).

LangExtract
- What/Why: Chunking and FTS-based retrieval of uploaded documents without network calls.
- Where: cedar_langextract.py ensures schema and provides chunk/FTS helpers; cedar_app db migrations call ensure_langextract_schema.
- Config: SQLite FTS5 is used; purely local.

Redis (or Valkey)
- What/Why: Optional Pub/Sub transport for incremental UI bubbles; served to browser via a Node SSE relay.
- Where: main_helpers._publish_relay_event; README “Redis + Node relay (SSE) for reliable incremental updates)”.
- Config: CEDARPY_REDIS_URL; dev instructions in README (valkey-server via brew on macOS, then npm start for relay). If relay isn’t running, WS still provides updates (SSE is preferred).

Node SSE relay (external, optional)
- What/Why: Subscribes to Redis channels and serves SSE to the browser for incremental updates.
- Where: Described in README; relay directory may be external/not included in this repo.
- Config: CEDARPY_REDIS_URL, CEDAR_RELAY_PORT; run with npm ci && npm start as per README.

WebSockets
- What/Why: Real-time chat, shell streaming, and health checks.
- Where: cedar_orchestrator/ws_chat.py, shell WebSocket handlers; FastAPI route modules under cedar_app/routes/.
- Config: Client acks posted back to /api/chat/ack; see README “WebSocket handshake and client acks”.

Playwright + pytest-playwright
- What/Why: E2E testing against the embedded QtWebEngine via CDP.
- Where: tests referencing Playwright; cedarqt.py exposes DevTools port.
- Config: CEDARPY_QT_DEVTOOLS_PORT (default 9222); CEDARPY_QT_HEADLESS=1 in CI.

httpx
- What/Why: HTTP client for internal requests/testing.
- Where: Tests and selective utilities.

pytest
- What/Why: Unit and integration testing.
- Where: test_*.py at repository root; includes WebSocket chat, SQL, file processing, and embedded browser tests.

Ruff
- What/Why: Fast linter enforced via pyproject.toml.
- Where: pyproject.toml (select E9/F821; excludes build artifacts and bundled resources).

PyInstaller (packaging)
- What/Why: Create macOS app bundles and DMGs.
- Where: Build intermediates under build-macos/; packaged outputs under dist-macos/.
- Config: See README packaging notes and GitHub Actions workflows (.github/workflows/macos-dmg*.yml).

psutil (optional dev)
- What/Why: Process inspection for server_manager (find servers, ports).
- Where: server_manager.py.
- Note: Ensure it is installed in your dev environment if you use server_manager.

lsof (system tool)
- What/Why: Port/process diagnostics on macOS.
- Where: cedarqt.py and server_manager.py use lsof for diagnostics when available.

GitHub Actions
- What/Why: CI for tests and packaging; DMG release workflows.
- Where: .github/workflows/ci.yml, tests.yml, macos-dmg.yml, macos-dmg-release.yml.

Git LFS
- What/Why: Manage large files efficiently in Git (per your environment rule). Ensure large binaries are tracked via LFS.


## 7) Operational notes and gotchas

- Single instance desktop shell: A lock file at ~/Library/Logs/CedarPy/cedarqt.lock enforces single instance. If stale, it is safely removed (PID liveness check) and re-acquired once (see README for logs/troubleshooting).
- Client logging: The app injects a tiny script into every page to proxy console.* and capture errors; logs flow to /api/client-log and appear in server logs.
- No silent fallbacks: When web services or keys fail/missing, the app prints verbose logs; we do not fabricate or mask results.
- Keys/README pointers: Code paths that use external APIs include comments pointing back to the relevant README sections for key setup and troubleshooting, per policy.


## 8) Where to start when making changes

- UI & Pages: cedar_app/utils/page_rendering_v2.py and cedar_app/routes/main_routes.py.
- File uploads & processing: cedar_app/utils/file_upload.py and cedar_app/utils/file_operations.py (LLM classification + tabular import), with supporting LLM code in cedar_app/llm/.
- Orchestration & Chat: cedar_orchestrator/ws_chat.py and cedar_orchestrator/orchestrator.py plus agents/*.
- SQL workspace: cedar_app/utils/sql_utils.py and cedar_app/routes/sql_routes.py.
- Configuration & paths: cedar_app/config.py. Keys live in ~/CedarPyData/.env for packaged runs.
- Databases: main_models.py; engines/sessions and per-project storage in cedar_app/database.py and cedar_app/db_utils.py.


---

If you need to configure OpenAI keys or run the optional Redis/Node relay, see the referenced sections in README.md:
- “LLM classification on file upload”
- “Where to put your OpenAI key (.env) when packaged”
- “Redis + Node relay (SSE) for reliable incremental updates”
- “Shell window and API (WebSockets-only)”


## 9) User story flows (end-to-end)

Below are representative user flows and the steps CedarPy takes (planning → parallel agent execution → synthesis → optional loop):

- Flow A: Quick calculation with code
  - User: “What is the mean of [3, 10, 4, 9, 12]? Show the Python code.”
  - Steps: Chief plans CodeAgent → CodeAgent returns JSON {answer, code, summary} → code executed → Chief synthesizes TLDR, recap, results, reasoning, next steps.

- Flow B: Image upload → extract → persist → summarize
  - Trigger: File upload creates auto chat with file_id.
  - Steps: Chief → ImageAnalysisAgent (requires context.file_id) → Chief loops to SQLAgent → SQLRunner executes → Chief finalizes.

- Flow C: Tabular import via upload
  - Background: LLM codegen imports into per-project SQLite.
  - Chat: Auto message suggests next steps; user can ask SQL questions; Chief routes to SQLAgent/SQLRunner or CodeAgent.

- Flow D: Repo search and summary
  - User asks to grep TODOs and summarize; Chief dispatches ShellAgent and CodeAgent in parallel; Chief synthesizes outputs.

- Flow E: Download URL and analyze
  - Chief dispatches FileAgent + CodeAgent in parallel; may loop with SQLAgent to persist; Chief summarizes with next steps.

- Flow F: Create schema then query
  - Chief uses SQLAgent to create/modify tables and insert; SQLRunner executes; Chief returns results and next steps.

Notes on concurrency: The Agent Dispatcher (see cedar_orchestrator/agent_dispatcher.py) executes multiple agents concurrently via asyncio.gather and returns structured AgentResult objects used in synthesis.


## 10) Agents and prompts (planning, routing, contracts)

Chief Agent (orchestrator)
- Planning vs. synthesis:
  - Planning (no agent results yet): decision="loop", user_facing_message, agent_tasks[].
  - Synthesis (with agent results): decision="final" | "loop" | "clarify", thinking_process, additional_guidance (if looping), final_answer, agent_tasks[].
- Routing examples: Trigger word map guides which agent(s) to choose (e.g., calculate → CodeAgent, SELECT/CREATE → SQLAgent, grep/find → ShellAgent, analyze image → ImageAnalysisAgent, etc.).
- Final answer format: TLDR → Recap of what was asked → What came back → Reasoning → Possible next steps.

Key prompt sources
- Chief prompt templates: cedar_orchestrator/prompts/chief_prompts.py
  - get_system_header(iteration, max_iterations, remaining_loops)
  - get_planning_schema() and get_synthesis_schema()
  - get_routing_examples() and get_agent_capabilities()
- Dynamic prompt extraction (for display/inspection): cedar_orchestrator/agent_prompts.py

Execution agent JSON contracts (enforced by prompts)
- CodeAgent (cedar_orchestrator/agents/code_agent.py)
  - Must return JSON: { answer: markdown, code: python, summary: string, db_update?: {...} }
  - Orchestrator executes the code and captures stdout/stderr; answer is displayed as-is.
- SQLAgent (cedar_orchestrator/agents/sql_agent.py)
  - Must return JSON: { answer: markdown, sql: text, operation_type: enum, summary: string }
  - SQLRunner executes the sql; answer/summary used for display/logging.
- ShellAgent (cedar_orchestrator/agents/shell_agent.py)
  - Must return JSON: { answer: markdown, command: text, expected_output: text, summary: string }
  - Non-interactive only; orchestrator executes exactly the provided command.
- ImageAnalysisAgent
  - Requires context.file_id; returns structured JSON per IMAGE_ANALYSIS_SCHEMA.md (axes, series, data_points, OCR, etc.).
- FileAgent
  - Downloads URLs, saves metadata to DB; may call LLM for a brief description JSON; integrates with per-project storage.
- Other agents: ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FormulaAgent have focused responsibilities and outputs as documented in their modules and capability map.

Master → parallel → synthesis loop
- Chief produces agent_tasks (planning) → Agent Dispatcher runs selected agents concurrently → Chief reviews AgentResult list (synthesis) and either (a) returns final_answer or (b) schedules a loop with additional_guidance and the next minimal agent_tasks.
- Limits/timeouts: Agents run with timeouts; Chief enforces iteration limits and provides finalization guidance when limits are reached.


## 11) Document index and source map

This architecture document is now the overarching reference and incorporates content from other docs. For deeper dives and rationale, see:
- USER_FLOWS_AND_AGENTS.md — Full user flows, orchestration internals, and prompt excerpts (kept as a standalone for focused reading; this section summarizes and inlines key points).
- README.md — Operational run modes, keys, uploads, client logging, shell API, Redis/relay, embedded UI testing, troubleshooting, stale-lock fix.
- COMPREHENSIVE_README.md — Broader background, directory map, and packaging/deployment context.
- IMAGE_ANALYSIS_SCHEMA.md — Expected JSON schema for image analysis results.
- CEDAR_AGENT_GUIDE.md, PROMPT_MANAGEMENT.md, PROMPT_IMPROVEMENT_GUIDE.md — Prompt patterns, management, and improvements.
- ORCHESTRATOR_REFACTORING_PLAN.md, ORCHESTRATION_FLOW_ISSUES.md, AGENT_FLOW_IMPROVEMENTS.md — Refactor history and design decisions.
- README_CHAT_HISTORY_SQL.md, README_NOTES_FEATURE.md — Chat history persistence and notes features.
- .github/workflows/*.yml — CI, tests, and macOS DMG packaging/release automation.

If anything drifts, this file should remain the canonical high-level entry point, with links pointing to the most detailed sources in the repo.


## 12) Academic Paper PDF workflow — the ultimate research tool

CedarPy is designed to ingest an academic PDF and orchestrate a multi‑agent pipeline that captures the paper’s knowledge comprehensively. When you upload a PDF of an academic paper, the Chief Agent automatically plans and dispatches specialized agents (in parallel where appropriate) to:

- Extract full text, sections, metadata, images, and tables
- Store images and extracted chart data in relational tables
- Generate executable code to replicate figures and analyses
- Identify and retrieve original citation PDFs and extract them as well
- Persist everything in the per‑project database and produce a structured research note

High‑level pipeline
1) PDF upload triggers auto‑chat (file_id provided to agents)
   - Chief Agent plans PDF processing using file_id context (no FileAgent needed for already‑uploaded files).

2) PDFExtractionAgent (analysis)
   - Extracts: title, authors, abstract, sections, page text, embedded images, tables, and basic metadata (author/title/creation_date/page_count). Returns structured JSON.

3) ImageAnalysisAgent (images)
   - For each embedded image (charts/figures), extracts: chart type, axes, legends, data series, representative data points, OCR text, and descriptive metadata.
   - Stores according to the documented schema in IMAGE_ANALYSIS_SCHEMA.md (image_metadata, image_purpose, image_conclusions, chart_axes, chart_series, chart_data_points, image_text).

4) SQLAgent + SQLRunner (storage)
   - Creates and populates pdf_documents, pdf_pages, pdf_images, pdf_tables, and citations tables, plus the image schema tables when applicable.
   - Ensures branch‑aware inserts and indexes for fast querying.
   - No fallbacks: errors surface with detailed logs; changes recorded via changelog entries.

5) CodeAgent (reproduction)
   - If code fragments or statistical steps are identified, generates Python to reproduce the paper’s analyses and figures (e.g., re‑plot extracted chart data, recompute summary statistics).
   - Saves outputs (plots, CSVs) into project files; can write structured results back to the database for traceability.

6) ResearchAgent + FileAgent (citations)
   - Parses references and locates the original citation pages/DOIs. For accessible references, FileAgent downloads the PDFs into project storage.
   - Optional: PDFExtractionAgent runs again on referenced PDFs to extract key metadata.
   - SQLAgent stores citations and cross‑links them to the originating document.

7) NotesAgent (knowledge capture)
   - Writes a structured research note for the paper including: key points, methods, datasets/tables created, generated artifacts, and citations. Tagging is applied to facilitate retrieval.

8) StrategyAgent (complex orchestration)
   - For multi‑paper batches or layered analysis, designs iterative plans spanning PDF extraction → data modeling → statistical reproduction → cross‑citation enrichment → reporting.

Principles and guardrails
- No fallbacks or fabrication: failures are visible with verbose logs and structured error outputs; retry/repair attempts are explicit.
- Deterministic CI mode (if enabled) skips external calls; normal runs require real keys.
- Everything is persisted: documents, images, tables, citations, generated code outputs, and notes live in the per‑project SQLite database and file storage for later queries.


## 13) Full inlined references (single‑document source of truth)

This section inlines the complete content of key reference documents and workflows so this file can serve as the one master reference going forward.

### USER_FLOWS_AND_AGENTS.md

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
```python
# Execute all agents in parallel
results = await asyncio.gather(*agent_tasks, return_exceptions=True)
logger.info(f"[AgentDispatcher] All {len(results)} agents completed")

return results
```

- Orchestrate: planning → dispatch → synthesis (and loop if needed):
```python
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
```python
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
```python
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
```python
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
```python
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
```python
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
```python
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
```python
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
```python
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


### README.md (full)

# CedarPython (Stage 1)

> Important: This README includes a postmortem of recent startup issues, how they were fixed, and how the app is now set up. It also links to tests we added to prevent regressions.

Minimal FastAPI + MySQL prototype to manage **Projects**, **Branches**, **Threads**, and **Files** with
simple roll-up behavior between Main and branches.

Refactor note: The codebase is modularized for maintainability:
- main_models.py: SQLAlchemy Base and all ORM models
- main_helpers.py: shared helpers (Redis/SSE relay publish, ACK registry, escape/add_version/branch helpers)
- main.py: FastAPI app, routes, and the WebSocket Chat orchestrator (planned to be extracted next)

## What this does (today)
- Lists projects and lets you create a new project (auto-creates a `Main` branch).
- Shows a project dashboard with tabs for branches.
- Upload a file to a branch (or Main). Files uploaded to a **branch** appear in _that branch_ **and in Main**.
  Files uploaded to **Main** appear in **all branches** and **Main**.
- Create a simple "thread" under the current branch.
- Shows stub "Databases" list (data model exists, creation UI can be added later).
- Stores simple version records in a `versions` table for created entities (Project, Branch, Thread, File).
- Stores an (unused for now) `settings` table (e.g., for OpenAI API key later).

> Note: We are intentionally **not** using DuckDB/Julia/Parquet per the current stage requirements.

## Quickstart

Important: For packaged distribution, always use the Qt DMG build so the app shows a Dock icon and can be quit via Cmd-Q/Dock.
- Build: bash packaging/build_qt_dmg.sh
- Install: open packaging/dist-qt/CedarPy-qt.dmg and drag CedarPy.app to Applications
- Do not use the embedded DMG for end-users if you need a Dock icon and standard quit behavior.

### Run as a desktop app (Qt + QtWebEngine)

- Install deps (includes PySide6):
  - pip install -r requirements.txt
- Launch the embedded-browser desktop shell with a Dock icon and Quit support:
  - python cedarqt.py

Why this matters: the Qt desktop shell presents a normal macOS app with a Dock icon and menu, so you can Quit via Cmd-Q or from the Dock. This is the supported way to run Cedar as a desktop app to ensure it can be exited cleanly.

This starts the FastAPI server and opens the UI inside a QtWebEngine window. JavaScript console output and in-page errors are captured and forwarded to your app logs under ~/Library/Logs/CedarPy (or $CEDARPY_LOG_DIR if set).

### Run the server in a normal browser

1. **Provision MySQL** (example uses a DB named `cedarpython`):
   ```sql
   CREATE DATABASE cedarpython CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
   ```

2. **Set your database URL** (adjust user/pass/host/port):
   ```bash
   export CEDARPY_MYSQL_URL="mysql+pymysql://root:password@localhost/cedarpython"
   # On Windows (PowerShell):
   # setx CEDARPY_MYSQL_URL "mysql+pymysql://root:password@localhost/cedarpython"
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**:
   ```bash
   uvicorn main:app --reload
   ```

5. Open http://127.0.0.1:8000 in your browser.

## Frontend (dynamic UI only)

The app serves a dynamic, backend-driven UI only. The legacy standalone page.html and any assets/static directories are no longer used or bundled.

- The home route renders server-side HTML with small inline JS.
- No external static bundles are mounted at /assets or /static.
- Logs continue to indicate UI route activity.

Overrides
- CEDARPY_LEGACY_UI is ignored; the dynamic UI is always used.

Packaging
- The DMG bundles only the application code; no page.html or assets/static directories are included.
- See packaging files: `packaging/cedarpy.spec` and `packaging/cedarpy_macos.spec`.

Notes
- No keys are needed for the frontend itself. For LLM-backed features, see "LLM classification on file upload" and "Where to put your OpenAI key (.env) when packaged" below. Relevant code paths include comments pointing back to those sections.

## Data model (MySQL)

- `projects` – top-level projects
- `branches` – per-project branches (unique by (project_id, name)); `Main` always exists
- `threads` – simple thread stub tied to (project, branch)
- `files` – uploaded files + metadata (`type`, `structure`, mime, size, path)
- `datasets` – a placeholder for future "Databases"
- `settings` – key/value settings (e.g., openai_api_key later)
- `versions` – lightweight row-versioning per-entity (entity_type, entity_id, version_num, data)

## Branch roll-up logic

- Viewing **Main**: shows **all** items in the project (Main + every branch).  
- Viewing **Branch X**: shows **Main + Branch X only** (not other branches).

This matches: *"I should be able to see that file in the branch and in main, but not in a separate branch from the one it was put in, unless it was put in main."*

## Merge (project-scoped)

- The Merge tab operates within a single project. It shows only that project’s branches and merges a selected branch back into Main.
- Navigation preserves project context (project_id and branch_id) so clicking Merge from a project will land on the correct page.
- Visiting /merge without context will either:
  - redirect to /merge/{project_id} if there’s exactly one project, or
  - show guidance to open a project first (it no longer lists all projects).

This design matches per-project data separation and avoids cross-project merges. To move data across projects, export/import files or datasets rather than merging.

## Uploads

Uploaded files are saved under `user_uploads/project_{id}/branch_{branchName}/...` (relative to the app working directory by default).  
Override with `CEDARPY_UPLOAD_DIR` if desired.

### Embedded Qt harness (uploads)
- When CEDARPY_QT_HARNESS=1 is set (used by the embedded test harness and macOS embedded UI e2e test), the upload endpoint responds immediately with a small 200 OK HTML page and `Connection: close`. All post-processing — LLM classification, versioning, changelog, and background indexing — runs in a background worker.
- Why: this avoids intermittent HTTP parser edge cases (httpx/httptools/h11) observed when emitting response headers for multipart POSTs under the embedded harness.
- Normal runs (without CEDARPY_QT_HARNESS) keep the standard behavior (303 redirect with `Content-Length: 0`).
- Logs: look for `[upload-api] qt_harness=1` followed by background logs.
- Keys: classification uses the same OpenAI key setup described in "LLM classification on file upload" in this README. The code includes comments pointing back to this section.

## Client-side logging

What gets captured
- console.log/info/warn/error (proxied)
- window.onerror and unhandledrejection (with stack when available)
- UI instrumentation for uploads: when you click the file input, select a file, click Upload, and submit the form, the page emits console logs like [ui] upload input clicked, [ui] file selected <name> <size>, [ui] upload clicked, [ui] upload submit. These flow into /api/client-log and show in the /log page.

How it works
- A small script is injected into every page that proxies console methods and posts to /api/client-log using navigator.sendBeacon when available or fetch(..., {keepalive:true}).
- The upload page includes a tiny inline script (added centrally in the injected block) that attaches event listeners to the upload form elements. See comments in main.py around layout() and project_page_html() for the selector details.

Troubleshooting
- If you don’t see upload UI logs at /log, make sure you’re on a page rendered by layout() (it injects the logging script) and that the selectors [data-testid=upload-form|upload-input|upload-submit] exist (inspect the DOM). The inline script logs [ui] upload instrumentation error if it cannot attach.
- The server-side will also print [upload-api] lines when an upload request arrives and after classification. Check the terminal or uvicorn logs.

What was wrong and how it was fixed
- Mistake: We weren’t emitting any console logs for file input clicks/changes or form submission, so nothing was sent to /api/client-log during the upload flow.
- Fix: Added explicit client-side instrumentation for the upload UI and added server-side [upload-api] prints before/after save and after classification. Verified by uploading a test file and seeing both the [ui] logs in /log and [upload-api] lines in the server logs.

## Auto-start chat on upload

When an upload completes, CedarPy automatically opens the chat for the upload-created thread and posts an initial user message containing structured details:

- First user message text prefix:
  "User uploaded a file with the following details:"
- JSON body fields included:
  - project_id, branch_id, thread_id, file_id
  - name (display_name), file_type, structure, mime_type, size_bytes
  - storage_path (absolute disk path)
  - sha256 (if available)
  - first_lines: first 40 lines from metadata_json.sample_text (if readable), clipped to ~2000 chars total

This lets you watch classification, tabular import (when applicable), and LangExtract indexing activity in one place and immediately start planning follow-up analysis.

Configuration
- CEDARPY_UPLOAD_AUTOCHAT=1 (default). Set to 0/false to disable auto-start (useful for demos/tests that don’t want the chat to kick off). The app reads this into cedar_app.config.UPLOAD_AUTOCHAT_ENABLED.

What the UI shows immediately
- On WebSocket chat start (when file_id is present), the server emits an action event that renders an assistant bubble with a spinner:
  "Processing <filename>…"

Notes
- The right-side Files panel still opens so the UI remains consistent with existing tests.
- Background upload steps remain the source of truth; the orchestrator will not re-run ingestion.

## LLM classification on file upload

Keys (how to configure)
- Set OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY in your shell before running. Never hardcode keys. When packaged (Qt app), environment variables can be loaded from the app’s Resources/.env (see cedarqt.py comments) — see this README for details.
- Code paths that require keys include comments pointing back to this section so you always know where to configure them.

When a file is uploaded, CedarPy can call an LLM to classify and annotate it. The model returns:
- structure: one of [images | sources | code | tabular]
- ai_title: friendly title (<= 100 chars)
- ai_description: friendly description (<= 350 chars)
- ai_category: category (<= 100 chars)

Configuration
- CEDARPY_FILE_LLM: Defaults to 1 (enabled). Set to 0/false to disable the classification step.
- CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY: API key for the OpenAI API.
- CEDARPY_OPENAI_MODEL: model name (default: gpt-5).

Security and troubleshooting
- Do not hardcode API keys. Use environment variables only.
- If the key is missing or the API fails, the upload still succeeds; verbose logs show [llm-*] lines describing the cause. We do not fallback or fabricate values.
- Code comments in main.py (search for "LLM classification") point back to this section.

### CI test mode (deterministic LLM stubs)

To make CI stable and deterministic without calling external APIs, set:

- CEDARPY_TEST_MODE=1

Behavior when enabled:
- All OpenAI chat calls via the internal client are stubbed with predictable JSON (no network).
- File classification returns a fixed result: structure="sources", ai_title="Test File", ai_description, ai_category.
- Ask orchestrator returns strict JSON with a single final function call ("Test mode OK").
- WebSocket chat returns a final function with text "Test mode (final)" and a title.
- Changelog summaries use a simple "TEST: <action> — ok" string.

Logging:
- Look for [llm-test] lines indicating the stubbed client is in use.

Notes:
- This flag is used only in CI; normal runs still require a real API key. See code comments around _llm_client_config() referencing this section.

## Tabular import via LLM codegen

If the classification step returns structure=tabular, CedarPy runs a second LLM job to generate Python code that imports the uploaded file into the per-project SQLite database.

What happens
- We prompt the model with extracted metadata (extension, mime guess, csv dialect, a small snippet) and the target DB path.
- The model must output a Python function run_import(src_path, sqlite_path, table_name, project_id, branch_id) using ONLY the Python standard library (csv/json/sqlite3/re/io).
- The generated code is executed in a restricted environment (no network, open() is limited to the uploaded file path, import is allowed only for whitelisted stdlib modules).
- A branch-aware table is created: id INTEGER PRIMARY KEY AUTOINCREMENT, project_id, branch_id, plus inferred columns. Rows are inserted with project_id and branch_id set to the current context.
- On success, we create a Dataset entry and show a thread message with the result. All steps are logged with [tabular] or [tabular-error] prefixes.

Configuration
- CEDARPY_TABULAR_IMPORT: Defaults to 1 (enabled). Set to 0/false to disable the codegen+import step.
- CEDARPY_TABULAR_MODEL: Optional model name for codegen (defaults to CEDARPY_OPENAI_MODEL or gpt-5).
- CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY: same key used for classification.

Notes and guardrails
- No external libraries are permitted; the code must rely on the Python standard library. This avoids environment drift and packaging issues.
- The execution sandbox blocks writing files except the SQLite database via sqlite3. It also restricts imports to csv/json/sqlite3/re/io/math/typing and replaces builtins.open with a read-only wrapper limited to the uploaded file path.
- We do not fabricate results. If the model fails or code raises, the UI shows a detailed error and logs are attached to the thread; the file remains available.

Where to look in code
- main.py: search for "Tabular import via LLM codegen" and _tabular_import_via_llm(). Comments in code link back to this section.

Planner tool
- The WebSocket chat orchestrator exposes a tabular_import tool you can call to refine imports (e.g., header_skip, delimiter). It replaces the per-file table in-place and posts the result back to the thread. See the orchestrator prompt examples for usage.

Dataset naming
- After a successful import, Cedar suggests a short human-friendly dataset name (uses a small model). The stable storage table name remains the same and is recorded in the Dataset description ("table: <name>").

Where to put your OpenAI key (.env) when packaged
- For the Qt DMG and embedded builds, environment variables from your shell are not inherited when launching via Finder.
- The app loads .env in this order:
  1) .env in the current working directory (developer CLI only)
  2) ~/CedarPyData/.env (preferred for packaged apps)
  3) .env inside the app Resources (packaged fallback)
- Recommended: create ~/CedarPyData/.env and add one of:
  OPENAI_API_KEY={{YOUR_OPENAI_API_KEY}}
  or
  CEDARPY_OPENAI_API_KEY={{YOUR_OPENAI_API_KEY}}
- Do not commit secrets to the repo. Keep .env under your home directory.
- UI hint: The header shows "LLM unavailable (missing key)" until a key is detected; logs include [llm-skip] missing OpenAI API key.

The app injects a small script into every HTML page that:
- Proxies console.log/info/warn/error
- Captures window.onerror and unhandledrejection
- POSTs logs to /api/client-log with details (level, message, URL, line/column, stack, userAgent)

Server route: POST /api/client-log
- Local-only by default (since the app binds to 127.0.0.1).
- Code comments point back to this README. No API keys are required for this feature.

Log locations (macOS):
- ~/Library/Logs/CedarPy/cedarqt_*.log — desktop shell
- ~/Library/Logs/CedarPy/uvicorn_from_qt.log — server started by the shell
- main server logs also print [client-log], [qt-console], and [qt-request] prefixes

Single-instance lock and stale lock recovery:
- The desktop shell enforces a single running instance using a lock file at $CEDARPY_LOG_DIR/cedarqt.lock (defaults to ~/Library/Logs/CedarPy/cedarqt.lock).
- If you see "another instance detected via ... cedarqt.lock; exiting" but no app is running, the lock is stale.
- Fix implemented: On startup, CedarPy now reads the PID from the lock, checks if it is alive (os.kill(pid, 0)), and if not, removes the stale lock and retries exactly once to acquire it. This avoids any infinite loops while recovering from crashes/ungraceful exits.
- Added logging: look for lines like:
  - "[cedarqt] removed stale lock: ... (pid=####)"
  - "[cedarqt] acquired single-instance lock: ..."

Troubleshooting:
- Override log/lock directory with:
  - export CEDARPY_LOG_DIR="$HOME/Library/Logs/CedarPy"
- Manually clear a stuck lock:
  - rm -f "$CEDARPY_LOG_DIR/cedarqt.lock"
- Verify startup:
  - tail -n 200 "$(ls -t "$CEDARPY_LOG_DIR"/cedarqt_*.log | head -n1)"

What was wrong and how it was fixed:
- Mistake: The app previously exited if the lock file existed without checking whether the PID inside was still running, causing a stale lock to block all future launches.
- Fix: Implemented PID liveness check and single-retry stale-lock removal. The lock path now honors $CEDARPY_LOG_DIR for consistency with logging.
- Test performed: Created a fake lock file with a non-running PID and launched the app; observed log lines indicating stale lock removal and successful re-acquisition. Also validated that if a real process is running with that PID, the app exits cleanly without attempting removal.
- Additional logging was added at startup to print lock_path and current pid for easier diagnosis.

## Shell window and API (WebSockets-only)

Danger zone: This feature executes arbitrary shell scripts with the same privileges as the user running the server. It is disabled by default and should only be enabled on your own machine in trusted environments.

Enable and secure:
- CEDARPY_SHELL_API_ENABLED: Defaults to 1 (enabled). Set to 0/false to disable.
- CEDARPY_SHELL_API_TOKEN=<token>: Optional. If set, API requests must include header X-API-Token: <token>.
  If not set, only local requests (127.0.0.1/::1) are allowed.

UI:
- Navigate to /shell for a textarea to enter a script and a live output pane. You can optionally specify a shell path; defaults to $SHELL or /bin/bash. The page uses WebSockets to stream lines back to the browser. No SSE is used anywhere.

API endpoints (for LLM integration):
- POST /api/shell/run
  - Headers: X-API-Token: <token> (required if CEDARPY_SHELL_API_TOKEN set)
  - Body (JSON): { "script": "echo hello", "shell_path": "/bin/zsh" (optional) }
  - Response: { job_id, pid, started_at }
- WS /ws/shell/{job_id}
  - Text WebSocket streaming. Each message is one line of output. A terminal message "__CEDARPY_EOF__" indicates completion.
  - Auth: If CEDARPY_SHELL_API_TOKEN is set, pass token in the query string (?token=...) or Cookie (Cedar-Shell-Token). Otherwise local-only.
- WS /ws/health
  - Simple handshake that replies "WS-OK" and closes. Useful for front-end readiness checks.
- POST /api/shell/stop/{job_id}
  - Stops the process group for the job (SIGTERM). Requires token or local request.
- GET /api/shell/status/{job_id}
  - Returns status, return_code, timestamps, and on-disk log path.

Logging:
- Logs are written under $CEDARPY_DATA_DIR/logs/shell/ with filenames like YYYYmmddTHHMMSSZ__<jobid>.log
- The UI streams output live and also writes to these log files for later inspection.

Security model:
- By default, the feature is OFF. When enabled, commands run with your user account, using your login shell ($SHELL or /bin/bash) with -l -c semantics.
- If CEDARPY_SHELL_API_TOKEN is set, the token must be provided via X-API-Token for all API calls. Otherwise, only local requests are accepted.
- There is no sandbox. Treat this as giving full shell access to anyone with the token or local access to the machine.

Examples:
```bash
# Enable locally (bash/zsh)
export CEDARPY_SHELL_API_ENABLED=1
export CEDARPY_SHELL_API_TOKEN="<choose-a-strong-secret>"

# Run the server
uvicorn main:app --reload

# Submit a job (macOS/Linux)
curl -sS -H "Content-Type: application/json" \
     -H "X-API-Token: $CEDARPY_SHELL_API_TOKEN" \
     -d '{"script":"echo hello && uname -a"}' \
     http://127.0.0.1:8000/api/shell/run
```

Note on API keys: This feature uses environment variables for configuration. See above for how to set them securely. Code comments reference this README for usage and pitfalls.

## WebSocket handshake and client acks

The chat and other live streams are delivered over WebSockets. Each UI bubble (submitted, planning, action, final, errors, etc.) is acknowledged by the client after it renders to ensure the backend knows the message was displayed.

- Endpoint: POST /api/chat/ack
- Payload: { "eid": "<event-id>", ... }
- Behavior: The backend records the ack in an in-memory store and prints a log line like:
  - [ack] eid=<id> type=<event-type> thread=<thread-id>
- If an ack is not received within the timeout (default 10s), the backend prints:
  - [ack-timeout] eid=<id> info={...}

Frontend behavior
- After the page renders a bubble, it immediately posts an ack with the event id.
- This handshake runs for every major LLM call, including the final call, and before/after thinking phases when those are streamed.

What was wrong and how it was fixed (import-time NameError)
- Mistake: The FastAPI route decorator for /api/chat/ack was placed above the declaration of app = FastAPI(...). During module import, app wasn’t defined yet, raising NameError when tests imported main.
- Fix: Move the route definition to immediately after app is created (see main.py: “WS ack handshake endpoint”). Tests that import main now succeed.
- How verified: Imported main in a REPL and confirmed HAS_ACK True via scanning app.routes; ran pytest -q tests/test_html_rendering.py which previously failed on NameError.

Notes
- This handshake is best-effort and uses an in-memory registry; if the server restarts, pending acks are cleared. It is intended for UI reliability and observability, not durability.

## Redis + Node relay (SSE) for reliable incremental updates

We now publish each chat/planner bubble to Redis and serve them to the browser via a tiny Node SSE relay.

- Python publishes to Redis Pub/Sub per thread: channel cedar:thread:{thread_id}:pub
- Node relay subscribes and serves Server-Sent Events at /sse/:threadId
- Frontend connects with EventSource and renders bubbles as they arrive. We still post /api/chat/ack after rendering.

Local run
- Start Redis (or Valkey). On macOS with Homebrew: brew install valkey && valkey-server
- Start the Node relay:
  - cd relay && npm ci && npm start
  - Env: CEDARPY_REDIS_URL (default redis://127.0.0.1:6379/0), CEDAR_RELAY_PORT (default 8808)
- Start CedarPy as usual (Qt app or uvicorn).

CI
- GitHub Actions runs Redis as a job service and launches the Node relay before Playwright tests.

Notes
- App still emits WebSocket messages, but the UI prefers the SSE stream for rendering. WS remains for command/control and as a fallback.
- If Redis or the relay isn’t running, incremental bubbles won’t appear over SSE, but WS may still provide updates.

## Front-end choice for embedded browser (QtWebEngine)

### Embedded UI testing via Playwright + CDP

We embed a Chromium-based engine (QtWebEngine) for the desktop app. You can test the exact embedded browser end-to-end using Playwright by connecting over the Chrome DevTools Protocol (CDP):

Environment variables (cedarqt.py reads these):
- CEDARPY_QT_DEVTOOLS_PORT: DevTools port to expose (default 9222).
- CEDARPY_QT_HEADLESS: Set to 1/true to run Qt in offscreen mode for CI.

Example manual run:
```bash
# one terminal: run embedded shell exposing DevTools
export CEDARPY_QT_DEVTOOLS_PORT=9222
export CEDARPY_QT_HEADLESS=1
export CEDARPY_OPEN_BROWSER=0
python cedarqt.py

# second terminal: run the embedded E2E test
pytest -q tests/test_embedded_qt_ui.py
```

Notes
- The test connects with playwright.chromium.connect_over_cdp("http://127.0.0.1:9222").
- We also keep cross-browser tests (Chromium/WebKit) to catch Safari/WebKit differences.
- Our upload tests assert the submit button is visible and enabled to prevent false passes where UI is not interactive.

- We standardize on vanilla ES modules and minimal inline JS for the built-in browser (QtWebEngine, Chromium-based). Live updates prefer SSE via the Node relay (EventSource), with WebSockets used for control and fallback.
- Rationale:
  - Keeps the bundle small and avoids additional frameworks.
  - Works reliably in the embedded runtime and regular browsers.
  - Our current UI is server-rendered HTML plus small JS. This remains the default.
- Future: If we want richer UX, we can layer in a lightweight micro-framework (e.g., preact/lit) as ES modules without a big toolchain, still using WebSockets for live updates.

## Packaging (macOS DMG)

See also: docs/CI.md (CI and Packaging Guide) and CHANGELOG.md (2025-09-20 CI stabilization) for pitfalls and fixes we applied to get the pipeline green and the DMG reliable.

- Build locally:
  - python -m pip install -r requirements.txt
  - python -m pip install -r packaging/requirements-macos.txt
  - bash packaging/build_macos_dmg.sh
  - Open dist/CedarPy.dmg

- Server-only bundle for isolation/debug (no Qt wrapper):
  - bash packaging/build_server_dmg.sh
  - Mount and run CedarPyServer.app; this starts only the FastAPI server to verify server startup independent of Qt.

- Gatekeeper quarantine and first run on macOS:
  1) Open the DMG and drag CedarPy.app (or CedarPyServer.app) to /Applications
  2) Remove quarantine attributes so the app can launch its embedded binaries
     macOS Terminal:
     xattr -dr com.apple.quarantine /Applications/CedarPy.app
     xattr -dr com.apple.quarantine /Applications/CedarPyServer.app
  3) Open the app via Finder or:
     open /Applications/CedarPy.app

- Logs and troubleshooting on macOS:
  - App/server logs: ~/Library/Logs/CedarPy
  - Desktop wrapper: cedarqt_*.log
  - Server (from Qt): uvicorn_from_qt.log
  - Doctor logs: doctor_*.log or /tmp/CedarPyDoctor_*.log

- CI builds on every push to main and on tags (v*). On tags, the DMG is attached to the GitHub Release automatically.

## Postmortem: startup failures and fixes

### No-server mode and prior startup issues — postmortem

Symptoms observed
- Earlier experiments with an alternate minimal app path caused confusion and inconsistent packaging. We have removed that path and only support the full app.
- Launching with CEDARPY_NO_SERVER=1 still emitted log lines indicating attempts to import backend frameworks and/or start uvicorn, sometimes followed by failure messages like "Server failed to start on 127.0.0.1:8000".
- Fallback logs also showed "failed to locate main.py in fallback paths" in certain bundles, because only main.py was considered and main_mini.py was not shipped.

Root causes
- The server launcher now only loads main.py (full app).
- The Qt wrapper (cedarqt.py) imported backend frameworks unconditionally at startup, even when the intention was frontend-only mode.
- Packaging standardizes on the full app and required dependencies; no alternate module is shipped.

Fixes implemented
- Module selection: The launcher no longer supports a minimal fallback path; it always loads the full app (main).
- Frontend-only mode: cedarqt.py supports CEDARPY_NO_SERVER to skip backend launch for diagnostics and to verify the Qt shell without starting the server.
- Packaging updates: DMG bundles the full app and UI assets (page.html and optional assets/static).

How to run the different modes
- Frontend-only (no server):
  - CEDARPY_NO_SERVER=1 open /Applications/CedarPy.app
  - Expect: Qt shell shows a static "Cedar (Frontend-only)" page; logs confirm backend was not launched.
- Full backend:
  - Open the app normally to run the standard FastAPI server from main.py.

What to keep in place (do not undo)
- Keep the early CEDARPY_NO_SERVER check for diagnostic-only runs.

How to avoid regressions
- Manual checks before shipping a DMG:
  1) CEDARPY_NO_SERVER=1 open CedarPy.app → should show frontend-only page, with logs confirming no backend import.
  2) Open CedarPy.app normally → full backend runs; homepage renders.
- Keep descriptive startup logs in cedarqt so mode is obvious.

Notes on macOS signing and quarantine
- If you see EXC_CRASH / taskgated rejections (invalid code signature), you may have an ad-hoc signature or a quarantined app. Either:
  - Remove quarantine for your test build: xattr -dr com.apple.quarantine /Applications/CedarPy.app
  - Or sign properly with a Developer ID and hardened runtime, and notarize the app.
- See Packaging (macOS DMG) and related sections above for the local workflow.

Recovery Playbook (documented attempts)
- Attempt A: Full Qt app DMG (CedarPy.dmg) — crashed
  - Symptom: Popup “Server failed to start…”, cedarqt logs initially showed SyntaxError (unterminated string literal). Fix applied: corrected header nav f-string (nav_html). Rebuilt.
  - Then: “No module named fastapi” in bundle when fallback loader imported main. Fix applied: updated cedarpy.spec to include FastAPI/Starlette/SQLAlchemy/uvicorn/websockets/httpx deps. Rebuilt.
  - Then: App still crashed silently on some environments. Moved to isolation.

- Attempt B: Server-only DMG (CedarPyServer.dmg) — backend only, no Qt
  - Purpose: Verify FastAPI server runs cleanly under PyInstaller without Qt. This isolates whether crashes are frontend-related.
  - Build: bash packaging/build_server_dmg.sh
  - Run: Mount DMG, copy CedarPyServer.app to /Applications, remove quarantine, open.
  - Outcome: Use this as a baseline — if this fails, investigate server imports and data dirs under ~/CedarPyData.


- What to record each time:
  - The exact DMG/build used and environment variables.
  - The most recent cedarqt_*.log and any uvicorn_from_qt.log contents.
  - Any SyntaxError/import errors, and the component where we applied fixes.

1) SyntaxError in main.py (unexpected character after line continuation) around projects list HTML
- Mistake: Inline HTML f-string formatting mixed with escaping caused Python to parse an invalid continuation sequence inside the HTML block.
- Fix: Rewrote the HTML string sections to use valid Python f-strings and explicit formatting. For datetime rendering we now use f"{obj.created_at:%Y-%m-%d %H:%M:%S} UTC" and ensured the blocks are triple-quoted without stray continuations.
- Test: Added tests/test_html_rendering.py::test_projects_list_html_formats_datetime to exercise the HTML render path and assert the formatted timestamp appears with UTC.
- Logging: Not applicable beyond standard server logs; the failure was at import time and is now covered by tests.

2) No logs on failure; app seemed to die before writing logs
- Fix: Added a "doctor mode" to run_cedarpy.py that imports the app, boots a server on an ephemeral port, probes readiness, and always writes a diagnostic log to ~/Library/Logs/CedarPy/doctor_*.log (or /tmp fallback).
- Usage:
  CEDARPY_DOCTOR=1 python run_cedarpy.py
- Test: Added tests/test_doctor_mode.py::test_doctor_mode_runs which runs the doctor path and expects a 0 exit code.

3) Desktop wrapper (Qt) could hang due to a stale single-instance lock
- Mistake: On prior versions, the wrapper exited if a lock file existed, even if the PID inside was no longer running.
- Fix: cedarqt.py now checks the PID from the lock, removes the lock if the process is not alive, and retries once. Lock path respects CEDARPY_LOG_DIR. See code comments and the "Single-instance lock and stale lock recovery" section above.
- Test: Added tests/test_qt_stale_lock_recovery.py::test_qt_stale_lock_recovery (skipped on CI) that pre-creates a stale lock, launches cedarqt.py headless, and asserts the log contains "removed stale lock".
- Logging: cedarqt_*.log includes entries like "removed stale lock:" and "acquired single-instance lock:" during startup.

4) Isolating FastAPI vs Qt issues
- Fix: Added a server-only PyInstaller build (packaging/cedarpy_server.spec, packaging/build_server_dmg.sh) to confirm the FastAPI server runs in a packaged context. This helped isolate that the server was fine and the problem was in the Qt wrapper.
- Usage:
  bash packaging/build_server_dmg.sh
  hdiutil attach dist/CedarPyServer.dmg
  open /Volumes/CedarPyServer/CedarPyServer.app

5) macOS Gatekeeper quarantine blocked launches
- Fix/Docs: Documented removing quarantine attributes with xattr -dr com.apple.quarantine for the installed .app before first run.
- Verification: After removing quarantine, the app launched and connected to http://127.0.0.1:PORT.

6) Packaged import SyntaxError (unterminated string literal) in main.py (header nav)
- Symptom: App shows “Server failed to start on 127.0.0.1:8000”. cedarqt_*.log contains lines like:
  - "unterminated string literal (detected at line NNNN) (main.py, line NNNN)"
- Root cause: A malformed header navigation f-string (nav_html) introduced a stray quote in the anchor markup which was embedded in a large triple-quoted block; in the packaged environment this produced a parse error when importing main.py.
- Fix: Corrected the nav_html construction to ensure balanced quotes and safe anchor text. The header nav now derives project context from the header link if nav_query is not provided, and builds links as plain strings without stray quoting.
- Verification: Rebuilt the DMG (packaging/build_macos_dmg.sh), mounted and launched CedarPy.app; logs no longer show the SyntaxError and the server starts.
- How to diagnose quickly if it happens again:
  1) Open ~/Library/Logs/CedarPy and inspect the newest cedarqt_*.log for "unterminated string literal".
  2) If present, inspect the packaged file to locate the offending lines:
     - sed -n '1200,1360p' "/Volumes/CedarPy/CedarPy.app/Contents/Resources/main.py"
  3) Rebuild after fixing quoting issues in nav or inline HTML f-strings.

7) LLM key missing when launching the packaged app (Qt DMG)
- Symptom: The UI shows "LLM unavailable (missing key)" and upload flows log [llm-skip] missing OpenAI API key.
- Root cause: Launching via Finder does not inherit shell exports; the packaged app does not see your terminal's OPENAI_API_KEY. Also, .env placed in the project repo is not read by the packaged app.
- Fix: The app now loads .env from ~/CedarPyData/.env for packaged runs. Place your key there as OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY. We added explicit README docs and code comments to prevent regressions.
- Verification: After creating ~/CedarPyData/.env with the key, restart the app. The header should show "LLM: <model>" instead of "LLM unavailable" and logs will include [llm] lines.
- Quick setup:
  mkdir -p "$HOME/CedarPyData"
  open -e "$HOME/CedarPyData/.env"   # paste: OPENAI_API_KEY={{YOUR_OPENAI_API_KEY}}
- Alternative (less preferred on macOS): use launchctl to set a GUI-wide env var:
  launchctl setenv OPENAI_API_KEY {{YOUR_OPENAI_API_KEY}}
  Note: This persists until unset (launchctl unsetenv OPENAI_API_KEY). Prefer the .env file method above.

8) Project page tabs (Plan / Files / Upload / SQL / Databases) not clickable
- Symptom: Right-pane tab links didn’t switch content; clicking had no effect.
- Root cause: The tab-initialization script (which binds click handlers and toggles .active/.hidden) was present only in an unreachable block and never injected into the page head. Additionally, a missing ">" on a closing </div> in the right pane could break the DOM in some browsers.
- Fix: Injected the tab initialization script in layout() so it ships with every page, and corrected the malformed closing tag. See main.py: layout() (search for "initTabs") and project_page_html() right pane closing tags.
- Verification: Ran tests/test_smoke.py::test_create_and_open_project to confirm render succeeds; manual check confirms tabs toggle panels. If tabs ever stop toggling, open DevTools console and ensure there are no JavaScript syntax errors and that the initTabs() script block exists in the head.

Notes
- Deprecation warnings for datetime.utcnow(): These do not block startup but will be addressed by migrating to timezone-aware datetime.now(timezone.utc) throughout. Some modules already use timezone-aware timestamps.

## Images tab and image agents

What’s new
- Images tab on the project page shows thumbnails of all image files. Clicking a thumbnail opens a thread focused on that image.
- Image Creation Agent: generates images via the OpenAI Images API and saves them under the project files store (structure="images").
- Image Analysis Agent: sends the selected image to GPT Vision, returns a JSON description, and updates the FileEntry AI fields (ai_title, ai_description) and metadata_json. This metadata is always passed in context (via file_id) so the agent knows what to update.

Configuration
- Keys: Set OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY (see earlier sections on .env and key loading). Never hardcode keys.
- Models:
  - CEDARPY_IMAGE_MODEL (default gpt-image-1) for image generation
  - CEDARPY_VISION_MODEL (default gpt-4o-mini) for image analysis

How to use
- Create: In chat, ask to “generate an image …” (e.g., "generate an image of a bar chart comparing X and Y"). The Image Creation Agent will generate and save a PNG and add it to Files/Images.
- Analyze: Open a file (or use the new Images tab), then in chat say “analyze this image” — the Image Analysis Agent will run and update the metadata for that file. You’ll see updated AI Title/Description and a vision section in metadata_json.

Notes and logging
- The agents log their activity with [ImageCreationAgent] and [ImageAnalysisAgent] prefixes. See /log for client logs and the standard server logs under ~/Library/Logs/CedarPy.
- There is no fake output: if keys are missing, the agents report that image operations are unavailable.

Security and keys
- Code paths for Images include comments pointing back to this README section. Do not commit secrets; use the environment/.env guidance above. If running the packaged app, place your key in ~/CedarPyData/.env.

## Next steps (future stages)

- Thread content & LLM runs
- OpenAI API settings & usage
- File conversion & extraction (PDF/JSON/etc.) and richer indexing
- Database attachments UX
- Rich versioning / diffs or git integration

### COMPREHENSIVE_README.md

# Cedar Research Application - Comprehensive Documentation

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture Overview](#architecture-overview)
- [Complete Directory Structure](#complete-directory-structure)
- [LLM-Driven Components](#llm-driven-components)
- [Prompt Engineering & LLM Integration](#prompt-engineering--llm-integration)
- [Code Duplication & Refactoring Opportunities](#code-duplication--refactoring-opportunities)
- [Testing Structure](#testing-structure)
- [Deployment & Packaging](#deployment--packaging)
- [Configuration & Environment](#configuration--environment)

## Project Overview

Cedar Research Application (CedarPy) is a FastAPI-based research and data management platform that heavily leverages Large Language Models (LLMs) for intelligent file processing, code analysis, and interactive chat-based workflows. The application supports project-based organization with branching, file uploads, SQL operations, and AI-powered data analysis.

### Key Features
- Project & Branch Management: Multi-project support with Git-like branching
- LLM-Powered File Processing: Automatic classification, summarization, and extraction
- Interactive Chat Interface: WebSocket-based chat with AI orchestration
- SQL Workspace: Branch-aware SQL execution with undo capabilities
- Code Analysis: Automatic code extraction and analysis from uploaded files
- Shell Integration: Secure shell command execution with streaming output

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Frontend Layer                    │
│  ├── QtWebEngine UI (cedarqt.py)                   │
│  ├── Web UI (HTML/JS in layout functions)          │
│  └── WebSocket Clients                             │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                  FastAPI Application                │
│  ├── main.py (orchestrator entry)                  │
│  ├── main_impl_full.py (core implementation)      │
│  └── web_ui.py (new modular UI entry)             │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│               Core Services & Utilities             │
│  ├── cedar_orchestrator/ (AI coordination)         │
│  ├── cedar_tools/ (Tool implementations)           │
│  ├── cedar_app/utils/ (Business logic)             │
│  └── cedar_app/routes/ (HTTP/WS endpoints)         │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   Data Layer                        │
│  ├── SQLAlchemy Models (main_models.py)            │
│  ├── MySQL/SQLite Databases                        │
│  └── File Storage (project-based)                  │
└─────────────────────────────────────────────────────┘
```

## Frontend Functions & User Flows

### 1. Application Boot Process

**Entry Points**:
- Web Server: python run_cedarpy.py → loads main.py → imports cedar_app/main_impl_full.py
- Desktop App: python cedarqt.py → Qt wrapper → embeds web server
- Production: uvicorn main:app → FastAPI application

**Boot Sequence**:
```python
run_cedarpy.py
├── Initialize logging (_init_logging)
├── Choose port (_choose_listen_port)
├── Kill other instances (_kill_other_instances)
├── Load environment variables
├── Import main:app (FastAPI)
├── Start uvicorn server
└── Open browser (if CEDARPY_OPEN_BROWSER=1)
```

### 2. Home Page & Project List

Route: GET /
- Expected: Should display project list
- Current: Route not defined in main_impl_full.py
- Backup Location: Was in @app.get("/") calling projects_list_html()

Code Flow:
```python
home() → get_registry_db() → query(Project) → projects_list_html() → layout()
```

### 3. Project Creation

Route: POST /projects/create (MISSING!)
- Form Fields: title (required)

Code Flow:
```python
create_project()
├── get_or_create_project_registry() # Idempotent creation
├── _get_project_engine() # Create project DB
├── Base.metadata.create_all() # Initialize schema
├── ensure_main_branch() # Create Main branch
├── _ensure_project_storage() # Create directories
└── RedirectResponse(/project/{id})
```

... (full content from COMPREHENSIVE_README.md continues here as in the source file) ...

### IMAGE_ANALYSIS_SCHEMA.md

# Image Analysis Database Schema

This document defines the structured data format for image analysis results and corresponding database tables.

## Database Tables

### 1. image_metadata
Core metadata and purpose assessment for analyzed images.

```sql
CREATE TABLE IF NOT EXISTS image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE,
    image_type TEXT NOT NULL,  -- 'chart', 'diagram', 'photo', 'screenshot', 'mixed'
    chart_type TEXT,           -- 'line', 'scatter', 'bar', 'histogram', 'heatmap', 'pie', etc.
    title TEXT,
    width INTEGER,
    height INTEGER,
    color_palette TEXT,        -- JSON array of hex colors
    has_annotations BOOLEAN,
    has_legend BOOLEAN,
    has_gridlines BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 2. image_purpose
Assessment of what the image is trying to communicate.

```sql
CREATE TABLE IF NOT EXISTS image_purpose (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    purpose_type TEXT NOT NULL,
    primary_message TEXT NOT NULL,
    audience TEXT,
    context TEXT,
    confidence REAL DEFAULT 0.8,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 3. image_conclusions
Conclusions drawn from the image with supporting reasoning.

```sql
CREATE TABLE IF NOT EXISTS image_conclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    conclusion_text TEXT NOT NULL,
    evidence TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    conclusion_type TEXT,
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 4. chart_axes
Axis information for charts and plots.

```sql
CREATE TABLE IF NOT EXISTS chart_axes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    axis_name TEXT NOT NULL,
    label TEXT,
    units TEXT,
    scale_type TEXT,
    min_value REAL,
    max_value REAL,
    tick_values TEXT,
    gridlines BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 5. chart_series
Data series information for charts.

```sql
CREATE TABLE IF NOT EXISTS chart_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    series_name TEXT NOT NULL,
    legend_label TEXT,
    color TEXT,
    marker_style TEXT,
    line_style TEXT,
    series_type TEXT,
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 6. chart_data_points
Individual data points extracted from charts.

```sql
CREATE TABLE IF NOT EXISTS chart_data_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    series_id INTEGER,
    x_value REAL,
    y_value REAL,
    z_value REAL,
    error_x REAL,
    error_y REAL,
    label TEXT,
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (series_id) REFERENCES chart_series(id) ON DELETE CASCADE
);
```

### 7. image_text
OCR text extraction results.

```sql
CREATE TABLE IF NOT EXISTS image_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    text_type TEXT,
    bbox_x0 INTEGER,
    bbox_y0 INTEGER,
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    confidence REAL DEFAULT 0.9,
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

---

## JSON Output Format

ImageAnalysisAgent should return results in this structured JSON format:

```json
{
  "file_id": 6,
  "metadata": { ... },
  "purpose": { ... },
  "conclusions": [ ... ],
  "axes": [ ... ],
  "series": [ ... ],
  "data_points": [ ... ],
  "text_extractions": [ ... ]
}
```

## Usage Notes
- All fields referencing file_id should use the uploaded file’s ID
- JSON fields stored as TEXT
- Confidence scores in [0.0, 1.0]
- order_index maintains sequence

## Agent Integration
- ImageAnalysisAgent analyzes and returns JSON
- SQLAgent creates tables and inserts rows according to this schema

### CEDAR_AGENT_GUIDE.md

# Cedar Agent Guide

These are the agents available in Cedar and what they do. The ChiefAgent orchestrates everything and may call several agents to achieve a high-confidence answer. If there are supporting files, images, or databases already in your project, prefer agents that can read/write those assets directly.

... (full content from CEDAR_AGENT_GUIDE.md continues here) ...

### PROMPT_MANAGEMENT.md

# Prompt Management System

... (full content from PROMPT_MANAGEMENT.md continues here) ...

### PROMPT_IMPROVEMENT_GUIDE.md

# Cedar Prompt Improvement Guide

... (full content from PROMPT_IMPROVEMENT_GUIDE.md continues here) ...

### ORCHESTRATOR_REFACTORING_PLAN.md

# Orchestrator Refactoring Plan

... (full content from ORCHESTRATOR_REFACTORING_PLAN.md continues here) ...

### ORCHESTRATION_FLOW_ISSUES.md

# Cedar Orchestration Flow - Issues Analysis and Remediation Plan

... (full content from ORCHESTRATION_FLOW_ISSUES.md continues here) ...

### AGENT_FLOW_IMPROVEMENTS.md

# Agent Flow Efficiency Improvements

... (full content from AGENT_FLOW_IMPROVEMENTS.md continues here) ...

### README_CHAT_HISTORY_SQL.md

# Chat History SQL Storage

... (full content from README_CHAT_HISTORY_SQL.md continues here) ...

### README_NOTES_FEATURE.md

# Cedar Notes Feature Documentation

... (full content from README_NOTES_FEATURE.md continues here) ...

### .github/workflows/ci.yml

```yaml
name: CI

# POLICY: No stubs in CI for LLM functionality.
# - We DO NOT set CEDARPY_TEST_MODE here.
# - We DO set CEDARPY_TEST_LLM_READY=1 so LLM-dependent tests run against real APIs using GitHub Secrets.
# - Do NOT re-introduce broad -k filters that drop major suites; only exclude Playwright/Qt where runners lack runtime.
# See README (LLM classification on file upload) for key setup and notes.

on:
  push:
  pull_request:

permissions:
  contents: read

env:
  PYTHONUNBUFFERED: "1"

jobs:
  lint:
    name: Lint (ruff)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dev deps (ruff only)
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
          pip list --format=freeze > pip-freeze-dev.txt

      - name: Environment info
        run: |
          python -V | tee env.txt
          pip -V | tee -a env.txt
          uname -a | tee -a env.txt

      - name: Ruff (lint)
        id: ruff
        shell: bash
        run: |
          echo "::group::ruff check"
          set -o pipefail
          ruff check . | tee ruff-output.txt
          STATUS=${PIPESTATUS[0]}
          echo "::endgroup::"
          if [[ $STATUS -eq 0 ]]; then
            echo "result=pass" >> "$GITHUB_OUTPUT"
          else
            echo "result=fail" >> "$GITHUB_OUTPUT"
            exit $STATUS
          fi

      - name: Upload lint artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: lint-artifacts
          path: |
            ruff-output.txt
            env.txt
            pip-freeze-dev.txt

      - name: Summary
        if: always()
        run: |
          {
            echo "## Lint results"
            echo ""
            echo "| Field | Value |"
            echo "|------:|:------|"
            echo "| Tool | `ruff` |"
            echo "| Result | **${{ steps.ruff.outputs.result || 'n/a' }}** |"
            echo ""
            echo "Artifacts: **lint-artifacts** (ruff-output, env, pip-freeze)"
          } >> "$GITHUB_STEP_SUMMARY"

  compile:
    name: Compile (syntax check)
    runs-on: ubuntu-latest
    needs: [lint]
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install minimal deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip list --format=freeze > pip-freeze.txt

      - name: Compile all
        id: compile
        shell: bash
        run: |
          echo "::group::python -m compileall"
          set -o pipefail
          set +e
          python -m compileall -q . > compile-stdout.txt 2> compile-stderr.txt
          STATUS=$?
          set -e
          echo "::endgroup::"

          if [[ $STATUS -ne 0 ]]; then
            echo "Some files failed to byte-compile. First 200 lines of stderr:"
            sed -n '1,200p' compile-stderr.txt || true
            echo "result=fail" >> "$GITHUB_OUTPUT"
            exit $STATUS
          else
            echo "result=pass" >> "$GITHUB_OUTPUT"
          fi

      - name: Upload compile artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: compile-artifacts
          path: |
            compile-stdout.txt
            compile-stderr.txt
            pip-freeze.txt

      - name: Summary
        if: always()
        run: |
          {
            echo "## Compile results"
            echo ""
            echo "| Field | Value |"
            echo "|------:|:------|"
            echo "| Command | `python -m compileall -q .` |"
            echo "| Result | **${{ steps.compile.outputs.result || 'n/a' }}** |"
            echo ""
            echo "Artifacts: **compile-artifacts** (stdout/stderr, pip-freeze)"
          } >> "$GITHUB_STEP_SUMMARY"

  tests_backend_core:
    name: Tests — backend core (fast, no UI/WS/LLM)
    runs-on: ubuntu-latest
    needs: [compile]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install app + dev deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          pip list --format=freeze > pip-freeze-all.txt

      - name: Verify pytest-cov is available
        run: |
          python -c "import pytest_cov; print('pytest-cov OK')" || { echo "pytest-cov not installed"; exit 1; }

      - name: Show pytest config
        run: |
          pytest --version | tee pytest-info.txt
          python -c "import sys,platform;print(platform.platform());print(sys.version)" | tee -a pytest-info.txt

      - name: Pytest (backend core)
        id: pytest
        env:
          PYTHONPATH: .
        shell: bash
        run: |
          mkdir -p reports coverage htmlcov
          set -o pipefail
          echo "PYTHONPATH=$PYTHONPATH" | tee run-env.txt
          pytest -vv \
            --maxfail=1 \
            --durations=25 \
            --log-cli-level=INFO --log-file=pytest.log \
            --junitxml=reports/junit.xml -o junit_family=xunit2 \
            --cov=cedarpy --cov-report=xml:coverage/coverage.xml --cov-report=term-missing \
            tests/test_smoke.py \
            tests/test_html_rendering.py \
            tests/test_threads_new_json.py \
            tests/test_shell_grep.py \
            tests/test_doctor_mode.py \
            2> pytest-stderr.txt | tee pytest-stdout.txt

      - name: Upload core test artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: core-tests-artifacts
          path: |
            reports/junit.xml
            pytest.log
            pytest-stdout.txt
            pytest-stderr.txt
            pip-freeze-all.txt
            pytest-info.txt

  tests_ws:
    name: Tests — WebSockets + Orchestrator (LLM)
    runs-on: ubuntu-latest
    needs: [compile]
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          pip list --format=freeze > pip-freeze-all.txt
      - name: Pytest (ws + orchestrator)
        env:
          PYTHONPATH: .
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          CEDARPY_OPENAI_API_KEY: ${{ secrets.CEDARPY_OPENAI_API_KEY }}
          CEDARPY_TEST_LLM_READY: "1"
          CEDARPY_CHAT_TIMEOUT_SECONDS: "120"
          CEDARPY_MAX_TURNS: "3"
        shell: bash
        run: |
          mkdir -p reports
          set -o pipefail
          pytest -vv \
            --maxfail=1 \
            --durations=25 \
            --log-cli-level=INFO --log-file=pytest.log \
            --junitxml=reports/junit-ws.xml -o junit_family=xunit2 \
            tests/test_websockets.py \
            tests/test_ws_chat_orchestrator.py \
            2> pytest-stderr.txt | tee pytest-stdout.txt
      - name: Upload ws test artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ws-tests-artifacts
          path: |
            reports/junit-ws.xml
            pytest.log
            pytest-stdout.txt
            pytest-stderr.txt

  tests_playwright:
    name: Tests — Playwright (UI/WS basic)
    runs-on: ubuntu-latest
    needs: [compile]
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - name: Install app deps + Playwright
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          python -m playwright install --with-deps chromium
      - name: Run Playwright tests
        env:
          PYTHONPATH: .
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          CEDARPY_OPENAI_API_KEY: ${{ secrets.CEDARPY_OPENAI_API_KEY }}
          CEDARPY_TEST_LLM_READY: "1"
          CEDARPY_OPEN_BROWSER: "0"
          CEDARPY_CHAT_TIMEOUT_SECONDS: "120"
        run: |
          pytest -vv \
            tests/test_playwright_chat_ack.py \
            tests/test_playwright_chat_submit.py
      - name: Upload UI test artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ui-tests-artifacts
          path: |
            playwright-report
            test-results
          path: |
            pytest-stdout.txt
            pytest-stderr.txt
            pytest.log
            run-env.txt
            pytest-info.txt
            reports/**
            coverage/**
            pip-freeze-all.txt

      - name: Publish JUnit as Check (optional)
        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)
        continue-on-error: true
        uses: mikepenz/action-junit-report@v4
        with:
          report_paths: "reports/junit.xml"
          check_name: "JUnit Test Report (unit)"
          include_passed: true
          detailed_summary: true

      - name: Summary (unit)
        if: always()
        shell: bash
        run: |
          PASSED=$(awk '/ passed/ {for(i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) c+=$i} END{print c+0}' pytest-stdout.txt)
          FAILED=$(awk '/ failed/ {for(i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) c+=$i} END{print c+0}' pytest-stdout.txt)
          SKIPPED=$(awk '/ skipped/ {for(i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) c+=$i} END{print c+0}' pytest-stdout.txt)
          DURATION=$(awk '/collected .* in [0-9.]+s/ {for(i=1;i<=NF;i++) if ($i ~ /^[0-9.]+s$/) d=$i} END{ if (d == "") { print "n/a" } else { sub(/s$/,"", d); print d } }' pytest-stdout.txt)
          HAVE_JUNIT="missing"; [[ -f reports/junit.xml ]] && HAVE_JUNIT="reports/junit.xml"
          HAVE_COV="missing";   [[ -f coverage/coverage.xml ]] && HAVE_COV="coverage/coverage.xml"
          cat <<'MD' >> "$GITHUB_STEP_SUMMARY"
          ## Test results (unit)

          | Metric  | Value |
          |-------: |:----- |
          | Result  | **${{ steps.pytest.outputs.result || 'n/a' }}** |
          MD
          printf "| Passed  | %s |\n" "${PASSED:-0}" >> "$GITHUB_STEP_SUMMARY"
          printf "| Failed  | %s |\n" "${FAILED:-0}" >> "$GITHUB_STEP_SUMMARY"
          printf "| Skipped | %s |\n" "${SKIPPED:-0}" >> "$GITHUB_STEP_SUMMARY"
          printf "| Runtime | %s s |\n\n" "${DURATION:-n/a}" >> "$GITHUB_STEP_SUMMARY"
          {
            echo "- JUnit: \`$HAVE_JUNIT\` (in **test-artifacts-unit**)"
            echo "- Coverage XML: \`$HAVE_COV\` (in **test-artifacts-unit**)"
          } >> "$GITHUB_STEP_SUMMARY"

### .github/workflows/tests.yml

```yaml
name: tests

# Note: This is a quick subset runner. It does NOT replace the main CI.
# POLICY: No LLM stubs here either; use real keys from Secrets if present.

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  workflow_dispatch: {}

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install -U pip
          python -m pip install -r requirements.txt
          python -m playwright install --with-deps chromium
      - name: Run tests (unit subset)
        env:
          PYTHONPATH: .
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          CEDARPY_OPENAI_API_KEY: ${{ secrets.CEDARPY_OPENAI_API_KEY }}
          CEDARPY_TEST_LLM_READY: "1"
          CEDARPY_DATA_DIR: ${{ runner.temp }}/CedarPyData
          CEDARPY_DATABASE_URL: sqlite:///${{ runner.temp }}/CedarPyData/cedarpy-registry.db
        run: |
          mkdir -p "$RUNNER_TEMP/CedarPyData"
          pytest -q -k "not playwright and not ws and not websockets and not qt" --maxfail=1 --disable-warnings --cache-clear
```

### .github/workflows/macos-dmg.yml

```yaml
name: macOS DMG (branch)

on:
  push:
    branches: [ main ]
    paths:
      - '**/*.py'
      - 'requirements.txt'
      - 'packaging/**'
      - '.github/workflows/macos-dmg.yml'
  workflow_dispatch: {}

jobs:
  build:
    runs-on: macos-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install -U pip
          python -m pip install -r requirements.txt
          if [ -f packaging/requirements-macos.txt ]; then
            python -m pip install -r packaging/requirements-macos.txt
          fi
      - name: Build DMG (Qt)
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          CEDARPY_CI_WORKFLOW: CI
        run: |
          bash packaging/build_qt_dmg.sh
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: CedarPy.dmg
          path: packaging/dist-qt/CedarPy-qt.dmg
```

### .github/workflows/macos-dmg-release.yml

```yaml
name: macOS DMG (release)

on:
  push:
    tags: [ 'v*' ]
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  build:
    runs-on: macos-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install -U pip
          python -m pip install -r requirements.txt
          if [ -f packaging/requirements-macos.txt ]; then
            python -m pip install -r packaging/requirements-macos.txt
          fi
      - name: Build DMG (Qt)
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          CEDARPY_CI_WORKFLOW: CI
        run: |
          bash packaging/build_qt_dmg.sh
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: CedarPy.dmg
          path: packaging/dist-qt/CedarPy-qt.dmg

  release:
    needs: build
    runs-on: macos-latest
    permissions:
      contents: write
    steps:
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: CedarPy.dmg
          path: dist
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/CedarPy-qt.dmg
          overwrite: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```
