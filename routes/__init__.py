"""
Routes package for Cedar application.

This package contains FastAPI router modules extracted from main.py to keep
the main file under 1000 lines as per project rules.

Modules:
- ui_routes: User interface pages (home, settings, logs, merge)
- project_routes: Project CRUD and management endpoints
- api_routes: REST API endpoints
- websocket_routes: WebSocket handlers

Each router module can be included in the main FastAPI app using app.include_router().
"""

__all__ = [
    'ui_routes',
    'project_routes',
    'api_routes',
    'websocket_routes',
]