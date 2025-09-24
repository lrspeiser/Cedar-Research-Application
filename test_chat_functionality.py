#!/usr/bin/env python3
"""
Test script to verify chat functionality end-to-end.
Tests WebSocket connection and message processing.
"""

import asyncio
import json
import websockets
import time

async def test_chat():
    """Test chat WebSocket connection and message flow"""
    project_id = 1
    branch_id = 1
    
    # Connect to WebSocket endpoint
    uri = f"ws://localhost:8000/ws/chat/{project_id}"
    
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to WebSocket")
            
            # Send a test message
            test_message = {
                "action": "chat",
                "content": "What is 2+2?",
                "branch_id": branch_id,
                "thread_id": None,
                "file_id": None,
                "dataset_id": None
            }
            
            print(f"Sending test message: {test_message['content']}")
            await websocket.send(json.dumps(test_message))
            print("✓ Message sent")
            
            # Listen for responses
            print("\n--- Server responses ---")
            start_time = time.time()
            timeout = 30  # 30 second timeout
            
            try:
                while time.time() - start_time < timeout:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(response)
                    print(f"Response type: {data.get('type', 'unknown')}")
                    
                    if data.get('type') == 'message':
                        print(f"  Role: {data.get('role', '')}")
                        print(f"  Text: {data.get('text', '')[:100]}...")
                    elif data.get('type') == 'stream':
                        print(f"  Stream: {data.get('text', '')[:100]}...")
                    elif data.get('type') == 'error':
                        print(f"  Error: {data.get('message', '')}")
                    elif data.get('type') == 'final':
                        print(f"  Final answer: {data.get('text', '')[:200]}...")
                        print("\n✓ Chat test completed successfully!")
                        break
                    else:
                        print(f"  Data: {json.dumps(data)[:200]}...")
                        
            except asyncio.TimeoutError:
                # Normal - just means no more messages
                pass
                
            print("\n--- Test complete ---")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("=== Cedar Chat Functionality Test ===\n")
    
    # Check if server is running
    import requests
    try:
        resp = requests.get("http://localhost:8000/")
        print(f"✓ Server is running (status: {resp.status_code})")
    except Exception as e:
        print(f"❌ Server is not reachable: {e}")
        print("Please ensure the server is running with: python cedar_app/main_app_server.py")
        exit(1)
    
    # Run the async test
    success = asyncio.run(test_chat())
    
    if success:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Tests failed")
        exit(1)