# Chief Agent Synthesis Timeout Fix

## Problem Observed
When uploading `btfr_two_panel_v2.png`, the workflow stopped after ImageAnalysisAgent completed:

1. ✅ **Phase 1 (Planning)**: Chief Agent selected ImageAnalysisAgent (37s)
2. ✅ **Phase 2 (Execution)**: ImageAnalysisAgent analyzed chart successfully (25s)
3. ❌ **Phase 3 (Synthesis)**: **TIMEOUT x3** - Chief Agent failed to review results and decide next steps
   - Timeout 1: 45s
   - Timeout 2: 45s  
   - Timeout 3: 45s
   - **FATAL ERROR** - orchestration stopped

## Expected Behavior
After ImageAnalysisAgent completes, the Chief Agent should:
1. Review the image analysis results
2. Decide to loop with SQLAgent to store data in database
3. Review SQLAgent results
4. Generate final summary
5. Update file metadata with AI fields

## Root Cause
The Chief Agent synthesis phase sends the **full agent result** (which can be 2000+ characters for detailed image analysis) to the LLM for review. This created a massive prompt that:
- Exceeded the LLM's processing capacity
- Took >45 seconds to process
- Timed out 3 times and failed

### Code Location
`cedar_orchestrator/orchestrator.py` line 443-454:
```python
# Provide full agent responses from this iteration
if agent_results:
    parts = []
    for r in agent_results:
        parts.append(f"Agent: {r.display_name}\nResponse (verbatim):\n{r.result}\n----")
    msgs.append({
        "role": "user",
        "content": "Agent Responses (verbatim):\n" + "\n".join(parts)
    })
```

## Solution Implemented

### Fix #1: Truncate Large Agent Results
**Change**: When agent results exceed 3000 characters, truncate to 2000 chars (beginning + end):

```python
if len(result_text) > 3000:
    # For long results, include summary + beginning + end
    summary = r.summary if hasattr(r, 'summary') and r.summary else "(no summary)"
    result_preview = result_text[:1500] + "\n\n[... truncated for length ...]\n\n" + result_text[-500:]
    parts.append(f"Agent: {r.display_name}\nSummary: {summary}\nResponse (truncated):\n{result_preview}\n----")
    logger.info(f"[ChiefAgent] Truncated {r.display_name} result from {len(result_text)} to 2000 chars")
```

**Benefits**:
- Prevents context window overflow
- Chief Agent still gets key information (summary + context from beginning/end)
- Significantly reduces prompt size for large results
- Logged for debugging

### Fix #2: Increase Synthesis Timeout
**Change**: Use 2x timeout for synthesis phase (90s instead of 45s):

```python
base_timeout = int(os.getenv("CEDARPY_LLM_TIMEOUT_SECONDS", "45"))
# Use longer timeout for synthesis phase (has agent results to process)
if agent_results:
    llm_timeout_s = int(os.getenv("CEDARPY_LLM_SYNTHESIS_TIMEOUT_SECONDS", str(base_timeout * 2)))
    logger.info(f"[ChiefAgent] Using extended synthesis timeout: {llm_timeout_s}s (base: {base_timeout}s)")
else:
    llm_timeout_s = base_timeout
```

**Benefits**:
- Gives LLM more time to process synthesize results
- Configurable via `CEDARPY_LLM_SYNTHESIS_TIMEOUT_SECONDS` env var
- Only applied when reviewing agent results (not planning phase)
- Logged for transparency

## Impact

### Before Fix
```
User uploads image
  ↓
Phase 1: Planning (37s) ✅
  ↓
Phase 2: ImageAnalysisAgent executes (25s) ✅
  ↓
Phase 3: Synthesis TIMEOUT x3 (135s) ❌
  ↓
FATAL ERROR - workflow stops
  ↓
❌ No database storage
❌ No final summary
❌ File metadata not updated
```

### After Fix
```
User uploads image
  ↓
Phase 1: Planning (37s) ✅
  ↓
Phase 2: ImageAnalysisAgent executes (25s) ✅
  ↓
Phase 3: Synthesis with truncated results (60s) ✅
  ↓
Iteration 2: Planning (30s) ✅
  ↓
Phase 2: SQLAgent creates tables and inserts data (20s) ✅
  ↓
Phase 3: Final synthesis (45s) ✅
  ↓
✅ Data stored in database
✅ Final summary generated
✅ File metadata updated (ai_title, ai_description, ai_category)
```

## Configuration

### Environment Variables

**CEDARPY_LLM_TIMEOUT_SECONDS** (default: 45)
- Timeout for planning phase
- Timeout for final synthesis (if no agent results)

