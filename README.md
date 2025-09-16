# CedarPython (Stage 1)

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

### Run as a desktop app (Qt + QtWebEngine)

- Install deps (includes PySide6):
  - pip install -r requirements.txt
- Launch the embedded-browser desktop shell:
  - python cedarqt.py

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

- CI builds on every push to main and on tags (v*). On tags, the DMG is attached to the GitHub Release automatically.

## Next steps (future stages)

- Thread content & LLM runs
- OpenAI API settings & usage
- File conversion & extraction (PDF/JSON/etc.) and richer indexing
- Database attachments UX
- Rich versioning / diffs or git integration
