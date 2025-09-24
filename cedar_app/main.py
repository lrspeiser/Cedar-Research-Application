"""
Main FastAPI application for Cedar.
This is the entry point for the refactored Cedar app.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from cedar_app.config import initialize_directories
from cedar_app.database import Base, registry_engine
from cedar_app.routes import (
    main_routes,
    project_routes,
    file_routes,
    thread_routes,
    shell_routes,
    websocket_routes,
    log_routes,
)
from cedar_app.utils.logging import _install_unified_logging

# Initialize app
app = FastAPI(title="Cedar", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize logging
_install_unified_logging()

# Register routes
app.include_router(main_routes.router)
app.include_router(project_routes.router, prefix="/project")
app.include_router(file_routes.router, prefix="/files")
app.include_router(thread_routes.router, prefix="/threads")
app.include_router(shell_routes.router, prefix="/shell")
app.include_router(websocket_routes.router, prefix="/ws")
app.include_router(log_routes.router, prefix="/log")

# Mount static files if needed
# app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
