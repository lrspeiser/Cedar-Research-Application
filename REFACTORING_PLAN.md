# Refactoring Plan: Split Large Files (<1000 Lines Rule)

## Overview
Three files exceed the 1000-line limit:
1. **cedar_app/utils/page_rendering.py** - 2,467 lines
2. **main.py** - 1,927 lines  
3. **cedar_orchestrator/orchestrator.py** - 1,461 lines

---

## 1. cedar_app/utils/page_rendering.py (2,467 lines → 3 files)

### Current Structure
- **Lines 1-75**: `projects_list_html()` function
- **Lines 84-2467**: Massive `project_page_html()` function with embedded JavaScript

### Proposed Split

#### **File 1: cedar_app/utils/page_rendering.py** (~200 lines)
- Keep `projects_list_html()` 
- Keep high-level `project_page_html()` that orchestrates calls to other modules
- Import and call specialized rendering functions

#### **File 2: cedar_app/utils/html_components.py** (~800 lines)
- File list rendering (`_file_detail_panel`, file list HTML)
- Image list rendering (thumbnails, metadata)
- Code list rendering (with base64 encoding)
- Notes panel rendering
- Dataset/database tables
- History panel
- All helper functions for building HTML components

#### **File 3: cedar_app/utils/javascript_bundles.py** (~1400 lines)
- `get_main_chat_script()` - Main WebSocket chat script (lines ~713-2164)
- `get_code_to_chat_script()` - Code interaction script (lines ~2253-2349)
- `get_refresh_notes_script()` - Notes refresh script (lines ~2230-2250)
- `get_page_initialization_script()` - Any other page-level JS

**Rationale**: The massive inline JavaScript is the main culprit. Splitting it into a dedicated module makes the code more maintainable and testable.

---

## 2. main.py (1,927 lines → 4 files)

### Current Structure
Analysis shows ~30+ routes mixed with middleware, event handlers, and utility functions.

### Proposed Split

#### **File 1: main.py** (~400 lines) - Core Application
```python
# Keep only:
- FastAPI app initialization
- Middleware registration  
- Event handlers (@app.on_event)
- Router registration (APIRouter imports)
- Main entry point
```

#### **File 2: cedar_app/routes/project_routes.py** (~600 lines)
```python
# Project CRUD and project-specific operations:
@router.get("/")  # Projects list
@router.post("/projects/create")
@router.get("/project/{project_id}")
@router.post("/project/{project_id}/delete")
@router.post("/project/{project_id}/merge_to_main")
@router.post("/project/{project_id}/files/delete_all")
@router.post("/project/{project_id}/sql/make_branch_aware")
@router.post("/project/{project_id}/sql/undo_last")
@router.get("/project/{project_id}/notes/add")
# File uploads
# Branches
```

#### **File 3: cedar_app/routes/api_routes.py** (~500 lines)
```python
# API endpoints (non-WebSocket):
@router.post("/api/chat/ack")
@router.post("/api/chat/cancel-summary")
@router.post("/api/chat/new")
@router.post("/api/chat/load")
@router.post("/api/model/change")
@router.post("/api/shell/run")
@router.post("/api/client-log")
@router.post("/api/test/tool")
@router.get("/api/threads/list")
@router.get("/api/threads/session/{thread_id}")
@router.get("/api/files/{file_id}/extracted")
```

#### **File 4: cedar_app/routes/websocket_routes.py** (~400 lines)
```python
# WebSocket endpoints:
@router.websocket("/ws/chat/{project_id}")
@router.websocket("/ws/shell/{job_id}")
@router.websocket("/ws/health")
@router.websocket("/ws/sql/{project_id}")
```

#### **File 5: cedar_app/routes/ui_routes.py** (~300 lines)
```python
# UI-specific routes:
@router.get("/settings")
@router.post("/settings/save")
@router.get("/log")
@router.get("/merge")
@router.get("/merge/{project_id}")
@router.get("/changelog")
@router.get("/shell")
@router.get("/uploads/{project_id}/{path:path}")
@router.get("/favicon.ico")
```

