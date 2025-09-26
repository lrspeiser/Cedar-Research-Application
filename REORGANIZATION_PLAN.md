# Cedar Codebase Reorganization Plan

Based on the function analysis, here's a comprehensive plan to reorganize and clean up the codebase.

## Summary of Issues Found

1. **Major Duplications**:
   - `cedar_tools/` and `cedar_tools_modules/` directories have identical files
   - `main.py` and `cedar_app/main_impl_full_refactored.py` have many duplicate functions
   - Multiple files define the same functions (30+ duplicate functions across 3+ files)

2. **Files That Are Too Large**:
   - `cedar_orchestrator/advanced_orchestrator.py`: 2,741 lines
   - `cedar_app/main_impl_full_refactored.py`: 2,655 lines  
   - `cedar_app/utils/page_rendering.py`: 1,934 lines
   - `main.py`: 1,790 lines

3. **Poor Organization**:
   - Functions scattered across multiple locations
   - No clear separation of concerns
   - Redundant implementations

## Immediate Actions Required

### 1. Delete Duplicate Modules
**Priority: HIGH**
- Delete `cedar_tools_modules/` entirely - it's a complete duplicate of `cedar_tools/`
- Keep only `cedar_tools/` as the single source of truth

### 2. Remove main_impl_full_refactored.py
**Priority: HIGH**
- This 2,655-line file is mostly duplicate code from `main.py`
- Any unique functions should be moved to appropriate modules
- Delete after extracting unique code

### 3. Consolidate Duplicate Functions
**Priority: HIGH**

Functions that appear 3+ times that need consolidation:
- Logging functions: Move to `cedar_app/utils/logging.py`
- Shell functions: Keep only in `cedar_app/shell_utils.py`
- API endpoints: Keep only in route files
- File operations: Consolidate in `cedar_app/utils/file_operations.py`

## File Splitting Plan

### 1. Split main.py (1,790 lines → ~200 lines)
The main.py should ONLY contain:
- FastAPI app initialization
- Middleware registration
- Route registration
- Server startup code

Move functions to:
- **API Routes** → Already in `cedar_app/routes/` (just need to remove duplicates from main.py)
- **Database operations** → `cedar_app/db_utils.py`
- **WebSocket handlers** → `cedar_app/routes/websocket_routes.py`
- **Project operations** → `cedar_app/utils/project_management.py`
- **HTML rendering** → `cedar_app/utils/page_rendering.py`

### 2. Split advanced_orchestrator.py (2,741 lines → 3-4 files of ~700 lines each)
Split into:
- `cedar_orchestrator/orchestrator_core.py` - Main orchestrator class and core logic
- `cedar_orchestrator/tool_execution.py` - Tool execution logic
- `cedar_orchestrator/message_handling.py` - Message processing and formatting
- `cedar_orchestrator/agent_coordination.py` - Agent selection and coordination

### 3. Split page_rendering.py (1,934 lines → 3 files of ~650 lines each)
Split into:
- `cedar_app/utils/html_components.py` - Reusable HTML components
- `cedar_app/utils/page_templates.py` - Full page templates
- `cedar_app/utils/project_views.py` - Project-specific views

## Module Organization Structure

```
cedarpy/
├── main.py                           # FastAPI app only (~200 lines)
├── main_models.py                    # SQLAlchemy models (keep as is)
├── main_helpers.py                   # Core helpers (keep as is)
│
├── cedar_app/
│   ├── routes/                       # All HTTP routes
│   │   ├── api_routes.py            # General API endpoints
│   │   ├── project_routes.py        # Project management
│   │   ├── file_routes.py           # File handling
│   │   ├── websocket_routes.py      # WebSocket endpoints
│   │   └── ...
│   │
│   ├── utils/                        # Utility modules
│   │   ├── file_operations.py       # All file operations
│   │   ├── project_management.py    # Project CRUD
│   │   ├── logging.py               # Unified logging
│   │   ├── html_components.py       # HTML generation (split from page_rendering)
│   │   ├── page_templates.py        # Page templates (split from page_rendering)
│   │   └── project_views.py         # Project views (split from page_rendering)
│   │
│   └── services/                     # Business logic (new directory)
│       ├── chat_service.py          # Chat functionality
│       ├── database_service.py      # Database operations
│       └── file_service.py          # File processing
│
├── cedar_orchestrator/               # Orchestrator modules
│   ├── orchestrator_core.py         # Core logic (split from advanced_orchestrator)
│   ├── tool_execution.py            # Tool handling (split)
│   ├── message_handling.py          # Message processing (split)
│   └── agent_coordination.py        # Agent logic (split)
│
└── cedar_tools/                      # Tool modules (keep, delete cedar_tools_modules/)
```

## Implementation Steps

### Phase 1: Clean Up Duplicates (Immediate)
1. Delete `cedar_tools_modules/` directory
2. Delete `cedar_app/main_impl_full_refactored.py`
3. Remove the analysis script `analyze_functions.py`
4. Commit these deletions

### Phase 2: Consolidate Functions (Today)
1. Move all duplicate functions to their single canonical location
2. Update imports throughout the codebase
3. Test that everything still works

### Phase 3: Split Large Files (This Week)
1. Split `main.py` - move routes and logic to appropriate modules
2. Split `advanced_orchestrator.py` into logical components
3. Split `page_rendering.py` into smaller view modules

### Phase 4: Create Service Layer (Next Week)
1. Create `cedar_app/services/` directory
2. Move business logic from routes to services
3. Keep routes as thin controllers

## Benefits of This Reorganization

1. **Eliminates all duplicate code** - Single source of truth for each function
2. **Improves maintainability** - Smaller, focused files are easier to understand
3. **Better separation of concerns** - Clear boundaries between layers
4. **Easier testing** - Can test business logic separately from routes
5. **Reduced confusion** - No more wondering which file has the "real" implementation

## Metrics After Reorganization

Expected improvements:
- **File count**: Reduce by ~15 files (removing duplicates)
- **Largest file**: < 800 lines (down from 2,741)
- **Duplicate functions**: 0 (down from 30+)
- **Code reduction**: ~20% less code overall

## Next Steps

1. Review and approve this plan
2. Start with Phase 1 (delete duplicates) - can be done immediately
3. Proceed with Phase 2-4 based on priority and available time

This reorganization will make the codebase much more maintainable and easier to work with.