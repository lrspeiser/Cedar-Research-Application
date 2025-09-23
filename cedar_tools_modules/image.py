from __future__ import annotations

from typing import Callable

def tool_image(*, image_id: int, purpose: str, exec_img: Callable[[int, str], dict]) -> dict:
    try:
        return exec_img(image_id, purpose)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}