**Rationale**: Splitting by route type (project operations, APIs, WebSockets, UI) creates clear separation of concerns. Each router can be independently tested and modified.

---

## 3. cedar_orchestrator/orchestrator.py (1,461 lines → 3 files)

### Current Structure
- **Lines 1-517**: `ChiefAgent` class with `review_and_decide()` method
- **Lines 518-680**: `FileProcessor` class  
- **Lines 681-1461**: `AdvancedOrchestrator` class with `orchestrate()` method

### Proposed Split

#### **File 1: cedar_orchestrator/orchestrator.py** (~300 lines)
```python
# Keep only AdvancedOrchestrator class skeleton:
class AdvancedOrchestrator:
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        # Initialize agents (import from chief_agent, file_processor)
        self.chief_agent = ChiefAgent(llm_client)
        self.file_processor = FileProcessor(api_key)
        
    async def orchestrate(self, message: str, websocket, ...):
        # Main orchestration loop
        # Call self.chief_agent.review_and_decide()
        # Call specialized agent methods from agent modules
```

#### **File 2: cedar_orchestrator/chief_agent.py** (~600 lines)
```python
# Move ChiefAgent class entirely:
class ChiefAgent:
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        ...
    
    async def review_and_decide(self, user_query: str, ...):
        # Full implementation of chief agent logic
        # Decision-making, planning, execution
```

#### **File 3: cedar_orchestrator/file_processor.py** (~400 lines)
```python
# Move FileProcessor class entirely:
class FileProcessor:
    def __init__(self, api_key: str):
        ...
    
    async def process_file(self, file_path: str, ...):
        # File analysis and processing logic
```

#### **Optional File 4: cedar_orchestrator/agent_registry.py** (~200 lines)
```python
# If you extract agent registration logic:
def build_agent_registry(llm_client) -> Dict[str, Agent]:
    # Create and return all specialized agents
    # (data_analyst, visualization, database_admin, etc.)
    pass
```

**Rationale**: Each class is already conceptually independent. The orchestrator becomes a coordinator that delegates to specialized classes. This also makes unit testing much easier.

---

## Implementation Order

### Phase 1: Low Risk (JavaScript extraction)
1. **cedar_app/utils/javascript_bundles.py** - Extract JS from page_rendering.py
2. **cedar_app/utils/html_components.py** - Extract HTML builders from page_rendering.py
3. Update `page_rendering.py` to import and use the new modules
4. **Test**: Verify pages render correctly

### Phase 2: Medium Risk (Route splitting)
1. Create router structure: `cedar_app/routes/__init__.py`
2. **cedar_app/routes/ui_routes.py** - Extract UI routes (lowest coupling)
3. **cedar_app/routes/api_routes.py** - Extract API routes
4. **cedar_app/routes/websocket_routes.py** - Extract WebSocket routes
5. **cedar_app/routes/project_routes.py** - Extract project routes
6. Update `main.py` to register routers
7. **Test**: Run full integration tests

### Phase 3: Medium Risk (Orchestrator splitting)
1. **cedar_orchestrator/file_processor.py** - Extract FileProcessor class
2. **cedar_orchestrator/chief_agent.py** - Extract ChiefAgent class  
3. **cedar_orchestrator/agent_registry.py** - Extract agent registration (optional)
4. Update `orchestrator.py` to import classes
5. **Test**: Run chat/orchestration tests

---

## Testing Strategy

### After Each Phase:
1. **Run existing tests**: `pytest tests/`
2. **Manual smoke test**: 
   - Upload a file
   - Start a chat
   - Check all tabs (Files, Images, Code, History, Notes)
3. **Check for import errors**: `python -m py_compile <file>`

### Validation Checklist:
- [ ] All imports resolve correctly
- [ ] No circular dependencies
- [ ] Functions maintain same signatures
- [ ] WebSocket connections work
- [ ] Static file serving works
- [ ] All routes respond correctly

