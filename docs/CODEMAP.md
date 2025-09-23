# CedarPy Code Map (Functions and Usage)

This document summarizes the main functions in the CedarPy codebase, what they do, and whether they are actively used. It also flags likely duplication or legacy paths that may cause confusion when making changes.

Scope
- Included: core Python files in this repo (server, Qt wrapper, utilities, scripts) and the Node relay.
- Excluded: generated/packaged artifacts under dist-*/build-*/packaging/build-embedded/ and test files.

Legend
- Route: FastAPI route handler or WebSocket endpoint
- Helper: internal utility/helper
- Model: SQLAlchemy ORM class
- Qt: GUI helper in the desktop wrapper
- Script: standalone CLI/diagnostic helper
- Node: Node-based SSE relay helper
- Usage status: (Used) certain; (Likely) inferred; (Review) possibly unused/dead; (Dup) potential duplication

---

File: main.py (FastAPI app, server logic)
- _load_dotenv_files(paths): Helper. Loads KEY=VALUE pairs into env. (Used: early config)
- _get_redis(): Helper. Returns cached redis async client if configured. (Used: SSE relay publish)
- _publish_relay_event(obj): Helper. Publish event JSON to Redis Pub/Sub channel cedar:thread:{thread_id}:pub. (Used)
- ensure_project_initialized(project_id): Helper. Creates per-project DB schema, seeds Project/Main. (Used: multiple routes and WS)
- _register_ack(eid, info, timeout_ms=10000): Helper. Tracks UI ACKs, logs [ack-timeout]. (Used by WS/ack flow)
- Models (SQLAlchemy):
  - Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Setting, Version (Used everywhere)
- get_db(): Helper (generator). Central registry Session. (Likely used in older routes; project-scoped routes use per-project sessions.)
- add_version(db, entity_type, entity_id, data): Helper. Append a row-version entry. (Used)
- record_changelog(db, project_id, branch_id, action, input_payload, output_payload): Helper. Persist changelog, optional LLM summary. (Used: chat, tools, cancel summary)
- escape(s): Helper. HTML escape. (Used in rendering)
- ensure_main_branch(db, project_id): Helper. Make sure Main exists, record version. (Used)
- file_extension_to_type(filename): Helper. Extension → canonical type mapping. (Used: uploads, downloads)
- branch_filter_ids(db, project_id, selected_branch_id): Helper. Determines which branch IDs to include for display/rollup. (Used: UI queries, tool helpers)
- current_branch(db, project_id, branch_id): Helper. Resolve effective branch, default Main. (Used)
- app = FastAPI(...)

File: main_models.py (SQLAlchemy ORM models)
- Base and models: Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Setting, Version, ChangelogEntry, SQLUndoLog, Note
- Used across routes, tools, and orchestrators.

File: main_helpers.py (shared helpers)
- _get_redis(), _publish_relay_event(obj)
- _ack_store, _register_ack(eid,...)
- escape(s), add_version(...), ensure_main_branch(...)
- file_extension_to_type(...), branch_filter_ids(...), current_branch(...)
- api_chat_ack(payload): Route POST /api/chat/ack. Marks eid as acked, logs [ack] or [ack-miss]. (Used by UI after each bubble)
- layout(title, body, ...): Helper. Global HTML layout; injects client log script, tabs, header. (Used by page renderers)
- settings_page(msg=None): Route GET /settings. Shows LLM key presence and model. (Used)
- settings_save(openai_key, model): Route POST /settings/save. Writes to ~/CedarPyData/.env. (Used)
- serve_project_upload(project_id, path): Route GET /uploads/{project_id}/{path}. Serves per‑project uploaded files. (Used by UI file links)
- projects_list_html(projects): Helper. Renders the Projects home. (Used)
- project_page_html(...): Helper. Renders Project UI including Chat/All Chats/Plan; injects WS+SSE client JS. (Used)
- Shell subsystem:
  - ShellJob (class): manages shell exec and streaming logs (Used by Shell API/UI)
  - _run_job(job): Helper. Spawns and streams process output to job queue and log file. (Used)
  - start_shell_job(script, shell_path, trace_x, workdir): Helper. Creates+starts job. (Used)
  - get_shell_job(job_id): Helper. Lookup job by id. (Used)
  - require_shell_enabled_and_auth(request, x_api_token): Helper. Feature flag + token security for Shell API. (Used)
  - shell_ui(request): Route GET /shell. Minimal shell UI and WS healthcheck. (Used)
  - api_shell_stop(job_id,...): Route POST /api/shell/stop/{job_id}. (Used)
  - api_shell_status(job_id,...): Route GET /api/shell/status/{job_id}. (Used)
