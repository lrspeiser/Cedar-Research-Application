# CedarPy Architecture

This document provides an overview of the CedarPy architecture, a tour of folders and key files, the main data flows, configuration and packaging notes, and a complete “Technologies and Libraries” section describing what we use, why, where, and how to configure each component.

If you are configuring API keys or system-level dependencies, see the README sections referenced throughout (we add explicit pointers so you know exactly where to look).


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
