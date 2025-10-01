# Preview Streaming - Fast Model Preview

## Overview
While waiting for gpt-5 to respond, we run gpt-5-nano in parallel and stream its response word-by-word. This makes the wait feel instant and keeps users engaged.

## How It Works

```
User sends query
    ↓
Chief Agent starts
    ↓
    ├─ gpt-5-nano (fast preview) ──→ streams word-by-word to UI
    │  Non-blocking background task
    │
    └─ gpt-5 (real model) ──→ waits for full response
    
When gpt-5 responds:
    - Cancel gpt-5-nano stream
    - Use gpt-5 response for actual decision
```

## Backend Implementation

### Module: `preview_streamer.py` (180 lines)

**PreviewStreamer** class:
- `stream_preview()` - Streams gpt-5-nano response word-by-word
- `start_preview_task()` - Starts preview as background task
- `cancel_preview()` - Cancels preview when real response arrives

**PreviewConfig** class:
- `ENABLED` - Enable/disable feature (env: `CEDARPY_PREVIEW_ENABLED`)
- `MODEL` - Preview model name (env: `CEDARPY_PREVIEW_MODEL`, default: "gpt-5-nano")
- `START_DELAY_MS` - Delay before starting (env: `CEDARPY_PREVIEW_DELAY`, default: 100ms)
- `MAX_TOKENS` - Max preview length (env: `CEDARPY_PREVIEW_MAX_TOKENS`, default: 2000)

### Integration in Chief Agent

Added 3 lines to `chief_agent.py`:
1. Start preview task before main LLM call
2. Run both in parallel
3. Cancel preview when real response arrives

```python
# Start preview (non-blocking)
preview_task = PreviewStreamer.start_preview_task(
    self.llm_client, messages, ws, phase
)

# Main call (blocking)
response = await self.llm_client.chat.completions.create(...)

# Cancel preview
await PreviewStreamer.cancel_preview(preview_task)
```

## Frontend Integration

### 1. WebSocket Events

#### Preview Events
```javascript
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'preview_start':
            // Preview streaming starting
            showPreviewBubble(data.phase); // "thinking" or "synthesis"
            break;
            
        case 'preview_token':
            // Stream each word/token
            appendToPreviewBubble(data.text);
            break;
            
        case 'preview_complete':
            // Preview finished
            // (Real response will arrive separately)
            break;
    }
};
```

#### Example UI Implementation
```javascript
let previewBubble = null;

function showPreviewBubble(phase) {
    previewBubble = document.createElement('div');
    previewBubble.className = 'preview-bubble';
    previewBubble.setAttribute('data-phase', phase);
    previewBubble.innerHTML = '<span class="preview-label">Preview...</span><div class="preview-text"></div>';
    chatContainer.appendChild(previewBubble);
}

function appendToPreviewBubble(text) {
    if (!previewBubble) return;
    const textDiv = previewBubble.querySelector('.preview-text');
    textDiv.textContent += text;
    
    // Auto-scroll
    chatContainer.scrollTop = chatContainer.scrollHeight;
}
```

### 2. CSS for Preview Bubble

```css
.preview-bubble {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 16px;
    border-radius: 12px;
    margin: 12px 0;
    opacity: 0.8;
    font-style: italic;
    animation: fadeIn 0.3s ease-in;
}

.preview-label {
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.7;
    margin-bottom: 8px;
}

.preview-text {
    line-height: 1.6;
    word-wrap: break-word;
}

/* Streaming cursor effect */
.preview-text::after {
    content: '▊';
    animation: blink 1s infinite;
}

@keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 0.8; transform: translateY(0); }
}
```

### 3. React Component Example

```jsx
function ChatBubble({ message }) {
    const [previewText, setPreviewText] = useState('');
    const [isPreview, setIsPreview] = useState(false);
    
    useEffect(() => {
        const handleMessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'preview_start') {
                setIsPreview(true);
                setPreviewText('');
            } else if (data.type === 'preview_token') {
                setPreviewText(prev => prev + data.text);
            } else if (data.type === 'preview_complete') {
                // Preview done, real answer coming
            }
        };
        
        ws.addEventListener('message', handleMessage);
        return () => ws.removeEventListener('message', handleMessage);
    }, []);
    
    if (isPreview && !message.final) {
        return (
            <div className="preview-bubble">
                <span className="preview-label">Preview...</span>
                <div className="preview-text">{previewText}</div>
            </div>
        );
    }
    
    return (
        <div className="message-bubble">
            {message.text}
        </div>
    );
}
```

