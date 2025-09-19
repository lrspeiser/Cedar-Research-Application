#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket backend test for CedarPy chat

Usage:
  python scripts/ws_backend_test.py --project 8 --branch 1 --prompt "what is 2+2" [--host localhost:8000] [--file-id 123] [--dataset-id 5]

What it does:
- Connects to ws://<host>/ws/chat/<project_id>
- Sends a chat payload with debug=1 (server will echo the exact prompt messages array)
- Prints all events: debug (prompt), info stages, action bubbles (plan/tool/final), final/error
- Exits non-zero if no final received

This isolates frontend vs backend issues. If you see proper events here, the backend is OK and the issue is in the UI.

Note: Requires the CedarPy backend running locally and OpenAI keys configured if you expect a real model reply.
"""
import argparse
import json
import sys
import time
from typing import Optional

try:
    import websockets  # type: ignore
except Exception:
    print("error: please install websockets: python -m pip install websockets", file=sys.stderr)
    sys.exit(2)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, required=True)
    ap.add_argument("--branch", type=int, required=True)
    ap.add_argument("--prompt", type=str, required=True)
    ap.add_argument("--host", type=str, default="127.0.0.1:8000", help="host:port (default 127.0.0.1:8000)")
    ap.add_argument("--file-id", type=int, default=None)
    ap.add_argument("--dataset-id", type=int, default=None)
    return ap.parse_args()


async def run(project_id: int, branch_id: int, prompt: str, host: str, file_id: Optional[int], dataset_id: Optional[int]) -> int:
    import asyncio
    url = f"ws://{host}/ws/chat/{project_id}"
    print(f"connecting: {url}")
    async with websockets.connect(url, open_timeout=10) as ws:
        payload = {
            "action": "chat",
            "content": prompt,
            "branch_id": branch_id,
            "thread_id": None,
            "file_id": file_id,
            "dataset_id": dataset_id,
            "debug": True,
        }
        await ws.send(json.dumps(payload))
        print("sent payload:\n" + json.dumps(payload, indent=2))
        got_final = False
        t0 = time.time()
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                print("timeout waiting for server events", file=sys.stderr)
                break
            try:
                msg = json.loads(raw)
            except Exception:
                print("recv (text):", raw)
                continue
            t = msg.get("type")
            if t == "debug":
                print("\n--- DEBUG: PROMPT MESSAGES ---")
                print(json.dumps(msg.get("prompt"), indent=2, ensure_ascii=False))
                print("--- END DEBUG ---\n")
            elif t == "info":
                print(f"[info] {msg.get('stage')}")
            elif t == "action":
                fn = msg.get("function")
                print(f"[action] {fn} args=" + json.dumps(msg.get("args"), ensure_ascii=False))
            elif t == "final":
                print("\nFINAL:\n" + (msg.get("text") or ""))
                got_final = True
                break
            elif t == "error":
                print("ERROR:", msg.get("error"), file=sys.stderr)
                break
            else:
                print("recv:", json.dumps(msg))
        dt = time.time() - t0
        print(f"elapsed: {dt:.2f}s")
        return 0 if got_final else 1


def main():
    args = parse_args()
    import asyncio
    rc = asyncio.run(run(args.project, args.branch, args.prompt, args.host, args.file_id, args.dataset_id))
    sys.exit(rc)


if __name__ == "__main__":
    main()
