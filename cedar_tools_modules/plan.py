from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .llm import get_client_and_model

# Keys: see README "Keys & Env". Troubleshooting: see README sections on LLM failures.

def tool_plan(*, user_text: str, resources: Dict[str, Any], history: List[Dict[str, Any]], notes: List[Dict[str, Any]], changelog: List[Dict[str, Any]], ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client, model = get_client_and_model("CEDARPY_PLAN_MODEL", "gpt-5")
    if not client or not model:
        # Deterministic fallback when key missing is not preferred, but we return a minimal plan to proceed.
        # The caller may choose to ignore.
        return {
            "ok": False,
            "function": "plan",
            "title": "Default Plan",
            "status": "in queue",
            "state": "new plan",
            "steps": [{"function": "final", "title": "Answer", "status": "in queue", "state": "new plan", "args": {"text": user_text[:200], "title": "Assistant"}}],
            "output_to_user": "LLM unavailable; minimal plan",
            "changelog_summary": "created default plan",
            "debug_prompt": None,
        }
    sys_prompt = (
        "You are Cedar's plan generator. Produce a STRICT JSON object with function='plan'. "
        "It must contain: title, status, state, steps (array of objects each with function, title, status, state, args), output_to_user, changelog_summary."
    )
    payload = {
        "user_text": user_text,
        "resources": resources,
        "history": history,
        "notes": notes,
        "changelog": changelog,
        "ctx": ctx or {},
        "functions": ["web","download","extract","image","db","code","notes","compose","tabular_import","final"],
    }
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    ]
    resp = client.chat.completions.create(model=model, messages=messages)
    raw = (resp.choices[0].message.content or "").strip()
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("function") != "plan":
        raise RuntimeError("plan: invalid response")
    obj["ok"] = True
    obj["debug_prompt"] = messages
    return obj