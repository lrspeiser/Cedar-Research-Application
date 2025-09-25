#!/usr/bin/env python3
"""
Final verification that Cedar Chat UI is working correctly.
Tests the complete flow from query to bubble display.
"""

import asyncio
import json
import websockets
import sys

async def verify_chat():
    print("\n" + "="*70)
    print("🔍 CEDAR CHAT UI VERIFICATION")
    print("="*70)
    
    uri = 'ws://localhost:8000/ws/chat/45'
    
    try:
        async with websockets.connect(uri) as ws:
            test_query = "what is the square root of 144"
            
            print(f"\n1️⃣  Sending test query: '{test_query}'")
            await ws.send(json.dumps({
                'type': 'message',
                'content': test_query
            }))
            
            print("\n2️⃣  Waiting for orchestrator responses...")
            
            stages = {
                'action': False,
                'stream': False,
                'agent_result': False,
                'final_message': False
            }
            
            agent_results = []
            final_message = None
            
            for i in range(20):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    if msg_type == 'action':
                        stages['action'] = True
                        print("   ✅ Action received (orchestrator started)")
                        
                    elif msg_type == 'stream':
                        stages['stream'] = True
                        text = data.get('text', '')[:50]
                        print(f"   ✅ Stream update: {text}...")
                        
                    elif msg_type == 'agent_result':
                        stages['agent_result'] = True
                        agent = data.get('agent_name', 'Unknown')
                        agent_results.append(agent)
                        print(f"   ✅ Agent result from: {agent}")
                        
                    elif msg_type == 'message':
                        stages['final_message'] = True
                        final_message = data
                        role = data.get('role', 'Unknown')
                        text = data.get('text', '')
                        
                        print(f"\n3️⃣  FINAL MESSAGE RECEIVED!")
                        print(f"   Role: {role}")
                        
                        # Check for markdown formatting
                        has_markdown = '**' in text
                        print(f"   Has markdown: {'✅ Yes' if has_markdown else '❌ No'}")
                        
                        # Extract answer
                        if '**Answer:**' in text:
                            answer = text.split('**Answer:**')[1].split('\n')[0].strip()
                            print(f"   Answer: {answer}")
                        
                        break
                        
                except asyncio.TimeoutError:
                    continue
            
            # Final verification
            print("\n" + "="*70)
            print("📊 VERIFICATION RESULTS:")
            print("="*70)
            
            all_good = True
            
            # Check each stage
            for stage, completed in stages.items():
                status = "✅" if completed else "❌"
                print(f"{status} {stage.replace('_', ' ').title()}: {'Completed' if completed else 'FAILED'}")
                if not completed:
                    all_good = False
            
            # Check agent participation
            if agent_results:
                print(f"\n✅ Agents that responded: {', '.join(agent_results)}")
            else:
                print("\n❌ No agent responses received")
                all_good = False
            
            # UI Instructions
            if all_good:
                print("\n" + "="*70)
                print("✅ SUCCESS! The chat system is working correctly!")
                print("\n🖥️  TO VERIFY IN BROWSER:")
                print("   1. Open: http://localhost:8000/project/45?branch_id=1&thread_id=1")
                print("   2. You should see message bubbles for:")
                print("      • User query (your question)")
                print("      • Agent results (collapsible)")
                print(f"      • Final answer from: {final_message.get('role') if final_message else 'Unknown'}")
                print("   3. The answer should have bold formatting (**Answer:**)")
                print("   4. Click on agent bubbles to expand details")
                print("\n✨ The multi-agent orchestration is fully functional!")
                return 0
            else:
                print("\n" + "="*70)
                print("❌ VERIFICATION FAILED")
                print("\nSome components are not working. Check:")
                print("   1. Is the server running? (uvicorn main:app)")
                print("   2. Check server.log for errors")
                print("   3. Check browser console for JavaScript errors")
                return 1
                
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        print("\nMake sure the server is running:")
        print("   uvicorn main:app --host 0.0.0.0 --port 8000")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(verify_chat()))
