#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CedarPy LLM Tool + Orchestrator End-to-End Audit (GPT-5 only)

What this does
- Imports the FastAPI app in-process and uses Starlette TestClient (no external server)
- Creates a new project and resolves the Main branch id
- Exercises every tool via POST /api/test/tool:
  db, code, web, download, extract, image, shell, notes, compose, tabular_import
- Uploads files (PNG + CSV) via /project/{id}/files/upload to trigger REAL LLM classification
- Demos the WebSocket orchestrator (/ws/chat) and prints full prompt + events
- For each call, prints to stdout:
  1) REQUEST: the exact endpoint and JSON body we sent
  2) RESPONSE: the raw JSON returned by the API
  3) TO LLM: the exact JSON envelope we would append to the LLM after processing (ToolResult)

Important keys and docs
- Uses real OpenAI calls (no stubs): we explicitly disable CEDARPY_TEST_MODE.
- You must set OPENAI_API_KEY (or CEDARPY_OPENAI_API_KEY) in your shell first.
- Models are pinned to the GPT-5 family only per your instruction.
- README references:
  * LLM classification on file upload — see README.md, section "LLM classification on file upload" (around lines 137–177)
  * CI test mode (deterministic LLM stubs) — see README.md, section "CI test mode" (around lines 159–177)
  * Tabular import via LLM codegen — see README.md, section "Tabular import via LLM codegen" (around lines 178–207)

Security
- Never prints secret values; only checks presence.
- Does not commit any files or send data externally beyond example.org and OpenAI (your keys).

Usage
  python scripts/run_llm_tool_audit.py

