# Refactoring Plan: advanced_orchestrator.py

## Current Structure (2,566 lines)
The file contains:
1. **Agent Classes** (ShellAgent, CodeAgent, SQLAgent, MathAgent, ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FileAgent)
2. **Chief Agent** (decision-making orchestrator)
3. **ThinkerOrchestrator** (main orchestrator class)
4. **AgentResult** dataclass and utilities

## Proposed 3-File Structure

### 1. `execution_agents.py` (~850 lines)
**Purpose:** Core agents that execute concrete actions (shell, code, SQL)

```python
# Contents:
- AgentResult dataclass
- ShellAgent class (lines 70-396)
- CodeAgent class (lines 397-610)
- SQLAgent class (lines 611-764)
```

**Why these together:** These are the primary execution agents that actually run commands, code, and queries. They share similar patterns and are often used together.

### 2. `specialized_agents.py` (~750 lines)
**Purpose:** Domain-specific agents for specialized tasks

```python
# Contents:
- MathAgent class (lines 766-853)
- ResearchAgent class (lines 854-947)
- StrategyAgent class (lines 948-1040)
- DataAgent class (lines 1041-1158)
- NotesAgent class (lines 1159-1387)
- FileAgent class (lines 1388-1487)
```

**Why these together:** These agents handle specific domain tasks and are typically called selectively based on query type.

### 3. `orchestrator.py` (~966 lines)
**Purpose:** Main orchestration logic and decision-making

```python
# Contents:
- Import statements and configuration (lines 1-55)
- ChiefAgent class (lines 1488-1913)
- ThinkerOrchestrator class (lines 1914-2566)
- Export statements
```

**Why this structure:** The orchestrator and chief agent work closely together to coordinate all other agents.

## Benefits of This Refactoring

1. **Better Separation of Concerns**
   - Execution agents handle concrete actions
   - Specialized agents handle domain-specific logic
   - Orchestrator handles coordination and decision-making

2. **Improved Maintainability**
   - Each file is ~750-950 lines (manageable size)
   - Related functionality is grouped together
   - Easier to locate specific agent implementations

3. **Cleaner Testing**
   - Can test execution agents independently
   - Can mock specialized agents for orchestrator tests
   - Easier to unit test individual components

4. **Better Import Management**
   - Clear dependencies between modules
   - Reduced circular import risks
   - More explicit about what each module provides

## Implementation Steps

1. **Create new files:**
   - `execution_agents.py`
   - `specialized_agents.py`
   - Keep `advanced_orchestrator.py` but rename to `orchestrator.py` after

2. **Move code sections:**
   - Extract agent classes to respective files
   - Update imports in each file
   - Ensure all dependencies are properly imported

3. **Update imports in orchestrator:**
   ```python
   from .execution_agents import AgentResult, ShellAgent, CodeAgent, SQLAgent
   from .specialized_agents import MathAgent, ResearchAgent, StrategyAgent, DataAgent, NotesAgent, FileAgent
   ```

4. **Update external imports:**
   - Find all files importing from `advanced_orchestrator`
   - Update to import from appropriate new modules

5. **Test thoroughly:**
   - Run existing tests to ensure nothing breaks
   - Test WebSocket connections
   - Verify all agents still function properly

## Alternative Structure (if preferred)

### Option B: By Responsibility
1. `agent_implementations.py` - All 9 agent classes
2. `chief_agent.py` - Chief Agent decision maker
3. `orchestrator_core.py` - ThinkerOrchestrator and utilities

### Option C: By Complexity
1. `simple_agents.py` - ShellAgent, SQLAgent, FileAgent
2. `llm_agents.py` - CodeAgent, MathAgent, ResearchAgent, StrategyAgent, DataAgent, NotesAgent
3. `orchestrator_core.py` - ChiefAgent and ThinkerOrchestrator

## Recommendation
Go with the first option (execution/specialized/orchestrator) as it provides the best balance of:
- Logical grouping
- File size management
- Clear separation of concerns
- Maintainability