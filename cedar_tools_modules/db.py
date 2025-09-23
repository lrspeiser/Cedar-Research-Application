from __future__ import annotations

def tool_db(*, project_id: int, sql_text: str, execute_sql) -> dict:
    if not sql_text.strip():
        return {"ok": False, "error": "sql required"}
    try:
        return execute_sql(sql_text, project_id, max_rows=200)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}