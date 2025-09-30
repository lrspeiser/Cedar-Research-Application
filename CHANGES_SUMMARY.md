# File Upload Instruction Prompt - Implementation Summary

## What Was Requested
Add an automatic user instruction prompt when files are uploaded to guide the LLM on how to process different file types:

> "The following file was added to the project. If this is an image, analyze the information in the image and update the metadata for it. If this is an unstructured file like a pdf, extract all of the unique findings and supporting data out of the paper and store them in one or more tables in the database. If this is tabular data, create or update our database with it."

## What Was Done

### 1. Code Changes
**File:** `cedar_app/utils/file_operations.py`

#### Location 1: `upload_file()` function (Standard Mode)
- **Lines 402-428:** Added user instruction message after thread creation
- Message is added with `role="user"` before the system classification message
- Display title: `"Process file: {filename}"`
- Content: The full instruction text
- Payload includes: action, file_name, file_type, mime_type, size_bytes, and instructions

#### Location 2: `_run_upload_postprocess_background()` function (Qt Harness Mode)
- **Lines 167-197:** Added identical user instruction message for background processing
- Ensures consistency between standard and Qt harness modes
- Also added as the first message in the background thread

### 2. Message Structure
```python
ThreadMessage(
    project_id=project.id, 
    branch_id=branch.id, 
    thread_id=thread.id, 
    role="user",  # Critical: This is a USER message, not system
    display_title=f"Process file: {original_name}",
    content="The following file was added...",  # Full instruction text
    payload_json={
        "action": "process_uploaded_file",
        "file_name": "example.pdf",
        "file_type": "pdf",
        "mime_type": "application/pdf",
        "size_bytes": 123456,
        "instructions": "The following file..."
    }
)
```

### 3. Documentation
**File:** `docs/FILE_UPLOAD_INSTRUCTIONS.md`
- Comprehensive documentation of the feature
- Explains both standard and Qt harness modes
- Details expected behavior by file type (images, PDFs, tabular data)
- Testing instructions
- Error handling approach
- Future enhancement ideas

### 4. Error Handling
- Wrapped in try/except blocks in both locations
- Non-blocking: if message creation fails, upload continues
- Rollback on exception to maintain database consistency
- No user-facing impact if instruction message fails

### 5. Git Commit
**Commit:** `36d9499`
**Message:** "Add user instruction prompt for file upload processing"
- Detailed commit message explaining all changes
- Pushed to main branch on GitHub

## Flow Comparison

### Before:
1. File uploaded → FileEntry created
2. Thread created
3. System message: "Submitting file to LLM to analyze..."
4. LLM classification runs
5. Assistant response with results

### After:
1. File uploaded → FileEntry created
2. Thread created
3. **NEW: User message: "Process file: {filename}"** with instructions
4. System message: "Submitting file to LLM to analyze..."
5. LLM classification runs (now guided by user instruction)
6. Assistant response with results

## Testing Verification

To verify the change is working:

1. **Start the CedarPy server**
2. **Upload any file** to a project
3. **Check the thread messages** for that file:
   - Should see a `role="user"` message with `display_title="Process file: {filename}"`
   - Message should appear BEFORE the system classification message
   - Content should be the full instruction text

### Test command:
```bash
curl -X POST http://localhost:8000/project/1/files/upload \
  -F "file=@test.pdf" \
  -F "branch_id=1"
```

## Benefits

1. **Consistent Guidance:** Every file upload gets the same processing instructions
2. **LLM Context:** The LLM now has explicit guidance on what to do with different file types
3. **Automated Processing:** Images → metadata update, PDFs → data extraction, CSVs → database import
4. **Traceable:** User instruction visible in thread history
5. **Non-Breaking:** Existing functionality unchanged, this is purely additive

## No Configuration Required

- Works out of the box for all file uploads
- No environment variables needed
- No changes to existing API contracts
- Backward compatible with existing code

## Files Modified

1. `cedar_app/utils/file_operations.py` - Core implementation
2. `docs/FILE_UPLOAD_INSTRUCTIONS.md` - Documentation (new file)
3. `CHANGES_SUMMARY.md` - This summary (new file)

## Commit Details

- **Branch:** main
- **Commit:** 36d9499
- **Pushed:** ✅ Successfully pushed to GitHub
- **Repository:** https://github.com/lrspeiser/cedarpy

---

## Next Steps (Optional Enhancements)

1. Monitor thread messages to verify LLM is following instructions
2. Add metrics to track success rate of different processing types
3. Consider making instruction customizable per project
4. Add file-type-specific instruction variations
5. Create UI element to display/edit the instruction template