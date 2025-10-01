# Stop Button and Spinner Control

## Overview
The system now supports user-initiated stop requests and consistent spinner control across all pages (main chat and history).

## Backend Implementation

### Stop Handler (`stop_handler.py`)
Manages graceful termination when user clicks stop:
- Thread-safe stop flags keyed by `thread_id`
- Generates summary of completed work
- Sends spinner-stop signals to UI
- Creates partial answer from completed agents

### Integration Points
Stop checks happen at 4 points in orchestration flow:
1. **Start of iteration** - Before any work begins
2. **Before Phase 2** - Before executing agents
3. **Before Phase 3** - Before synthesis
4. **Normal completion** - Cleanup

## Frontend Integration

### 1. WebSocket Events to Handle

#### Spinner Control Events
```javascript
// Start spinners
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'thinking_start':
            showSpinner('Planning'); // Planning phase
            break;
            
        case 'synthesis_start':
            showSpinner('Synthesis'); // Synthesis phase
            break;
            
        // CRITICAL: Stop spinner events
        case 'thinking_complete':
        case 'synthesis_complete':
        case 'processing_stopped':
            hideSpinner(); // Stop spinner on ALL pages
            break;
            
        case 'final':
            hideSpinner(); // Also stop on final answer
            break;
    }
};
```

#### Stop-Related Events
```javascript
case 'user_stopped':
    // User clicked stop, processing terminated
    hideSpinner();
    showMessage("Processing stopped by user");
    console.log(`Partial results: ${data.partial_results_count} agents completed`);
    break;
```

### 2. Stop Button Implementation

#### HTML/React Component
```jsx
function ChatInterface() {
    const [isProcessing, setIsProcessing] = useState(false);
    const [currentThreadId, setCurrentThreadId] = useState(null);
    
    return (
        <div className="chat-input-area">
            <input 
                type="text" 
                placeholder="Ask a question..."
                onSubmit={handleSubmit}
            />
            
            {!isProcessing ? (
                <button onClick={handleSubmit}>
                    Submit
                </button>
            ) : (
                <button 
                    onClick={handleStop}
                    className="stop-button"
                    style={{ background: '#ff4444' }}
                >
                    Stop
                </button>
            )}
        </div>
    );
}
```

#### Stop Handler
```javascript
async function handleStop() {
    if (!currentThreadId) {
        console.warn('No active thread to stop');
        return;
    }
    
    try {
        // Send stop request to backend
        const response = await fetch('/api/stop_orchestration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thread_id: currentThreadId })
        });
        
        if (response.ok) {
            console.log('Stop request sent');
            // UI will update via WebSocket events
        }
    } catch (error) {
        console.error('Failed to send stop request:', error);
    }
}
```

### 3. Backend API Endpoint

Add this endpoint to your FastAPI app:

```python
from cedar_orchestrator.stop_handler import StopHandler

@app.post("/api/stop_orchestration")
async def stop_orchestration(request: Request):
    """Handle user stop request"""
    data = await request.json()
    thread_id = data.get('thread_id')
    
    if not thread_id:
        return JSONResponse(
            status_code=400,
            content={"error": "thread_id required"}
        )
    
    # Request stop (orchestrator will check on next cycle)
    StopHandler.request_stop(thread_id)
    
    return JSONResponse(content={
        "status": "stop_requested",
        "thread_id": thread_id,
        "message": "Orchestration will stop gracefully"
    })
```

### 4. Spinner Control Across Pages

**Key:** Use the same WebSocket connection for both main page and history page.

```javascript
// Shared spinner control (works on any page)
function setupSpinnerControl(ws) {
    ws.addEventListener('message', (event) => {
        const data = JSON.parse(event.data);
        
        // These events work on BOTH main and history pages
        if (['thinking_complete', 'synthesis_complete', 
             'processing_stopped', 'final'].includes(data.type)) {
            // Stop ALL spinners (finds spinner regardless of page)
            document.querySelectorAll('.spinner').forEach(spinner => {
                spinner.classList.add('hidden');
            });
        }
    });
}
```

### 5. State Management

```javascript
// Global state for orchestration status
const orchestrationState = {
    isProcessing: false,
    threadId: null,
    startTime: null
};

// Update on message send
function sendMessage(message) {
    orchestrationState.isProcessing = true;
    orchestrationState.threadId = generateThreadId();
    orchestrationState.startTime = Date.now();
    
    // Show stop button, hide submit
    updateUIForProcessing(true);
}

// Update on completion/stop
ws.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    
    if (['final', 'user_stopped', 'processing_stopped'].includes(data.type)) {
        orchestrationState.isProcessing = false;
        orchestrationState.threadId = null;
        
        // Hide stop button, show submit
        updateUIForProcessing(false);
    }
});
```

## Behavior

### User Clicks Stop
1. **Frontend** sends POST to `/api/stop_orchestration` with `thread_id`
2. **Backend** sets stop flag via `StopHandler.request_stop(thread_id)`
3. **Orchestrator** checks stop flag at next checkpoint
4. **Generates** summary of completed work with logs
5. **Sends** `user_stopped` + spinner stop events
6. **Clears** stop flag automatically

### Graceful Termination
The user gets a partial answer showing:
- Which agents completed
- Their confidence levels
- Summary of findings
- Processing timeline from logs

Example:
```
**Processing stopped by user**

**Completed Work (2 agents ran):**
1. **Coding Agent** (confidence: 0.95)
   Executed code successfully: 2 + 2 = 4
   
2. **Formula Agent** (confidence: 0.90)
   Verified calculation mathematically

**Processing Timeline:**
- Phase: planning.start
- Planning: agents=CodeAgent,FormulaAgent
- AgentOK: Coding Agent conf=0.95 sum=Executed code
- User requested stop
```

## Testing

### Test Stop at Different Phases
```javascript
// 1. Stop during planning (before agents run)
setTimeout(() => handleStop(), 500);

// 2. Stop during agent execution
setTimeout(() => handleStop(), 5000);

// 3. Stop during synthesis
setTimeout(() => handleStop(), 15000);
```

### Verify Spinner Stops
```javascript
// Should stop spinner on both pages
function verifySpinnerStopped() {
    const spinners = document.querySelectorAll('.spinner:not(.hidden)');
    console.assert(spinners.length === 0, 'Spinners still visible!');
}
```

## Spinner Events Summary

| Event | When | Action |
|-------|------|--------|
| `thinking_start` | Planning begins | Show spinner |
| `synthesis_start` | Synthesis begins | Show spinner |
| `thinking_complete` | Planning done | **Hide spinner** |
| `synthesis_complete` | Synthesis done | **Hide spinner** |
| `processing_stopped` | User stop/error | **Hide spinner** |
| `final` | Final answer | **Hide spinner** |
| `user_stopped` | Stop request processed | **Hide spinner** |

**All hide-spinner events work on both main page and history page.**

## Notes

- Stop is **graceful** - doesn't force-kill, waits for checkpoint
- Stop flag is **thread-specific** - won't affect other conversations
- Spinners use **multiple events** for redundancy (all stop the spinner)
- Stop button **only shows during processing** - use `isProcessing` state
- Thread ID **must be passed** with stop request for targeting
