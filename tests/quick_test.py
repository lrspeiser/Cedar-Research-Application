#!/usr/bin/env python3
"""
Quick test to verify CedarPy app is working
"""

import requests
import time
import json
import asyncio
import websockets

def test_basic_connectivity():
    """Test basic connectivity to the app"""
    base_url = "http://localhost:8000"
    
    print("Testing CedarPy App Connectivity...")
    print("="*50)
    
    # Wait for app to start
    print("Waiting for app to start...")
    for i in range(10):
        try:
            response = requests.get(f"{base_url}/", timeout=2)
            if response.status_code == 200:
                print("✓ App is running!")
                break
        except:
            pass
        time.sleep(1)
        if i > 0 and i % 3 == 0:
            print(f"  Still waiting... ({i}s)")
    else:
        print("✗ App failed to start or respond")
        return False
    
    # Test home page
    print("\n1. Testing home page...")
    try:
        response = requests.get(f"{base_url}/")
        print(f"   Status: {response.status_code}")
        if "cedar" in response.text.lower() or "project" in response.text.lower():
            print("   ✓ Home page contains expected content")
        else:
            print("   ⚠ Home page loaded but content unexpected")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test various endpoints
    endpoints = [
        "/",
        "/shell",
        "/settings",
        "/changelog",
        "/projects",
        "/api/projects",
    ]
    
    print("\n2. Testing endpoints...")
    working = []
    broken = []
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=2)
            if response.status_code in [200, 302]:
                working.append(endpoint)
                print(f"   ✓ {endpoint}: {response.status_code}")
            else:
                broken.append(f"{endpoint}:{response.status_code}")
                print(f"   ✗ {endpoint}: {response.status_code}")
        except Exception as e:
            broken.append(f"{endpoint}:error")
            print(f"   ✗ {endpoint}: Error")
    
    print(f"\n   Working: {len(working)}/{len(endpoints)}")
    if broken:
        print(f"   Failed: {', '.join(broken)}")
    
    # Test WebSocket
    print("\n3. Testing WebSocket chat...")
    
    async def test_ws():
        try:
            uri = "ws://localhost:8000/ws/chat"
            async with websockets.connect(uri) as websocket:
                # Wait for connection message
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2)
                    data = json.loads(response)
                    print(f"   ✓ WebSocket connected: {data.get('type', 'connected')}")
                except asyncio.TimeoutError:
                    print("   ✓ WebSocket connected (no greeting)")
                
                # Send test message
                test_msg = json.dumps({"type": "message", "content": "test"})
                await websocket.send(test_msg)
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5)
                    data = json.loads(response)
                    print(f"   ✓ Received response: {data.get('type')}")
                    return True
                except asyncio.TimeoutError:
                    print("   ⚠ No response received (timeout)")
                    return True
        except ConnectionRefusedError:
            print("   ✗ WebSocket connection refused")
            return False
        except Exception as e:
            print(f"   ✗ WebSocket error: {e}")
            return False
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ws_result = loop.run_until_complete(test_ws())
        loop.close()
    except Exception as e:
        print(f"   ✗ WebSocket test failed: {e}")
        ws_result = False
    
    # Test math question (if WebSocket works)
    if ws_result:
        print("\n4. Testing math question via WebSocket...")
        
        async def test_math():
            try:
                uri = "ws://localhost:8000/ws/chat"
                async with websockets.connect(uri) as websocket:
                    # Skip greeting
                    try:
                        await asyncio.wait_for(websocket.recv(), timeout=1)
                    except:
                        pass
                    
                    # Send math question
                    math_q = {"type": "message", "content": "What is the square root of 9393492?"}
                    await websocket.send(json.dumps(math_q))
                    
                    # Collect responses
                    responses = []
                    final_answer = None
                    start = time.time()
                    
                    while time.time() - start < 10:
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=1)
                            data = json.loads(response)
                            responses.append(data.get("type"))
                            
                            if data.get("type") == "final_response":
                                final_answer = data.get("content", "")
                                break
                        except asyncio.TimeoutError:
                            continue
                        except:
                            break
                    
                    if final_answer:
                        # Check if answer contains expected value (≈3065)
                        if "3065" in final_answer or "3,065" in final_answer:
                            print(f"   ✓ Correct answer received: {final_answer[:50]}...")
                        else:
                            print(f"   ⚠ Answer received: {final_answer[:50]}...")
                    elif responses:
                        print(f"   ⚠ Got {len(responses)} messages: {', '.join(set(responses))}")
                    else:
                        print("   ✗ No response to math question")
                        
            except Exception as e:
                print(f"   ✗ Math test error: {e}")
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(test_math())
            loop.close()
        except Exception as e:
            print(f"   ✗ Math test failed: {e}")
    
    print("\n" + "="*50)
    print("Quick test complete!")
    
    if len(working) >= 3:
        print("✓ App appears to be working!")
        return True
    else:
        print("⚠ App is running but some features may not work")
        return False

if __name__ == "__main__":
    import sys
    success = test_basic_connectivity()
    sys.exit(0 if success else 1)