from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Cedar (Mini)")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""
<!doctype html>
<html><head><meta charset="utf-8"><title>Cedar (Mini)</title></head>
<body>
  <h1>Cedar (Mini)</h1>
  <p class="muted">Minimal server-only view. This is used for packaging isolation. If you can see this page, the packaged server is running.</p>
</body></html>
""")