### 4. Optional: Replace Preview with Real Answer

```javascript
function handleRealAnswer(data) {
    // When real answer arrives, fade out preview and show real content
    const previewBubble = document.querySelector('.preview-bubble');
    
    if (previewBubble) {
        // Smooth transition
        previewBubble.style.transition = 'opacity 0.3s';
        previewBubble.style.opacity = '0';
        
        setTimeout(() => {
            previewBubble.remove();
            showRealAnswer(data);
        }, 300);
    } else {
        showRealAnswer(data);
    }
}
```

## Configuration

### Environment Variables

```bash
# Enable/disable preview streaming
export CEDARPY_PREVIEW_ENABLED=true

# Preview model (must be faster than main model)
export CEDARPY_PREVIEW_MODEL=gpt-5-nano

# Delay before starting preview (ms)
# Useful if main model sometimes responds instantly
export CEDARPY_PREVIEW_DELAY=100

# Max tokens for preview
export CEDARPY_PREVIEW_MAX_TOKENS=2000
```

### Runtime Control

```python
from cedar_orchestrator.preview_streamer import PreviewConfig

# Disable temporarily
PreviewConfig.ENABLED = False

# Change model
PreviewConfig.MODEL = "gpt-4o-mini"
```

## Behavior

### Normal Flow
1. User sends query
2. **Preview starts immediately** (gpt-5-nano streams)
3. User sees words appearing in real-time
4. After ~1-2 seconds, gpt-5 responds
5. Preview is cancelled
6. Real answer is used for decision

### If Preview Fails
- Preview failure is logged but doesn't affect orchestration
- Main gpt-5 call continues normally
- User experience degrades gracefully (just no preview)

### If Main Model Is Fast
- Preview might complete before being cancelled
- That's OK - preview gives same answer, just faster
- Real model's answer is still used for decisions

## Benefits

✅ **Perceived speed** - Feels 10x faster even though real model takes same time  
✅ **Engagement** - Users stay engaged watching text stream  
✅ **Non-blocking** - Doesn't slow down main process  
✅ **Safe** - Preview is ignored, real model decides  
✅ **Configurable** - Can be disabled or customized  

## Testing

### Test Preview Streaming
```javascript
// Watch for preview events
ws.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    if (data.type.startsWith('preview_')) {
        console.log('Preview event:', data);
    }
});
```

### Verify Real Answer Used
```python
# Check logs
grep "Preview task started" logs/orchestrator*.log
grep "Preview task cancelled" logs/orchestrator*.log
```

### Performance Check
```javascript
const startTime = Date.now();

ws.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'preview_start') {
        console.log('Preview started at:', Date.now() - startTime, 'ms');
    }
    
    if (data.type === 'thinking_complete' || data.type === 'synthesis_complete') {
        console.log('Real answer at:', Date.now() - startTime, 'ms');
    }
});
```

## Edge Cases

### Preview Finishes First
- Preview completes before real model
- User sees full preview text
- Real model arrives and replaces preview (or preview stays if same)

### Preview Is Wrong
- Doesn't matter - real model's answer is used for decisions
- Preview is just UI candy for perceived speed

### WebSocket Disconnects
- Preview fails gracefully
- Main orchestration continues
- No error thrown

### Model Not Available
- If gpt-5-nano not available, preview fails
- Logged as warning, doesn't crash
- Main model continues normally

## Event Timeline

```
0ms:    User sends "what is 2+2"
100ms:  preview_start event
120ms:  preview_token: "I'll"
140ms:  preview_token: " calculate"
160ms:  preview_token: " that"
180ms:  preview_token: " for"
200ms:  preview_token: " you..."
...
2000ms: Real gpt-5 response arrives
2001ms: Preview cancelled
2002ms: thinking_complete event
2003ms: Real answer displayed
```

## Notes

- Preview runs in **background task** - doesn't block
- Preview uses **same messages** as real model
- Preview is **cancelled immediately** when real response arrives
- Preview text is **never used for decisions** - only for UI
- Works for both **planning** and **synthesis** phases
