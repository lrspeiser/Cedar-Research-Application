# Cedar Prompt Improvement Guide

This guide outlines options for improving prompts throughout the Cedar system to enhance agent selection, task execution, and result quality.

## Table of Contents
1. [Chief Agent Planning Prompts](#chief-agent-planning-prompts)
2. [File Upload Context Prompts](#file-upload-context-prompts)
3. [Individual Agent Prompts](#individual-agent-prompts)
4. [Error Handling & Recovery Prompts](#error-handling--recovery-prompts)
5. [Implementation Priorities](#implementation-priorities)

---

## Chief Agent Planning Prompts

### Current Issues
1. **Over-selection of agents**: Chief Agent sometimes selects redundant agents (e.g., both ImageAnalysisAgent and FileAgent for an uploaded file)
2. **Vague task descriptions**: Agent tasks sometimes lack specific context or parameters
3. **Missing file_id awareness**: Chief Agent doesn't always realize that uploaded files have a `file_id` in context

### Improvement Options

#### Option 1: Add Uploaded File Context to System Prompt
**Location:** `cedar_orchestrator/orchestrator.py` lines 113-200

**Change:** Add section explaining file_id context:
```python
system_header = f"""You are the Chief Agent...

FILE UPLOAD CONTEXT:
- When a user uploads a file, it is stored in the database with a file_id
- The file_id is automatically passed in context to agents
- Use ImageAnalysisAgent for image files (PNG, JPG, etc.) - it will look up the file using file_id
- Use PDFExtractionAgent for PDFs - it will look up the file using file_id
- Use FileAgent ONLY for downloading files from URLs (not for already-uploaded files)
- When a file is already uploaded, DO NOT use FileAgent - the file path is already known

IMPORTANT:
- For uploaded files: Use specialized agents (ImageAnalysisAgent, PDFExtractionAgent, etc.)
- For URLs to download: Use FileAgent to download, THEN use specialized agents
- Never use FileAgent for files that are already in the database
"""
```

**Benefit:** Reduces unnecessary agent calls, improves efficiency

---

#### Option 2: Improve Agent Selection Examples
**Location:** `cedar_orchestrator/orchestrator.py` lines 190-250

**Change:** Add explicit examples for file processing:
```python
examples = """

Examples (Routing Guidance):
...existing examples...

- ImageAnalysisAgent (uploaded image files)
  • User uploads image.png
    Context: file_id=5
    Agents to use: [ImageAnalysisAgent]
    Task for ImageAnalysisAgent: "Analyze this image and extract any chart data, perform OCR, and describe what's shown."
  • User: "What data is in this chart?" (with uploaded file context)
    Context: file_id=5
    Agents to use: [ImageAnalysisAgent, SQLAgent]
    Task for ImageAnalysisAgent: "Extract structured data from the chart including axes labels, series names, and data points"
    Task for SQLAgent: "Create a table to store the extracted chart data and insert the rows"

- FileAgent (download from URL)
  • User: "Download https://example.com/data.csv and analyze it"
    Agents to use: [FileAgent, DataAgent]
    Task for FileAgent: "Download the CSV from https://example.com/data.csv"
    Task for DataAgent: "Analyze the CSV schema and create database tables"
  • NEVER use FileAgent for: "Analyze the uploaded file" - file is already uploaded!
"""
```

**Benefit:** Clear examples reduce confusion about when to use each agent

---

#### Option 3: Add Task Specification Requirements
**Location:** `cedar_orchestrator/orchestrator.py` lines 168-188

**Change:** Make task requirements more explicit:
```python
IMPORTANT - PLANNING PHASE (no agent results yet):
- decision MUST BE "loop" to dispatch agents
- user_facing_message: Brief explanation of what you're doing
- agent_tasks: List of tasks with SPECIFIC instructions for each agent

TASK SPECIFICATION REQUIREMENTS:
- Each task must be a complete, self-contained instruction
- Include ALL necessary context (file_id, table names, column names, etc.)
- Specify the expected OUTPUT format for each agent
- For charts/images: "Extract X, Y, Z" not just "Analyze image"
- For SQL: "CREATE TABLE with columns A, B, C; INSERT rows" not just "Store data"
- For research: "Find 3-5 citations for X published after 2020" not just "Research X"

BAD TASK: "Analyze the image and store results"
GOOD TASK: "Analyze this histogram chart. Extract: (1) axis labels and units, (2) bin ranges and frequencies, (3) any text/title via OCR. Return as structured data with fields: title, x_axis, y_axis, bins (array of {range, count}), ocr_text."
```

**Benefit:** More specific tasks → better agent execution → higher quality results

---

## File Upload Context Prompts

### Current Implementation
**Location:** `cedar_orchestrator/ws_chat.py` lines 310-349

The current auto-generated prompt for file uploads is very comprehensive but could be improved:

### Improvement Options

#### Option 1: Add File Type Detection
**Change:** Detect the actual file type and customize the prompt accordingly

```python
if is_file_upload_message:
    # Get file metadata
    file_metadata = {}
    file_type_category = "unknown"
    if db_session and file_id:
        from main_models import FileEntry
        rec = db_session.query(FileEntry).filter(
            FileEntry.id == int(file_id),
            FileEntry.project_id == int(project_id)
        ).first()
        if rec:
            file_metadata = {
                "filename": rec.display_name or rec.name,
                "mime_type": rec.mime_type,
                "size_bytes": rec.size_bytes
            }
            
            # Categorize file type
            mime = (rec.mime_type or "").lower()
            ext = os.path.splitext(rec.display_name or "")[1].lower()
            
            if "image" in mime or ext in [".png", ".jpg", ".jpeg", ".gif"]:
                file_type_category = "image"
            elif "pdf" in mime or ext == ".pdf":
                file_type_category = "pdf"
            elif any(x in mime for x in ["csv", "excel", "spreadsheet"]) or ext in [".csv", ".xlsx", ".xls"]:
                file_type_category = "tabular"
            elif any(x in mime for x in ["text", "json", "xml"]) or ext in [".txt", ".json", ".xml", ".md"]:
                file_type_category = "text"
    
    # Build type-specific prompt
    if file_type_category == "image":
        query_to_send = f"""I uploaded an image file: {file_metadata.get('filename', 'unknown')} (file_id: {file_id})

**SPECIFIC ACTIONS REQUIRED:**

1. **Image Analysis** (ImageAnalysisAgent):
   - Identify the type of image (chart, diagram, photo, screenshot, etc.)
   - If it's a chart/plot:
     * Extract chart type (bar, line, scatter, histogram, etc.)
     * Extract axis labels, titles, units
     * Extract legend entries and colors
     * Extract data points: create structured list of (x, y, series, label) tuples
   - If it contains text:
     * Perform OCR and extract all readable text
     * Identify language and confidence
   - If it's a diagram:
     * Describe the structure and components
     * Extract any labels or annotations
   - Provide: description, tags, extracted_data, ocr_text

2. **Data Storage** (SQLAgent):
   - Create/update 'images' table with columns:
     * file_id (FK), filename, description, image_type, width, height, tags
   - If chart data was extracted, create 'chart_data' table:
     * chart_id (FK to images), series_name, x_value, y_value, label, color
   - If OCR text was extracted, create 'image_text' table:
     * image_id (FK), ocr_text, language, confidence
   - Execute all CREATE TABLE and INSERT statements
   - Return row counts and table names

3. **Summary**:
   - Confirm what was stored where
   - If this is a chart, offer to recreate/plot the data
   - Suggest next analysis steps

**Database context:**
{db_metadata}

START by analyzing the image, THEN store results in the database."""

    elif file_type_category == "tabular":
        query_to_send = f"""I uploaded tabular data: {file_metadata.get('filename', 'unknown')} (file_id: {file_id})

**SPECIFIC ACTIONS REQUIRED:**

1. **Data Analysis** (DataAgent or CodeAgent):
   - Read the file and infer schema
   - Identify columns: name, data type, nullable, unique, primary key candidates
   - Detect data issues: nulls, duplicates, outliers, inconsistencies
   - Generate summary statistics: row count, column types, value distributions
   - Provide: schema, sample_rows (first 5), issues, statistics

2. **Database Storage** (SQLAgent):
   - CREATE TABLE with appropriate column types (INTEGER, REAL, TEXT, BOOLEAN, TIMESTAMP)
   - Add NOT NULL, UNIQUE, PRIMARY KEY constraints as appropriate
   - Add CHECK constraints for data validation if needed
   - INSERT all rows (use batch insert for efficiency)
   - Add index on likely query columns
   - Add metadata: CREATE TABLE IF NOT EXISTS file_metadata (file_id, source_table, imported_at)
   - Return: table_name, rows_inserted, indexes_created

3. **Validation**:
   - Run SELECT COUNT(*) to confirm row count
   - Run SELECT * LIMIT 5 to verify data
   - Check for any INSERT errors or data truncation

4. **Summary**:
   - Confirm table created and row count
   - Suggest possible queries or analyses
   - Identify relationships with existing tables

**Database context:**
{db_metadata}"""

    elif file_type_category == "pdf":
        query_to_send = f"""I uploaded a PDF: {file_metadata.get('filename', 'unknown')} (file_id: {file_id})

**SPECIFIC ACTIONS REQUIRED:**

1. **PDF Processing** (PDFExtractionAgent):
   - Extract text content from all pages
   - Extract metadata: author, title, creation_date, page_count
   - Extract embedded images (save separately)
   - Extract tables (convert to structured data)
   - Identify document type: research paper, report, presentation, etc.
   - Provide: full_text, metadata, images, tables

2. **Content Analysis** (depends on document type):
   - For research papers:
     * Extract: title, authors, abstract, sections, citations
     * Identify key findings and methods
   - For reports:
     * Extract: executive summary, sections, figures, tables
     * Identify metrics and KPIs
   - For any document:
     * Extract actionable items, decisions, dates
     * Summarize main points

3. **Data Storage** (SQLAgent):
   - CREATE 'pdf_documents' table: file_id, title, author, page_count, doc_type, summary
   - CREATE 'pdf_pages' table: doc_id, page_num, text_content, word_count
   - CREATE 'pdf_images' table: doc_id, page_num, image_id, caption
   - CREATE 'pdf_tables' table: doc_id, page_num, table_num, structured_data (JSON)
   - If research paper: CREATE 'citations' table: doc_id, citation_text, author, year, title, url
   - INSERT all extracted data
   - Return table names and row counts

**Database context:**
{db_metadata}"""
    
    else:  # unknown/text
        query_to_send = # ...existing generic prompt...
```

**Benefit:** Type-specific prompts produce better, more targeted results

---

#### Option 2: Add Success Criteria to Prompts
**Change:** Explicitly state what constitutes successful processing

```python
query_to_send += """

**SUCCESS CRITERIA:**
✓ All data extracted from the file
✓ Appropriate database tables created
✓ All rows inserted successfully
✓ Confirmation message with table names and row counts
✓ No silent failures or skipped steps

**FAILURE CONDITIONS:**
✗ Suggesting what to do without actually doing it
✗ Creating tables but not inserting data
✗ Partial data extraction without completing the process
✗ Generic "file processed" message without specifics
"""
```

**Benefit:** Clear success criteria reduce ambiguous results

---

## Individual Agent Prompts

### ImageAnalysisAgent

**Current Location:** `cedar_orchestrator/agents/image_analysis_agent.py` lines 134-146

**Current Prompt:**
```python
content: """You are an expert image analyst. Provide detailed, structured analysis.

For charts/plots: Identify chart type, axes, legend, data series, and extract visible data points.
For diagrams: Describe structure, flow, and key components.
For text-heavy images: Perform OCR and extract all readable text.
For photos: Describe scene, objects, composition.

Format your response with markdown headings and bullet points for clarity."""
```

#### Improvement Option: Add Structured Output Format
**Change:**
```python
content: """You are an expert image analyst. Provide detailed, structured analysis in a consistent format.

OUTPUT FORMAT (use this structure for ALL images):

## Image Type
[Chart/Diagram/Photo/Screenshot/Text Document/Mixed]

## Primary Content
[1-2 sentence description of what's shown]

## Detailed Analysis

### For Charts/Plots:
- **Chart Type**: [bar/line/scatter/histogram/pie/heatmap/other]
- **Title**: [extracted title or "None"]
- **Axes**:
  * X-axis: [label], unit: [unit], range: [min-max]
  * Y-axis: [label], unit: [unit], range: [min-max]
- **Legend**: [list entries with colors]
- **Data Series**: For EACH series:
  * Series name: [name]
  * Color: [color]
  * Data points: [(x1,y1), (x2,y2), ...] (extract at least 5-10 representative points)
- **Annotations**: [any text labels, arrows, callouts]

### For Diagrams/Flowcharts:
- **Diagram Type**: [flowchart/system diagram/architecture/network/other]
- **Components**: List all major components/nodes
- **Connections**: Describe relationships and flow
- **Labels**: Extract all text labels
- **Key Insights**: What does this diagram communicate?

### For Text Documents/Screenshots:
- **OCR Text**: [full extracted text]
- **Language**: [detected language]
- **Confidence**: [OCR confidence score if available]
- **Layout**: [describe text layout: columns, headings, lists]
- **Formatting**: [bold, italic, colors, fonts if notable]

### For Photos:
- **Scene**: [overall scene description]
- **Objects**: [list detected objects with locations]
- **People**: [number, activities if relevant]
- **Text**: [any visible text via OCR]
- **Composition**: [perspective, lighting, focus]

## Extracted Data
[If chart/table: provide data in machine-readable format - JSON or CSV-like structure]

## Metadata
- **Dimensions**: [width x height if detectable]
- **Quality**: [clear/blurry/pixelated/high-resolution]
- **Colors**: [dominant colors or color scheme]

## Recommendations
- Next steps for working with this image
- Suggested database storage schema
- Possible analyses or visualizations

Use specific measurements and data points wherever possible. Prefer quantitative descriptions over qualitative."""
```

**Benefit:** Structured format makes it easier to parse results and store in database

---

### CodeAgent

**Current Location:** `cedar_orchestrator/agents/code_agent.py` lines 78-102

#### Improvement Option: Add Chart/Plot Generation Capabilities
**Change:** Add to system prompt:
```python
"""You are a Python code generator.

You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "...",
  "code": "...",
  "summary": "..."
}

SPECIAL CAPABILITIES:
- For chart data: Use matplotlib or plotly to create visualizations
- For data analysis: Use pandas, numpy for processing
- For image processing: Use PIL, cv2 for image operations
- For data extraction: Use regex, parsing libraries

CHART GENERATION TEMPLATE:
When asked to plot/visualize chart data:
```python
import matplotlib.pyplot as plt
import numpy as np

# Data (from extracted chart data)
x = [...]
y = [...]

# Create figure
plt.figure(figsize=(10, 6))
plt.plot(x, y, marker='o', label='Series Name')
plt.xlabel('X Label')
plt.ylabel('Y Label')
plt.title('Chart Title')
plt.legend()
plt.grid(True, alpha=0.3)

# Save to file
output_path = '/path/to/output/chart.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight')
plt.close()

print(f'Chart saved to: {output_path}')
```

Always save charts to files and return the file path."""
```

**Benefit:** Enables recreating charts from extracted data

---

### SQLAgent

**Current Location:** `cedar_orchestrator/agents/sql_agent.py`

#### Improvement Option: Add Schema Design Best Practices
**Change:** Add to SQL generation instructions:
```python
"""SQL SCHEMA DESIGN REQUIREMENTS:

1. **Table Naming**:
   - Use descriptive plural names: 'images', 'chart_data', 'citations'
   - Use snake_case: 'pdf_documents', 'image_metadata'

2. **Column Naming**:
   - Primary keys: 'id' (INTEGER PRIMARY KEY AUTOINCREMENT)
   - Foreign keys: '{table}_id' (e.g., 'image_id', 'document_id')
   - Always include: created_at, updated_at timestamps

3. **Data Types**:
   - Use INTEGER for whole numbers, REAL for decimals
   - Use TEXT for strings (SQLite doesn't limit size)
   - Use BOOLEAN as INTEGER (0/1)
   - Use TIMESTAMP as TEXT (ISO 8601 format)

4. **Constraints**:
   - Add NOT NULL for required fields
   - Add UNIQUE for fields that must be unique
   - Add CHECK constraints for validation
   - Add FOREIGN KEY constraints with ON DELETE CASCADE

5. **Indexes**:
   - Create indexes on foreign keys
   - Create indexes on frequently queried columns
   - Consider composite indexes for multi-column queries

6. **Schema Template for File-Related Data**:
```sql
-- Main file record
CREATE TABLE IF NOT EXISTS {file_type}_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,  -- FK to files table
    filename TEXT NOT NULL,
    file_path TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Extracted data
CREATE TABLE IF NOT EXISTS {file_type}_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {file_type}_file_id INTEGER NOT NULL,
    data_type TEXT,  -- 'chart', 'text', 'table', etc.
    data_json TEXT,  -- JSON-encoded structured data
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY ({file_type}_file_id) REFERENCES {file_type}_files(id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_{file_type}_file_id ON {file_type}_data({file_type}_file_id);
```

ALWAYS generate complete working SQL that can be executed immediately."""
```

**Benefit:** Consistent, well-designed schemas across all file imports

---

## Error Handling & Recovery Prompts

### Improvement Option: Add Self-Correction Prompts

**Location:** `cedar_orchestrator/orchestrator.py` (Chief Agent synthesis phase)

**Change:** When agents return errors, add self-correction guidance:
```python
if any(r.confidence < 0.5 for r in agent_results):
    msgs.append({
        "role": "system",
        "content": """AGENT ERRORS DETECTED:

Some agents returned low-confidence results or errors. Options:

1. **Retry with Modified Task**:
   - If the task was unclear, rephrase it with more specific instructions
   - If the agent lacked context, provide additional context
   
2. **Try Alternative Agent**:
   - If CodeAgent failed, try ShellAgent or vice versa
   - If one analysis approach failed, try a different approach

3. **Break Down the Task**:
   - Split complex tasks into smaller, sequential steps
   - Use multiple iterations to build up the solution

4. **Provide Partial Results**:
   - If some agents succeeded, synthesize their results
   - Explain what worked and what didn't
   - Suggest manual steps for the failed parts

Choose the best recovery strategy based on the error types."""
    })
```

**Benefit:** Better handling of partial failures, improved robustness

---

## Implementation Priorities

### High Priority (Implement First)

1. **Fix FileAgent Over-Selection** ✅
   - Add uploaded file context to Chief Agent system prompt
   - Clarify when to use FileAgent vs specialized agents
   - **Impact:** Reduces unnecessary agent calls, faster processing
   - **Effort:** Low (prompt change only)

2. **Add Task Specification Requirements**
   - Make agent task requirements more explicit
   - Add examples of good vs bad task descriptions
   - **Impact:** Better agent execution, higher quality results
   - **Effort:** Low (prompt change only)

3. **Structured Output for ImageAnalysisAgent**
   - Add consistent output format template
   - Ensure extracted data is machine-readable
   - **Impact:** Easier to parse and store image analysis results
   - **Effort:** Low (prompt change only)

### Medium Priority (Implement Next)

4. **File Type-Specific Upload Prompts**
   - Detect file type and use customized prompts
   - Add success criteria to each prompt
   - **Impact:** Better targeted analysis for each file type
   - **Effort:** Medium (requires file type detection logic)

5. **SQL Schema Best Practices**
   - Add schema design guidelines to SQLAgent
   - Ensure consistent table/column naming
   - **Impact:** Better database organization, easier querying
   - **Effort:** Medium (prompt + validation)

6. **Error Recovery Prompts**
   - Add self-correction guidance for low-confidence results
   - Enable retry with modified tasks
   - **Impact:** Better handling of edge cases
   - **Effort:** Medium (prompt + retry logic)

### Low Priority (Nice to Have)

7. **Chart Recreation Capabilities**
   - Add matplotlib/plotly templates to CodeAgent
   - Enable recreating charts from extracted data
   - **Impact:** Enables data visualization from charts
   - **Effort:** High (requires chart generation logic)

8. **Agent Performance Feedback**
   - Log which prompts produce best results
   - A/B test prompt variations
   - **Impact:** Data-driven prompt improvement
   - **Effort:** High (requires metrics collection)

---

## Testing Prompt Changes

### Methodology

1. **Baseline Test Set**: Create test files covering:
   - Simple bar chart
   - Complex multi-series line chart
   - Histogram with annotations
   - CSV with mixed data types
   - PDF with tables and images
   - Text document with structured content

2. **Metrics to Track**:
   - Agent selection accuracy (right agents chosen?)
   - Task completion rate (agents finished successfully?)
   - Result quality (structured data extracted correctly?)
   - Execution time (faster with better prompts?)
   - User satisfaction (results match expectations?)

3. **A/B Testing**:
   - Run same file with old prompt vs new prompt
   - Compare agent selections and results
   - Measure improvement quantitatively

4. **Regression Testing**:
   - Ensure prompt changes don't break existing functionality
   - Test on previously successful cases

---

## Quick Wins (Implement Today)

### 1. Add to Chief Agent System Prompt (5 minutes)
```python
# In orchestrator.py line ~118, add:
FILE CONTEXT AWARENESS:
- Uploaded files have file_id in context - specialized agents can look them up
- Use FileAgent ONLY for downloading from URLs (not for uploaded files)
- For uploaded images: Use ImageAnalysisAgent (it will find file via file_id)
- For uploaded PDFs: Use PDFExtractionAgent (it will find file via file_id)
```

### 2. Improve Agent Task Examples (10 minutes)
```python
# In orchestrator.py line ~190, add:
- ImageAnalysisAgent for uploaded chart.png (file_id=5)
  Agents: [ImageAnalysisAgent]
  WRONG: "Analyze the file" 
  RIGHT: "Extract chart type, axis labels, data points, and perform OCR on any text"
```

### 3. Add Success Criteria to File Upload Prompt (5 minutes)
```python
# In ws_chat.py line ~342, add:
**SUCCESS CRITERIA:**
✓ All data extracted and stored in database tables
✓ Confirmation with table names and row counts provided
✓ No placeholders or "TODO" comments in results
```

These three changes alone will significantly improve file processing quality!

---

## Next Steps

1. **Implement High Priority Changes** (prompts only, no code changes)
2. **Test with Your Current File** (`outer_slopes_hist_v2.png`)
3. **Measure Improvement** (does it extract chart data correctly?)
4. **Iterate** based on results
5. **Move to Medium Priority Items** once high priority is working well

Would you like me to implement any of these prompt improvements right now?