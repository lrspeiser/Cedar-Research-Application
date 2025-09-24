"""
Test configuration for CedarPy application testing
"""

import os
from typing import Dict, Any

# Base configuration
BASE_URL = os.getenv("CEDARPY_TEST_URL", "http://localhost:8000")
WS_URL = os.getenv("CEDARPY_WS_URL", "ws://localhost:8000")
TEST_TIMEOUT = int(os.getenv("CEDARPY_TEST_TIMEOUT", "30"))

# Test data
TEST_PROJECT_NAME = "Test Project Auto"
TEST_PROJECT_DESCRIPTION = "Automated test project"
TEST_MATH_QUESTION = "What is the square root of 9393492?"
TEST_SIMPLE_QUESTION = "What is 2 + 2?"

# Expected responses
EXPECTED_MATH_ANSWER_CONTAINS = ["3065", "square root"]  # sqrt(9393492) ≈ 3065.08
EXPECTED_SIMPLE_ANSWER_CONTAINS = ["4", "four"]

# API endpoints
ENDPOINTS = {
    "home": "/",
    "projects": "/projects",
    "api_projects": "/api/projects",
    "api_health": "/api/health",
    "settings": "/settings",
    "shell": "/shell",
    "changelog": "/changelog",
}

# WebSocket endpoints
WS_ENDPOINTS = {
    "chat": "/ws/chat",
    "chat_with_project": "/ws/chat/{project_id}",
}

# Test configuration flags
TEST_CONFIG = {
    "skip_ws_tests": os.getenv("SKIP_WS_TESTS", "").lower() in ("true", "1", "yes"),
    "skip_llm_tests": os.getenv("SKIP_LLM_TESTS", "").lower() in ("true", "1", "yes"),
    "verbose": os.getenv("TEST_VERBOSE", "").lower() in ("true", "1", "yes"),
    "cleanup_after_test": os.getenv("TEST_CLEANUP", "true").lower() in ("true", "1", "yes"),
}

def get_headers() -> Dict[str, str]:
    """Get standard headers for API requests"""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }