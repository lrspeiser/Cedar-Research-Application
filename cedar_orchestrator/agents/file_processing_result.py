"""
File Processing Result and Constants
Shared utilities for file processing agents
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# PDF and image processing libraries availability
try:
    import fitz  # PyMuPDF for digital PDFs
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    from PIL import Image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# For language extraction
try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


@dataclass
class FileProcessingResult:
    """Result from a file processing agent"""
    agent_name: str
    success: bool
    data: Any
    metadata: Dict[str, Any]
    error: Optional[str] = None
    extracted_files: List[str] = None  # Paths to extracted files