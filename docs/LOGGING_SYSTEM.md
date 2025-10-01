# CedarPy Comprehensive Logging System

## Overview

CedarPy now has a **comprehensive file-based logging system** that logs every step of backend execution. This system was created to provide complete visibility into:

- What code is actually running
- Where execution succeeds or fails
- Complete execution traces for debugging
- Step-by-step progress through every function

## Why This Exists

**Problem**: When debugging issues like preview streaming not working, we couldn't see what was actually happening in the backend. Logs were going to stdout/stderr and disappearing, making it impossible to verify if code was running or where it was failing.

**Solution**: Every backend function now uses centralized file-based logging with:
- ✅ Detailed function entry/exit logging
- ✅ Step-by-step progress logging
- ✅ Success confirmations
- ✅ Error logging with full stack traces
- ✅ All logs written to easily accessible files

## Log File Locations

All logs are written to: `~/Library/Logs/CedarPy/`

### Log Files Created

Each backend session creates:

1. **`backend_<timestamp>.log`** - Main log file containing ALL backend activity
2. **`<component>_<timestamp>.log`** - Component-specific logs (one per module)

Examples:
```
~/Library/Logs/CedarPy/
├── backend_20250930_182200.log          # All backend activity
├── chief_agent_20250930_182200.log      # ChiefAgent activity only
├── preview_streamer_20250930_182200.log # PreviewStreamer activity only
├── ws_chat_20250930_182200.log          # WebSocket handler activity only
└── orchestrator_20250930_182200.log     # Orchestrator activity only
```

## Log Format

Each log line includes:
```
<timestamp> | <level> | <module> | <function> | Line <line_number> | <message>
```

Example:
```
2025-09-30 18:22:00.123 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 40   | → ENTERING review_and_decide
2025-09-30 18:22:00.124 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 50   |   ▸ Starting review (iteration 0/10, 9 loops remaining)
2025-09-30 18:22:00.125 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 59   |   ▸ Using LLM model: gpt-5
2025-09-30 18:22:00.500 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 136  |   ▸ Preview enabled: True, WebSocket: True
2025-09-30 18:22:00.501 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 140  |   ▸ Starting preview task for thinking phase
2025-09-30 18:22:00.502 | INFO     | cedar_orchestrator.chief_agent | review_and_decide | Line 145  | ✓ SUCCESS: Preview task started for thinking phase
```

## Usage in Code

### Import the Logging System

```python
from cedar_orchestrator.logging_config import (
    get_logger, 
    log_function_entry, 
    log_function_exit, 
    log_step, 
    log_success, 
    log_error, 
    log_warning
)

# Create logger for your module
logger = get_logger(__name__)
```

### Log Function Entry/Exit

```python
def my_function(param1, param2):
    log_function_entry(logger, "my_function", param1=param1, param2=param2)
    
    try:
        # Do work...
        result = do_something()
        
        log_function_exit(logger, "my_function", result=result)
        return result
    except Exception as e:
        log_error(logger, "Function failed", e)
        log_function_exit(logger, "my_function", result="ERROR")
        raise
```

### Log Steps

```python
def process_data(data):
    log_function_entry(logger, "process_data", data_size=len(data))
    
    log_step(logger, "Validating input data")
    if not validate(data):
        log_error(logger, "Validation failed")
        return None
    log_success(logger, "Validation passed")
    
    log_step(logger, "Processing data")
    result = process(data)
    log_success(logger, f"Processed {len(result)} items")
    
    log_function_exit(logger, "process_data")
    return result
```

### Log Warnings

```python
if not optional_feature_available:
    log_warning(logger, "Optional feature not available", "Continuing without it")
```

### Log Errors with Stack Traces

```python
try:
    risky_operation()
except Exception as e:
    log_error(logger, "Operation failed", e)
    # Stack trace is automatically logged
```

## Viewing Logs

### View Latest Backend Log

```bash
# Find latest log
ls -lt ~/Library/Logs/CedarPy/ | head -5

# View full log
cat ~/Library/Logs/CedarPy/backend_YYYYMMDD_HHMMSS.log

# Tail log in real-time
tail -f ~/Library/Logs/CedarPy/backend_YYYYMMDD_HHMMSS.log

# Search for specific events
grep "preview" ~/Library/Logs/CedarPy/backend_*.log
grep "ERROR" ~/Library/Logs/CedarPy/backend_*.log
grep "ChiefAgent" ~/Library/Logs/CedarPy/backend_*.log
```

### View Component-Specific Log

```bash
# View ChiefAgent logs only
cat ~/Library/Logs/CedarPy/chief_agent_*.log

# View PreviewStreamer logs only
cat ~/Library/Logs/CedarPy/preview_streamer_*.log
```

## What Gets Logged

### Every Backend Component Logs:

