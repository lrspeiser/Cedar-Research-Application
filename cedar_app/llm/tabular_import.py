"""
Tabular import module for Cedar app.
Handles importing CSV/TSV/NDJSON files via LLM code generation.
"""

from typing import Dict, Any

def tabular_import_via_llm(
    file_id: int,
    project_id: int,
    branch_id: int,
    db: Any,
    options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Import tabular data using LLM-generated code.
    This is a simplified version - the full function is 218 lines.
    """
    return {
        "ok": False,
        "error": "Tabular import temporarily disabled during refactoring"
    }
