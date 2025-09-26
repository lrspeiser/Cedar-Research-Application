#!/usr/bin/env python3
"""
Test script to verify the Shell Agent is working correctly
"""

import asyncio
import os
import sys
from pathlib import Path
from cedar_orchestrator.advanced_orchestrator import ShellAgent, AgentResult
from openai import AsyncOpenAI

async def test_shell_agent():
    """Test the Shell Agent with various command formats"""
    
    # Try to load from .env file
    env_path = Path.home() / "CedarPyData" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        if key in ['OPENAI_API_KEY', 'CEDARPY_OPENAI_API_KEY']:
                            os.environ[key] = value.strip('"\'')
    
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found. Set OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY")
        return
    
    # Create Shell Agent
    llm_client = AsyncOpenAI(api_key=api_key)
    shell_agent = ShellAgent(llm_client)
    
    print("Testing Shell Agent with various command formats...")
    print("=" * 60)
    
    # Test 1: Command in backticks
    print("\n1. Testing command in backticks:")
    task1 = "Execute: `ls -la | head -5`"
    result1 = await shell_agent.process(task1)
    print(f"   Task: {task1}")
    print(f"   Found command: {'✓' if result1.confidence > 0.5 else '✗'}")
    print(f"   Confidence: {result1.confidence}")
    print(f"   Method: {result1.method}")
    
    # Test 2: Command after Execute keyword
    print("\n2. Testing command after Execute keyword:")
    task2 = "Execute: pwd"
    result2 = await shell_agent.process(task2)
    print(f"   Task: {task2}")
    print(f"   Found command: {'✓' if result2.confidence > 0.5 else '✗'}")
    print(f"   Confidence: {result2.confidence}")
    print(f"   Method: {result2.method}")
    
    # Test 3: Direct command
    print("\n3. Testing direct command:")
    task3 = "echo 'Hello from Shell Agent'"
    result3 = await shell_agent.process(task3)
    print(f"   Task: {task3}")
    print(f"   Found command: {'✓' if result3.confidence > 0.5 else '✗'}")
    print(f"   Confidence: {result3.confidence}")
    print(f"   Method: {result3.method}")
    
    # Test 4: Complex command with pipe
    print("\n4. Testing complex command with pipe:")
    task4 = "`find . -name '*.py' -type f | head -3`"
    result4 = await shell_agent.process(task4, conversation_context="User wants to find Python files")
    print(f"   Task: {task4}")
    print(f"   Found command: {'✓' if result4.confidence > 0.5 else '✗'}")
    print(f"   Confidence: {result4.confidence}")
    print(f"   Method: {result4.method}")
    
    # Test 5: No command (should fail)
    print("\n5. Testing with no command (should fail):")
    task5 = "Please run a command to list files"
    result5 = await shell_agent.process(task5)
    print(f"   Task: {task5}")
    print(f"   Found command: {'✓' if result5.confidence > 0.5 else '✗'}")
    print(f"   Confidence: {result5.confidence}")
    print(f"   Method: {result5.method}")
    
    print("\n" + "=" * 60)
    print("Shell Agent tests completed!")
    
    # Show one full result for inspection
    print("\nDetailed result from test 1:")
    print("-" * 40)
    print(result1.result[:500] if len(result1.result) > 500 else result1.result)

if __name__ == "__main__":
    print("Shell Agent Test Suite")
    print("=" * 60)
    asyncio.run(test_shell_agent())