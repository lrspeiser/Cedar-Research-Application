from __future__ import annotations

import re as _re
from typing import Any, Dict, List

# Keys: see README "Keys & Env"
# This tool does not require an LLM; it fetches pages or search results directly.

def tool_web(*, url: str | None = None, query: str | None = None, timeout: int = 25) -> dict:
    import urllib.request as _req
    url = (url or '').strip()
    query = (query or '').strip()
    if query and not url:
        try:
            import urllib.parse as _u
            search_url = "https://duckduckgo.com/html/?q=" + _u.quote(query)
            with _req.urlopen(search_url, timeout=timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
            hrefs = list(set(_re.findall(r'href=[\"\']([^\"\']+)', body)))
            results: List[Dict[str, Any]] = []
            try:
                from urllib.parse import urlparse as _up, parse_qs as _pqs, unquote as _unq
            except Exception:
                _up = None  # type: ignore
            for h in hrefs:
                try:
                    if 'duckduckgo.com' in h and 'uddg=' in h and _up:
                        uo = _up(h)
                        qs = _pqs(uo.query)
                        if 'uddg' in qs:
                            real = _unq(qs['uddg'][0])
                            if real.startswith('http'):
                                results.append({"url": real})
                    elif h.startswith('http') and 'duckduckgo.com' not in h:
                        results.append({"url": h})
                except Exception:
                    continue
            seen = set(); uniq: List[Dict[str, Any]] = []
            for r in results:
                u = r.get('url')
                if u and u not in seen:
                    seen.add(u); uniq.append(r)
            return {"ok": True, "query": query, "results": uniq[:10], "count": len(uniq[:10])}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if url:
        try:
            with _req.urlopen(url, timeout=timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
            links = list(set(_re.findall(r'href=[\"\']([^\"\']+)', body)))
            title_m = _re.search(r'<title[^>]*>(.*?)</title>', body, _re.IGNORECASE | _re.DOTALL)
            title = title_m.group(1).strip() if title_m else ''
            return {"ok": True, "url": url, "title": title, "links": links[:200], "bytes": len(body)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": "web: provide url or query"}