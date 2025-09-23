from __future__ import annotations

import os
import json
from typing import Any, Tuple

# Helper to obtain an OpenAI client and model. Uses a small stub in test mode.
# Keys: see README "Keys & Env" (env or ~/CedarPyData/.env)

def get_client_and_model(model_env_var: str, default_model: str) -> Tuple[Any, str | None]:
    test_mode = str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower() in {"1","true","yes","on"}
    if test_mode:
        class _Msg:  # minimal shape for OpenAI SDK compatibility
            def __init__(self, content: str):
                self.message = type("M", (), {"content": content})()
        class _Choices:
            def __init__(self, content: str):
                self.choices = [_Msg(content)]
        class _Chat:
            def __init__(self):
                self.completions = self
            def create(self, model: str, messages: list[dict]) -> Any:  # type: ignore[override]
                # Simple routing based on prompts
                joined = "\n".join([str(m.get("content") or "") for m in messages])
                if "Generate the code now." in joined or "run_import(" in joined:
                    code = '''\
import csv, sqlite3, re, io

def _snake(s):
    s = re.sub(r'[^0-9a-zA-Z]+', '_', str(s or '').strip()).strip('_').lower()
    if not s:
        s = 'col'
    if s[0].isdigit():
        s = 'c_' + s
    return s

def run_import(src_path, sqlite_path, table_name, project_id, branch_id):
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS ' + table_name)
    with open(src_path, newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        header = next(r, None)
        rows_buf = None
        if header and len(header) > 0:
            cols = [_snake(h) for h in header]
        else:
            row = next(r, None)
            if row is None:
                cols = ['col_1']
                rows_buf = []
            else:
                n = max(1, len(row))
                cols = ['col_' + str(i+1) for i in range(n)]
                rows_buf = [row]
        col_defs = ', '.join([c + ' TEXT' for c in cols])
        cur.execute('CREATE TABLE IF NOT EXISTS ' + table_name + ' (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, branch_id INTEGER NOT NULL, ' + col_defs + ')')
        placeholders = ','.join(['?'] * (2 + len(cols)))
        insert_sql = 'INSERT INTO ' + table_name + ' (project_id, branch_id, ' + ','.join(cols) + ') VALUES (' + placeholders + ')'
        ins = 0
        if rows_buf is not None:
            for row in rows_buf:
                vals = [project_id, branch_id] + [ (row[i] if i < len(row) else None) for i in range(len(cols)) ]
                cur.execute(insert_sql, vals)
                ins += 1
        for row in r:
            vals = [project_id, branch_id] + [ (row[i] if i < len(row) else None) for i in range(len(cols)) ]
            cur.execute(insert_sql, vals)
            ins += 1
    conn.commit(); conn.close()
    return {"ok": True, "table": table_name, "rows_inserted": ins, "columns": cols, "warnings": []}
'''
                    return _Choices(code)
                if "You are Cedar's aggregator" in joined or 'function":"final"' in joined:
                    return _Choices(json.dumps({"function":"final","args":{"text":"Done.","title":"Assistant","run_summary":["test-mode"]}}))
                if "You are Cedar's plan generator" in joined or '"function": "plan"' in joined:
                    plan = {"function":"plan","title":"Test Plan","status":"in queue","state":"new plan","steps":[{"function":"web","title":"Search","status":"in queue","state":"new plan","args":{"query":"example"}}],"output_to_user":"Plan ready","changelog_summary":"created plan"}
                    return _Choices(json.dumps(plan))
                # Default: echo last user content
                last_user = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
                return _Choices(str(last_user or ""))
        class _Client:
            def __init__(self):
                self.chat = _Chat()
        return _Client(), os.getenv(model_env_var) or default_model
    # Real client
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, None
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, None
    model = os.getenv(model_env_var) or default_model
    return OpenAI(api_key=api_key), model


def summarize_comment(action: str, payload: dict) -> str | None:
    """Optional lightweight summarization for tool outputs. Returns None if no key."""
    client, model = get_client_and_model("CEDARPY_SUMMARY_MODEL", "gpt-5-nano")
    if not client or not model:
        return None
    try:
        sys = "You produce a 1-2 sentence, factual, terse summary for a UI log."
        content = json.dumps({"action": action, "payload": payload}, ensure_ascii=False)
        resp = client.chat.completions.create(model=model, messages=[{"role":"system","content":sys},{"role":"user","content":content}])
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None