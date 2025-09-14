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

## Next steps (future stages)

- Thread content & LLM runs
- OpenAI API settings & usage
- File conversion & extraction (PDF/JSON/etc.) and richer indexing
- Database attachments UX
- Rich versioning / diffs or git integration
