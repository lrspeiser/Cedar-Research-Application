import os
import sys
import pathlib

# Ensure repo root importable
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import cedar_tools as ct


def test_tool_shell_echo_hello():
    res = ct.tool_shell(script="echo hello")
    assert res.get("ok") is True
    assert "hello" in (res.get("stdout") or "")


def test_tool_db_stub_execute_sql():
    calls = {}
    def _exec(sql_text: str, project_id: int, max_rows: int = 200):
        calls["sql"] = sql_text
        calls["project_id"] = project_id
        calls["max_rows"] = max_rows
        return {"success": True, "columns": ["n"], "rows": [[1]]}
    out = ct.tool_db(project_id=1, sql_text="SELECT 1", execute_sql=_exec)
    assert out.get("ok") is not False
    assert out.get("columns") == ["n"]


def test_tool_web_fetch_example_org():
    res = ct.tool_web(url="https://example.org/")
    assert res.get("ok") is True
    assert isinstance(res.get("bytes"), int) and res.get("bytes") > 0
