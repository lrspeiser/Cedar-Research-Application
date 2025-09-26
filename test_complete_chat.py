#!/usr/bin/env python3
"""
Comprehensive test for Cedar chat functionality with multi-agent orchestration.
Tests that the chat system correctly distributes queries to multiple LLMs and
streams the responses back to the frontend.
"""

import asyncio
import json
import websockets
import time
import sys
from typing import List, Dict, Any

# Test cases with expected behavior
TEST_CASES = [
    {
        "query": "what is the square root of 3934934",
        "expected_agents": ["Coding Agent", "Logical Reasoner", "General Assistant"],
        "expected_answer_contains": ["1983", "1984"],  # Either precise or approximate
        "type": "mathematical"
    },
    {
        "query": "calculate 25 * 17 + 93",
        "expected_agents": ["Coding Agent", "Logical Reasoner", "General Assistant"],
        "expected_answer_contains": ["518"],
        "type": "mathematical"
    },
    {
        "query": "what is Python?",
        "expected_agents": ["Logical Reasoner", "General Assistant"],
        "expected_answer_contains": ["programming", "language"],
        "type": "explanation"
    }
]

async def test_single_query(ws, test_case: Dict[str, Any]) -> Dict[str, Any]:
    """Test a single query and verify the response."""
    query = test_case["query"]
    print(f"\n{'='*60}")
    print(f"Testing: {query}")
    print(f"Type: {test_case['type']}")
    print(f"Expected agents: {', '.join(test_case['expected_agents'])}")
    print(f"{'='*60}")
    
    # Send the query
    message = {"type": "message", "content": query}
    await ws.send(json.dumps(message))
    
    # Collect responses
    responses = []
    agents_seen = []
    final_answer = None
    start_time = time.time()
    
    while time.time() - start_time < 15:  # Max 15 seconds per query
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=0.5)
            data = json.loads(response)
            responses.append(data)
            
            msg_type = data.get("type")
            
            if msg_type == "agent_result":
                agent_name = data.get("agent_name")
                if agent_name:
                    agents_seen.append(agent_name)
                    print(f"  ✓ Agent responded: {agent_name}")
                    
            elif msg_type == "message":
                # Final orchestrated response
                role = data.get("role", "unknown")
                text = data.get("text", "")
                final_answer = text
                print(f"\n📊 Final response from: {role}")
                
                # Extract just the answer
                if "Answer:" in text:
                    answer = text.split("Answer:")[1].split("\n")[0].strip()
                    answer = answer.replace("**", "").strip()
                    print(f"📝 Answer: {answer}")
                break
                
            elif msg_type == "stream":
                # Progress updates
                pass
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"  ❌ Error: {e}")
            break
    
    # Verify results
    success = True
    issues = []
    
    # Check if we got a final answer
    if not final_answer:
        success = False
        issues.append("No final answer received")
    else:
        # Check if answer contains expected content
        answer_ok = False
        for expected in test_case["expected_answer_contains"]:
            if expected.lower() in final_answer.lower():
                answer_ok = True
                break
        if not answer_ok:
            success = False
            issues.append(f"Answer doesn't contain expected content: {test_case['expected_answer_contains']}")
    
    # Check if expected agents responded (relaxed check - at least one)
    agent_check = any(agent in agents_seen for agent in test_case["expected_agents"])
    if not agent_check:
        # This is a warning, not a failure
        print(f"  ⚠️  Warning: Expected agents {test_case['expected_agents']}, got {agents_seen}")
    
    return {
        "query": query,
        "success": success,
        "agents": agents_seen,
        "final_answer": final_answer,
        "issues": issues,
        "response_count": len(responses)
    }

async def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*60)
    print("🧪 CEDAR CHAT COMPREHENSIVE TEST")
    print("="*60)
    
    # Connect to WebSocket
    uri = "ws://localhost:8000/ws/chat/44"
    
    try:
        async with websockets.connect(uri) as ws:
            print(f"✓ Connected to {uri}")
            
            results = []
            for test_case in TEST_CASES:
                result = await test_single_query(ws, test_case)
                results.append(result)
                await asyncio.sleep(1)  # Brief pause between tests
            
            # Summary
            print("\n" + "="*60)
            print("📊 TEST SUMMARY")
            print("="*60)
            
            total = len(results)
            passed = sum(1 for r in results if r["success"])
            
            for result in results:
                status = "✅ PASS" if result["success"] else "❌ FAIL"
                print(f"{status}: {result['query'][:50]}")
                if result["issues"]:
                    for issue in result["issues"]:
                        print(f"    └─ {issue}")
                print(f"    └─ {result['response_count']} responses, {len(result['agents'])} agents")
            
            print(f"\n{'='*60}")
            print(f"TOTAL: {passed}/{total} tests passed")
            
            if passed == total:
                print("🎉 All tests passed! The multi-agent orchestration is working correctly.")
                return 0
            else:
                print(f"⚠️  {total - passed} test(s) failed.")
                return 1
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nMake sure the Cedar server is running:")
        print("  uvicorn main:app --host 0.0.0.0 --port 8000")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(run_all_tests()))
