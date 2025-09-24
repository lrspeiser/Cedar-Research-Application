#!/usr/bin/env python3
"""
Test script for the new thinker-orchestrator flow.
Tests simple queries like "what is 2+2" to ensure everything works.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from openai import AsyncOpenAI
from thinker import Thinker, ThinkerContext
from orchestrator import Orchestrator
from agents.base_agent import AgentContext
from agents import get_agent

async def test_simple_arithmetic():
    """Test simple arithmetic query: 'what is 2+2'"""
    print("\n" + "="*60)
    print("TEST: Simple Arithmetic - 'what is 2+2'")
    print("="*60)
    
    # Initialize OpenAI client (optional - will work without it for simple math)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        print("✓ OpenAI client initialized")
    else:
        client = None
        print("⚠ No OpenAI API key - running in limited mode")
    
    # Test the final agent directly first
    print("\n1. Testing Final Agent directly...")
    final_agent = get_agent("final", client)
    context = AgentContext(
        query="what is 2+2",
        thinking_notes="This is a simple arithmetic question.",
        chat_history=[],
        files=[],
        databases=[],
        notes=[],
        code_snippets=[],
        changelog=[],
        previous_results=None
    )
    
    result = await final_agent.execute(context)
    print(f"   Agent: {result.agent_name}")
    print(f"   Success: {result.success}")
    print(f"   Output: {result.output}")
    if result.metadata:
        print(f"   Metadata: {result.metadata}")
    
    # Test with thinker if available
    if client:
        print("\n2. Testing Thinker...")
        thinker = Thinker(client)
        thinker_context = ThinkerContext(
            query="what is 2+2",
            chat_history=[],
            files=[],
            databases=[],
            notes=[],
            code_snippets=[],
            changelog=[],
            available_agents=["plan", "code", "web", "file", "db", "notes", "images", "question", "final"]
        )
        
        print("   Thinking process:")
        thinking_notes = ""
        async for chunk in thinker.think(thinker_context):
            print(chunk, end="", flush=True)
            thinking_notes += chunk
        print()
        
        thinking_output = thinker.parse_thinking_output(thinking_notes)
        print(f"\n   Suggested agents: {thinking_output.suggested_agents}")
        print(f"   Strategy: {thinking_output.initial_strategy}")
        print(f"   Expected iterations: {thinking_output.expected_iterations}")
        
        # Test orchestrator
        print("\n3. Testing Orchestrator...")
        orchestrator = Orchestrator(client)
        
        agent_context = AgentContext(
            query="what is 2+2",
            thinking_notes=thinking_notes,
            chat_history=[],
            files=[],
            databases=[],
            notes=[],
            code_snippets=[],
            changelog=[],
            previous_results=None
        )
        
        results, decision = await orchestrator.orchestrate(agent_context, thinking_output)
        
        print(f"   Executed agents: {[r.agent_name for r in results]}")
        print(f"   Results:")
        for r in results:
            print(f"     - {r.agent_name}: {'✓' if r.success else '✗'} {r.output if r.success else r.error}")
        
        print(f"\n   Decision:")
        print(f"     Selected: {decision.selected_result.agent_name if decision.selected_result else 'None'}")
        print(f"     Continue: {decision.should_continue}")
        print(f"     Reasoning: {decision.reasoning}")
        
        if decision.selected_result and decision.selected_result.success:
            print(f"\n   Final Answer: {decision.selected_result.output}")

async def test_code_generation():
    """Test code generation query"""
    print("\n" + "="*60)
    print("TEST: Code Generation - 'write a function to calculate fibonacci'")
    print("="*60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠ Skipping - requires OpenAI API key")
        return
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Test code agent
    print("\n1. Testing Code Agent...")
    code_agent = get_agent("code", client)
    context = AgentContext(
        query="write a Python function to calculate the nth fibonacci number",
        thinking_notes="The user wants a code implementation for fibonacci sequence.",
        chat_history=[],
        files=[],
        databases=[],
        notes=[],
        code_snippets=[],
        changelog=[],
        previous_results=None
    )
    
    result = await code_agent.execute(context)
    print(f"   Success: {result.success}")
    if result.success:
        print(f"   Output:\n{result.output}")

async def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# NEW FLOW TEST SUITE")
    print("#"*60)
    
    try:
        await test_simple_arithmetic()
        await test_code_generation()
        
        print("\n" + "#"*60)
        print("# ALL TESTS COMPLETED")
        print("#"*60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)