Exit code
- 0 on success; 1 on hard failure (e.g., missing key).
"""

from __future__ import annotations

import os
import sys
import io
import re
import json
import time
import importlib
from typing import Any, Dict, List, Optional, Tuple

from starlette.testclient import TestClient

# Ensure repo root is importable (so `import main` resolves to main.py in repo root)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _print_header(msg: str) -> None:
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)


def _print_block(label: str, data: Any) -> None:
    print(f"\n--- {label} ---")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(str(data))
    print(f"--- END {label} ---\n")


def _env_bool(name: str, default: bool = False) -> bool:
    try:
        v = str(os.getenv(name, "")).strip().lower()
        if v in {"1", "true", "yes", "on"}: return True
        if v in {"0", "false", "no", "off", ""}: return False
    except Exception:
        pass
    return default


def _ensure_env() -> None:
    # Honor team rules: never use placeholders or stubs when testing web services.
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        print("ERROR: Missing OPENAI_API_KEY (or CEDARPY_OPENAI_API_KEY). Aborting per policy.")
        print("See README: 'LLM classification on file upload' and 'CI test mode (deterministic LLM stubs)'.")
        sys.exit(1)

    # Force real OpenAI usage (disable deterministic stubs), while still allowing /api/test/tool
    os.environ["CEDARPY_TEST_MODE"] = "0"                      # no stubs
    os.environ["CEDARPY_DEV_ALLOW_TEST_TOOL"] = "1"             # allow /api/test/tool locally
    os.environ["CEDARPY_SHELL_API_ENABLED"] = "1"               # allow shell tool locally

    # Pin GPT-5 family everywhere per instruction
    os.environ["CEDARPY_OPENAI_MODEL"] = os.getenv("CEDARPY_OPENAI_MODEL", "gpt-5")
    os.environ["CEDARPY_SUMMARY_MODEL"] = os.getenv("CEDARPY_SUMMARY_MODEL", "gpt-5")
    os.environ["CEDARPY_TABULAR_MODEL"] = os.getenv("CEDARPY_TABULAR_MODEL", "gpt-5")
    # Ensure WS fast model does not pick a non-gpt-5 default
    os.environ["CEDARPY_FAST_MODEL"] = os.getenv("CEDARPY_FAST_MODEL", "gpt-5")


class App:
    def __init__(self) -> None:
        # Import or reload the app to pick up env vars
        import main  # noqa: F401
        importlib.reload(main)
        self.main = main
        self.client = TestClient(main.app)

    def create_project(self, title: str) -> int:
        # Create a project
        r = self.client.post("/projects/create", data={"title": title})
        if r.status_code not in (200, 303):
            raise RuntimeError(f"create project failed: {r.status_code}: {r.text[:500]}")
        # Resolve project id from the home page HTML
        home = self.client.get("/")
        if home.status_code != 200:
            raise RuntimeError(f"home fetch failed: {home.status_code}")
        m = re.search(r"/project/(\d+)", home.text)
        if not m:
            raise RuntimeError("project id not found in home page")
        return int(m.group(1))

    def _tool_call(self, pid: int, bid: Optional[int], function: str, args: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        body = {
            "function": function,
            "project_id": pid,
            "branch_id": bid,
            "args": args or {},
        }
        _print_block("REQUEST", {"endpoint": "/api/test/tool", "body": body})
        r = self.client.post("/api/test/tool", json=body)
        try:
            jd = r.json()
        except Exception:
            jd = {"error": f"non-JSON response: status={r.status_code}", "text": r.text[:1000]}
        _print_block("RESPONSE", jd)
        # Compute the exact ToolResult envelope we would send back to the LLM
        # WS orchestrator uses two user messages: "ToolResult:" and the JSON payload
        result_payload = jd.get("result") if isinstance(jd, dict) else None
        if result_payload is None:
            result_payload = jd  # fall back to the whole response
        tool_result_envelope = {"function": function, "result": result_payload}
        _print_block("TO LLM", [{"role": "user", "content": "ToolResult:"}, tool_result_envelope])
        return jd, tool_result_envelope

    def sql_scalar(self, pid: int, sql: str) -> Any:
        jd, _ = self._tool_call(pid, None, "db", {"sql": sql})
        if not jd or not jd.get("ok"):
            raise RuntimeError(f"db failed: {jd}")
        rows = jd.get("rows") or []
        if not rows or not rows[0]:
            return None
        return rows[0][0]


def main() -> int:
    _print_header("CedarPy LLM Tool + Orchestrator End-to-End Audit (GPT-5 only)")
    _ensure_env()

    # Show effective env flags (do not print secrets)
    eff = {
        "CEDARPY_TEST_MODE": os.getenv("CEDARPY_TEST_MODE"),
        "CEDARPY_DEV_ALLOW_TEST_TOOL": os.getenv("CEDARPY_DEV_ALLOW_TEST_TOOL"),
        "CEDARPY_SHELL_API_ENABLED": os.getenv("CEDARPY_SHELL_API_ENABLED"),
        "CEDARPY_OPENAI_MODEL": os.getenv("CEDARPY_OPENAI_MODEL"),
        "CEDARPY_SUMMARY_MODEL": os.getenv("CEDARPY_SUMMARY_MODEL"),
        "CEDARPY_TABULAR_MODEL": os.getenv("CEDARPY_TABULAR_MODEL"),
        "CEDARPY_FAST_MODEL": os.getenv("CEDARPY_FAST_MODEL"),
        "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")),
    }
    _print_block("ENV", eff)

    app = App()

    # Create project
    title = f"Tool Audit {int(time.time())}"
    pid = app.create_project(title)
    print(f"Created project_id={pid}")

    # Resolve Main branch id via SQL
    try:
        main_bid = int(app.sql_scalar(pid, "SELECT id FROM branches WHERE name='Main' LIMIT 1") or 1)
    except Exception as e:
        print(f"WARN: main branch resolution failed; defaulting to 1: {e}")
        main_bid = 1
    print(f"Using branch_id={main_bid}")

    # 1) db
    _print_header("Tool 1: db")
    app._tool_call(pid, None, "db", {"sql": "SELECT 1 AS one"})

    # 2) code
    _print_header("Tool 2: code (python)")
    jd_code, _ = app._tool_call(pid, main_bid, "code", {"source": "print('ok')"})
    try:
        logs = jd_code.get("logs") or ""
        print(f"[verify] code logs contains 'ok': {('ok' in logs)}")
    except Exception:
        pass

    # 3) web
    _print_header("Tool 3: web (fetch example.org)")
    app._tool_call(pid, None, "web", {"url": "https://example.org/"})

    # 4) download
    _print_header("Tool 4: download (example.org)")
    jd_dl, _ = app._tool_call(pid, main_bid, "download", {"urls": ["https://example.org/"]})
    dl_file_id = None
    try:
        dls = jd_dl.get("downloads") or []
        if dls:
            dl_file_id = int(dls[0].get("file_id"))
    except Exception:
        dl_file_id = None
    print(f"downloaded file_id={dl_file_id}")

    # 5) extract
    if dl_file_id:
        _print_header("Tool 5: extract (from downloaded file)")
        app._tool_call(pid, None, "extract", {"file_id": dl_file_id})

    # 6) image: upload tiny PNG then call image
    _print_header("Upload tiny PNG (triggers LLM classification on upload)")
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01"
        b"\x0b\xe7\x02\x9a\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("tiny.png", io.BytesIO(tiny_png), "image/png")}
    r_up_png = app.client.post(f"/project/{pid}/files/upload?branch_id={main_bid}", files=files, follow_redirects=False)
    print(f"upload PNG status={r_up_png.status_code}")
    # Query last file id via db tool
    try:
        img_file_id = int(app.sql_scalar(pid, "SELECT id FROM files ORDER BY id DESC LIMIT 1") or 0)
    except Exception:
        img_file_id = 0
    _print_header("Tool 6: image (on uploaded PNG)")
    if img_file_id:
        app._tool_call(pid, None, "image", {"image_id": img_file_id, "purpose": "sanity"})

    # 7) shell
    _print_header("Tool 7: shell (echo hello)")
    jd_shell, _ = app._tool_call(pid, None, "shell", {"script": "echo hello"})
    try:
        stdout = jd_shell.get("stdout") or ""
        print(f"[verify] shell stdout contains 'hello': {('hello' in stdout)}")
    except Exception:
        pass

    # 8) notes
    _print_header("Tool 8: notes")
    app._tool_call(pid, main_bid, "notes", {"themes": [{"name": "T", "notes": ["n1"]}]})

    # 9) compose
    _print_header("Tool 9: compose")
    app._tool_call(pid, main_bid, "compose", {"sections": [{"title": "Intro", "text": "This is a test composition section."}]})

    # 10) tabular_import: upload CSV then import via LLM codegen
    _print_header("Upload CSV (triggers LLM classification on upload)")
    csv_bytes = b"a,b\n1,2\n3,4\n"
    files_csv = {"file": ("demo.csv", io.BytesIO(csv_bytes), "text/csv")}
    r_up_csv = app.client.post(f"/project/{pid}/files/upload?branch_id={main_bid}", files=files_csv, follow_redirects=False)
    print(f"upload CSV status={r_up_csv.status_code}")
    try:
        csv_file_id = int(app.sql_scalar(pid, "SELECT id FROM files ORDER BY id DESC LIMIT 1") or 0)
    except Exception:
        csv_file_id = 0
    _print_header("Tool 10: tabular_import (LLM codegen -> SQLite)")
    if csv_file_id:
        jd_tab, _ = app._tool_call(pid, main_bid, "tabular_import", {"file_id": csv_file_id, "options": {"header_skip": 0}})
        try:
            table = jd_tab.get("table")
            rows_inserted = jd_tab.get("rows_inserted")
            model = jd_tab.get("model")
            print(f"[verify] tabular_import model={model} table={table} rows_inserted={rows_inserted}")
            if table:
                cnt = app.sql_scalar(pid, f"SELECT COUNT(*) FROM {table}")
                print(f"[verify] SQL COUNT(*) from {table} = {cnt}")
        except Exception as e:
            print(f"[verify] tabular_import verification error: {type(e).__name__}: {e}")

    # Upload a small text for an explicit classification demo
    _print_header("Upload TEXT (classification demo)")
    files_txt = {"file": ("classify-me.txt", io.BytesIO(b"Classification demo about Example Domain"), "text/plain")}
    r_up_txt = app.client.post(f"/project/{pid}/files/upload?branch_id={main_bid}", files=files_txt, follow_redirects=False)
    print(f"upload TEXT status={r_up_txt.status_code}")
    try:
        row = None
        jd_info, _ = app._tool_call(pid, None, "db", {"sql": "SELECT id, ai_title, ai_category, structure FROM files ORDER BY id DESC LIMIT 1"})
        cols = jd_info.get("columns") or []
        rows = jd_info.get("rows") or []
        if rows:
            row = {cols[i]: rows[0][i] for i in range(len(cols))}
        _print_block("CLASSIFICATION", row or {})
        print("(See README: 'LLM classification on file upload')")
    except Exception:
        pass

    # WebSocket orchestrator demo
    _print_header("WebSocket Orchestrator Demo (/ws/chat)")
    try:
        with app.client.websocket_connect(f"/ws/chat/{pid}") as ws:
            payload = {
                "action": "chat",
                "content": "Fetch https://example.org and tell me the page title, do not answer from memory.",
                "branch_id": main_bid,
                "debug": True,
            }
            _print_block("REQUEST (WS)", {"url": f"/ws/chat/{pid}", "payload": payload})
            ws.send_text(json.dumps(payload))
            got_final = False
            thread_id: Optional[int] = None
            # Print each event as it arrives
            for _ in range(200):
                raw = ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    print("recv (text):", raw)
                    continue
                t = msg.get("type")
                if t == "debug":
                    _print_block("WS DEBUG prompt messages", msg.get("prompt"))
                    # thread id is provided in 'prompt' event (server places thread_id there)
                    try:
                        thread_id = int(msg.get("thread_id") or 0)
                        print(f"[ws] thread_id={thread_id}")
                    except Exception:
                        pass
                elif t == "action":
                    fn = msg.get("function")
                    _print_block(f"WS ACTION: {fn}", msg.get("call"))
                elif t == "info":
                    print(f"[ws info] {msg.get('stage')}")
                elif t == "final":
                    _print_block("WS FINAL text", msg.get("text"))
                    _print_block("WS FINAL json", msg.get("json"))
                    got_final = True
                    break
                elif t == "error":
                    _print_block("WS ERROR", msg)
                    break
                else:
                    _print_block("WS EVENT", msg)
            # After close, pull the latest persisted Tool: * messages for this thread to reconstruct ToolResult payloads
            if thread_id:
                jd_tools, _ = app._tool_call(pid, None, "db", {"sql": f"SELECT display_title, payload_json FROM thread_messages WHERE thread_id = {thread_id} AND role='assistant' AND display_title LIKE 'Tool:%' ORDER BY id DESC LIMIT 5"})
                rows = jd_tools.get("rows") or []
                cols = jd_tools.get("columns") or []
                for r in rows:
                    row = {cols[i]: r[i] for i in range(len(cols))}
                    title = row.get("display_title") or ""
                    payload = row.get("payload_json") or {}
                    try:
                        fn_name = str(title).split(":", 1)[1].strip()
                    except Exception:
                        fn_name = payload.get("function") or "?"
                    # Exact ToolResult envelope we feed back to the LLM in the WS loop
                    tr = {"function": fn_name, "result": (payload.get("result") if isinstance(payload, dict) else payload)}
                    _print_block("WS ToolResult (from persisted payload)", tr)
            print(f"[ws] got_final={got_final}")
    except Exception as e:
        _print_block("WS EXCEPTION", {"error": f"{type(e).__name__}: {e}"})

    print("\nAll done. If any step failed, scroll up for the REQUEST/RESPONSE/TO LLM blocks and error messages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())