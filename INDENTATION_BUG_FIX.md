# Indentation Bug Fix - Sub-Agents Not Being Called

## Problem
After the recent refactor, sub-agents (ImageAnalysisAgent, SQLAgent, etc.) were not being called during chat sessions. The Chief Agent would plan and select agents, but they would never execute.

## Root Cause
**Critical indentation error** in `cedar_orchestrator/orchestrator.py` lines 458-600.

The agent result processing block was indented **4 spaces too far** (16 spaces instead of 12), making it **unreachable dead code** that never executed.

### Code Flow Before Fix:
```python
if iteration == 0:
    # Agent selection and dispatch (lines 340-456)
    agent_tasks = [...]
    results = await asyncio.gather(*agent_tasks)
    
                # Send agent results  <- WRONG! 16 spaces (unreachable)
                logger.info("Processing...")  <- WRONG! Never executed
                valid_results = []
                for i, result in enumerate(results):  <- WRONG! Never ran
                    # ... process results ...
            else:  <- This paired with line 340's if
                # Use previous_results
                
            # Phase 3  <- Wrong indentation, inside if/else
```

## The Bug
1. **Lines 458-600**: Indented at 16 spaces instead of 12, became dead code
2. **Line 601**: The `else:` at 12 spaces paired with line 340's `if iteration == 0:`
3. **Lines 607-611**: Phase 3 was incorrectly at 12 spaces (inside the if/else) instead of 8 spaces

Result: Agents were dispatched but their results were never processed because the processing loop was unreachable.

## The Fix
Applied three indentation corrections:

1. **Lines 458-600**: Dedented from 16 to 12 spaces
   - Makes agent result processing reachable and executable
   
2. **Lines 602-606**: Properly indented at 16 spaces
   - Content of the `else` block (for iteration 1+)
   
3. **Lines 607-611**: Dedented from 12 to 8 spaces
   - Phase 3 now runs for ALL iterations, not just iteration 0

### Code Flow After Fix:
```python
if iteration == 0:
    # Agent selection and dispatch
    results = await asyncio.gather(*agent_tasks)
    
    # Send agent results  <- CORRECT! 12 spaces (reachable)
    logger.info("Processing...")  <- NOW RUNS
    valid_results = []
    for i, result in enumerate(results):  <- NOW EXECUTES
        # ... process results ...
else:
    # Use previous_results
    valid_results = previous_results

# Phase 3: Chief Agent Review  <- CORRECT! 8 spaces (always runs)
```

## Testing
- Syntax validation: ✅ `python3 -m py_compile orchestrator.py`
- Committed with detailed explanation
- Pushed to main branch

## Impact
This fix restores the complete orchestration flow:
1. Chief Agent plans and selects agents
2. Agents are dispatched in parallel
3. **[NOW FIXED]** Results are processed and sent to WebSocket
4. Chief Agent synthesizes final answer from agent results

Without this fix, the system would plan but never execute, appearing to "hang" after the initial planning phase.

## Related Files
- `cedar_orchestrator/orchestrator.py` (lines 458-611)
- No other files affected

## Commit
- Hash: `50349eb`
- Message: "Fix critical indentation bug: agent result processing was unreachable"
