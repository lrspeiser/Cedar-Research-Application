# CedarPython (Stage 1)

> Important: This README includes a postmortem of recent startup issues, how they were fixed, and how the app is now set up. It also links to tests we added to prevent regressions.

Minimal FastAPI + MySQL prototype to manage **Projects**, **Branches**, **Threads**, and **Files** with
simple roll-up behavior between Main and branches. Everything is in `main.py` as requested.

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

## Uploads

Uploaded files are saved under `user_uploads/project_{id}/branch_{branchName}/...` (relative to the app working directory by default).  
Override with `CEDARPY_UPLOAD_DIR` if desired.

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

## LLM classification on file upload

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

- We standardize on vanilla ES modules and minimal inline JS for the built-in browser (QtWebEngine, Chromium-based). No SSE is used; all live streams use WebSockets.
- Rationale:
  - Keeps the bundle small and avoids additional frameworks.
  - Works reliably in the embedded runtime and regular browsers.
  - Our current UI is server-rendered HTML plus small JS. This remains the default.
- Future: If we want richer UX, we can layer in a lightweight micro-framework (e.g., preact/lit) as ES modules without a big toolchain, still using WebSockets for live updates.

## Packaging (macOS DMG)

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

### Mini/no-server modes and the packaged FastAPI import error — what happened and the durable fix

Symptoms observed
- Launching the app with CEDARPY_MINI=1 still tried to import FastAPI (from main.py), producing "No module named 'fastapi'" and failing to start the server.
- Launching with CEDARPY_NO_SERVER=1 still emitted log lines indicating attempts to import backend frameworks and/or start uvicorn, sometimes followed by failure messages like "Server failed to start on 127.0.0.1:8000".
- Fallback logs also showed "failed to locate main.py in fallback paths" in certain bundles, because only main.py was considered and main_mini.py was not shipped.

Root causes
- The server launcher only attempted to load main.py; it did not support selecting a different module or falling back to main_mini.py.
- The Qt wrapper (cedarqt.py) imported backend frameworks unconditionally at startup, even when the intention was frontend-only mode.
- Packaging configurations (PyInstaller, py2app, embedded DMG) didn't consistently include main_mini.py, so even when a fallback tried to import it, the file wasn't available inside the bundle.

Fixes implemented
- Module selection: The server launcher supports CEDARPY_APP_MODULE and CEDARPY_MINI.
  - Set CEDARPY_APP_MODULE=main_mini to explicitly select the minimal app module (pure ASGI, no FastAPI).
  - Or set CEDARPY_MINI=1 to auto-select main_mini.
  - Robust file-based fallback now looks for both main.py and main_mini.py across packaged locations.
- Frontend-only mode: cedarqt.py reads CEDARPY_NO_SERVER very early and skips importing backend frameworks when enabled.
  - Startup logs show: "[cedarqt] startup flags: NO_SERVER=1 MINI=... APP_MODULE=..." and "no_server=1: running frontend-only".
  - In this mode, it renders a small static HTML page to verify the Qt shell without starting a backend.
- Packaging updates: All build paths now include main_mini.py so the fallback can always find it.
  - PyInstaller (build_dmg.sh): Adds hidden-import main_mini and add-data main_mini.py.
  - py2app (py2app_setup.py): Includes 'main_mini' and ships the file in data_files.
  - Embedded DMG (build_dmg_embedded.sh): Copies main_mini.py into Resources alongside main.py and run_cedarpy.py.

How to run the different modes
- Frontend-only (no server):
  - CEDARPY_NO_SERVER=1 open /Applications/CedarPy.app
  - Expect: Qt shell shows a static "Cedar (Frontend-only)" page; logs confirm backend was not launched.
- Minimal backend (no FastAPI):
  - CEDARPY_MINI=1 open /Applications/CedarPy.app
  - Expect: The launcher loads main_mini.app (pure ASGI), uvicorn runs, and the minimal page is served.
- Full backend:
  - Open the app without those variables (or set CEDARPY_APP_MODULE=main) to run the standard FastAPI server from main.py.

What to keep in place (do not undo)
- Do not remove the module selection logic in run_cedarpy.py or its fallback that includes main_mini.
- Do not move backend import statements in cedarqt.py above the early CEDARPY_NO_SERVER check.
- Do not remove main_mini.py from packaging scripts (PyInstaller, py2app, embedded DMG). The minimal module is a safety valve whenever FastAPI is not available in the target machine.

How to avoid regressions
- Manual checks before shipping a DMG:
  1) CEDARPY_NO_SERVER=1 open CedarPy.app → should show frontend-only page, with logs confirming no backend import.
  2) CEDARPY_MINI=1 open CedarPy.app → minimal page is served; logs show app module main_mini.
  3) Open CedarPy.app with no env flags → full backend runs; homepage renders.
- Ensure build scripts include main_mini.py and hidden-imports/data as described above.
- Keep the "startup flags" lines in cedarqt logs; they make it obvious which mode is active.

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

- Attempt C: Minimal packaged server inside Qt (CEDARPY_MINI=1)
  - Purpose: Remove most frontend and app logic while keeping Qt wrapper. Adds main_mini.py (serves just “Cedar (Mini)”).
  - How to run: CEDARPY_MINI=1 open /Applications/CedarPy.app
  - If this works: gradually re-enable features (Shell API, project pages, LLM) to find the crashing layer.
  - If this fails: focus on Qt/WebEngine init and bundle layout issues (e.g., Resources path, permissions, sandbox).

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

Notes
- Deprecation warnings for datetime.utcnow(): These do not block startup but will be addressed by migrating to timezone-aware datetime.now(timezone.utc) throughout. Some modules already use timezone-aware timestamps.

## Next steps (future stages)

- Thread content & LLM runs
- OpenAI API settings & usage
- File conversion & extraction (PDF/JSON/etc.) and richer indexing
- Database attachments UX
- Rich versioning / diffs or git integration
