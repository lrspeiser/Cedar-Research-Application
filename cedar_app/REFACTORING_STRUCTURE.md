# Cedar App Module Structure

This document describes the refactored module organization for the Cedar app, breaking down the monolithic `main_impl_full.py` into smaller, manageable modules.

## Module Organization

```
cedar_app/
├── __init__.py              # Package initialization
├── config.py                # Configuration and environment setup
├── database.py              # Database engines and connection management
├── models.py                # SQLAlchemy models (from main_models.py)
├── llm/                     # LLM-related functionality
│   ├── __init__.py
│   ├── client.py            # LLM client configuration
│   ├── classification.py    # File classification via LLM
│   └── tabular_import.py    # Tabular data import via LLM
├── tools/                   # Tool functions
│   ├── __init__.py
│   ├── file_ops.py          # File operations
│   ├── web_scraper.py       # Web scraping
│   └── shell.py             # Shell execution
├── routes/                  # API routes
│   ├── __init__.py
│   ├── main.py              # Main page and basic routes
│   ├── projects.py          # Project management routes
│   ├── files.py             # File upload and management
│   ├── threads.py           # Thread/chat routes
│   ├── shell.py             # Shell API routes
│   ├── websocket.py         # WebSocket endpoints
│   └── logs.py              # Logging routes
├── utils/                   # Utility functions
│   ├── __init__.py
│   ├── html.py              # HTML generation and layout
│   ├── logging.py           # Logging setup
│   └── helpers.py           # General helpers
└── main.py                  # FastAPI app initialization
```

## Migration Steps

1. Create directory structure
2. Extract configuration to `config.py`
3. Extract database setup to `database.py`
4. Extract LLM functions to `llm/` modules
5. Extract tool functions to `tools/` modules
6. Extract routes to `routes/` modules
7. Extract utilities to `utils/` modules
8. Create main app initialization in `main.py`
9. Update all imports
10. Delete `main_impl_full.py`