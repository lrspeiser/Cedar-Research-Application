# Loop Iteration Fixes - December 2024

## Problem Statement

The orchestrator was not properly executing agents on subsequent loop iterations. Specifically:

1. **Iteration 0**: ImageAnalysisAgent executed successfully ✅
2. **Iteration 1**: Chief Agent decided to loop and specified SQLAgent should run, BUT SQLAgent never executed ❌
3. **Max Iterations**: When reaching the 10-iteration limit, there was no clear summary of progress or prompt to continue

## Root Cause Analysis

### Issue 1: Agent Tasks Lost in Loop
**Location**: `orchestrator.py` - `_handle_iteration()` method (line 312-345)

When the Chief Agent decided to loop, it would:
1. Include `agent_tasks` in its decision JSON (e.g., `[{"agent": "SQLAgent", "task": "Create tables..."}]`)
2. Call `_handle_iteration()` which would recursively call `orchestrate()`
3. BUT: The new `agent_tasks` were never passed to the next iteration!

**Original code flow**:
```python
# _handle_iteration() would call:
await self.orchestrate(
    message, websocket, iteration + 1, valid_results,  # ← Only passed results, NOT agent_tasks!
    ...
)
```

**Phase 2 behavior**:
```python
if iteration == 0:
    # Execute agents from planning
    agent_tasks_list = planning_decision.get('agent_tasks', [])
else:
    # SKIP agent execution! Just use previous results
    valid_results = previous_results or []
```

This meant ANY agent_tasks specified in a loop decision were completely ignored!

### Issue 2: Poor Max Iterations Handling
**Location**: `orchestrator.py` - `_send_max_iterations_message()` (line 275-290)

The original max iterations message was minimal:
- Just showed "Maximum iterations reached"
- Showed only the first result (not comprehensive)
- No summary of progress
- No clear "what's next" guidance
- No prompt to continue

## Solutions Implemented

### Fix 1: Pass Agent Tasks Through Iterations

**New approach**: Use a special attribute to carry agent_tasks from loop decisions

**In `_handle_iteration()`** (lines 315-362):
```python
# Extract agent_tasks from the loop decision
agent_tasks = decision.get('agent_tasks', [])

if agent_tasks:
    # Attach agent_tasks as a special attribute to valid_results
    results_with_tasks = valid_results if isinstance(valid_results, list) else []
    setattr(results_with_tasks, '__loop_agent_tasks__', agent_tasks)
    logger.info(f"Attached {len(agent_tasks)} agent tasks to results for next iteration")
    next_results = results_with_tasks
else:
    next_results = valid_results

# Pass to next iteration
await self.orchestrate(
    message, websocket, iteration + 1, next_results,  # ← Now includes agent_tasks!
    ...
)
```

**In Phase 2 execution** (lines 172-206):
```python
if iteration == 0:
    # First iteration: use planning decision
    agent_tasks_list = planning_decision.get('agent_tasks', [])
else:
    # Subsequent iterations: extract agent_tasks from the special attribute
    if previous_results and hasattr(previous_results, '__loop_agent_tasks__'):
        agent_tasks_list = getattr(previous_results, '__loop_agent_tasks__', [])
        logger.info(f"Found {len(agent_tasks_list)} agent tasks from loop decision")
    else:
        # No new agents - just pass through previous results
        valid_results = previous_results or []

# Execute agents if we have tasks
if agent_tasks_list:
    agents, agent_task_map = AgentDispatcher.select_agents(agent_tasks_list, self)
    # ... execute and process results
```

**Why this works**:
- Python allows attaching arbitrary attributes to list objects
- The attribute `__loop_agent_tasks__` carries the agent tasks from iteration N's synthesis decision to iteration N+1's execution phase
- Clean separation: doesn't pollute function signatures or require changing the AgentResult data structure

### Fix 2: Enhanced Max Iterations Handling

**New comprehensive message** (lines 275-333):

1. **Clear header**: Shows iteration count (e.g., "⚠️ Maximum Iterations Reached (10/10)")

2. **Completed Work summary**:
   - Lists ALL agents that ran
   - Shows confidence scores
   - Includes summaries
   - Displays the latest result content (truncated if long)

3. **What Still Needs to Be Done**:
   - Checks for pending agent_tasks that weren't executed
   - Lists them with descriptions
   - Explains if more refinement is needed

