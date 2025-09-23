import os
import asyncio
from datetime import datetime
from typing import Any, Dict

# Optional Redis (Valkey) for real-time relay (Node SSE). If not available, we silently skip publishing.
REDIS_URL = os.getenv("CEDARPY_REDIS_URL") or "redis://127.0.0.1:6379/0"
try:
    import redis.asyncio as _redis  # type: ignore
except Exception:  # pragma: no cover
    _redis = None

_redis_client = None
async def _get_redis():
    global _redis_client
    try:
        if _redis is None:
            return None
        if _redis_client is None:
            _redis_client = _redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        return _redis_client
    except Exception:
        return None

async def _publish_relay_event(obj: Dict[str, Any]) -> None:
    try:
        r = await _get_redis()
        if r is None:
            return
        tid = obj.get("thread_id")
        if not tid:
            return
        chan = f"cedar:thread:{tid}:pub"
        # Keep the payload small; serialize as-is (frontend expects same shape)
        import json as _json_pub
        await r.publish(chan, _json_pub.dumps(obj))
    except Exception:
        # Best-effort only
        pass

# Step-level ack registry (best-effort, in-memory). Used to verify the UI rendered a bubble.
_ack_store: Dict[str, Dict[str, Any]] = {}

async def _register_ack(eid: str, info: Dict[str, Any], timeout_ms: int = 10000) -> None:
    try:
        _ack_store[eid] = {
            'eid': eid,
            'info': info,
            'created_at': datetime.utcnow().isoformat()+"Z",
            'acked': False,
            'ack_at': None,
        }
        async def _timeout():
            try:
                await asyncio.sleep(max(0.5, timeout_ms/1000.0))
                rec = _ack_store.get(eid)
                if rec and not rec.get('acked'):
                    try:
                        print(f"[ack-timeout] eid={eid} info={rec.get('info')}")
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            asyncio.get_event_loop().create_task(_timeout())
        except Exception:
            pass
    except Exception:
        pass
