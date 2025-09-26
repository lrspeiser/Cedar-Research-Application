# WebSocket Chat Multi-Agent Orchestration Fix

## Problem
The chat functionality was broken after switching to WebSocket/FastAPI. When a user typed a query like "what is the square root of 3934934", it should have distributed the query to multiple LLMs and streamed the responses back, but this was not working.

## Root Causes
1. **Wrong main module**: Server was using `cedar_app.main:app` instead of `main:app` which doesn't include the orchestrator registration
2. **JavaScript syntax error**: Regex patterns in `page_rendering.py` had incorrect escaping (`\\\\` instead of `\\`)

## Solution

### 1. Fixed Server Launch
```bash
# Wrong:
uvicorn cedar_app.main:app

# Correct:
uvicorn main:app
```

### 2. Fixed JavaScript Regex Escaping
In `cedar_app/utils/page_rendering.py` line 868:
```javascript
// Before (broken):
var answerMatch = fullText.match(/Answer:\\\\s*([^\\\\n]+...)/);

// After (fixed):
var answerMatch = fullText.match(/Answer:\\s*([^\\n]+...)/);
```

## How It Works Now

1. **User sends query** via WebSocket to `/ws/chat/{project_id}`
2. **Thinker analyzes** the query type (mathematical, coding, explanation, etc.)
3. **Orchestrator dispatches** to relevant agents in parallel:
   - Coding Agent (for calculations)
   - Logical Reasoner (for step-by-step analysis)
   - General Assistant (for direct answers)
   - SQL Agent (for database queries)
4. **Each agent processes** the query independently
5. **Results stream back** to the frontend as they complete
6. **Best answer selected** based on confidence scores
7. **Final formatted response** sent with Answer/Why/Issues/Next Steps structure

## Testing

Run the comprehensive test:
```bash
python test_complete_chat.py
```

Test individual queries:
```python
import asyncio
import json
import websockets

async def test():
    async with websockets.connect("ws://localhost:8000/ws/chat/44") as ws:
        await ws.send(json.dumps({"type": "message", "content": "what is 25 * 17 + 93"}))
        while True:
            data = json.loads(await ws.recv())
            if data.get("type") == "message":
                print(data.get("text"))
                break

asyncio.run(test())
```

## Files Modified
- `cedar_app/utils/page_rendering.py` - Fixed JavaScript regex escaping
- `test_complete_chat.py` - Added comprehensive test suite

## Verification
✅ Mathematical calculations work (square roots, arithmetic)  
✅ Multiple agents respond in parallel  
✅ Responses properly formatted  
✅ No JavaScript syntax errors  
✅ WebSocket streaming functional
