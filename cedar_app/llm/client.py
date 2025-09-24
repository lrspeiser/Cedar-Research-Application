"""
LLM client module for Cedar app.
Handles LLM client configuration and classification.
"""

import os
from typing import Optional, Tuple, Dict, Any

def _llm_client_config():
    """
    Returns (client, model) if OpenAI SDK is available and a key is configured.
    Looks up key from env first, then falls back to the user settings file via _env_get.

    CI/Test mode: if CEDARPY_TEST_MODE is truthy, returns a stub client that emits
    deterministic JSON (no network calls). See README: "CI test mode (deterministic LLM stubs)".
    """
    # Test-mode stub (no external calls). Enabled in CI and auto-enabled under pytest/Playwright unless explicitly disabled.
    try:
        _test_mode = str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
        if not _test_mode:
            # Auto-detect test runners
            if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_ADDOPTS") or os.getenv("PW_TEST") or os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
                # Allow explicit override with CEDARPY_TEST_MODE=0
                _explicit = str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower()
                if _explicit not in {"0", "false", "no", "off"}:
                    _test_mode = True
    except Exception:
        _test_mode = False
    if _test_mode:
        try:
            print("[llm-test] CEDARPY_TEST_MODE=1; using stubbed LLM client")
        except Exception:
            pass

        class _StubMsg:
            def __init__(self, content: str):
                self.content = content
        class _StubChoice:
            def __init__(self, content: str):
                self.message = _StubMsg(content)
        class _StubResp:
            def __init__(self, content: str):
                self.choices = [_StubChoice(content)]
        class _StubCompletions:
            def create(self, model: str, messages: list):  # type: ignore[override]
                # Inspect prompt to choose an appropriate deterministic JSON
                try:
                    joined = "\n".join([str((m or {}).get("content") or "") for m in (messages or [])])
                except Exception:
                    joined = ""
                out = None
                try:
                    # Tabular import codegen stub: return valid Python code with run_import()
                    if ("Generate the code now." in joined) or ("run_import(" in joined) or ("ONLY Python source code" in joined and "sqlite" in joined.lower()):
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
    # Drop/recreate table
    cur.execute('DROP TABLE IF EXISTS ' + table_name)
    # Inspect header
    with open(src_path, newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        header = next(r, None)
        rows_buf = None
        if header and len(header) > 0:
            cols = [_snake(h) for h in header]
        else:
            # Peek first data row to decide width
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
                        return _StubResp(code)
                    if "Classify incoming files" in joined or "Classify this file" in joined:
                        # File classification stub
                        out = {
                            "structure": "sources",
                            "ai_title": "Test File",
                            "ai_description": "Deterministic test description",
                            "ai_category": "General"
                        }
                        return _StubResp(json.dumps(out))
                    if "Cedar's orchestrator" in joined or "Schema: { \"Text Visible To User\"" in joined:
                        out = {
                            "Text Visible To User": "Test mode: planning done; finalizing.",
                            "function_calls": [
                                {"name": "final", "args": {"text": "Test mode OK"}}
                            ]
                        }
                        return _StubResp(json.dumps(out))
                    if "This is a research tool" in joined or "Functions include" in joined:
                        out = {"function": "final", "args": {"text": "Test mode (final)", "title": "Test Session"}}
                        return _StubResp(json.dumps(out))
                except Exception:
                    pass
                # Generic minimal final
                out = {"function": "final", "args": {"text": "Test mode", "title": "Test"}}
                return _StubResp(json.dumps(out))
        class _StubChat:
            def __init__(self):
                self.completions = _StubCompletions()
        class _StubClient:
            def __init__(self):
                self.chat = _StubChat()
        return _StubClient(), (os.getenv("CEDARPY_OPENAI_MODEL") or _env_get("CEDARPY_OPENAI_MODEL") or "gpt-5")

    # Normal client
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, None
    # Prefer env, then fallback to settings file
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or _env_get("CEDARPY_OPENAI_API_KEY") or _env_get("OPENAI_API_KEY")
    if not api_key or not str(api_key).strip():
        return None, None
    model = os.getenv("CEDARPY_OPENAI_MODEL") or _env_get("CEDARPY_OPENAI_MODEL") or "gpt-5"
    try:
        client = OpenAI(api_key=str(api_key).strip())
        return client, model
    except Exception:
        return None, None


def _llm_classify_file(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Calls GPT model to classify a file into one of: images | sources | code | tabular
    and produce ai_title (<=100), ai_description (<=350), ai_category (<=100).

    Input: metadata produced by interpret_file(), including:
    - extension, mime_guess, format, language, is_text, size_bytes, line_count, sample_text

    Returns dict or None on error. Errors are logged verbosely.
    """
    if str(os.getenv("CEDARPY_FILE_LLM", "1")).strip().lower() in {"0","false","no","off"}:
        try:
            print("[llm-skip] CEDARPY_FILE_LLM=0")
        except Exception:
            pass
        return None
    client, model = _llm_client_config()
    if not client:
        try:
            print("[llm-skip] missing OpenAI API key; set CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY")
        except Exception:
            pass
        return None
    # Prepare a bounded sample
    sample_text = (meta.get("sample_text") or "")
    if len(sample_text) > 8000:
        sample_text = sample_text[:8000]
    info = {
        k: meta.get(k) for k in [
            "extension","mime_guess","format","language","is_text","size_bytes","line_count","json_valid","json_top_level_keys","csv_dialect"
        ] if k in meta
    }
    sys_prompt = (
        "You are an expert data librarian. Classify incoming files and produce short, friendly labels.\n"
        "Output strict JSON with keys: structure, ai_title, ai_description, ai_category.\n"
        "Rules: structure must be one of: images | sources | code | tabular.\n"
        "ai_title <= 100 chars. ai_description <= 350 chars. ai_category <= 100 chars.\n"
        "Do not include newlines in values. If in doubt, choose the best fit."
    )
    user_payload = {
        "metadata": info,
        "display_name": meta.get("display_name"),
        "snippet_utf8": sample_text,
    }
    import json as _json
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Classify this file and produce JSON as specified. Input:"},
        {"role": "user", "content": _json.dumps(user_payload, ensure_ascii=False)},
    ]
    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        content = (resp.choices[0].message.content or "").strip()
        result = _json.loads(content)
        # Normalize and enforce limits
        struct = str(result.get("structure"," ")).strip().lower()
        if struct not in {"images","sources","code","tabular"}:
            struct = None
        def _clip(s, n):
            s = '' if s is None else str(s)
            return s[:n]
        title = _clip(result.get("ai_title"), 100)
        desc = _clip(result.get("ai_description"), 350)
        cat = _clip(result.get("ai_category"), 100)
        out = {"structure": struct, "ai_title": title, "ai_description": desc, "ai_category": cat}
        try:
            print(f"[llm] model={model} structure={struct} title={len(title)} chars cat={cat}")
        except Exception:
            pass
        return out
    except Exception as e:
        try:
            print(f"[llm-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None
