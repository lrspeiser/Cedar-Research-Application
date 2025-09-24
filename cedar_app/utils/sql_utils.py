"""
SQL utilities for Cedar app.
Handles SQL execution and result formatting.
"""

from typing import Dict, Any, List
from sqlalchemy import text

def execute_sql(engine, query: str) -> Dict[str, Any]:
    """Execute SQL query and return results."""
    try:
        with engine.begin() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                rows = result.fetchall()
                columns = list(result.keys())
                return {
                    "ok": True,
                    "columns": columns,
                    "rows": [list(row) for row in rows]
                }
            else:
                return {
                    "ok": True,
                    "rowcount": result.rowcount
                }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }
