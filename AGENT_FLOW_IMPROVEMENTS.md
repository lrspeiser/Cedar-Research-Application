# Agent Flow Efficiency Improvements

## Current Problem: 6+ Iterations for Simple Image Processing

### Observed Flow (Iteration Count: 6!)
```
Iteration 1: ImageAnalysisAgent extracts ALL chart data ✅
Iteration 2: SQLAgent queries files table (why??) ❌
Iteration 3: SQLAgent queries files table AGAIN ❌
Iteration 4: SQLAgent creates files table & queries ❌
Iteration 5: SQLAgent inspects schema & queries ❌
Iteration 6: SQLAgent still trying to query metadata ❌
Result: Workflow incomplete, no data stored
```

### What SHOULD Happen (2 iterations max)
```
Iteration 1: ImageAnalysisAgent extracts chart data ✅
Iteration 2: SQLAgent inserts extracted data into tables ✅
Result: Complete in 2 iterations, data stored
```

---

## Root Causes

### 1. **Missing File Metadata in Upload Prompt** 🔴 CRITICAL
**Location:** `cedar_orchestrator/ws_chat.py` lines 234-250, 310

**Current Code:**
```python
rec = db_session.query(FileEntry).filter(...).first()
if rec:
    # Sends to UI but NOT to prompt!
    await websocket.send_json({
        "filename": rec.display_name,
        "mime_type": rec.mime_type
    })

# Later, prompt is generated WITHOUT this metadata:
query_to_send = f"""I uploaded a file (file_id: {file_id}). Please process it..."""
# ❌ No filename, no mime_type, no extension!
```

**Problem:** Chief Agent doesn't know the file is an image, so it tries to query the database first!

**Fix:** Include file metadata in the upload prompt:
```python
if rec:
    file_metadata_text = f"""**File Information:**
- Filename: {rec.display_name or rec.name}
- Type: {rec.mime_type} ({rec.file_type})
- Size: {rec.size_bytes:,} bytes
- File ID: {file_id}"""
    
    query_to_send = f"""{file_metadata_text}

I uploaded this {'image' if 'image' in (rec.mime_type or '') else 'file'}. Please process it and integrate into our database system:
..."""
```

**Impact:** Chief Agent will immediately know it's an image and route to ImageAnalysisAgent without SQL queries.

---

### 2. **Overly Generic Upload Prompt** 🟡 HIGH PRIORITY
**Location:** `cedar_orchestrator/ws_chat.py` lines 316-349

**Current:** One giant prompt with instructions for ALL file types (CSV, JSON, Excel, PDF, images, etc.)

**Problem:** 
- Chief Agent gets confused by too many options
- Doesn't know which section applies
- Tries to "figure out" file type first (leading to SQL queries)

**Fix:** Generate **file-type-specific prompts** based on `mime_type`:

```python
if rec:
    mime = (rec.mime_type or "").lower()
    ext = (rec.file_type or "").lower()
    
    if "image" in mime or ext in ["png", "jpg", "jpeg", "gif", "svg"]:
        query_to_send = f"""**Uploaded Image File:**
- Filename: {rec.display_name}
- Type: {mime}
- Size: {rec.size_bytes:,} bytes
- File ID: {file_id}

**Task:** Extract and store chart/image data

**Step 1 (Current):** Use ImageAnalysisAgent to extract:
- Chart type, axes, data points
- OCR text
- Metadata

**Step 2 (Next iteration):** Use SQLAgent to:
- CREATE tables: chart_data, chart_metadata, image_ocr
- INSERT extracted data with file_id as foreign key
- Return confirmation of rows inserted

{db_metadata}

**Start by analyzing the image.**"""

    elif "pdf" in mime or ext == "pdf":
        query_to_send = f"""**Uploaded PDF File:**
- Filename: {rec.display_name}
- Type: {mime}
- File ID: {file_id}

**Task:** Extract PDF content and store in database

**Step 1:** Use PDFExtractionAgent to extract text, tables, images
**Step 2:** Use SQLAgent to create pdf_pages, pdf_tables tables and insert data

{db_metadata}"""

    elif any(x in mime for x in ["csv", "json", "excel"]) or ext in ["csv", "json", "xlsx", "xls"]:
        query_to_send = f"""**Uploaded Structured Data File:**
- Filename: {rec.display_name}
- Type: {mime}
- File ID: {file_id}

**Task:** Parse and load into database

**Step 1:** Use CodeAgent to read file and infer schema
**Step 2:** Use SQLAgent to CREATE TABLE and INSERT rows

{db_metadata}"""
    
    else:
        # Fallback to generic prompt
        query_to_send = f"""..."""
```

