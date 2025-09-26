# Agent Optimization and File Agent Implementation

## Overview
This update optimizes the multi-agent orchestration system by:
1. **Reducing redundant agent usage**: GeneralAgent and ReasoningAgent are now used sparingly
2. **Adding FileAgent**: New specialized agent for file downloads and management
3. **Improving agent selection**: More targeted agent selection based on query type

## Changes Made

### 1. Reduced Agent Usage

#### Before
- GeneralAgent and ReasoningAgent were included in almost every query
- This led to redundant processing and slower response times
- Example: A math calculation would run 4 agents (Code, Math, Reasoning, General)

#### After
- Agents are selected more precisely based on need
- Most queries now use only 1-2 specialized agents
- GeneralAgent is only used as a fallback for truly general queries
- ReasoningAgent is only used for explanation and derivation tasks

### 2. New FileAgent

The FileAgent is a specialized agent that handles:
- **URL Downloads**: Downloads files from web URLs
- **File Path Analysis**: Analyzes local file paths
- **Metadata Extraction**: Extracts and saves file metadata
- **Database Integration**: Automatically saves file info to the FileEntry table
- **AI Description**: Uses LLM to generate descriptions for text files

#### Features
- Downloads files to `~/CedarDownloads` directory
- Generates unique timestamped filenames
- Detects MIME types automatically
- Reads first 500 bytes for text preview
- Saves complete metadata to database including:
  - Original filename and URL
  - File size and MIME type
  - AI-generated title and description
  - Download timestamp

### 3. Optimized Agent Selection

| Query Type | Before | After |
|------------|--------|-------|
| File operations | Not supported | FileAgent + NotesAgent |
| Math calculations | Code + Math + Reasoning + General | Code + Math |
| Code generation | Code + Strategy + General | Code + Strategy |
| SQL queries | Data + SQL + General | Data + SQL |
| Research | Research + General + Notes | Research + Notes |
| Strategy/Planning | Strategy + Reasoning + General | Strategy only |
| Note-taking | Notes + General | Notes only |
| Explanations | Reasoning + Research + General | Research + Reasoning |

## Usage Examples

### File Download
```
User: "Download https://example.com/data.csv"
Agents Used: FileAgent, NotesAgent
Result: File downloaded, saved to database, metadata extracted
```

### Math Calculation
```
User: "Calculate the square root of 144"
Agents Used: CodeAgent, MathAgent
Result: Faster execution with same accuracy
```

### Code Generation
```
User: "Write a Python function to sort a list"
Agents Used: CodeAgent, StrategyAgent
Result: Cleaner code with better design approach
```

## Database Schema

The FileAgent uses the existing FileEntry model:
```python
class FileEntry:
    id: Integer (Primary Key)
    project_id: Integer
    branch_id: Integer
    filename: String (storage name)
    display_name: String (original name)
    file_type: String (extension)
    structure: String (content type)
    mime_type: String
    size_bytes: Integer
    storage_path: String
    ai_title: String
    ai_description: Text
    ai_category: String
    metadata_json: JSON (includes source_url, download_time)
```

## Performance Improvements

- **Reduced latency**: Fewer agents mean faster response times
- **Lower token usage**: Less redundant processing saves API costs
- **Better accuracy**: Specialized agents provide more focused results
- **Cleaner output**: No conflicting responses from too many agents

## Configuration

### Environment Variables
- `CEDARPY_OPENAI_MODEL`: Model for AI descriptions (default: gpt-5)
- `OPENAI_API_KEY`: Required for LLM features

### File Storage
- Downloads are saved to: `~/CedarDownloads/`
- Filename format: `YYYYMMDD_HHMMSS_originalname`

## Error Handling
- Failed downloads are reported with error details
- Database save failures are logged but don't stop the download
- AI description generation failures fall back to basic descriptions

## Future Enhancements
- [ ] Support for batch file downloads
- [ ] Integration with cloud storage (S3, GCS)
- [ ] File type specific processing (PDF extraction, image analysis)
- [ ] Virus scanning for downloaded files
- [ ] Configurable download directory per project

## Testing
To test the FileAgent:
```python
# Download a file
"Please download https://raw.githubusercontent.com/example/repo/main/README.md"

# Analyze a local file
"Analyze the file at /Users/me/document.txt"

# Multiple URLs
"Download these files: https://example.com/file1.pdf and https://example.com/file2.csv"
```

## Migration Notes
No database migrations needed - uses existing FileEntry table.