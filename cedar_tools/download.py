from __future__ import annotations

import os
import mimetypes
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

# Keys & Troubleshooting: see README sections referenced across modules

def tool_download(*, project_id: int, branch_id: int, branch_name: str, urls: List[str], project_dirs: Callable[[int], Dict[str, str]], SessionLocal: Callable[[], Any], FileEntry: Any, file_extension_to_type: Callable[[str], str], timeout: int = 45) -> dict:
    import urllib.request as _req
    import re as _re
    if not urls:
        return {"ok": False, "error": "urls required"}
    paths = project_dirs(project_id)
    files_root = paths.get("files_root") or ''
    branch_dir_name = f"branch_{branch_name or 'Main'}"
    project_dir = os.path.join(files_root, branch_dir_name)
    os.makedirs(project_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        for u in urls[:10]:
            try:
                with _req.urlopen(u, timeout=timeout) as resp:
                    data = resp.read()
                parsed = _re.sub(r'[^a-zA-Z0-9._-]', '_', os.path.basename(u.split('?')[0]) or 'download.bin')
                ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                storage_name = f"{ts}__{parsed}"
                disk_path = os.path.join(project_dir, storage_name)
                with open(disk_path, 'wb') as fh:
                    fh.write(data)
                size = len(data)
                mime, _ = mimetypes.guess_type(parsed)
                ftype = file_extension_to_type(parsed)
                rec = FileEntry(project_id=project_id, branch_id=branch_id, filename=storage_name, display_name=parsed, file_type=ftype, structure=None, mime_type=mime or '', size_bytes=size, storage_path=os.path.abspath(disk_path), metadata_json=None, ai_processing=False)
                db.add(rec); db.commit(); db.refresh(rec)
                results.append({"url": u, "file_id": rec.id, "display_name": parsed, "bytes": size})
            except Exception as e:
                results.append({"url": u, "error": f"{type(e).__name__}: {e}"})
        return {"ok": True, "downloads": results}
    finally:
        try: db.close()
        except Exception: pass