**Impact:** Focused, concise prompts → faster planning, correct agent selection.

---

### 3. **Chief Agent Doesn't Trust Agent Results** 🟡 MEDIUM PRIORITY
**Location:** `cedar_orchestrator/orchestrator.py` synthesis phase

**Problem:** After ImageAnalysisAgent extracts data, Chief Agent should immediately proceed to SQLAgent. Instead, it doubts itself and tries to verify file type first.

**Current Synthesis Logic:**
```python
# Agent results: ImageAnalysisAgent successfully extracted chart data
# Chief Agent thinking: "I need to check what file type this is..."
# Decision: Loop with SQLAgent to query files table ❌
```

**Fix:** Add synthesis guidance that trusts agent results:
```python
SYNTHESIS RULES:
1. If ImageAnalysisAgent returned chart data → MUST use SQLAgent next to store it
2. If PDFExtractionAgent returned text/tables → MUST use SQLAgent next to store it
3. If CodeAgent parsed CSV → MUST use SQLAgent next to CREATE/INSERT
4. DO NOT query files table if you already have file metadata
5. DO NOT re-analyze the file - agent results are authoritative
```

**Add to synthesis prompt:**
```python
IMPORTANT AFTER AGENT EXECUTION:
- Agent results are AUTHORITATIVE - do not re-check or re-analyze
- If extraction agent (Image/PDF/Code) succeeded, the ONLY next step is SQLAgent to store data
- DO NOT query files table for metadata you already have
- DO NOT select the same agent twice in a row
```

---

### 4. **No "One-Shot" Agent for Simple Cases** 🟢 NICE TO HAVE

**Proposal:** Create `FileProcessorAgent` that combines analysis + storage in one call:

```python
class FileProcessorAgent:
    """All-in-one file processor: analyzes file and stores in database"""
    
    async def process(self, task: str, file_id: int, db_session) -> AgentResult:
        # Step 1: Determine file type
        file_entry = db_session.query(FileEntry).filter_by(id=file_id).first()
        
        # Step 2: Analyze based on type
        if file_entry.mime_type.startswith("image/"):
            analysis = await self.analyze_image(file_entry.storage_path)
            tables_created = await self.store_image_data(db_session, file_id, analysis)
        elif file_entry.mime_type == "application/pdf":
            analysis = await self.analyze_pdf(file_entry.storage_path)
            tables_created = await self.store_pdf_data(db_session, file_id, analysis)
        elif file_entry.mime_type == "text/csv":
            analysis = await self.analyze_csv(file_entry.storage_path)
            tables_created = await self.store_csv_data(db_session, file_id, analysis)
        
        # Step 3: Return complete result
        return AgentResult(
            agent_name="FileProcessorAgent",
            display_name="File Processor",
            result=f"Processed {file_entry.display_name} and stored in tables: {', '.join(tables_created)}",
            confidence=0.95,
            method="All-in-one file processing",
            summary=f"Analyzed and stored {len(tables_created)} tables"
        )
```

**Benefit:** 1 iteration instead of 2+ for simple file uploads.

**Tradeoff:** Less modular, harder to debug, but much faster for common cases.

---

## Proposed Solutions (Priority Order)

### **Solution 1: Add File Metadata to Upload Prompt** ⚡ QUICK WIN
- **Effort:** 15 minutes
- **Impact:** Eliminates 4-5 wasted iterations
- **Location:** `cedar_orchestrator/ws_chat.py` line 310
- **Change:** Include filename, mime_type, extension in prompt

```python
file_metadata_text = f"""**Uploaded File:**
- Filename: {rec.display_name}
- Type: {rec.mime_type} (.{rec.file_type})
- Size: {rec.size_bytes:,} bytes
- File ID: {file_id}
"""
```

