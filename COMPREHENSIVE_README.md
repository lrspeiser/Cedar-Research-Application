# Cedar Research Application - Comprehensive Documentation

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture Overview](#architecture-overview)
- [Complete Directory Structure](#complete-directory-structure)
- [LLM-Driven Components](#llm-driven-components)
- [Prompt Engineering & LLM Integration](#prompt-engineering--llm-integration)
- [Code Duplication & Refactoring Opportunities](#code-duplication--refactoring-opportunities)
- [Testing Structure](#testing-structure)
- [Deployment & Packaging](#deployment--packaging)
- [Configuration & Environment](#configuration--environment)

## Project Overview

Cedar Research Application (CedarPy) is a FastAPI-based research and data management platform that heavily leverages Large Language Models (LLMs) for intelligent file processing, code analysis, and interactive chat-based workflows. The application supports project-based organization with branching, file uploads, SQL operations, and AI-powered data analysis.

### Key Features
- **Project & Branch Management**: Multi-project support with Git-like branching
- **LLM-Powered File Processing**: Automatic classification, summarization, and extraction
- **Interactive Chat Interface**: WebSocket-based chat with AI orchestration
- **SQL Workspace**: Branch-aware SQL execution with undo capabilities
- **Code Analysis**: Automatic code extraction and analysis from uploaded files
- **Shell Integration**: Secure shell command execution with streaming output

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Frontend Layer                    │
│  ├── QtWebEngine UI (cedarqt.py)                   │
│  ├── Web UI (HTML/JS in layout functions)          │
│  └── WebSocket Clients                             │
└─────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────┐
│                  FastAPI Application                │
│  ├── main.py (orchestrator entry)                  │
│  ├── main_impl_full.py (core implementation)      │
│  └── web_ui.py (new modular UI entry)             │
└─────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────┐
│               Core Services & Utilities             │
│  ├── cedar_orchestrator/ (AI coordination)         │
│  ├── cedar_tools/ (Tool implementations)           │
│  ├── cedar_app/utils/ (Business logic)             │
│  └── cedar_app/routes/ (HTTP/WS endpoints)         │
└─────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────┐
│                   Data Layer                        │
│  ├── SQLAlchemy Models (main_models.py)            │
│  ├── MySQL/SQLite Databases                        │
│  └── File Storage (project-based)                  │
└─────────────────────────────────────────────────────┘
```

## Complete Directory Structure

### Root Level Files
```
/Users/leonardspeiser/Projects/cedarpy/
├── main.py                    # Main orchestrator entry point, delegates to main_impl_full
├── main_impl_full.py          # Core FastAPI implementation (being refactored)
├── main_models.py             # SQLAlchemy ORM models
├── main_helpers.py            # Shared utility functions
├── run_cedarpy.py             # Application launcher with logging setup
├── cedarqt.py                 # Qt desktop application wrapper
├── orchestrator.py            # Legacy orchestrator (being replaced)
├── thinker.py                 # 🤖 LLM-powered "thinking" agent for complex tasks
├── cedar_langextract.py       # 🤖 LLM-based language extraction from files
├── cedar_tools.py             # Tool registry and dispatcher
├── refactor_to_web_ui.py      # Refactoring script for modularization
├── extract_modules.py         # Module extraction utilities
├── complete_refactor.py       # Complete refactoring automation
└── test_*.py                  # Various test files
```

### Core Application Directory (`cedar_app/`)
```
cedar_app/
├── __init__.py
├── main.py                    # New refactored main entry
├── main_impl_full.py          # Full implementation (1590 lines, being modularized)
├── main_impl_full_refactored.py  # Refactored version attempt
├── web_ui.py                  # New lightweight UI-focused entry point
├── config.py                  # Application configuration
├── database.py                # Database connection management
├── api_routes.py              # API route definitions
├── orchestrator.py            # Chat orchestration logic
├── file_upload_handler.py    # File upload processing
├── shell_utils.py             # Shell command utilities
├── ui_utils.py                # UI rendering utilities
│
├── llm/                       # 🤖 LLM Integration Module
│   ├── __init__.py
│   ├── client.py             # 🤖 OpenAI client wrapper with stubbing support
│   └── tabular_import.py     # 🤖 LLM-powered CSV/Excel import
│
├── routes/                    # Modularized route handlers
│   ├── __init__.py
│   ├── main_routes.py        # Main application routes
│   ├── project_routes.py     # Project management endpoints
│   ├── project_thread_routes.py  # Project & thread creation
│   ├── file_routes.py        # File handling endpoints
│   ├── thread_routes.py      # Thread management
│   ├── shell_routes.py       # Shell execution endpoints
│   ├── sql_routes.py         # SQL execution endpoints (stub)
│   ├── websocket_routes.py   # WebSocket handlers
│   └── log_routes.py         # Logging endpoints
│
├── utils/                     # Utility modules
│   ├── __init__.py
│   ├── ask_orchestrator.py   # 🤖 AI orchestration utilities
│   ├── branch_management.py  # Branch operations
│   ├── client_logging.py     # Client-side log handling
│   ├── code_collection.py    # Code extraction from messages
│   ├── dataset_management.py # Dataset operations
│   ├── dev_tools.py          # Development utilities
│   ├── file_management.py    # File operations
│   ├── file_operations.py    # File I/O utilities
│   ├── file_upload.py        # Upload processing
│   ├── html.py               # HTML generation helpers
│   ├── logging.py            # Logging configuration
│   ├── note_management.py    # Note handling
│   ├── page_rendering.py     # Page generation
│   ├── project_management.py # Project operations
│   ├── sql_utils.py          # SQL helpers
│   ├── sql_websocket.py     # SQL WebSocket handling
│   ├── test_tools.py         # Testing utilities
│   ├── thread_chat.py        # 🤖 Thread chat handling
│   ├── thread_management.py  # Thread operations
│   ├── ui_views.py           # UI view rendering
│   └── websocket_chat.py     # 🤖 WebSocket chat handling
│
├── tools/                     # Tool implementations
│   ├── __init__.py
│   └── shell.py              # Shell execution tool
│
└── scripts/                   # Utility scripts
    └── extract_sql_routes.py # SQL route extraction script
```

### LLM Orchestration Directory (`cedar_orchestrator/`) 🤖
```
cedar_orchestrator/            # AI/LLM Coordination Layer
├── __init__.py
├── advanced_orchestrator.py   # 🤖 Advanced AI orchestration with planning
├── file_processing_agents.py  # 🤖 LLM agents for file analysis
└── ws_chat.py                 # 🤖 WebSocket chat orchestration
```

### Cedar Tools Directories (`cedar_tools/` & `cedar_tools_modules/`)
```
cedar_tools/                   # Tool implementations (legacy)
├── __init__.py
├── base.py                   # Base tool classes
├── code.py                   # 🤖 Code execution tool
├── compose.py                # 🤖 Text composition tool
├── db.py                     # Database query tool
├── download.py               # File download tool
├── extract.py                # 🤖 Content extraction tool
├── image.py                  # 🤖 Image analysis tool
├── notes.py                  # Note management tool
├── shell.py                  # Shell execution tool
├── tabular_import.py         # 🤖 Tabular data import
└── web.py                    # 🤖 Web search/scraping tool

cedar_tools_modules/           # Refactored tool modules
├── __init__.py
├── code.py                   # Code execution
├── compose.py                # 🤖 AI text composition
├── db.py                     # Database operations
├── download.py               # Download handling
├── extract.py                # 🤖 AI extraction
├── image.py                  # 🤖 AI image processing
├── llm.py                    # 🤖 Direct LLM interface
├── notes.py                  # Note operations
├── plan.py                   # 🤖 AI planning tool
├── shell.py                  # Shell commands
├── tabular_import.py         # 🤖 AI tabular import
└── web.py                    # 🤖 AI web interaction
```

### Agent System (`agents/`) 🤖
```
agents/                        # AI Agent System
├── __init__.py
├── base_agent.py             # Base agent class
├── code.py                   # 🤖 Code analysis agent
└── final.py                  # 🤖 Final response agent
```

### Testing Directory (`tests/`)
```
tests/
├── conftest.py               # Pytest configuration
├── test_cedar_tools.py       # Tool testing
├── test_core_functionality.py # Core features
├── test_websocket_chat.py    # 🤖 WebSocket chat tests
├── test_file_llm.py          # 🤖 File LLM classification tests
├── test_playwright_*.py      # E2E browser tests (9 files)
├── test_threads_new_json.py  # Thread JSON handling
├── test_tool_functions.py    # Tool function tests
└── [17 more test files...]   # Various component tests
```

### Packaging & Distribution (`packaging/`)
```
packaging/
├── README.md                 # Packaging instructions
├── build_dmg.sh             # Basic DMG builder
├── build_qt_dmg.sh          # Qt-based DMG builder
├── build_server_dmg.sh      # Server DMG builder
├── py2app_setup.py          # Python app bundling
├── requirements-app.txt     # App dependencies
├── requirements-macos.txt   # macOS dependencies
└── build-embedded/          # Embedded build artifacts
```

## LLM-Driven Components

### 1. Chat Orchestration System 🤖
**Location**: `cedar_orchestrator/ws_chat.py`, `cedar_orchestrator/advanced_orchestrator.py`

The chat system uses a sophisticated prompt engineering approach:

```python
# System Prompt Structure (simplified)
SYSTEM_PROMPT = """
You are an AI assistant helping with data analysis and research.
You have access to the following tools:
- code: Execute Python code
- db: Query databases
- web: Search and extract web content
- compose: Generate documents
- plan: Create execution plans

Current Context:
- Project: {project_name}
- Branch: {branch_name}
- Files: {available_files}

Guidelines:
1. Always validate inputs before processing
2. Prefer structured outputs (JSON/tables)
3. Chain operations for complex tasks
4. Provide clear explanations
"""
```

**Key Features**:
- Multi-turn conversation with context retention
- Tool calling with automatic validation
- Parallel execution of independent tasks
- Automatic error recovery and retries

### 2. File Classification System 🤖
**Location**: `cedar_app/llm/client.py`, `cedar_app/file_upload_handler.py`

When files are uploaded, they're automatically classified:

```python
# Classification Prompt Template
CLASSIFY_PROMPT = """
Analyze this file and provide:
1. structure: one of [images|sources|code|tabular]
2. ai_title: descriptive title (max 100 chars)
3. ai_description: summary (max 350 chars)
4. ai_category: category (max 100 chars)

File info:
- Name: {filename}
- Type: {mime_type}
- Size: {size}
- Preview: {content_preview}

Return JSON only.
"""
```

### 3. Code Analysis Agent 🤖
**Location**: `agents/code.py`, `cedar_langextract.py`

Analyzes code files for:
- Function/class extraction
- Dependency mapping
- Documentation generation
- Test coverage suggestions

### 4. Tabular Import Intelligence 🤖
**Location**: `cedar_app/llm/tabular_import.py`, `cedar_tools_modules/tabular_import.py`

Smart CSV/Excel import with:
- Automatic schema detection
- Data type inference
- Missing value handling
- Relationship discovery

### 5. Planning & Execution System 🤖
**Location**: `cedar_tools_modules/plan.py`, `thinker.py`

The "Thinker" system for complex multi-step operations:

```python
# Planning Prompt Structure
PLAN_PROMPT = """
Create a step-by-step plan to: {user_request}

Available resources:
- Files: {files}
- Databases: {databases}
- Tools: {tools}

Output a JSON plan with:
- steps: ordered list of operations
- dependencies: step dependencies
- expected_outputs: what each step produces
- success_criteria: how to verify completion
"""
```

## Prompt Engineering & LLM Integration

### Prompt Patterns Used

1. **Chain-of-Thought (CoT)**
   - Used in: `thinker.py`, planning operations
   - Forces step-by-step reasoning

2. **Few-Shot Learning**
   - Used in: File classification, code analysis
   - Provides examples in prompts

3. **Structured Output Enforcement**
   - All LLM calls specify JSON schemas
   - Validation and retry on malformed outputs

4. **Context Window Management**
   - Smart truncation of long inputs
   - Chunking strategies for large files

5. **Tool Use Patterns**
   ```python
   # Example from orchestrator
   TOOL_USE_PROMPT = """
   You need to {task}.
   
   Available tools:
   {tool_descriptions}
   
   Call tools like:
   {"function": "tool_name", "args": {...}}
   
   Chain multiple tools if needed.
   ```

### LLM Configuration

**Environment Variables**:
```bash
CEDARPY_OPENAI_API_KEY=sk-...     # OpenAI API key
CEDARPY_OPENAI_MODEL=gpt-4        # Model selection
CEDARPY_FILE_LLM=1                 # Enable file classification
CEDARPY_TEST_MODE=1                # Use deterministic stubs for testing
```

**Model Selection Strategy**:
- GPT-4 for complex reasoning (planning, code analysis)
- GPT-3.5 for simple classification tasks
- Local models supported via OpenAI-compatible APIs

## Code Duplication & Refactoring Opportunities

### Identified Duplications

1. **File Upload Handling** ⚠️
   - `cedar_app/file_upload_handler.py`
   - `cedar_app/utils/file_upload.py`
   - `cedar_app/utils/file_operations.py`
   - **Recommendation**: Consolidate into single module

2. **SQL Execution** ⚠️
   - `cedar_app/utils/sql_utils.py`
   - `cedar_app/utils/sql_websocket.py`
   - `cedar_app/routes/sql_routes.py` (stub)
   - SQL logic in `main_impl_full.py`
   - **Recommendation**: Complete sql_routes.py implementation

3. **Thread Management** ⚠️
   - `cedar_app/utils/thread_management.py`
   - `cedar_app/utils/thread_chat.py`
   - `cedar_app/routes/thread_routes.py`
   - **Recommendation**: Merge chat functionality into thread_routes

4. **WebSocket Handlers** ⚠️
   - `cedar_app/utils/websocket_chat.py`
   - `cedar_orchestrator/ws_chat.py`
   - WebSocket code in `main_impl_full.py`
   - **Recommendation**: Single WebSocket manager

5. **Tool Implementations** ⚠️
   - `cedar_tools/` (15 files)
   - `cedar_tools_modules/` (13 files)
   - Significant overlap between directories
   - **Recommendation**: Remove cedar_tools/, use only cedar_tools_modules/

6. **Main Entry Points** ⚠️
   - `main.py` (thin orchestrator)
   - `main_impl_full.py` (1590 lines)
   - `cedar_app/main.py` (new refactored)
   - `cedar_app/web_ui.py` (new UI entry)
   - **Recommendation**: Complete migration to cedar_app/main.py

7. **Orchestrator Implementations** ⚠️
   - `orchestrator.py` (root level)
   - `cedar_app/orchestrator.py`
   - `cedar_orchestrator/advanced_orchestrator.py`
   - **Recommendation**: Remove legacy orchestrators

8. **File Utilities** ⚠️
   - `cedar_app/file_utils.py`
   - `cedar_app/utils/file_utils.py`
   - `cedar_app/utils/file_management.py`
   - **Recommendation**: Consolidate file operations

### Refactoring Progress

**Completed**:
- ✅ Extracted UI views to `utils/ui_views.py`
- ✅ Extracted code collection to `utils/code_collection.py`
- ✅ Created modular route structure in `routes/`
- ✅ Separated project/thread creation

**In Progress**:
- 🔄 Migrating from `main_impl_full.py` to modular structure
- 🔄 Consolidating tool implementations
- 🔄 Removing duplicate orchestrators

**Planned**:
- 📋 Complete SQL route implementation
- 📋 Unify WebSocket handling
- 📋 Consolidate file operations
- 📋 Remove legacy code

## Testing Structure

### Test Categories

1. **Unit Tests**
   - `test_core_functionality.py` - Core features
   - `test_cedar_tools.py` - Tool implementations
   - `test_config.py` - Configuration

2. **Integration Tests**
   - `test_websocket_chat.py` - WebSocket communication
   - `test_file_llm.py` - LLM file processing
   - `test_project_management.py` - Project operations

3. **E2E Browser Tests** (Playwright)
   - `test_playwright_chat_submit.py` - Chat interactions
   - `test_playwright_upload.py` - File uploads
   - `test_playwright_merge.py` - Branch merging
   - `test_playwright_shell.py` - Shell execution

4. **Performance Tests**
   - WebSocket stress testing
   - LLM response time monitoring
   - Database query optimization

### Test Utilities

**Deterministic LLM Testing**:
```python
# When CEDARPY_TEST_MODE=1
- Returns fixed JSON responses
- No external API calls
- Predictable classification results
- Stable CI/CD pipeline
```

## Deployment & Packaging

### Desktop Application (Qt)
```bash
# Build Qt-based DMG for macOS
bash packaging/build_qt_dmg.sh

# Creates: packaging/dist-qt/CedarPy-qt.dmg
# Features: Dock icon, native quit, embedded browser
```

### Server Deployment
```bash
# Standard FastAPI deployment
uvicorn cedar_app.main:app --host 0.0.0.0 --port 8000

# Or use run_cedarpy.py for logging
python run_cedarpy.py
```

### Docker Deployment (Planned)
```dockerfile
# Dockerfile (to be created)
FROM python:3.11
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app
WORKDIR /app
CMD ["uvicorn", "cedar_app.main:app"]
```

## Configuration & Environment

### Critical Environment Variables

```bash
# LLM Configuration
CEDARPY_OPENAI_API_KEY=sk-...     # OpenAI API key
CEDARPY_OPENAI_MODEL=gpt-4        # Model to use
CEDARPY_FILE_LLM=1                 # Enable file classification

# Database
CEDARPY_DATABASE_URL=sqlite:///... # Or mysql+pymysql://...
CEDARPY_MYSQL_URL=mysql+pymysql://... # MySQL connection

# File Storage
CEDARPY_DATA_DIR=~/CedarPyData    # Data directory
CEDARPY_UPLOAD_DIR=./uploads      # Upload directory

# Features
CEDARPY_TEST_MODE=1                # Use LLM stubs for testing
CEDARPY_UPLOAD_AUTOCHAT=1          # Auto-start chat on upload
CEDARPY_SHELL_ENABLED=1            # Enable shell execution
CEDARPY_SHELL_TOKEN=secret         # Shell API token

# Logging
CEDARPY_LOG_DIR=~/Library/Logs/CedarPy  # Log directory
CEDARPY_TRACE=1                    # Ultra-verbose tracing

# UI
CEDARPY_QT_HARNESS=1              # Qt harness mode
CEDARPY_HOST=127.0.0.1            # Server host
CEDARPY_PORT=8000                 # Server port
```

### Configuration Files

1. **`.env`** (Git-ignored)
   ```env
   OPENAI_API_KEY=sk-...
   CEDARPY_MYSQL_URL=mysql+pymysql://...
   ```

2. **`pyproject.toml`**
   - Python package configuration
   - Dependency specifications
   - Build settings

3. **`requirements.txt`** (Main dependencies)
   - FastAPI, SQLAlchemy, PySide6
   - OpenAI, LangChain (planned)
   - Playwright for testing

## Next Steps & Recommendations

### Immediate Priorities

1. **Complete SQL Route Implementation**
   - Replace stub in `routes/sql_routes.py`
   - Migrate SQL logic from `main_impl_full.py`

2. **Consolidate File Operations**
   - Single module for all file operations
   - Remove duplicate implementations

3. **Unify WebSocket Handling**
   - Single WebSocket manager
   - Consistent error handling

4. **Remove Legacy Code**
   - Delete superseded orchestrators
   - Clean up old tool implementations

### Long-term Improvements

1. **Add Comprehensive Documentation**
   - API documentation (OpenAPI/Swagger)
   - Developer guides
   - Deployment documentation

2. **Implement Monitoring**
   - LLM token usage tracking
   - Performance metrics
   - Error tracking (Sentry integration)

3. **Enhance Testing**
   - Increase test coverage to >80%
   - Add load testing
   - Implement contract testing for LLM interactions

4. **Security Enhancements**
   - API rate limiting
   - Input sanitization
   - Secure file upload validation
   - RBAC implementation

5. **Performance Optimization**
   - Database query optimization
   - Caching layer (Redis)
   - Async/background job processing
   - CDN for static assets

## Contributing

When contributing to Cedar:

1. **Follow the modular structure** - Place new code in appropriate utils/routes modules
2. **Document LLM prompts** - Use clear prompt templates with examples
3. **Add tests** - Minimum 80% coverage for new features
4. **Update this README** - Keep documentation current
5. **Use environment variables** - Never hardcode sensitive data
6. **Mark LLM components** - Use 🤖 emoji in comments for LLM-driven code

---

*Last Updated: September 25, 2025*
*Version: 2.0.0-refactor*
*Maintainer: Cedar Development Team*