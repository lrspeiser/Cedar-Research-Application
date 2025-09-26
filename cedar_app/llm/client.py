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


def _llm_classify_file(meta: Dict[str, Any], file_content: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Calls GPT model to classify a file and extract its content intelligently.
    For files under 20MB, sends full content for extraction.
    For larger files, uses sample for classification only.
    
    Produces:
    - structure: images | sources | code | tabular 
    - ai_title (<=100), ai_description (<=350), ai_category (<=100)
    - extracted_content: markdown or SQL depending on file type
    - data_schema: for tabular data, includes column descriptions

    Input: metadata produced by interpret_file() and optionally file content

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
    # Determine if we should send full content or just sample
    size_bytes = meta.get("size_bytes", 0)
    send_full_content = size_bytes < 20 * 1024 * 1024  # 20MB limit
    
    # Prepare content to send
    content_to_analyze = file_content if (file_content and send_full_content) else ""
    sample_text = (meta.get("sample_text") or "")
    
    # If we have full content but it's still too large for a single request, truncate
    if content_to_analyze and len(content_to_analyze) > 100000:  # ~100KB text limit for GPT
        content_to_analyze = content_to_analyze[:100000]
        send_full_content = False  # Mark as truncated
    elif not content_to_analyze and sample_text:
        content_to_analyze = sample_text[:8000]
    
    info = {
        k: meta.get(k) for k in [
            "extension","mime_guess","format","language","is_text","size_bytes","line_count",
            "json_valid","json_top_level_keys","csv_dialect","csv_headers"
        ] if k in meta
    }
    
    # Enhanced prompt for content extraction
    sys_prompt = (
        "You are an expert data analyst and librarian. Analyze files and extract their content intelligently.\n"
        "Output strict JSON with these keys:\n"
        "- structure: must be one of: images | sources | code | tabular\n"
        "- ai_title: <= 100 chars, friendly title\n"
        "- ai_description: <= 350 chars, what the file contains\n"
        "- ai_category: <= 100 chars, general category\n"
        "- extracted_content: For text/code files, provide markdown formatted version. "
        "For tabular data, provide SQL CREATE TABLE statement with proper types.\n"
        "- data_schema: For tabular data only, provide object with 'columns' array containing "
        "{name, type, description, sample_values} for each column.\n"
        "\nRules:\n"
        "- For code files, preserve formatting in markdown code blocks\n"
        "- For documents, convert to clean markdown\n" 
        "- For CSVs/tabular, infer column types and provide DDL\n"
        "- For images, just classify (no extraction)\n"
        "- Limit extracted_content to 50KB characters\n"
        "- Do not include newlines in title/description/category values"
    )
    user_payload = {
        "metadata": info,
        "display_name": meta.get("display_name"),
        "file_content": content_to_analyze if send_full_content else None,
        "content_sample": content_to_analyze if not send_full_content else None,
        "is_full_content": send_full_content
    }
    import json as _json
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Analyze this file and produce JSON as specified. Input:"},
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
        
        # Include extracted content and schema if provided
        out = {
            "structure": struct, 
            "ai_title": title, 
            "ai_description": desc, 
            "ai_category": cat,
            "extracted_content": result.get("extracted_content"),
            "data_schema": result.get("data_schema"),
            "was_full_content": send_full_content
        }
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
