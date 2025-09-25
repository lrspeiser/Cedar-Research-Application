# Items To Fix

This document lists missing or inconsistent frontend functions and routes discovered during the audit on 2025-09-25.

## Critical (Routing/UI)

1. ✅ FIXED: Home Route
- Added GET / to main_impl_full.py line 376
- Shows project list with projects_list_html()

2. ✅ FIXED: Project Creation Route  
- Added POST /projects/create to main_impl_full.py line 1346
- Added get_or_create_project_registry() helper at line 1302
- Creates project DB and redirects to /project/{id}

3. ✅ FIXED: SQL Routes Implementation
- Fully implemented in cedar_app/routes/sql_routes.py
- make_table_branch_aware: Adds branch_id column to tables
- undo_last_sql: Reverses last SQL operation using SQLUndoLog
- execute_sql: Executes SQL with proper result handling

4. ✅ RESOLVED: Orchestrator Clarification
- LIVE: cedar_orchestrator/ws_chat.py (registered at main_impl_full.py:343)
- TO REMOVE: orchestrator.py (root), cedar_app/orchestrator.py
- The live one is working correctly via register_ws_chat()

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

9. ✅ FIXED: README vs Implementation
- README mentions root route and projects list, route was missing
- FIXED: Added routes to main_impl_full.py

10. UI Instrumentation JS Warning
- Warning: SyntaxWarning invalid escape sequence for "+" replacement in JS regex in main_impl_full.py
- Action: Escape string properly or mark as r"" string

## Additional Fixes Applied (2025-09-25 13:45)

12. ✅ FIXED: ClientLogEntry Import Missing
- Location: cedar_app/main_impl_full.py line 850
- Issue: ClientLogEntry was used but not imported, causing NameError
- Fix: Added import from cedar_app.utils.logging

13. ✅ FIXED: web_ui.py Missing Routes
- Added GET / route to web_ui.py (though app currently uses main_impl_full.py)
- Updated POST /projects/create in web_ui.py with correct implementation
- Note: App still uses main_impl_full.py; web_ui.py is backup/future migration target

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