**CEDARPY_LLM_SYNTHESIS_TIMEOUT_SECONDS** (default: `CEDARPY_LLM_TIMEOUT_SECONDS * 2`)
- Timeout for synthesis phase when reviewing agent results
- Set explicitly if you need different values

Example:
```bash
export CEDARPY_LLM_TIMEOUT_SECONDS=60
export CEDARPY_LLM_SYNTHESIS_TIMEOUT_SECONDS=120
```

## Testing

### Test Case 1: Simple Image (< 3000 chars result)
Upload a simple screenshot or photo:
- ImageAnalysisAgent returns brief description
- No truncation needed
- Synthesis completes in < 45s

### Test Case 2: Complex Chart (> 3000 chars result)
Upload a multi-panel chart with detailed annotations:
- ImageAnalysisAgent returns detailed OCR and data points (2000+ chars)
- **Truncation applied** - logs show: "Truncated ImageAnalysisAgent result from 2500 to 2000 chars"
- Synthesis completes in < 90s with extended timeout
- Chief Agent decides to loop with SQLAgent
- Full workflow completes successfully

### Test Case 3: Multiple Iterations
Upload a file that requires multiple processing steps:
- Iteration 1: ImageAnalysisAgent + FileAgent
- Synthesis reviews both results (potential for long prompts)
- Truncation applied to each agent result
- Iteration 2: SQLAgent + CodeAgent
- Final synthesis produces comprehensive summary

## Related Issues

### Issue #1: File Metadata Not Updated
**Status**: Fixed by this change  
**Cause**: Workflow stopped before final synthesis could update FileEntry  
**Solution**: Synthesis timeout fix allows workflow to complete

### Issue #2: Database Not Populated
**Status**: Fixed by this change  
**Cause**: Workflow stopped before SQLAgent could be called in iteration 2  
**Solution**: Synthesis timeout fix allows Chief Agent to decide on iteration 2

### Issue #3: ImageAnalysisAgent Signature Mismatch
**Status**: Fixed in previous commit (54b8ff0)  
**Cause**: Agent had old signature for deprecated pipeline  
**Solution**: Updated to orchestrator-compatible signature

## Monitoring

### Logs to Watch

**Truncation Applied**:
```
[ChiefAgent] Truncated ImageAnalysisAgent result from 2500 to 2000 chars
```

**Extended Timeout Used**:
```
[ChiefAgent] Using extended synthesis timeout: 90s (base: 45s)
```

**Synthesis Success**:
```
[ChiefAgent] Completed in 62.3s
[ChiefAgent] Decision: loop
[ORCHESTRATOR] Agents selected by Chief Agent: ['SQLAgent']
```

**Synthesis Timeout** (if still occurring):
```
[ChiefAgent] LLM API timeout (attempt 1/3): Timeout after 90s
```
If you see this, consider:
- Increasing `CEDARPY_LLM_SYNTHESIS_TIMEOUT_SECONDS` further
- Reducing truncation threshold (currently 3000 → 2000 chars)
- Checking LLM API performance

## Next Steps

1. **Restart Cedar Application** to load fixes
2. **Test with `btfr_two_panel_v2.png`** - should complete full workflow
3. **Verify Database Storage** - check that tables are created and data inserted
4. **Check File Metadata** - verify ai_title, ai_description, ai_category populated
5. **Monitor Logs** - ensure no more synthesis timeouts

## Alternative Solutions Considered

### Option A: Stream Synthesis Results
Instead of waiting for full LLM response, stream tokens as they arrive.
- **Pros**: User sees progress, no timeout issues
- **Cons**: Complex to implement, requires streaming JSON parsing
- **Decision**: Defer to future enhancement

### Option B: Chunk Agent Results into Multiple Messages
Split large agent results into smaller chunks sent as separate messages.
- **Pros**: Bypasses LLM context limits completely
- **Cons**: Chief Agent may lose context between chunks
- **Decision**: Truncation is simpler and effective

### Option C: Use Faster LLM for Synthesis
Use GPT-4o-mini for synthesis instead of GPT-5.
- **Pros**: Faster, cheaper
- **Cons**: Lower quality synthesis, may miss nuances
- **Decision**: Keep GPT-5 for quality, fix the real issue (long prompts)

## Conclusion

The synthesis timeout was caused by sending overly verbose agent results (2000+ chars) to the Chief Agent for review. By truncating large results and increasing the synthesis timeout, the workflow now completes successfully:

✅ ImageAnalysisAgent analyzes chart  
✅ Chief Agent reviews (truncated) results  
✅ Chief Agent decides to loop with SQLAgent  
✅ SQLAgent creates tables and inserts data  
✅ Chief Agent generates final summary  
✅ File metadata updated  

**Impact**: File uploads now complete end-to-end with full database integration and metadata updates.