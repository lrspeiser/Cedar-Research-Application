"""
File Processing Utilities for Cedar
====================================

This module contains all file processing and interpretation utilities including:
- File type detection
- Text vs binary detection
- Metadata extraction
- JSON/CSV validation
- Hash computation
"""

import os
import csv
import json
import hashlib
import mimetypes
from datetime import datetime, timezone
from typing import Dict, Any

# Import file_extension_to_type from main_helpers
from main_helpers import file_extension_to_type


def is_probably_text(path: str, sample_bytes: int = 4096) -> bool:
    """
    Determine if a file is probably text by examining its content.
    
    Args:
        path: Path to the file to check
        sample_bytes: Number of bytes to sample from the file
        
    Returns:
        True if the file is probably text, False otherwise
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_bytes)
        if b"\x00" in chunk:
            return False
        # If mostly ASCII or UTF-8 bytes, consider text
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
        nontext = chunk.translate(None, text_chars)
        return len(nontext) / (len(chunk) or 1) < 0.30
    except Exception:
        return False


def interpret_file(path: str, original_name: str) -> Dict[str, Any]:
    """
    Extracts comprehensive metadata from a file for storage in FileEntry.metadata_json.
    
    This function performs best-effort analysis using extension/mime and light parsing,
    avoiding heavy dependencies.
    
    Args:
        path: Absolute path to the file on disk
        original_name: Original filename (may differ from path basename)
        
    Returns:
        Dictionary containing file metadata including size, type, format, language,
        text sample, validation results for JSON/CSV, line count, and SHA256 hash.
    """
    meta: Dict[str, Any] = {}
    
    # Basic file stats
    try:
        stat = os.stat(path)
        meta["size_bytes"] = stat.st_size
        meta["mtime"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        meta["ctime"] = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()
    except Exception:
        pass

    # Extension and MIME type
    ext = os.path.splitext(original_name)[1].lower().lstrip(".")
    meta["extension"] = ext
    mime, _ = mimetypes.guess_type(original_name)
    meta["mime_guess"] = mime or ""

    # Format (high-level) and language
    ftype = file_extension_to_type(original_name)
    meta["format"] = ftype
    language_map = {
        "python": "Python", "rust": "Rust", "javascript": "JavaScript", "typescript": "TypeScript",
        "c": "C", "c-header": "C", "cpp": "C++", "cpp-header": "C++", 
        "objective-c": "Objective-C", "objective-c++": "Objective-C++",
        "java": "Java", "kotlin": "Kotlin", "go": "Go", "ruby": "Ruby", 
        "php": "PHP", "csharp": "C#", "swift": "Swift", "scala": "Scala", 
        "haskell": "Haskell", "clojure": "Clojure", "elixir": "Elixir", 
        "erlang": "Erlang", "lua": "Lua", "r": "R", "perl": "Perl", "shell": "Shell",
    }
    meta["language"] = language_map.get(ftype)

    # Text / binary detection
    is_text = is_probably_text(path)
    meta["is_text"] = is_text

    # Store a UTF-8 text sample of the first N bytes (for LLM inspection)
    try:
        limit = int(os.getenv("CEDARPY_SAMPLE_BYTES", "65536"))
    except Exception:
        limit = 65536
    
    try:
        with open(path, "rb") as f:
            sample_b = f.read(max(0, limit))
        sample_text = sample_b.decode("utf-8", errors="replace")
        meta["sample_text"] = sample_text
        meta["sample_bytes_read"] = len(sample_b)
        meta["sample_truncated"] = (meta.get("size_bytes") or 0) > len(sample_b)
        meta["sample_encoding"] = "utf-8-replace"
    except Exception:
        pass

    # Text-specific analysis
    if is_text:
        # JSON validation for .json / .ndjson / .ipynb
        if ext in {"json", "ndjson", "ipynb"}:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    if ext == "ndjson":
                        # Count lines and JSON-parse first line only
                        first = f.readline()
                        json.loads(first)
                        meta["json_valid"] = True
                    else:
                        data = json.load(f)
                        meta["json_valid"] = True
                        if isinstance(data, dict):
                            meta["json_top_level_keys"] = list(data.keys())[:50]
                        elif isinstance(data, list):
                            meta["json_list_length_sample"] = min(len(data), 1000)
            except Exception:
                meta["json_valid"] = False
                
        # CSV dialect detection
        if ext in {"csv", "tsv"}:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    sample = f.read(2048)
                dialect = csv.Sniffer().sniff(sample)
                meta["csv_dialect"] = {
                    "delimiter": getattr(dialect, "delimiter", ","),
                    "quotechar": getattr(dialect, "quotechar", '"'),
                    "doublequote": getattr(dialect, "doublequote", True),
                    "skipinitialspace": getattr(dialect, "skipinitialspace", False),
                }
            except Exception:
                pass
                
        # Line count (bounded to avoid excessive memory usage)
        try:
            lc = 0
            with open(path, "rb") as f:
                for i, _ in enumerate(f):
                    lc = i + 1
                    if lc > 2000000:
                        break
            meta["line_count"] = lc
        except Exception:
            pass

    # SHA256 hash computation
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        meta["sha256"] = h.hexdigest()
    except Exception:
        pass

    return meta