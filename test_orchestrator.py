#!/usr/bin/env python3
"""Test the orchestrator directly to ensure it works"""

import asyncio
import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)

from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator

class MockWebSocket:
    """Mock WebSocket for testing"""
    def __init__(self):
        self.messages = []
    
    async def send_json(self, data):
        msg_type = data.get('type', 'unknown')
        text = data.get('text', data.get('content', ''))
        print(f"\n[{msg_type}]: {text[:200]}")
        self.messages.append(data)

async def test_simple_query():
    """Test with a simple query like 2+2"""
    print("="*80)
    print("Testing simple query: 2+2")
    print("="*80)
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    if not api_key:
        print("WARNING: No API key found. Will use fallback behavior.")
    
    orchestrator = ThinkerOrchestrator(api_key)
    websocket = MockWebSocket()
    
    try:
        # First test the think method
        print("\nPhase 1: Testing think method...")
        thinking = await orchestrator.think("2+2")
        print(f"Thinking result: {thinking}")
        
        # Now test full orchestration
        print("\nPhase 2: Testing full orchestration...")
        await orchestrator.orchestrate("2+2", websocket)
        
        print(f"\n\nReceived {len(websocket.messages)} messages total")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple_query())