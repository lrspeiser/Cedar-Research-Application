"""
File utilities for Cedar app.
Handles file operations and processing.
"""

import os
import mimetypes
from typing import Optional, Dict, Any

def interpret_file(path: str) -> Dict[str, Any]:
    """Interpret file metadata."""
    if not os.path.exists(path):
        return {"error": "File not found"}
    
    stat = os.stat(path)
    mime_type, _ = mimetypes.guess_type(path)
    
    return {
        "path": path,
        "size_bytes": stat.st_size,
        "mime_type": mime_type,
        "is_text": _is_probably_text(path)
    }

def _is_probably_text(path: str, sample_bytes: int = 4096) -> bool:
    """Check if a file is probably text."""
    try:
        with open(path, "rb") as f:
            sample = f.read(sample_bytes)
        # Simple heuristic: if we can decode as UTF-8, it's probably text
        try:
            sample.decode('utf-8')
            return True
        except UnicodeDecodeError:
            return False
    except Exception:
        return False
