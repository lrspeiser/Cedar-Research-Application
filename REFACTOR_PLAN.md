# Refactoring Plan for main_impl_full.py

## Current Status
- Original file: ~9000 lines
- Current: ~8199 lines  
- Extracted: ~800 lines
- Target: Break down into manageable modules < 500 lines each

## Completed Modules ✅
1. **cedar_app/config.py** - Configuration and environment management
2. **cedar_app/db_utils.py** - Database utilities and connection management
3. **cedar_app/llm_utils.py** - LLM/OpenAI integration
4. **cedar_app/file_utils.py** - File processing and data import
5. **cedar_app/ui_utils.py** - UI layout and environment helpers
6. **cedar_app/changelog_utils.py** - Changelog and version tracking
7. **cedar_app/api_routes.py** - Settings and misc API routes
8. **cedar_app/shell_utils.py** - Shell execution (created, not integrated)

## Remaining Routes & Functions to Extract

### 1. Shell Routes Integration (~950 lines) ✅ COMPLETE
**Target: Integrated shell_utils.py**
- [x] Shell UI route (lines ~2641-2925)
- [x] Shell API routes (lines ~2926-3108) 
- [x] Shell WebSocket routes (lines ~2965-3108)
- [x] Shell stop/status routes (lines ~3359-3395)
- [x] Remove ShellJob class and related functions
- **Result: Removed 1100+ lines, file now 7894 lines**

### 2. SQL/Database Operations (~600 lines)
**Target: cedar_app/sql_operations.py**
- [ ] SQL WebSocket handlers (/ws/sql, /ws/sqlx) (lines ~3110-3358)
- [ ] SQL execution functions
- [ ] SQL undo operations (line ~4117)
- [ ] Make branch aware route (line ~4009)
- [ ] SQL UI and query execution (line ~4243)

### 3. Project Management Routes (~800 lines)
**Target: cedar_app/project_management.py**
- [ ] Project creation route (line ~5015)
- [ ] Project deletion route (line ~4084)
- [ ] Merge to main route (line ~3823)
- [ ] Branch creation route (line ~5384)
- [ ] Files delete all route (line ~3979)
- [ ] Project page route (line ~5249)

### 4. Thread & Chat Routes (~1500 lines)
**Target: cedar_app/thread_routes.py**
- [ ] Thread list API (line ~4600)
- [ ] Thread session API (line ~4633)
- [ ] Thread creation routes (lines ~5409-5410)
- [ ] Thread page route (line ~5058)
- [ ] Chat routes (lines ~5472, ~5846)
- [ ] Legacy WebSocket chat (line ~6153)
- [ ] Cancel summary route (line ~3742)

### 5. Page Routes (~600 lines)
**Target: cedar_app/page_routes.py**
- [ ] Home page route (line ~4588)
- [ ] Log page route (line ~4668)
- [ ] Changelog page route (line ~4731)
- [ ] Merge page routes (lines ~4870, ~4904)

### 6. File Upload Routes (~300 lines)
**Target: cedar_app/file_upload_routes.py**
- [ ] File upload handler (line ~7889)
- [ ] Related file upload utilities

### 7. Client Logging & Testing (~200 lines)
**Target: cedar_app/client_utils.py**
- [ ] Client log route (line ~3706)
- [ ] Test tool route (line ~3396)
- [ ] Client log storage and management

### 8. Helper Functions (~400 lines)
**Target: cedar_app/helpers.py or existing modules**
- [ ] Branch helpers (ensure_main_branch, branch_filter_ids, current_branch)
- [ ] File type detection (file_extension_to_type)
- [ ] HTML escaping and formatting utilities
- [ ] Miscellaneous utility functions

## Execution Order

### Phase 1: Shell Integration (Current)
1. Update main_impl_full.py to use shell_utils.py
2. Remove duplicate shell code
3. Test shell functionality

### Phase 2: SQL Operations
1. Create sql_operations.py
2. Extract SQL WebSocket handlers and execution
3. Update imports and test

### Phase 3: Project Management
1. Create project_management.py
2. Extract project CRUD operations
3. Test project operations

### Phase 4: Thread & Chat
1. Create thread_routes.py
2. Extract thread and chat functionality
3. Test chat/thread features

### Phase 5: Page Routes
1. Create page_routes.py
2. Extract all HTML page generation routes
3. Test UI pages

### Phase 6: Final Cleanup
1. Extract remaining helpers
2. Clean up imports
3. Final testing

## Success Metrics
- [ ] main_impl_full.py < 1000 lines
- [ ] No module > 500 lines (except special cases)
- [ ] All tests passing
- [ ] Server starts without errors
- [ ] All functionality preserved

## Notes
- Maintain backward compatibility with wrapper functions where needed
- Keep dependencies injected to avoid circular imports
- Test after each phase to ensure nothing breaks
- Commit after each successful extraction