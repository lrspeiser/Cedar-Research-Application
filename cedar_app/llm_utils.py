"""
LLM Utilities Module
====================

This module contains all LLM-related functionality for Cedar, including:
- LLM client configuration
- File classification
- Action summarization  
- Dataset naming
- Tabular import via code generation

See README for configuration and troubleshooting.
"""

import os
import re
import json
import csv
import io
import contextlib
import sqlite3
import math
import builtins
import types
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

# ----------------------------------------------------------------------------------
# LLM Configuration and Client
# ----------------------------------------------------------------------------------

def llm_client_config():
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
                        code = '''import csv, sqlite3, re, io

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


def _env_get(k: str) -> Optional[str]:
    """Helper to get environment variables from settings file"""
    from cedar_app.config import DATA_DIR
    SETTINGS_PATH = os.path.join(DATA_DIR, ".env")
    try:
        v = os.getenv(k)
        if v is None and os.path.isfile(SETTINGS_PATH):
            # Fallback: try file parse
            with open(SETTINGS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    kk, vv = s.split("=", 1)
                    if kk.strip() == k:
                        return vv.strip().strip('"').strip("'")
        return v
    except Exception:
        return None


# ----------------------------------------------------------------------------------
# File Classification
# ----------------------------------------------------------------------------------

def llm_classify_file(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    client, model = llm_client_config()
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
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Classify this file and produce JSON as specified. Input:"},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        content = (resp.choices[0].message.content or "").strip()
        result = json.loads(content)
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


# ----------------------------------------------------------------------------------
# Action Summarization
# ----------------------------------------------------------------------------------

def llm_summarize_action(action: str, input_payload: Dict[str, Any], output_payload: Dict[str, Any]) -> Optional[str]:
    """Summarize an action for the changelog using a small, fast model.
    Default model: gpt-5-nano (override via CEDARPY_SUMMARY_MODEL).
    Returns summary text or None on error/missing key.

    CI/Test mode: if CEDARPY_TEST_MODE is truthy, return a deterministic summary without calling the API.
    See README: "CI test mode (deterministic LLM stubs)".
    """
    try:
        if str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}:
            return f"TEST: {action} — ok"
    except Exception:
        pass
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("CEDARPY_SUMMARY_MODEL", "gpt-5-nano")
    try:
        client = OpenAI(api_key=api_key)
        sys_prompt = (
            "You are Cedar's changelog assistant. Summarize the action in 1-3 concise sentences. "
            "Focus on what changed, why, and outcomes (including errors). Avoid secrets and long dumps."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Action: {action}"},
            {"role": "user", "content": "Input payload:"},
            {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
            {"role": "user", "content": "Output payload:"},
            {"role": "user", "content": json.dumps(output_payload, ensure_ascii=False)},
        ]
        resp = client.chat.completions.create(model=model, messages=messages)
        text = (resp.choices[0].message.content or "").strip()
        return text
    except Exception as e:
        try:
            print(f"[llm-summary-error] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


# ----------------------------------------------------------------------------------
# Dataset Naming
# ----------------------------------------------------------------------------------

def llm_dataset_friendly_name(file_rec, table_name: str, columns: List[str]) -> Optional[str]:
    """Suggest a short, human-friendly dataset name based on file metadata and columns.
    Uses a small/fast model. Returns None on error or when key is missing.
    In test mode, returns a deterministic fallback.
    """
    try:
        if str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}:
            base = (file_rec.ai_title or file_rec.display_name or table_name or "Data").strip()
            return (base[:60] if base else "Test Dataset")
    except Exception:
        pass
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    api_key = os.getenv("CEDARPY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("CEDARPY_SUMMARY_MODEL", "gpt-5-nano")
    try:
        client = OpenAI(api_key=api_key)
        sys_prompt = (
            "You propose concise, human-friendly dataset names (<= 60 chars). "
            "Use the provided file title, category, and columns. Output plain text only."
        )
        info = {
            "file_title": (file_rec.ai_title or file_rec.display_name),
            "category": file_rec.ai_category,
            "table": table_name,
            "columns": list(columns or [])[:20],
        }
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps(info, ensure_ascii=False)}
        ]
        resp = client.chat.completions.create(model=model, messages=messages)
        name = (resp.choices[0].message.content or "").strip()
        name = name.replace("\n", " ").strip()
        if len(name) > 60:
            name = name[:60]
        return name or None
    except Exception as e:
        try:
            print(f"[dataset-namer] {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


# ----------------------------------------------------------------------------------
# Tabular Import via LLM Codegen
# ----------------------------------------------------------------------------------

def snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name or "").strip("_")
    s = re.sub(r"_+", "_", s)
    s = s.lower()
    if not s:
        s = "t"
    if s[0].isdigit():
        s = "t_" + s
    return s


def suggest_table_name(display_name: str) -> str:
    base = os.path.splitext(os.path.basename(display_name or "table"))[0]
    return snake_case(base)


def extract_code_from_markdown(s: str) -> str:
    try:
        m = re.search(r"```python\n(.*?)```", s, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1)
        m2 = re.search(r"```\n(.*?)```", s, flags=re.DOTALL)
        if m2:
            return m2.group(1)
        return s
    except Exception:
        return s


def tabular_import_via_llm(project_id: int, branch_id: int, file_rec, db: Session, 
                           project_dirs_fn, get_project_engine_fn, Dataset,
                           options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate Python code via LLM to import a tabular file into the per-project SQLite DB and execute it safely.
    - Uses only stdlib modules (csv/json/sqlite3/re/io) in a restricted exec environment.
    - Creates a branch-aware table with columns: id (INTEGER PRIMARY KEY AUTOINCREMENT), project_id, branch_id, + inferred columns.
    - Inserts rows scoped to (project_id, branch_id).
    Returns a result dict with keys: ok, table, rows_inserted, columns, warnings, logs, code_size, model.
    """
    # Determine DB path and table suggestion
    paths = project_dirs_fn(project_id)
    sqlite_path = paths.get("db_path")
    src_path = os.path.abspath(file_rec.storage_path or "")
    table_suggest = suggest_table_name(file_rec.display_name or file_rec.filename or "data")

    # Collect lightweight metadata for prompt
    meta = file_rec.metadata_json or {}
    sample_text = (meta.get("sample_text") or "")
    if len(sample_text) > 4000:
        sample_text = sample_text[:4000]
    info = {
        "extension": meta.get("extension"),
        "mime_guess": meta.get("mime_guess"),
        "csv_dialect": meta.get("csv_dialect"),
        "line_count": meta.get("line_count"),
        "size_bytes": meta.get("size_bytes"),
    }

    client, model_default = llm_client_config()
    if not client:
        return {"ok": False, "error": "missing OpenAI key", "model": None}
    model = os.getenv("CEDARPY_TABULAR_MODEL") or model_default or "gpt-5"

    sys_prompt = (
        "You generate safe, robust Python 3 code to import a local tabular file into SQLite.\n"
        "Requirements:\n"
        "- Define a function run_import(src_path, sqlite_path, table_name, project_id, branch_id) -> dict.\n"
        "- Use ONLY Python standard library modules: csv, json, sqlite3, re, io, typing, math.\n"
        "- Do NOT use pandas, requests, openpyxl, numpy, duckdb, or any external libraries.\n"
        "- Create table if not exists with schema: id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, branch_id INTEGER NOT NULL, and columns inferred from the file.\n"
        "- Infer column names from headers (for CSV/TSV) or keys (for NDJSON). Normalize to snake_case, TEXT/INTEGER/REAL types conservatively.\n"
        "- Insert rows with project_id and branch_id set from the function arguments.\n"
        "- If this is a re-import, you may DROP TABLE IF EXISTS <table_name> first and then recreate it with the inferred schema before inserting rows.\n"
        "- Stream the file (avoid loading everything into memory).\n"
        "- Return a JSON-serializable dict: {ok: bool, table: str, rows_inserted: int, columns: [str], warnings: [str]}.\n"
        "- Print minimal progress is okay; main signal should be the returned dict.\n"
        "- Do not write any files except via sqlite3 to the provided sqlite_path.\n"
        "Implementation constraints (strict):\n"
        "- ALWAYS specify the column list in INSERT statements as (project_id, branch_id, <data columns...>). Do NOT include id in the INSERT column list; id is auto-incremented.\n"
        "- Ensure the number of placeholders matches the number of specified columns exactly.\n"
        "- For CSV: open with newline='' and the correct encoding; use csv.reader and call next(reader) to consume the header when present (or skip header_skip rows).\n"
        "- When returning the 'columns' field, include ONLY the inferred data columns (exclude id, project_id, branch_id).\n"
        "Take into account optional hints provided in the 'options' object (e.g., header_skip, delimiter, quotechar, encoding, date_formats, rename).\n"
        "Output: ONLY Python source code, no surrounding explanations."
    )

    user_payload = {
        "context": {
            "meta": info,
            "display_name": file_rec.display_name,
            "table_suggest": table_suggest,
            "hints": [
                "CSV/TSV: use csv module; prefer provided delimiter if available",
                "NDJSON: each line is a JSON object; union keys from first 100 rows",
                "If no headers, synthesize col_1..col_n"
            ]
        },
        "paths": {"src_path": src_path, "sqlite_path": sqlite_path},
        "project": {"project_id": project_id, "branch_id": branch_id},
        "snippet_utf8": sample_text,
        "options": (options or {}),
    }

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Generate the code now."},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    try:
        print(f"[tabular] codegen model={model} file={file_rec.display_name} table_suggest={table_suggest}")
    except Exception:
        pass

    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        try:
            print(f"[tabular-error] codegen {type(e).__name__}: {e}")
        except Exception:
            pass
        return {"ok": False, "error": str(e), "stage": "codegen", "model": model}

    code = extract_code_from_markdown(content)

    # Prepare a restricted exec environment
    # Provide a small typing shim so "from typing import List" doesn't fail
    class _TypingParam:
        def __getitem__(self, item):
            return object

    _typing_dummy = types.SimpleNamespace(
        __name__="typing",
        List=list,
        Dict=dict,
        Tuple=tuple,
        Set=set,
        Optional=_TypingParam(),
        Any=object,
        Iterable=_TypingParam(),
        Union=_TypingParam(),
        Callable=_TypingParam(),
    )

    allowed_modules = {
        "csv": csv,
        "json": json,
        "sqlite3": sqlite3,
        "re": re,
        "io": io,
        "math": math,
        "typing": _typing_dummy,
    }

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in allowed_modules and allowed_modules[name] is not None:
            return allowed_modules[name]
        raise ImportError(f"disallowed import: {name}")

    def _safe_open(p, mode="r", *args, **kwargs):
        ab = os.path.abspath(p)
        if ("w" in mode) or ("a" in mode) or ("+" in mode):
            raise PermissionError("open() write modes are not allowed")
        if ab != src_path:
            raise PermissionError("open() denied for this path")
        return builtins.open(p, mode, *args, **kwargs)

    allowed_builtin_names = [
        "abs", "min", "max", "sum", "len", "range", "enumerate", "zip", "map", "filter",
        "any", "all", "sorted", "reversed", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
        "print", "Exception", "isinstance", "StopIteration", "next", "iter"
    ]
    _base_builtins = {}
    try:
        for n in allowed_builtin_names:
            _base_builtins[n] = getattr(builtins, n)
    except Exception:
        pass
    _base_builtins["__import__"] = _safe_import
    _base_builtins["open"] = _safe_open

    safe_globals: Dict[str, Any] = {"__builtins__": _base_builtins}

    # Also inject modules for import-less usage
    safe_globals.update({"csv": csv, "json": json, "sqlite3": sqlite3, "re": re, "io": io})

    buf = io.StringIO()
    run_ok = False
    result: Dict[str, Any] = {}
    try:
        with contextlib.redirect_stdout(buf):
            # Compile then exec
            compiled = compile(code, filename="<llm_tabular_import>", mode="exec")
            exec(compiled, safe_globals, safe_globals)
            run_import = safe_globals.get("run_import")
            if not callable(run_import):
                raise RuntimeError("Generated code did not define run_import()")
            ret = run_import(src_path, sqlite_path, table_suggest, int(project_id), int(branch_id))
            if not isinstance(ret, dict):
                raise RuntimeError("run_import() did not return a dict")
            result = ret
            run_ok = bool(ret.get("ok"))
    except Exception as e:
        result = {"ok": False, "error": f"exec: {type(e).__name__}: {e}"}
    logs = buf.getvalue()

    # Optionally verify row count via our engine
    table_name = str(result.get("table") or table_suggest)
    rows_inserted = int(result.get("rows_inserted") or 0)
    try:
        with get_project_engine_fn(project_id).begin() as conn:
            try:
                cnt = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar()
                result["rowcount_check"] = int(cnt or 0)
            except Exception:
                pass
    except Exception:
        pass

    # Create Dataset entry on success
    if run_ok:
        try:
            friendly = llm_dataset_friendly_name(file_rec, table_name, (result.get("columns") or []))
            desc = f"Imported from {file_rec.display_name} — table: {table_name}"
            if friendly:
                ds = Dataset(project_id=project_id, branch_id=branch_id, name=friendly[:60], description=desc)
            else:
                ds = Dataset(project_id=project_id, branch_id=branch_id, name=table_name, description=desc)
            db.add(ds); db.commit()
        except Exception:
            db.rollback()

    out = {
        "ok": run_ok,
        "table": table_name,
        "rows_inserted": rows_inserted,
        "columns": result.get("columns"),
        "warnings": result.get("warnings"),
        "code_size": len(code or ""),
        "logs": logs[-10000:] if logs else "",
        "model": model,
    }
    if not run_ok and result.get("error"):
        out["error"] = result.get("error")
    return out