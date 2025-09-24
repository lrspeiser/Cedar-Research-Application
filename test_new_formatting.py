#!/usr/bin/env python
"""
Test script to demonstrate the new orchestrator formatting
Run this to see the improved output structure
"""

import asyncio
import json
from websockets import connect

async def test_orchestrator():
    """Test the orchestrator with various queries"""
    
    test_queries = [
        # Simple math that should work
        "What is the square root of 144?",
        
        # Complex calculation
        "Calculate 25 * 4 + sqrt(100) - 3^2",
        
        # Query that might need clarification (uncomment to test)
        # "Do something unclear and ambiguous???",
    ]
    
    uri = "ws://localhost:8000/ws/chat"
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Testing: {query}")
        print('='*60)
        
        try:
            async with connect(uri) as websocket:
                # Send the query
                message = {
                    "action": "chat",
                    "content": query,
                    "use_orchestrator": True
                }
                await websocket.send(json.dumps(message))
                
                # Receive responses
                while True:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        data = json.loads(response)
                        
                        # Print based on message type
                        if data.get("type") == "agent_result":
                            agent_name = data.get("agent_name", "Unknown")
                            text = data.get("text", "")
                            # Extract just the Answer line for display
                            if "Answer:" in text:
                                answer_line = text.split('\n')[0]
                                print(f"  [{agent_name}] {answer_line}")
                            else:
                                print(f"  [{agent_name}] Processing...")
                                
                        elif data.get("type") == "message":
                            role = data.get("role", "Unknown")
                            text = data.get("text", "")
                            print(f"\nFINAL RESPONSE from {role}:")
                            print("-" * 40)
                            print(text)
                            break
                            
                        elif data.get("type") == "action":
                            function = data.get("function", "")
                            if function == "processing":
                                print("  [System] Analyzing request...")
                                
                    except asyncio.TimeoutError:
                        print("  [Timeout] No more responses")
                        break
                        
        except Exception as e:
            print(f"  [Error] {e}")

if __name__ == "__main__":
    print("Testing New Orchestrator Formatting")
    print("====================================")
    print("This will show:")
    print("1. Collapsible agent bubbles (in UI)")
    print("2. Structured Answer/Why/Issues/Next Steps format")
    print("3. Cleaner final output")
    print("")
    
    asyncio.run(test_orchestrator())
    
    print("\n\nTest complete! Check the web UI for the visual improvements:")
    print("- Agent bubbles show just the answer with '(click for details)'")
    print("- Final response uses structured format")
    print("- Processing time shown minimally at the end")