"""
Cedar app package.

Note: Avoid importing the FastAPI app at package import time to prevent
side effects and missing-module errors in source builds (cedar_app/main.py
is only present in packaged distributions).
"""

__version__ = "2.0.0"
# Intentionally do not export app here; app is defined in top-level main.py
__all__: list[str] = []
