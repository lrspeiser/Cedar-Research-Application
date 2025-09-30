# Orchestrator Refactoring Plan

## Current State
- **File**: `cedar_orchestrator/orchestrator.py`
- **Lines**: 1696 lines
- **Classes**: 2 main classes (ChiefAgent, ThinkerOrchestrator)
- **Problem**: Too long, hard to maintain, difficult to navigate

## Proposed Structure

```
cedar_orchestrator/
├── __init__.py                    # Main exports
├── orchestrator.py                # Simplified main orchestrator (300-400 lines)
├── chief_agent.py                 # ChiefAgent class (~700 lines)
├── agent_coordination.py          # Agent selection & dispatch logic (~400 lines)
├── iteration_manager.py           # Iteration & loop control (~200 lines)
├── result_processor.py            # Process & synthesize agent results (~300 lines)
└── prompts/
    ├── __init__.py
    ├── chief_prompts.py           # Chief Agent system prompts
    └── coordination_prompts.py    # Orchestration prompts
```

## Refactoring Steps

### Step 1: Extract ChiefAgent to separate file
**File**: `cedar_orchestrator/chief_agent.py`
**Contains**:
- ChiefAgent class (lines 74-766)
- All Chief Agent decision-making logic
- JSON validation and repair logic
- WebSocket streaming for thinking process

### Step 2: Extract Agent Coordination Logic
**File**: `cedar_orchestrator/agent_coordination.py`
**Contains**:
- Agent selection logic (currently in ThinkerOrchestrator.think)
- Agent task mapping
- Parallel agent dispatch logic
- Helper functions like `_add()` for agent queuing

### Step 3: Extract Iteration Management
**File**: `cedar_orchestrator/iteration_manager.py`
**Contains**:
- Iteration counting and limits
- Loop control logic
- Decision on whether to continue or finalize
- Context preservation across iterations

### Step 4: Extract Result Processing
**File**: `cedar_orchestrator/result_processor.py`
**Contains**:
- Agent result validation and formatting
- Error handling for agent failures
- Code artifact persistence
- Result aggregation and synthesis

### Step 5: Extract Prompts
**File**: `cedar_orchestrator/prompts/chief_prompts.py`
**Contains**:
- Chief Agent system prompts
- JSON schema templates
- Few-shot examples

**File**: `cedar_orchestrator/prompts/coordination_prompts.py`
**Contains**:
- Orchestration guidance
- Agent selection criteria
- Confidence strategy prompts

### Step 6: Simplify Main Orchestrator
**File**: `cedar_orchestrator/orchestrator.py` (simplified)
**Contains**:
- ThinkerOrchestrator class (simplified to ~300-400 lines)
- High-level orchestrate() method that delegates to other modules
- Agent initialization
- Main imports and exports

## Benefits

1. **Maintainability**: Each file has a single, clear responsibility
2. **Readability**: Easier to find and understand specific logic
3. **Testing**: Can test each component independently
4. **Collaboration**: Multiple developers can work on different files
5. **Debugging**: Easier to trace issues to specific modules
6. **Reusability**: Components can be reused in different contexts

## Implementation Order

1. ✅ Create new files with extracted code
2. ✅ Update imports in orchestrator.py
3. ✅ Test that everything still works
4. ✅ Update any external imports
5. ✅ Commit with clear documentation

## Backward Compatibility

All external imports will continue to work:
```python
from cedar_orchestrator.orchestrator import ThinkerOrchestrator  # Still works
from cedar_orchestrator import ThinkerOrchestrator               # Still works
```

The refactoring is internal - external APIs remain unchanged.