---

## File Size Targets

| File | Current | Target | Status |
|------|---------|--------|--------|
| page_rendering.py | 2,467 | <800 | ✅ After Phase 1 |
| main.py | 1,927 | <400 | ✅ After Phase 2 |
| orchestrator.py | 1,461 | <300 | ✅ After Phase 3 |
| html_components.py | 0 | ~800 | New file |
| javascript_bundles.py | 0 | ~1,400 | New file (JS is verbose) |
| project_routes.py | 0 | ~600 | New file |
| api_routes.py | 0 | ~500 | New file |
| websocket_routes.py | 0 | ~400 | New file |
| ui_routes.py | 0 | ~300 | New file |
| chief_agent.py | 0 | ~600 | New file |
| file_processor.py | 0 | ~400 | New file |

**Note**: `javascript_bundles.py` may be ~1,400 lines but this is acceptable because:
1. It's pure data (JS strings), not logic
2. Each function returns a self-contained script
3. Easy to split further if needed (one file per script)
4. Alternative: Consider moving to `.js` files served statically

---

## Additional Recommendations

### After Refactoring:
1. **Add __init__.py files** to new route directories with clear documentation
2. **Create README.md** in each new directory explaining the module's purpose
3. **Update import paths** in all affected files
4. **Run linter**: `ruff check cedar_app/ cedar_orchestrator/`
5. **Consider**: Moving inline JavaScript to static `.js` files for better IDE support

### Long-term:
- Consider splitting `javascript_bundles.py` into actual `.js` files in `cedar_app/static/js/`
- This would enable:
  - Better syntax highlighting
  - JavaScript linting (ESLint)
  - Minification in production
  - Browser caching
---

## ⚠️ IMPORTANT: Phase 1 Implementation Notes

Phase 1 extraction is complex due to the large JavaScript codebase (~1,400 lines). Here's a safer approach:

### Step-by-Step Phase 1 Execution:

1. **Create stub modules first** (to avoid breaking imports)
2. **Extract one script at a time** (smallest to largest)
3. **Test after each extraction**

### Detailed Steps:

#### Step 1: Create Empty Modules
```bash
touch cedar_app/utils/javascript_bundles.py
touch cedar_app/utils/html_components.py
```

#### Step 2: Extract refresh_notes_script (smallest, ~20 lines)
- Move lines 2129-2149 from page_rendering.py to javascript_bundles.py
- Create function: `get_refresh_notes_script() -> str`
- Test: Verify notes tab switching works

#### Step 3: Extract code_to_chat_js (~100 lines)
- Move lines 2152-2249 from page_rendering.py to javascript_bundles.py  
- Create function: `get_code_to_chat_script(project_id: int, branch_id: int) -> str`
- Test: Verify code click-to-chat works

#### Step 4: Extract main script_js (~1,350 lines) **- Most Complex**
- Move lines 713-2064 from page_rendering.py to javascript_bundles.py
- Create function: `get_main_chat_script(project: Project, current: Branch, selected_file, selected_thread, selected_dataset, file_details_json_text: Optional[str]) -> str`
- Handle all placeholder replacements
- Test: Verify WebSocket chat works

#### Step 5: Extract HTML Components
- File lists, image grids, code lists, notes panels
- Create individual functions in html_components.py
- Test each component

### Risk Mitigation:

- **Backup first**: `cp cedar_app/utils/page_rendering.py cedar_app/utils/page_rendering.py.backup`
- **Git commits**: Commit after each successful extraction
- **Rollback plan**: Keep backup file until all tests pass

### Alternative: Consider Static JS Files

Instead of Python strings, consider:
```
cedar_app/static/js/main-chat.js
cedar_app/static/js/code-to-chat.js  
cedar_app/static/js/refresh-notes.js
```

Benefits:
- Better IDE support (syntax highlighting, linting)
- Easier to maintain
- Can minify for production
- Browser caching

This would require changing the HTML template to use `<script src="...">` instead of inline scripts.

