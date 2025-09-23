from __future__ import annotations

import os

def tool_shell(*, script: str) -> dict:
    if not script.strip():
        return {"ok": False, "error": "script required"}
    try:
        base = os.environ.get('SHELL') or '/bin/zsh'
        import subprocess
        proc = subprocess.run([base, '-lc', script], capture_output=True, text=True, timeout=60)
        return {"ok": proc.returncode == 0, "return_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}