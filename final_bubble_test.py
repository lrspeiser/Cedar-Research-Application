#!/usr/bin/env python3
import asyncio
import json
import websockets
import time

async def test():
    print("🧪 Testing Cedar Chat UI Bubble Display")
    print("=" * 60)
    
    uri = 'ws://localhost:8000/ws/chat/44'
    async with websockets.connect(uri) as ws:
        query = "what is the square root of 25"
        await ws.send(json.dumps({'type': 'message', 'content': query}))
        print(f"✅ Sent query: {query}")
        print("\n📨 Waiting for responses...")
        
        message_count = 0
        bubble_should_appear = False
        start_time = time.time()
        
        while time.time() - start_time < 15:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(msg)
                message_count += 1
                msg_type = data.get('type')
                
                print(f"\n  {message_count}. Received: type={msg_type}")
                
                if msg_type == 'message':
                    bubble_should_appear = True
                    role = data.get('role', 'unknown')
                    text = data.get('text', '')
                    
                    print(f"     🎯 FINAL MESSAGE - Bubble should appear!")
                    print(f"     Role: '{role}'")
                    print(f"     Text preview: {text[:100]}...")
                    
                    # Check if the message has proper formatting
                    if '**' in text:
                        print(f"     ✅ Has markdown formatting")
                    
                    break
                elif msg_type == 'agent_result':
                    print(f"     Agent: {data.get('agent_name', 'unknown')}")
                elif msg_type == 'stream':
                    print(f"     Stream: {data.get('text', '')[:50]}")
                    
            except asyncio.TimeoutError:
                continue
        
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS:")
        if bubble_should_appear:
            print("✅ SUCCESS: Final message received - bubble should be displayed!")
            print("\n🖥️  To verify in browser:")
            print("   1. Open http://localhost:8000/project/44?branch_id=1&thread_id=1")
            print("   2. Type: 'what is the square root of 25'")
            print("   3. You should see:")
            print("      - Your message bubble (user)")
            print("      - Processing messages")
            print("      - Agent result bubbles")
            print("      - Final answer bubble with agent name (e.g., 'Code Executor')")
        else:
            print("❌ FAILURE: No final message received - bubble won't appear!")
            
        print(f"\nTotal messages: {message_count}")

if __name__ == "__main__":
    asyncio.run(test())
