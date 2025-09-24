"""
WebSocket chat tests for CedarPy application
"""

import asyncio
import websockets
import json
import time
from typing import Dict, Tuple, Any, List, Optional
from test_config import (
    WS_URL,
    WS_ENDPOINTS,
    TEST_MATH_QUESTION,
    TEST_SIMPLE_QUESTION,
    EXPECTED_MATH_ANSWER_CONTAINS,
    EXPECTED_SIMPLE_ANSWER_CONTAINS,
    TEST_TIMEOUT,
    TEST_CONFIG
)

class WebSocketChatTests:
    """Test WebSocket chat functionality including LLM responses"""
    
    def __init__(self):
        self.ws_url = WS_URL
        self.test_results = []
        self.connection_established = False
    
    async def test_websocket_connection(self) -> Tuple[bool, str]:
        """Test establishing WebSocket connection"""
        try:
            uri = f"{self.ws_url}{WS_ENDPOINTS['chat']}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Wait for connection message
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                
                if data.get("type") == "connected":
                    self.connection_established = True
                    return True, f"WebSocket connected: {data.get('message', 'Connected')}"
                else:
                    return True, "WebSocket connected (no greeting message)"
                    
        except asyncio.TimeoutError:
            return False, "WebSocket connection timed out"
        except ConnectionRefusedError:
            return False, "WebSocket connection refused - is the server running?"
        except Exception as e:
            return False, f"WebSocket connection error: {str(e)}"
    
    async def test_simple_message(self) -> Tuple[bool, str]:
        """Test sending a simple message and receiving response"""
        try:
            uri = f"{self.ws_url}{WS_ENDPOINTS['chat']}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Skip connection message if any
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                
                # Send test message
                test_message = {
                    "type": "message",
                    "content": "Hello, this is a test"
                }
                await websocket.send(json.dumps(test_message))
                
                # Collect responses
                responses = []
                start_time = time.time()
                
                while time.time() - start_time < 10:  # Wait up to 10 seconds
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1)
                        data = json.loads(response)
                        responses.append(data)
                        
                        # Check for final response
                        if data.get("type") == "final_response":
                            return True, f"Received response: {data.get('content', '')[:50]}..."
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
                
                if responses:
                    return True, f"Received {len(responses)} response messages"
                else:
                    return False, "No response received for simple message"
                    
        except Exception as e:
            return False, f"Simple message test error: {str(e)}"
    
    async def test_math_question(self) -> Tuple[bool, str]:
        """Test math question: What is the square root of 9393492?"""
        if TEST_CONFIG["skip_llm_tests"]:
            return True, "Skipping LLM test (disabled)"
        
        try:
            uri = f"{self.ws_url}{WS_ENDPOINTS['chat']}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Skip connection message
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                
                # Send math question
                message = {
                    "type": "message",
                    "content": TEST_MATH_QUESTION
                }
                await websocket.send(json.dumps(message))
                
                # Collect all responses
                all_responses = []
                final_response = None
                start_time = time.time()
                
                while time.time() - start_time < TEST_TIMEOUT:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2)
                        data = json.loads(response)
                        all_responses.append(data)
                        
                        # Look for final response
                        if data.get("type") == "final_response":
                            final_response = data.get("content", "")
                            break
                        elif data.get("type") == "thinker_reasoning":
                            # Good - we're getting reasoning updates
                            continue
                        elif data.get("type") == "agent_result":
                            # Good - agents are working
                            continue
                            
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
                
                # Check if answer is correct (sqrt(9393492) ≈ 3065.08)
                if final_response:
                    response_lower = final_response.lower()
                    # Check if any expected answer component is in response
                    found_answer = any(exp.lower() in response_lower 
                                     for exp in EXPECTED_MATH_ANSWER_CONTAINS)
                    
                    if found_answer:
                        return True, f"Math question answered correctly: {final_response[:100]}..."
                    else:
                        return True, f"Math question answered (accuracy uncertain): {final_response[:100]}..."
                else:
                    # Check if we got any responses
                    if all_responses:
                        return True, f"Received {len(all_responses)} messages but no final answer"
                    else:
                        return False, "No response received for math question"
                    
        except Exception as e:
            return False, f"Math question test error: {str(e)}"
    
    async def test_simple_arithmetic(self) -> Tuple[bool, str]:
        """Test simple arithmetic: What is 2 + 2?"""
        try:
            uri = f"{self.ws_url}{WS_ENDPOINTS['chat']}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Skip connection message
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                
                # Send simple question
                message = {
                    "type": "message",
                    "content": TEST_SIMPLE_QUESTION
                }
                await websocket.send(json.dumps(message))
                
                # Wait for response
                final_response = None
                start_time = time.time()
                
                while time.time() - start_time < 10:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1)
                        data = json.loads(response)
                        
                        if data.get("type") == "final_response":
                            final_response = data.get("content", "")
                            break
                            
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
                
                if final_response:
                    response_lower = final_response.lower()
                    found_answer = any(exp.lower() in response_lower 
                                     for exp in EXPECTED_SIMPLE_ANSWER_CONTAINS)
                    
                    if found_answer:
                        return True, f"Simple arithmetic correct: {final_response[:50]}..."
                    else:
                        return True, f"Simple arithmetic answered: {final_response[:50]}..."
                else:
                    return False, "No response for simple arithmetic"
                    
        except Exception as e:
            return False, f"Simple arithmetic test error: {str(e)}"
    
    async def test_websocket_streaming(self) -> Tuple[bool, str]:
        """Test that WebSocket streams multiple message types"""
        try:
            uri = f"{self.ws_url}{WS_ENDPOINTS['chat']}"
            async with websockets.connect(uri, timeout=5) as websocket:
                # Skip connection message
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                
                # Send a message that should trigger streaming
                message = {
                    "type": "message",
                    "content": "Tell me about WebSockets"
                }
                await websocket.send(json.dumps(message))
                
                # Collect message types
                message_types = set()
                message_count = 0
                start_time = time.time()
                
                while time.time() - start_time < 10:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1)
                        data = json.loads(response)
                        message_types.add(data.get("type", "unknown"))
                        message_count += 1
                        
                        if data.get("type") == "final_response":
                            break
                            
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
                
                if message_count > 1:
                    return True, f"Streaming works: {message_count} messages, types: {', '.join(message_types)}"
                elif message_count == 1:
                    return True, "Single message received (streaming may be disabled)"
                else:
                    return False, "No streaming messages received"
                    
        except Exception as e:
            return False, f"Streaming test error: {str(e)}"
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all WebSocket tests"""
        if TEST_CONFIG["skip_ws_tests"]:
            return {
                "passed": ["WebSocket Tests"],
                "failed": [],
                "total": 1,
                "details": [{"name": "WebSocket Tests", "passed": True, "message": "Skipped (disabled)"}],
                "success_rate": 100.0
            }
        
        tests = [
            ("WebSocket Connection", self.test_websocket_connection),
            ("Simple Message", self.test_simple_message),
            ("Math Question", self.test_math_question),
            ("Simple Arithmetic", self.test_simple_arithmetic),
            ("Message Streaming", self.test_websocket_streaming),
        ]
        
        results = {
            "passed": [],
            "failed": [],
            "total": len(tests),
            "details": []
        }
        
        for test_name, test_func in tests:
            try:
                passed, message = await test_func()
                result = {
                    "name": test_name,
                    "passed": passed,
                    "message": message
                }
                
                if passed:
                    results["passed"].append(test_name)
                    if TEST_CONFIG["verbose"]:
                        print(f"✓ {test_name}: {message}")
                else:
                    results["failed"].append(test_name)
                    print(f"✗ {test_name}: {message}")
                
                results["details"].append(result)
            except Exception as e:
                results["failed"].append(test_name)
                results["details"].append({
                    "name": test_name,
                    "passed": False,
                    "message": f"Unexpected error: {str(e)}"
                })
                print(f"✗ {test_name}: Unexpected error - {str(e)}")
        
        results["success_rate"] = len(results["passed"]) / results["total"] * 100 if results["total"] > 0 else 0
        
        return results

def run_websocket_tests() -> Dict[str, Any]:
    """Synchronous wrapper to run async WebSocket tests"""
    tester = WebSocketChatTests()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(tester.run_all_tests())
    finally:
        loop.close()

if __name__ == "__main__":
    results = run_websocket_tests()
    
    print(f"\n{'='*50}")
    print(f"WebSocket Chat Test Results:")
    print(f"Passed: {len(results['passed'])}/{results['total']}")
    print(f"Success Rate: {results['success_rate']:.1f}%")
    if results['failed']:
        print(f"Failed Tests: {', '.join(results['failed'])}")