- Test tool API (local only):
  - ToolExecRequest (pydantic)
  - api_test_tool_exec(body, request): Route POST /api/test/tool. Executes tools (db, code, web, download, extract, image, shell, notes, compose, tabular_import) in a constrained/local way. (Used in tests/dev only) (Dup: see WS tool_* below)
- Client logging:
  - _CLIENT_LOG_BUFFER (deque)
  - ClientLogEntry (pydantic)
  - api_client_log(entry, request): Route POST /api/client-log. Receives client console/error logs; prints [client-log] and buffers for /log page. (Used by injected script in layout())
- Cancellation summary:
  - api_chat_cancel_summary(payload): Route POST /api/chat/cancel_summary. Builds a concise LLM summary when a run is cancelled; persists to ThreadMessages + Changelog. (Used by client on cancel)
- Chat form submit (HTTP):
  - ask_orchestrator(project_id,...): Route POST /project/{project_id}/ask. Single‑turn orchestrator (non‑WS) to compute/return final text; persists assistant message + changelog; redirects to thread. (Likely legacy/simple path; WS path is primary)
- Threads & branches:
  - create_branch(project_id, name): Route POST /project/{project_id}/branches/create. (Used)
  - create_thread(project_id, request, title): Routes POST /project/{project_id}/threads/create and GET /project/{project_id}/threads/new. Returns JSON when ?json=1 or redirects. (Used by UI to ensure thread id)
- WebSocket chat streaming orchestrator:
  - _ws_send_safe(ws, text): Helper. Best‑effort WS send guard. (Used)
  - ws_chat_stream(websocket, project_id): WS /ws/chat/{project_id}. Orchestrates plan/execute loop, emits events, requires ACKs, publishes to Redis for SSE relay. (Used)
  - _enqueue(obj, require_ack=False): Inner helper. Adds eid, schedules ack timeout, publishes to Redis (SSE), enqueues WS message. (Used)
  - _send_info(label): Inner helper. Emits info stage events. (Used)
  - Tool executors (inner functions): tool_web, tool_download, tool_extract, tool_image, tool_db, tool_code, tool_shell, tool_notes, tool_compose, tool_tabular_import. (Used by orchestrator)
  - _args_complete_for(fn, args): Determines if a step has enough concrete args to execute immediately. (Used)
  - tools_map: dispatch map for tools. (Used)

Usage assessment (main points)
- Routes are actively used by the UI or tests and are in use.
- WS orchestrator is the primary live path for Chat; the test tool API duplicates tool logic for dev/testing (Dup: tool_* logic; consider refactoring shared helpers).
- LangExtract/FTS schema appears both in main.py migrations and cedar_langextract.py (Dup: schema/triggers definitions – see below).

Potential duplication / legacy
- Tool logic implemented twice:
  - In WS orchestrator (inner functions) and in /api/test/tool (Route). They should either call a shared module-level helper to avoid drift or one should document its dev-only nature.
- LangExtract schema/triggers appear in two places:
  - In main.py within migrations for per‑project DB (doc_chunks, doc_chunks_fts, triggers)
  - In cedar_langextract.ensure_langextract_schema(...)
  - Risk: changing one without the other causes divergence. Prefer centralizing in cedar_langextract.py and have migrations call it.
- ask_orchestrator (HTTP) vs ws_chat_stream (WS): Two chat paths exist. The WS path is the main live experience; HTTP path is likely for simple/legacy flows. Ensure future changes land in WS path first.

---

