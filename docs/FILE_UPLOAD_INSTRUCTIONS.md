# File Upload Processing Instructions

## Overview
When a file is uploaded to CedarPy, a user instruction message is automatically added to the thread to guide the LLM on how to process different file types.

## What Was Changed

### Location
`cedar_app/utils/file_operations.py`

### Changes Made
1. **Added user instruction message** in `upload_file()` function (lines 369-395)
2. **Added user instruction message** in `_run_upload_postprocess_background()` function (lines 167-197)

### The Instruction Prompt
Every uploaded file now receives this user message:

```
The following file was added to the project. If this is an image, analyze the 
information in the image and update the metadata for it. If this is an unstructured 
file like a pdf, extract all of the unique findings and supporting data out of the 
paper and store them in one or more tables in the database. If this is tabular 
data, create or update our database with it.
```

## How It Works

### Standard Mode
1. File is uploaded and saved to disk
2. FileEntry record created in database
3. Thread created for tracking processing
4. **NEW: User instruction message added** (role="user")
5. System message added with metadata
6. LLM classification begins
7. Background indexing (LangExtract)
8. Tabular import (if applicable)

### Qt Harness Mode (`CEDARPY_QT_HARNESS=1`)
1. File is uploaded and saved to disk
2. FileEntry record created
3. Thread created
4. HTTP 303 redirect to the project page with `?msg=File+uploaded` (background processing continues)
5. Background worker started:
   - **NEW: User instruction message added**
   - LLM classification
   - Background indexing
   - Tabular import

## Message Structure

### User Instruction Message
```python
{
    "role": "user",
    "display_title": "Process file: {filename}",
    "content": "{instruction_text}",
    "payload_json": {
        "action": "process_uploaded_file",
        "file_name": "example.pdf",
        "file_type": "pdf",
        "mime_type": "application/pdf",
        "size_bytes": 123456,
        "instructions": "{instruction_text}"
    }
}
```

## Expected Behavior by File Type

### Images (PNG, JPG, GIF, etc.)
- LLM should analyze visual content
- Extract text from image if present
- Update metadata with description and detected elements
- Store in file record's `ai_description` and `metadata_json`

### Unstructured Documents (PDF, DOCX, etc.)
- Extract all unique findings
- Identify key data points and supporting information
- Create one or more database tables to store structured findings
- Store relationships between findings
- Link back to source file

### Tabular Data (CSV, JSON, Excel, etc.)
- Parse data schema
- Create or update Dataset records
- Import data into project database tables
- Maintain data integrity and relationships

## Testing

To verify the instruction message is added:

```python
# Upload a file
response = requests.post(
    f"http://localhost:8000/project/1/files/upload",
    files={'file': ('test.csv', 'col1,col2\n1,2', 'text/csv')},
    params={'branch_id': 1}
)

# Check thread messages
# Should see a "user" role message with display_title "Process file: test.csv"
```

## Error Handling

- If the user message fails to be added, processing continues normally
- The instruction is non-blocking - failures are caught and logged
- Both synchronous and background modes handle exceptions gracefully

## Configuration

No new configuration variables required. The instruction is always added for all file uploads.

## Related Code

- `cedar_app/utils/file_operations.py::upload_file()` - Main upload handler
- `cedar_app/utils/file_operations.py::_run_upload_postprocess_background()` - Background worker
- `cedar_app/llm_utils.py::llm_classify_file()` - LLM classification
- `cedar_app/llm_utils.py::tabular_import_via_llm()` - Tabular data import
- `main_models.py::ThreadMessage` - Message model

## Future Enhancements

Potential improvements:
1. Make instruction customizable per project via settings
2. Add file-type-specific variations of the instruction
3. Include project context in the instruction
4. Allow users to override the default instruction
5. Add instruction templates for different workflows