### **Solution 2: File-Type-Specific Prompts** ⚡ HIGH IMPACT
- **Effort:** 1 hour
- **Impact:** Faster planning, better agent selection
- **Location:** `cedar_orchestrator/ws_chat.py` lines 316-349
- **Change:** Branch on mime_type to generate focused prompts

### **Solution 3: Strengthen Synthesis Rules** ⏱️ MEDIUM EFFORT
- **Effort:** 30 minutes
- **Impact:** Prevents redundant agent calls
- **Location:** `cedar_orchestrator/orchestrator.py` synthesis phase
- **Change:** Add rules to trust agent results and proceed directly to storage

### **Solution 4: Create FileProcessorAgent** 🏗️ LONG-TERM
- **Effort:** 4-6 hours
- **Impact:** 1-iteration file processing
- **Location:** New file `cedar_orchestrator/agents/file_processor_agent.py`
- **Change:** All-in-one agent for common file types

---

## Expected Improvement

### Before Fixes
```
Iterations: 6+
Time: ~8 minutes
SQL Queries: 5+ (all wasteful)
Result: Often incomplete
```

### After Solution 1 + 2 (Quick Wins)
```
Iterations: 2
Time: ~2 minutes
SQL Queries: 0 (metadata in prompt)
Result: Complete workflow
```

### After Solution 1 + 2 + 3 (Full Fix)
```
Iterations: 2 (guaranteed)
Time: ~90 seconds
SQL Queries: 0 metadata, 3-5 INSERT
Result: Complete, metadata updated
```

### After Solution 4 (FileProcessorAgent)
```
Iterations: 1
Time: ~60 seconds
SQL Queries: 3-5 INSERT only
Result: Complete in single pass
```

---

## Implementation Plan

### Phase 1: Immediate Fixes (Today)
1. ✅ Add file metadata to upload prompt (Solution 1)
2. ✅ Generate file-type-specific prompts (Solution 2)
3. Test with your `mw_rc_compare_v2.png` file

### Phase 2: Strengthen Orchestration (This Week)
1. Add synthesis rules to trust agent results (Solution 3)
2. Add guard rails against re-analyzing files
3. Add metrics: track iteration count per file type

### Phase 3: Optimization (Next Week)
1. Design FileProcessorAgent API
2. Implement for images, PDFs, CSV
3. A/B test: 2-agent flow vs 1-agent flow
4. Measure: latency, success rate, user satisfaction

---

## Monitoring & Metrics

### Track These Metrics
```python
# Add to orchestrator logging
logger.info(f"[METRICS] file_type={mime_type} iterations={iteration+1} time={duration}s agents={agent_names}")
```

### Dashboard Queries
```sql
-- Average iterations by file type
SELECT 
    file_type,
    AVG(iteration_count) as avg_iterations,
    AVG(duration_seconds) as avg_duration,
    COUNT(*) as file_count
FROM file_processing_logs
GROUP BY file_type
ORDER BY avg_iterations DESC;

-- Success rate by file type
SELECT
    file_type,
    SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
FROM file_processing_logs
GROUP BY file_type;
```

---

## Alternative: Streaming Agent Results

Instead of waiting for full agent completion, stream partial results:

```python
async def process(self, task: str, ws: WebSocket) -> AgentResult:
    # Stream OCR text as it's extracted
    await ws.send_json({"type": "partial", "ocr_text": "..."})
    
    # Stream data points as they're found
    await ws.send_json({"type": "partial", "data_point": [x, y]})
    
    # Final result
    return AgentResult(...)
```

**Benefit:** User sees progress, can stop early if wrong track.

**Tradeoff:** More complex, harder to orchestrate multi-step flows.

---

## Conclusion

The current flow is **massively inefficient** because:
1. File metadata isn't included in the upload prompt
2. Generic prompts confuse the Chief Agent
3. Chief Agent doesn't trust agent results and re-checks

**Quick wins (Solutions 1+2)** will reduce 6+ iterations to 2.
**Full fix (Solutions 1+2+3)** guarantees 2-iteration completion.
**Future optimization (Solution 4)** enables 1-iteration processing.

**Recommend:** Implement Solutions 1 & 2 immediately (30 min work, 4x speedup).