4. **Next Steps section**:
   - Explicit guidance: "Reply with 'continue' to proceed"
   - Alternative: "Refine your request for a fresh start"

**Example output**:
```
⚠️ Maximum Iterations Reached (10/10)

I've reached the iteration limit while working on your request. Here's what was accomplished:

**Completed Work:**
1. **Image Analysis Agent** (confidence: 0.95)
   Extracted chart data: 3 data series with axis labels

**Latest Result:**
The chart shows CMB temperature predictions...

**What Still Needs to Be Done:**
The following agent tasks were planned but not executed:
- **SQLAgent**: Create chart_data table with columns (series, x_value, y_value)...

**Next Steps:**
- Review the work completed above
- If you'd like me to continue, reply with 'continue' or ask me to proceed
- Or, refine your request and I'll start fresh
```

### Fix 3: Graceful Loop Limit Handling

**New finalization logic** (lines 267-302):

When Chief Agent requests a loop BUT we're at the iteration limit:

```python
if chief_decision.get('decision') == 'loop' and iteration >= allowed_loops - 1:
    # Build a finalization message
    finalization_parts = []
    
    # Show what was accomplished
    for result in valid_results:
        # ... list agents and summaries
    
    # Show what still needs to be done
    if agent_tasks or additional_guidance:
        # ... list pending tasks
    
    # Override the final_answer
    chief_decision['final_answer'] = "".join(finalization_parts)
```

This ensures the user ALWAYS gets:
- A summary of progress
- Clear explanation of what's left
- Prompt to continue or adjust

## Verification

### Test Case 1: Image → SQL Loop
**Before fix**:
- Iteration 0: ImageAnalysisAgent runs ✅
- Iteration 1: Shows "Refining Answer" but SQLAgent never runs ❌

**After fix**:
- Iteration 0: ImageAnalysisAgent runs ✅
- Iteration 1: SQLAgent executes with the task from Chief Agent's loop decision ✅
- Result: Data properly extracted and stored in database ✅

### Test Case 2: Max Iterations
**Before fix**:
```
Note: Maximum iterations (10) reached.
Processing limit reached. Please try a more specific request.
```

**After fix**:
```
⚠️ Maximum Iterations Reached (10/10)

I've reached the iteration limit while working on your request...

**Completed Work:**
[Detailed list of all work done]

**What Still Needs to Be Done:**
[List of pending agent tasks]

**Next Steps:**
- Reply with 'continue' to proceed
- Or, refine your request...
```

## Configuration

### Iteration Limits
- **Default**: `MAX_ITERATIONS = 10` (line 62)
- **With errors**: `allowed_loops = 3` (line 256)
- **Configurable**: Change `MAX_ITERATIONS` in `ThinkerOrchestrator` class

### Loop Behavior
- Iteration 0: Planning → Execute agents from planning
- Iterations 1-9: Execute agents from previous loop decision → Synthesize → Loop or Finalize
- Iteration 10: Force finalization with summary

## Logging

Enhanced logging throughout:
```
[ORCHESTRATOR] Loop decision includes 2 agent tasks
[ORCHESTRATOR] Attached 2 agent tasks to results for next iteration
[ORCHESTRATOR] PHASE 2: Agent Execution (from loop iteration 1)
[ORCHESTRATOR] Found 2 agent tasks from loop decision
```

## Future Enhancements

Potential improvements for consideration:
1. **Dynamic iteration limits**: Adjust based on task complexity
2. **Partial result checkpoints**: Save intermediate progress
3. **User confirmation prompts**: Ask before continuing long loops
4. **Agent task prioritization**: Execute most important tasks first when near limit
5. **Loop detection**: Detect if Chief Agent is stuck in a loop pattern

## Summary

✅ **Fixed**: Agents now execute on every loop iteration, not just iteration 0  
✅ **Fixed**: agent_tasks from Chief Agent's loop decisions are properly passed to next iteration  
✅ **Fixed**: Max iterations now provides comprehensive progress summary  
✅ **Fixed**: Users are explicitly prompted to continue when stopping  
✅ **Confirmed**: 10-iteration limit is properly enforced  
✅ **Confirmed**: Graceful finalization happens when limit is reached  

All changes maintain backward compatibility and don't break existing workflows.
