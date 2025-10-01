# Python Bytecode Cache Issue

## Problem

When developing CedarPy, we encountered an issue where code changes weren't taking effect even after editing Python files. The backend was running **stale code** from bytecode cache files (`.pyc` files in `__pycache__` directories).

### What Happened

1. We added preview streaming functionality to `chief_agent.py`
2. Restarted the backend
3. The preview didn't work - old code was still running
4. Manually cleared `__pycache__` directories
5. Restarted again - preview streaming worked perfectly

### Root Cause

Python compiles `.py` files to `.pyc` bytecode files for faster loading. These are stored in `__pycache__/` directories. When Python loads a module:

1. It checks if a `.pyc` file exists
2. If the `.pyc` timestamp matches the `.py` file, it uses the cached bytecode
3. **If timestamps are wrong or there's a filesystem sync issue, stale bytecode runs**

This is especially common when:
- Files are edited while the Python process is running
- Using file sync tools (Dropbox, iCloud, etc.)
- Working in virtual environments
- Fast edit-reload cycles during development

## Solution

### Automatic Cache Clearing (Recommended)

Use the provided startup script that automatically clears cache before running:

```bash
./clear_cache_and_run.sh
```

This script:
1. Clears all `__pycache__/` directories
2. Deletes all `.pyc` files
3. Sets `PYTHONDONTWRITEBYTECODE=1` to prevent new cache files
4. Starts the backend

### Manual Cache Clearing

If you need to clear cache manually:

```bash
# Clear all __pycache__ directories
find /Users/leonardspeiser/Projects/cedarpy -type d -name "__pycache__" -exec rm -rf {} +

# Clear all .pyc files
find /Users/leonardspeiser/Projects/cedarpy -type f -name "*.pyc" -delete
```

### Alternative: Disable Bytecode Writing

Add to your `.env` file:

```bash
PYTHONDONTWRITEBYTECODE=1
```

Or set in your shell before running:

```bash
export PYTHONDONTWRITEBYTECODE=1
python main.py
```

**Trade-off**: This disables bytecode caching entirely, which means:
- ✅ No stale code issues
- ❌ Slightly slower module imports (negligible for most apps)

## Prevention

### For Development

**Always use the cache-clearing startup script**:
```bash
./clear_cache_and_run.sh
```

### For Production

In production, bytecode caching is beneficial and safe (code doesn't change). Keep it enabled.

## Symptoms of Cache Issues

If you see these symptoms, you likely have a cache issue:

- Code changes don't take effect after restart
- Old functions/classes are still being called
- Imports work but behavior is wrong
- Logs show old code paths executing
- `git diff` shows changes but behavior hasn't changed

**Solution**: Clear the cache and restart.

## Related Commands

```bash
# Find all cache directories
find . -type d -name "__pycache__"

# Find all bytecode files
find . -type f -name "*.pyc"

# Clear cache for specific module
rm -rf cedar_orchestrator/__pycache__

# Clear all cache in project
find . -type d -name "__pycache__" -exec rm -rf {} +
```

## References

- [Python Docs: `__pycache__`](https://docs.python.org/3/tutorial/modules.html#compiled-python-files)
- [PEP 3147: PYC Repository Directories](https://www.python.org/dev/peps/pep-3147/)
