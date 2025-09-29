# Preventing HTML Caching Issues in Cedar Development

## Problem
When developing Cedar, HTML responses may be cached by:
1. Browser caches
2. Python bytecode cache (__pycache__)
3. FastAPI/Uvicorn development server caching
4. CDN or proxy caches (in production)

## Solutions

### 1. Development Server Configuration

#### Use --reload flag with uvicorn
```bash
# Always use reload in development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or set environment variable
export UVICORN_RELOAD=true
uvicorn main:app
```

#### Clear Python cache before starting
```bash
# Add to your start script
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
python -m uvicorn main:app --reload
```

### 2. Browser Cache Prevention

#### Add cache-control headers to HTML responses
```python
# In cedar_app/routes/agents_route.py or any route returning HTML
from fastapi.responses import HTMLResponse

@app.get("/agents")
async def view_agents(request: Request):
    html_content = render_agents_page()
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
```

#### Development browser techniques
- Open DevTools and check "Disable cache" in Network tab
- Use Incognito/Private browsing mode
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows/Linux)
- Clear browser cache: Cmd+Shift+Delete (Mac) or Ctrl+Shift+Delete (Windows/Linux)

### 3. Python Import Cache

#### Force module reload in development
```python
# For testing changes without server restart
import importlib
import cedar_app.routes.agents_route
importlib.reload(cedar_app.routes.agents_route)
```

#### Environment variable to disable bytecode
```bash
# Prevents .pyc file creation
export PYTHONDONTWRITEBYTECODE=1
python -m uvicorn main:app
```

### 4. Testing Without Cache

#### Direct Python testing (bypasses all HTTP caching)
```python
# Test route directly without HTTP layer
from cedar_app.routes.agents_route import register_agents_route

class MockApp:
    def get(self, path, **kwargs):
        def decorator(f):
            self.view_func = f
            return f
        return decorator

app = MockApp()
register_agents_route(app)

# Get fresh HTML
response = app.view_func(MockRequest())
html = response.body.decode() if hasattr(response, 'body') else str(response)
print("Checking for deprecated content...")
```

#### Use curl for testing (no browser cache)
```bash
# Always gets fresh content
curl -H "Cache-Control: no-cache" http://localhost:8000/agents | grep "General Assistant"
```

### 5. Production Cache Busting

#### Version query parameters
```python
# Add version to static assets
VERSION = hashlib.md5(open(__file__,'rb').read()).hexdigest()[:8]
html = f'<link href="/static/style.css?v={VERSION}" rel="stylesheet">'
```

#### ETags for dynamic content
```python
import hashlib

def generate_etag(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()

@app.get("/agents")
async def view_agents(request: Request):
    html_content = render_agents_page()
    etag = generate_etag(html_content)
    
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)  # Not Modified
    
    return HTMLResponse(
        content=html_content,
        headers={"ETag": etag}
    )
```

### 6. Development Workflow Best Practices

#### Clean restart script
Create `scripts/dev-restart.sh`:
```bash
#!/bin/bash
# Kill existing servers
pkill -f uvicorn 2>/dev/null
pkill -f "python.*main:app" 2>/dev/null

# Clear caches
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# Set development environment
export PYTHONDONTWRITEBYTECODE=1
export UVICORN_RELOAD=true

# Start fresh
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Makefile targets
```makefile
.PHONY: clean-cache dev test

clean-cache:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

dev: clean-cache
	PYTHONDONTWRITEBYTECODE=1 uvicorn main:app --reload

test: clean-cache
	pytest tests/ -v
```

### 7. Debugging Cache Issues

#### Check what's being served
```bash
# See actual headers
curl -I http://localhost:8000/agents

# Check file modification times
ls -la cedar_app/routes/agents_route.py
ls -la cedar_app/routes/__pycache__/

# Check if process is using old code
lsof -p $(pgrep -f uvicorn) | grep agents_route
```

#### Force fresh imports in Python
```python
# In main.py for development
import sys
if "--reload" in sys.argv or os.getenv("UVICORN_RELOAD"):
    # Clear import cache for our modules
    for module in list(sys.modules.keys()):
        if module.startswith('cedar'):
            del sys.modules[module]
```

## Summary

To prevent cache issues during Cedar development:

1. **Always use `--reload` flag** with uvicorn
2. **Set `PYTHONDONTWRITEBYTECODE=1`** environment variable
3. **Clear __pycache__ directories** before testing
4. **Use cache-busting headers** in HTTP responses
5. **Test with curl** instead of browser when verifying changes
6. **Hard refresh browser** (Cmd+Shift+R) when testing UI

For production, implement proper cache headers and ETags to balance performance with freshness.