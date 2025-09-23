from __future__ import annotations

import os
import io
import re
import json
import contextlib
import builtins
from typing import Any, Callable, Dict, Optional, List, Tuple

from .llm import get_client_and_model

# Keys: see README "Keys & Env"; for troubleshooting see README "Tabular import via LLM codegen".


def _snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name or "").strip("_")
    s = re.sub(r"_+", "_", s)
    s = s.lower()
    if not s:
        s = "t"
    if s[0].isdigit():
        s = "t_" + s
    return s


def _suggest_table_name(display_name: str) -> str:
    base = os.path.splitext(os.path.basename(display_name or "table"))[0]
    return _snake_case(base)


def _extract_code_from_markdown(s: str) -> str:
    try:
        import re as _re
        m = _re.search(r"```python\n(.*?)```", s, flags=_re.DOTALL | _re.IGNORECASE)
        if m:
            return m.group(1)
        m2 = _re.search(r"```\n(.*?)```", s, flags=_re.DOTALL)
        if m2:
            return m2.group(1)
        return s
    except Exception:
        return s


def _llm_dataset_friendly_name(file_rec: Any, table_name: str, columns: List[str]) -> Optional[str]:
    try:
        if str(os.getenv("CEDARPY_TEST_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}:
            base = (getattr(file_rec, 'ai_title', None) or getattr(file_rec, 'display_name', None) or table_name or "Data").strip()
            return (base[:60] if base else "Test Dataset")
    except Exception:
        pass
    client, model = get_client_and_model("CEDARPY_SUMMARY_MODEL", "gpt-5-nano")
    if not client or not model:
        return None
    try:
        sys_prompt = (
            "You propose concise, human-friendly dataset names (<= 60 chars). "
            "Use the provided file title, category, and columns. Output plain text only."
        )
        info = {
            "file_title": (getattr(file_rec, 'ai_title', None) or getattr(file_rec, 'display_name', None)),
            "category": getattr(file_rec, 'ai_category', None),
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
    except Exception:
        return None


def tabular_import_via_llm(
    project_id: int,
    branch_id: int,
    file_rec: Any,
    db: Any,
    *,
    options: Optional[Dict[str, Any]] = None,
    project_dirs: Callable[[int], Dict[str, str]],
    get_project_engine: Callable[[int], Any],
    Dataset: Any,
) -> Dict[str, Any]:
    # Determine DB path and table suggestion
    paths = project_dirs(project_id)
    sqlite_path = paths.get("db_path")
    src_path = os.path.abspath(getattr(file_rec, 'storage_path', '') or "")
    table_suggest = _suggest_table_name((getattr(file_rec, 'display_name', None) or getattr(file_rec, 'filename', None) or "data"))

    # Collect lightweight metadata for prompt
    meta = getattr(file_rec, 'metadata_json', None) or {}
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

    client, model_default = get_client_and_model("CEDARPY_TABULAR_MODEL", "gpt-5")
    if not client:
        return {"ok": False, "error": "missing OpenAI key", "model": None}
    model = model_default or "gpt-5"

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
            "display_name": getattr(file_rec, 'display_name', None),
            "table_suggest": table_suggest,
            "hints": [
                "CSV/TSV: use csv module; prefer provided delimiter if available",
                "NDJSON: each line is a JSON object; union keys from first 100 rows",
                "If no headers, synthesize col_1..col_n"
            ]
        },
        "paths": {"src_path": src_path, "sqlite_path": sqlite_path},
        "project": {"project_id": project_id, "branch_id": branch_id},
        "snippet_utf8": (meta.get("sample_text") or "")[:4000],
        "options": (options or {}),
    }

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "Generate the code now."},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    try:
        print(f"[tabular] codegen model={model} file={getattr(file_rec,'display_name',None)} table_suggest={table_suggest}")
    except Exception:
        pass

    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"ok": False, "error": str(e), "stage": "codegen", "model": model}

    code = _extract_code_from_markdown(content)

    # Prepare a restricted exec environment
    import csv as _csv, json as _json2, sqlite3 as _sqlite3, re as _re, io as _io, math as _math, types as _types

    class _TypingParam:
        def __getitem__(self, item):
            return object

    _typing_dummy = _types.SimpleNamespace(
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
        "csv": _csv,
        "json": _json2,
        "sqlite3": _sqlite3,
        "re": _re,
        "io": _io,
        "math": _math,
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
    for n in allowed_builtin_names:
        try:
            _base_builtins[n] = getattr(builtins, n)
        except Exception:
            pass
    _base_builtins["__import__"] = _safe_import
    _base_builtins["open"] = _safe_open

    safe_globals: Dict[str, Any] = {"__builtins__": _base_builtins}
    safe_globals.update({"csv": _csv, "json": _json2, "sqlite3": _sqlite3, "re": _re, "io": _io})

    buf = io.StringIO()
    run_ok = False
    result: Dict[str, Any] = {}
    try:
        with contextlib.redirect_stdout(buf):
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
        with get_project_engine(project_id).begin() as conn:
            try:
                cnt = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar()
                result["rowcount_check"] = int(cnt or 0)
            except Exception:
                pass
    except Exception:
        pass

    if run_ok:
        try:
            friendly = _llm_dataset_friendly_name(file_rec, table_name, (result.get("columns") or []))
            desc = f"Imported from {getattr(file_rec,'display_name',None)} — table: {table_name}"
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


def tool_tabular_import(*, project_id: int, branch_id: int, file_id: int, options: Optional[dict], SessionLocal: Callable[[], Any], FileEntry: Any, project_dirs: Callable[[int], Dict[str, str]], get_project_engine: Callable[[int], Any], Dataset: Any) -> dict:
    db = SessionLocal()
    try:
        rec = db.query(FileEntry).filter(FileEntry.id==file_id, FileEntry.project_id==project_id).first()
        if not rec:
            return {"ok": False, "error": "file not found"}
        res = tabular_import_via_llm(project_id, branch_id, rec, db, options=options, project_dirs=project_dirs, get_project_engine=get_project_engine, Dataset=Dataset)
        out = {"ok": bool(res.get("ok"))}
        out.update(res)
        return out
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try: db.close()
        except Exception: pass
