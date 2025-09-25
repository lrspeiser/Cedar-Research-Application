# Items To Fix

This document lists missing or inconsistent frontend functions and routes discovered during the audit on 2025-09-25.

## Critical (Routing/UI)

1. Missing Home Route
- Expected: GET /
- Current: Not present in cedar_app/main_impl_full.py
- Backup: Exists in packaged main.py (packaging/build-embedded/.../main.py) and redirects to projects list
- Action: Recreate in routes/main_routes.py or directly in main_impl_full.py to call projects_list_html() and layout()

2. Missing Project Creation Route
- Expected: POST /projects/create
- Current: Not present in cedar_app/main_impl_full.py (present in backup main_impl_full.py.backup4)
- Action: Restore create_project() using get_or_create_project_registry(), initialize project schema, and redirect to /project/{id}

3. SQL Routes Are Stubs
- File: cedar_app/routes/sql_routes.py
- Current: Stub implementations
- Action: Implement ws_sqlx, make_table_branch_aware, undo_last_sql, execute_sql using utils/sql_utils.py and utils/sql_websocket.py

4. Duplicate Orchestrator Paths
- Files: orchestrator.py (root), cedar_app/orchestrator.py, cedar_orchestrator/ws_chat.py
- Impact: Confusion over the canonical WebSocket chat implementation
- Action: Pick cedar_orchestrator/ws_chat.py as canonical, remove or wrap others

## Medium (Duplication/Consistency)

5. Duplicated File Utilities
- Files: cedar_app/file_utils.py vs cedar_app/utils/file_utils.py vs cedar_app/utils/file_management.py vs cedar_app/utils/file_operations.py
- Action: Consolidate into a single module; update imports across codebase

6. WebSocket SQL Handler Paths
- main_impl_full.py registers /ws/sql/{project_id} with handle_sql_websocket, while /ws/sqlx seems referenced elsewhere
- Action: Standardize on a single path (/ws/sql or /ws/sqlx) and update clients/tests

7. Inconsistent Upload Endpoints
- New API: POST /api/upload/process and WS /ws/process-file (file_upload_handler.py)
- Existing UI: POST /project/{id}/files/upload
- Action: Document intended use; either migrate UI to new API or remove new API if unused

8. Two Tool Trees
- Directories: cedar_tools/ and cedar_tools_modules/
- Action: Consolidate to cedar_tools_modules/, deprecate cedar_tools/

## Low (Docs/UX)

9. README vs Implementation
- README mentions root route and projects list, but route missing in current impl
- Action: Keep README aligned or restore routes

10. UI Instrumentation JS Warning
- Warning: SyntaxWarning invalid escape sequence for "+" replacement in JS regex in main_impl_full.py
- Action: Escape string properly or mark as r"" string

11. Legacy Endpoints
- /ws/chat_legacy/{project_id}
- Action: Remove when tests/migrations complete

## Suggested Fix Order
1) Restore GET / and POST /projects/create
2) Implement sql_routes.py using utils/sql_utils.py
3) Consolidate file upload paths (pick one) and update UI
4) Consolidate orchestrator/websocket paths
5) Remove duplicated tool tree
6) Clean up duplicate file utils modules
