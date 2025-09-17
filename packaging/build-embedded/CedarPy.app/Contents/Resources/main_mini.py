# Minimal ASGI "Hello World" app without FastAPI/Starlette dependencies.
# This is used to verify the packaged Qt wrapper and uvicorn can run with a bare ASGI app.

async def app(scope, receive, send):
    if scope.get("type") != "http":
        return
    path = scope.get("path", "/")
    if path != "/":
        status = 404
        body = b"Not Found"
    else:
        status = 200
        body = (
            b"<!doctype html><html><head><meta charset='utf-8'>"
            b"<title>Cedar (Hello)</title></head><body>"
            b"<h1>Cedar (Hello)</h1><p>ASGI minimal app is running.</p>"
            b"</body></html>"
        )
    headers = [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
