"""
Aggregator LLM for reconciling component outputs.

Keys: see README "Keys & Env" for how keys are loaded from env or ~/CedarPyData/.env
Troubleshooting: see README "Troubleshooting LLM failures"; do not fabricate results
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def normalize_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    norm: List[Dict[str, Any]] = []
    for c in candidates or []:
        try:
            norm.append({
                "name": str(c.get("name") or ""),
                "ok": bool(c.get("ok")),
                "status": str(c.get("status") or ""),
                "summary": c.get("content"),
                "error": c.get("error"),
            })
        except Exception:
            norm.append({"name": str(c.get("name") or ""), "ok": False, "status": "error", "summary": None, "error": "normalize-error"})
    return norm


def build_prompt(user_text: str, normalized: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    system = (
        "You are Cedar's aggregator. You must produce ONE strict JSON function-call object with function='final'. "
        "Use the components' summaries to decide the best final answer. No prose, no explanations. STRICT JSON only."
    )
    examples = {
        "final": {"function": "final", "args": {"text": "<answer>", "title": "<3-6 words>", "run_summary": ["...", "..."]}},
    }
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": "User request:"},
        {"role": "user", "content": user_text or "(empty)"},
        {"role": "user", "content": "Component candidates (JSON):"},
        {"role": "user", "content": json.dumps(normalized, ensure_ascii=False)},
        {"role": "user", "content": "Example (required output schema):"},
        {"role": "user", "content": json.dumps(examples, ensure_ascii=False)},
    ]
    return msgs


def aggregate(user_text: str, candidates: List[Dict[str, Any]], *, client: Any, model: str) -> Dict[str, Any]:
    """
    Call the LLM to reconcile component outputs into a single final function call.
    Returns: {ok, final_json, final_text, debug_prompt}
    """
    normalized = normalize_candidates(candidates)
    prompt = build_prompt(user_text, normalized)
    resp = client.chat.completions.create(model=model, messages=prompt)
    raw = (resp.choices[0].message.content or "").strip()
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("function") != "final":
        raise RuntimeError("aggregator: invalid response (missing final)")
    final_text = str(((obj.get("args") or {}).get("text")) or "").strip()
    return {"ok": True, "final_json": obj, "final_text": final_text, "debug_prompt": prompt}
