#!/usr/bin/env python3
"""Simple WebSocket test to verify preview streaming"""

import asyncio
import websockets
import json
import sys

async def test():
    uri = "ws://localhost:8000/ws/chat"
    
    print("Connecting...")
    async with websockets.connect(uri) as ws:
        print("Connected!\n")
        
        # Send message
        message = {
            "type": "message",
            "content": "I need to analyze a chart from a PDF file and store the data in my database. How should I approach this?",
            "project_id": 1
        }
        
        print(f"Sending: {message['content']}\n")
        await ws.send(json.dumps(message))
        
        print("=" * 80)
        print("RECEIVING EVENTS:")
        print("=" * 80)
        
        preview_started = False
        preview_text = ""
        
        async for msg in ws:
            data = json.loads(msg)
            event_type = data.get("type", "unknown")
            
            if event_type == "preview_start":
                preview_started = True
                print(f"\n🎬 PREVIEW START ({data.get('phase')}, {data.get('model')})")
                print("-" * 80)
            
            elif event_type == "preview_token":
                text = data.get("text", "")
                preview_text += text
                print(text, end="", flush=True)
            
            elif event_type == "preview_complete":
                if preview_started:
                    print("\n" + "-" * 80)
                    print(f"✅ PREVIEW COMPLETE ({data.get('total_length')} chars)\n")
            
            elif event_type == "final":
                print(f"\n📝 FINAL ANSWER:\n{data.get('text', '')}\n")
                break
            
            elif event_type == "error":
                print(f"\n❌ ERROR: {data.get('error', 'unknown')}\n")
                break
            
            else:
                # Show other events concisely
                print(f"[{event_type}]", end=" ", flush=True)
        
        print("\n" + "=" * 80)
        print("DONE")
        print("=" * 80)

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