1. **Function Entry**: Parameters and context
2. **Each Step**: What's happening at each stage
3. **Success**: When operations complete successfully
4. **Warnings**: When something is missing or suboptimal
5. **Errors**: When things fail, with full stack traces
6. **Function Exit**: Return values and completion status

### Example: ChiefAgent Decision Flow

```
→ ENTERING review_and_decide
  ▸ Starting review (iteration 0/10)
  ▸ Using LLM model: gpt-5
  ▸ Sending thinking/synthesis start event to UI
  ▸ Sending WebSocket event: thinking_start
✓ SUCCESS: WebSocket event sent successfully
  ▸ Building messages for Chief Agent
  ▸ Checking preview streaming configuration
  ▸ Preview enabled: True, WebSocket: True
  ▸ Starting preview task for thinking phase
✓ SUCCESS: Preview task started for thinking phase
  ▸ Calling LLM with 5 messages
✓ SUCCESS: LLM response received
  ▸ Cancelling preview task
✓ SUCCESS: Preview task cancelled
  ▸ Got response: 1234 chars
  ▸ Parsing JSON response
✓ SUCCESS: JSON parsed successfully
← EXITING review_and_decide
```

## Debugging with Logs

### Find Where Code is Failing

```bash
# Search for errors
grep "ERROR" ~/Library/Logs/CedarPy/backend_*.log

# Find last function that succeeded
grep "SUCCESS" ~/Library/Logs/CedarPy/backend_*.log | tail -20

# See what step failed
grep -A 5 "ERROR" ~/Library/Logs/CedarPy/backend_*.log
```

### Verify Code is Actually Running

```bash
# Check if preview streaming is running
grep -i "preview" ~/Library/Logs/CedarPy/backend_*.log

# Check if ChiefAgent is being called
grep "ENTERING review_and_decide" ~/Library/Logs/CedarPy/backend_*.log

# Check if WebSocket events are being sent
grep "WebSocket event" ~/Library/Logs/CedarPy/backend_*.log
```

### Trace Execution Flow

```bash
# Follow a specific thread or request
grep "thread_id=123" ~/Library/Logs/CedarPy/backend_*.log

# See all function entries and exits
grep -E "(ENTERING|EXITING)" ~/Library/Logs/CedarPy/backend_*.log
```

## Testing the Logging System

Run the test script to verify logging is working:

```bash
cd /Users/leonardspeiser/Projects/cedarpy
python test_preview_streaming.py
```

This will:
1. Connect to WebSocket
2. Send a test query
3. Display all log files created
4. Show the last 50 lines of the main log

## Log Levels

- **DEBUG**: Detailed information for debugging (parameters, intermediate values)
- **INFO**: General progress updates (steps, successes)
- **WARNING**: Something is missing or suboptimal but not critical
- **ERROR**: Something failed

## Configuration

### Console Output

By default, logs go to:
- File (always, DEBUG level)
- Console (INFO level and above)

To disable console output:
```python
logger = get_logger(__name__, also_to_console=False)
```

### Log Level

To change log level:
```python
logger = get_logger(__name__, level=logging.INFO)  # Less verbose
logger = get_logger(__name__, level=logging.DEBUG) # More verbose
```

## Best Practices

1. **Always log function entry/exit** for any non-trivial function
2. **Log each significant step** in multi-step operations
3. **Log success** when operations complete (don't just log failures!)
4. **Log with context** - include relevant parameters and state
5. **Don't log secrets** - avoid logging API keys, passwords, etc.
6. **Use appropriate levels** - DEBUG for details, INFO for progress, WARNING for issues, ERROR for failures

## Related

- [Bytecode Cache Issue Documentation](BYTECODE_CACHE_ISSUE.md)
- [Preview Streaming Documentation](PREVIEW_STREAMING.md)

## Example: Debugging Preview Streaming

**Before comprehensive logging:**
- "Preview streaming doesn't work"
- No way to see if preview code is running
- Can't tell if it's a code issue or configuration issue

**After comprehensive logging:**
```bash
# Check logs
grep -i "preview" ~/Library/Logs/CedarPy/backend_*.log

# Output shows:
→ ENTERING start_preview_task
  ▸ Preview enabled: True, WebSocket: True
  ▸ Starting preview task for thinking phase
  ▸ Creating preview task
✓ SUCCESS: Preview task created successfully
← EXITING start_preview_task

→ ENTERING stream_preview
  ▸ Starting preview stream for thinking phase
  ▸ Messages to send: 5
  ▸ Using preview model: gpt-5-nano
  ▸ Calling OpenAI API for preview streaming
✓ SUCCESS: Preview stream initiated
  ▸ Sending preview_start event to WebSocket
✓ SUCCESS: preview_start event sent
```

Now we can **see exactly what's happening** and verify the code is working!
