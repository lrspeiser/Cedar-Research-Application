# Cedar Codebase Refactoring Plan

## Current State Analysis

### Line Count Distribution (Top Files)
```
2,740 lines - cedar_orchestrator/advanced_orchestrator.py (CRITICAL - needs immediate refactoring)
2,655 lines - cedar_app/main_impl_full_refactored.py
1,934 lines - cedar_app/utils/page_rendering.py
1,841 lines - cedar_app/web_ui.py
1,625 lines - main.py
```

## Detailed Analysis: advanced_orchestrator.py (2,740 lines)

### Current Structure
The file contains 14 agent classes + 2 orchestrator classes all in one massive file:

1. **AgentResult** (Data class)
2. **ShellAgent** (~340 lines)
3. **CodeAgent** (~200 lines)
4. **ReasoningAgent** (~100 lines)
5. **SQLAgent** (~150 lines)
6. **GeneralAgent** (~90 lines)
7. **MathAgent** (~140 lines)
8. **ResearchAgent** (~95 lines)
9. **StrategyAgent** (~95 lines)
10. **DataAgent** (~120 lines)
11. **FileAgent** (~230 lines)
12. **NotesAgent** (~170 lines)
13. **ChiefAgent** (~430 lines)
14. **ThinkerOrchestrator** (~630 lines)

## Refactoring Strategy for advanced_orchestrator.py

### Phase 1: Split into Logical Modules (Target: All files < 1000 lines)

```
cedar_orchestrator/
├── __init__.py                    # Public API exports
├── base/
│   ├── __init__.py
│   ├── agent_result.py            # ~50 lines - AgentResult class
│   └── base_agent.py              # ~100 lines - Abstract base class for all agents
│
├── agents/
│   ├── __init__.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── shell_agent.py         # ~340 lines - ShellAgent
│   │   ├── code_agent.py          # ~200 lines - CodeAgent
│   │   └── sql_agent.py           # ~150 lines - SQLAgent
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── reasoning_agent.py     # ~100 lines - ReasoningAgent
│   │   ├── math_agent.py          # ~140 lines - MathAgent
│   │   └── data_agent.py          # ~120 lines - DataAgent
│   │
│   ├── research/
│   │   ├── __init__.py
│   │   ├── research_agent.py      # ~95 lines - ResearchAgent
│   │   ├── strategy_agent.py      # ~95 lines - StrategyAgent
│   │   └── general_agent.py       # ~90 lines - GeneralAgent
│   │
│   └── content/
│       ├── __init__.py
│       ├── file_agent.py          # ~230 lines - FileAgent
│       └── notes_agent.py         # ~170 lines - NotesAgent
│
├── orchestration/
│   ├── __init__.py
│   ├── chief_agent.py             # ~430 lines - ChiefAgent decision making
│   └── thinker_orchestrator.py    # ~630 lines - Main orchestrator
│
└── utils/
    ├── __init__.py
    ├── constants.py                # ~50 lines - Shared constants
    └── helpers.py                  # ~100 lines - Utility functions
```

### Benefits of This Structure

1. **Logical Grouping**: Agents are grouped by their primary function
2. **All Files < 400 Lines**: Most agent files will be 100-350 lines
3. **Easy Navigation**: Clear hierarchy makes finding code simple
4. **Independent Testing**: Each agent can be tested in isolation
5. **Reduced Merge Conflicts**: Multiple developers can work on different agents
6. **Clear Dependencies**: Import structure shows dependencies explicitly

## Refactoring Plan for Other Large Files

### 2. main.py (1,625 lines)

**Split into:**
```
main.py                          # ~200 lines - FastAPI app initialization only
routes/
├── projects.py                  # ~300 lines - Project CRUD routes
├── threads.py                   # ~250 lines - Thread management routes
├── files.py                     # ~200 lines - File upload/management
├── branches.py                  # ~150 lines - Branch operations
├── websocket.py                 # ~200 lines - WebSocket endpoints
└── api.py                       # ~325 lines - REST API endpoints
```

### 3. page_rendering.py (1,934 lines)

**Split into:**
```
cedar_app/utils/rendering/
├── __init__.py
├── base_renderer.py             # ~150 lines - Base rendering functions
├── project_renderer.py          # ~400 lines - Project page rendering
├── chat_renderer.py             # ~500 lines - Chat UI rendering
├── file_renderer.py             # ~300 lines - File display rendering
├── database_renderer.py         # ~250 lines - Database tab rendering
├── notes_renderer.py            # ~200 lines - Notes tab rendering
└── javascript_renderer.py       # ~400 lines - Client-side JS generation
```

### 4. web_ui.py (1,841 lines)

**Split into:**
```
cedar_app/web/
├── __init__.py
├── layouts.py                   # ~200 lines - Page layouts
├── components.py                # ~300 lines - Reusable UI components
├── forms.py                     # ~250 lines - Form builders
├── tables.py                    # ~200 lines - Table generators
├── modals.py                    # ~150 lines - Modal dialogs
├── chat_ui.py                   # ~400 lines - Chat interface
└── project_ui.py                # ~341 lines - Project interface
```

## Implementation Strategy

### Phase 1: Refactor advanced_orchestrator.py (Week 1)
1. Create new directory structure
2. Extract AgentResult to base module
3. Create BaseAgent abstract class
4. Move each agent to its own file
5. Update imports in all dependent files
6. Run comprehensive tests

### Phase 2: Refactor main.py (Week 2)
1. Create routes directory
2. Move route handlers to appropriate files
3. Keep only FastAPI app setup in main.py
4. Update all imports
5. Test all endpoints

### Phase 3: Refactor UI Files (Week 3)
1. Split page_rendering.py
2. Split web_ui.py
3. Create reusable component library
4. Update all template references
5. Test UI thoroughly

### Phase 4: Documentation & Testing (Week 4)
1. Document new architecture
2. Create module dependency diagram
3. Write unit tests for each module
4. Create integration test suite
5. Update development guidelines

## Success Metrics

1. **No file > 1000 lines** (target: < 500 lines average)
2. **Clear module boundaries** with well-defined interfaces
3. **Improved test coverage** (target: > 80%)
4. **Faster development** - bugs found and fixed in < 30 minutes
5. **Reduced merge conflicts** - parallel development enabled
6. **Better performance** - lazy loading and optimized imports

## Migration Path

### Step 1: Create Parallel Structure
- Keep old files working while building new structure
- Use feature flags to switch between old and new

### Step 2: Gradual Migration
- Move one agent at a time
- Test thoroughly after each move
- Keep CI/CD passing throughout

### Step 3: Deprecate Old Code
- Mark old code as deprecated
- Update all imports to use new structure
- Remove old files after stabilization period

## File Size Guidelines

### Ideal File Sizes
- **Data Classes**: 50-100 lines
- **Simple Agents**: 100-200 lines
- **Complex Agents**: 200-400 lines
- **Orchestrators**: 400-600 lines
- **Route Handlers**: 200-300 lines
- **UI Components**: 100-300 lines
- **Utilities**: 50-200 lines

### Red Flags
- Any file > 1000 lines needs immediate refactoring
- Any file > 500 lines should be reviewed for splitting
- Any class > 300 lines should be decomposed
- Any function > 50 lines should be refactored

## Next Immediate Steps

1. **Create the new directory structure** for agents
2. **Extract AgentResult and BaseAgent** classes
3. **Move ShellAgent** as the first pilot migration
4. **Update imports and test**
5. **Continue with remaining agents** one by one

This refactoring will transform the codebase from a few massive files into a well-organized collection of focused modules, making bugs easier to find and fix, and enabling multiple developers to work efficiently in parallel.