File: cedarqt.py (Qt desktop wrapper)
- _init_logging(): Helper. Redirects stdout/stderr to ~/Library/Logs/CedarPy/cedarqt_*.log. (Used at startup)
- _pid_is_running(pid): Helper. Check PID liveness. (Used by lock logic)
- _acquire_single_instance_lock(lock_path): Helper. Single-instance guard with stale-lock recovery. (Used)
- RequestLogger (QWebEngineUrlRequestInterceptor): Logs HTTP requests from the embedded browser. (Used)
- LoggingWebPage (QWebEnginePage): Captures console logs and forwards to app log; test hooks for file chooser. (Used)
- _wait_for_server(url, timeout_sec=20): Helper. Polls HTTP server readiness. (Used)
- _find_pids_listening_on(port): Helper. lsof-based process discovery. (Used in preflight cleanup)
- _http_get(url, timeout): Helper. Simple GET. (Used)
- _preflight_cleanup_existing_server(host, desired_port): Helper. Kills stale server on that port if existing. (Used)
- _open_full_disk_access_settings(): Helper. Opens macOS Full Disk Access UI. (Used)
- _maybe_prompt_full_disk_access_once(): Helper. Shows one-time FDA prompt. (Used)
- _choose_listen_port(host, desired): Helper. Choose an available port. (Used)
- main(): Entry point. Starts uvicorn in-process (unless CEDARPY_NO_SERVER=1), builds Qt WebView and window, menu, and shows URL. (Used)

Usage assessment
- All helpers are referenced by main(). This module is active in the packaged app and during dev (python cedarqt.py).

---

File: run_cedarpy.py (CLI server launcher)
- _init_logging(): Helper. Redirects to cedarpy_*.log (server logs). (Used)
- _mask_dsn(url): Helper. Obfuscates DSN credentials in logs. (Used in logs)
- Dynamic import of ASGI app:
  - Loads main or main_mini depending on env; falls back to file-based loader in packaged contexts. (Used)
- _kill_other_instances(): Helper. Attempts to terminate other CedarPy instances. (Likely used by packagers or when run directly)
- _choose_listen_port(host, desired): Helper. Similar to Qt’s variant. (Used)
- Doctor helpers: _doctor_log_paths, _doctor_write, run_doctor(): diagnostics. (Used by doctor mode and CI tests)

Duplication
- _choose_listen_port is also in cedarqt.py. Consider unifying.

---

File: cedar_langextract.py (LangExtract integration)
- ensure_langextract_schema(engine): Create doc_chunks table + FTS + triggers (AI/AD/AU). (Used via project migrations or when called explicitly)
- file_to_text(path, display_name, meta): Convert a file to text (supports multiple types). (Used in ingestion/classification flows)
- chunk_document_insert(engine, file_id, text, max_char_buffer): Chunk text and insert into doc_chunks. (Used when chunking is triggered)
- retrieve_top_chunks(engine, query, file_id=None, limit=20): Run BM25 search over FTS. (Used by retrieval flows)

Duplication
- Schema/triggers duplicate definitions found in main.py migrations. Prefer a single source (this module), and call from migrations.

---

File: relay/relay.js (Node SSE relay)
- start SSE server on http://127.0.0.1:8808
  - /sse/:threadId: Subscribes to Redis channel cedar:thread:{threadId}:pub via ioredis and streams events as SSE data lines.
  - CORS allowed via CEDAR_RELAY_CORS (default "*").

Usage assessment
- (Used) when a local Redis is running and the Node relay started; the frontend EventSource connects and renders bubbles incrementally. If not running, UI falls back to WebSockets.

---

Possible dead/legacy paths to review
- ask_orchestrator (HTTP) may be superseded by ws_chat_stream for the main Chat UX. Keep if needed for minimal runs; otherwise document as legacy and ensure updates go to WS path.
- Triggers/FTS for LangExtract exist both in this file and in core migrations in main.py. Consolidate to avoid drift.
- Tool logic duplication (test route vs WS inner functions). Consider extracting a shared tools module to reduce maintenance risk.
- Two "choose listen port" helpers (run_cedarpy.py, cedarqt.py). Consider a shared utility.

Search coverage notes
- main.py is ~9k lines; function list above groups the most important helpers, routes, and inner tool functions. Additional small helpers not listed here are either inner closures or pure render code.
- We focused on files in active use by the server/app; generated artifacts and dist resources were intentionally ignored.

Next steps
- Decide ownership for LangExtract schema: move all schema logic into cedar_langextract.ensure_langextract_schema() and call that from migrations only.
- Extract tool_* implementations into a shared module (e.g., cedar_tools.py) used by both WS and test routes.
- If ask_orchestrator is kept, add tests to avoid drift with the WS path, or mark as legacy and guide contributors.
- Unify _choose_listen_port and related small utilities into a common module to avoid duplication across CLI/Qt.
