# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

Project at a glance
- Minimal FastAPI + MySQL prototype for managing Projects, Branches, Threads, and Files with roll-up behavior between Main and branches.
- Single-file app: main.py contains configuration, SQLAlchemy models, routes, and inline HTML views. No separate templates or migrations.
- Files uploaded to a branch are visible in that branch and in Main; files uploaded to Main are visible in all branches.

Common commands
- Create the MySQL database (example; adjust as needed):
  ```
  CREATE DATABASE cedarpython CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
  ```
- Install dependencies:
  ```
  pip install -r requirements.txt
  ```
- Configure environment (replace with your actual credentials/host/db):
  ```
  export CEDARPY_MYSQL_URL="mysql+pymysql://<user>:<password>@<host>/<db>"
  # optionally change where uploads are stored (defaults to ./user_uploads):
  export CEDARPY_UPLOAD_DIR="/absolute/path/to/uploads"
  ```
- Run the app (auto-reload for development):
  ```
  uvicorn main:app --reload
  ```
- Quick smoke checks:
  - Open http://127.0.0.1:8000 to see Projects.
  - Create a project via the UI, then create a branch and upload a file; verify visibility matches roll-up rules.

Notes on build/lint/tests
- There is no build step (pure Python app run via uvicorn).
- No linters or formatters are configured in this repo.
- No tests or test runner configuration are present as of this version.

Environment variables
- CEDARPY_DATABASE_URL: SQLAlchemy DSN. Defaults to SQLite at ~/CedarPyData/cedarpy.db if not provided.
- CEDARPY_MYSQL_URL: Legacy variable for MySQL DSN; used if CEDARPY_DATABASE_URL is not set.
- CEDARPY_UPLOAD_DIR: Directory where uploaded files are stored. Defaults to ./user_uploads and is mounted at /uploads by the app for convenience.
- CEDARPY_DATA_DIR: Base directory for default SQLite database location (defaults to ~/CedarPyData).

Architecture overview
- Configuration
  - DATABASE_URL and UPLOAD_DIR are read from env; UPLOAD_DIR is created if missing.
  - StaticFiles mounts UPLOAD_DIR at /uploads so saved files are browsable.
- Database layer (SQLAlchemy; synchronous engine)
  - Base metadata is created at startup via Base.metadata.create_all(engine). No Alembic migrations.
  - Models:
    - Project(id, title, created_at) with one-to-many Branch.
    - Branch(id, project_id, name, is_default, created_at) unique on (project_id, name). ensure_main_branch() guarantees a “Main” branch per project.
    - Thread(id, project_id, branch_id, title, created_at) associated to a branch.
    - FileEntry(id, project_id, branch_id, filename, display_name, file_type, structure, mime_type, size_bytes, storage_path, created_at). Index on (project_id, branch_id).
    - Dataset placeholder model for future “Databases”.
    - Setting key/value store for future configuration (e.g., API keys later).
    - Version(entity_type, entity_id, version_num, data, created_at) with unique (entity_type, entity_id, version_num). add_version() appends a new snapshot on entity changes.
- Branch roll-up logic
  - branch_filter_ids(project_id, selected_branch_id):
    - If viewing Main: include all branches in the project.
    - If viewing a non-Main branch: include [Main, selected].
  - current_branch(project_id, branch_id): resolves to Main when absent/invalid.
- Routes (HTML responses; no JSON API yet)
  - GET /: List projects with a create form.
  - POST /projects/create: Create a project, ensure Main, then redirect to its page.
  - GET /project/{project_id}?branch_id=...: Project dashboard with tabs for branches and tables for Files, Threads, Datasets. Applies roll-up filtering to show items from the appropriate branches.
  - POST /project/{project_id}/branches/create: Create a new branch (validates unique name; “Main” is reserved).
  - POST /project/{project_id}/threads/create?branch_id=...: Create a thread under the resolved branch.
  - POST /project/{project_id}/files/upload?branch_id=...: Save uploaded file to UPLOAD_DIR/project_{id}/branch_{name}/timestamp__filename and create a FileEntry record. Serves back via /uploads.
- HTML rendering
  - Simple inline layout/styles and string-built HTML generators (no templating engine). Links to /uploads for file previews when storage_path is inside UPLOAD_DIR.

Operational considerations
- Database: Defaults to SQLite for out-of-the-box runs. For production-like testing, set a MySQL DSN (utf8mb4_0900_ai_ci recommended).
- Table creation: First run will create all tables automatically. To “reset,” drop the database (SQLite file or MySQL schema) manually.
- Auth/security: None implemented in this stage; app is for local prototype use.

Git
- Default branch: main. Push commits directly to main unless you explicitly choose to work on a branch.
