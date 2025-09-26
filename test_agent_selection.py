#!/usr/bin/env python3
"""
Test script to verify the Chief Agent correctly selects agents for different tasks
"""

import asyncio
import os
import sys
from pathlib import Path
from cedar_orchestrator.advanced_orchestrator import ThinkerOrchestrator

async def test_agent_selection():
    """Test that Chief Agent selects the correct agents for different tasks"""
    
    # Load API key from .env
    env_path = Path.home() / "CedarPyData" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        if key in ['OPENAI_API_KEY', 'CEDARPY_OPENAI_API_KEY']:
                            os.environ[key] = value.strip('"\'')
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CEDARPY_OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return
    
    # Create orchestrator
    orchestrator = ThinkerOrchestrator(api_key)
    
    print("Testing Agent Selection by Chief Agent")
    print("=" * 60)
    
    # Test cases
    test_cases = [
        {
            "query": "Find all files on my computer related to 'mond'",
            "expected_agents": ["ShellAgent"],
            "reason": "Should use Shell Agent to search filesystem"
        },
        {
            "query": "Search for Python files containing the word 'orchestrator'",
            "expected_agents": ["ShellAgent"],
            "reason": "Should use Shell Agent with grep command"
        },
        {
            "query": "Download this file: https://example.com/data.csv",
            "expected_agents": ["FileAgent"],
            "reason": "Should use File Agent for URL download"
        },
        {
            "query": "Calculate the correlation between two variables in this dataset",
            "expected_agents": ["CodeAgent"],
            "reason": "Should use Coding Agent for statistical computation"
        },
        {
            "query": "Create a database schema for storing research papers",
            "expected_agents": ["SQLAgent"],
            "reason": "Should use SQL Agent to create database"
        },
        {
            "query": "Find academic papers about machine learning in biology",
            "expected_agents": ["ResearchAgent"],
            "reason": "Should use Research Agent for citations"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['query'][:50]}...")
        
        # Get the thinking phase result
        thinking = await orchestrator.think(test['query'])
        
        selected_agents = thinking.get('agents_to_use', [])
        
        # Check if correct agents were selected
        correct = all(agent in selected_agents for agent in test['expected_agents'])
        
        if correct:
            print(f"  ✅ Correct: Selected {selected_agents}")
        else:
            print(f"  ❌ Wrong: Selected {selected_agents}")
            print(f"     Expected: {test['expected_agents']}")
        
        print(f"  Reason: {test['reason']}")
        print(f"  Type identified: {thinking.get('identified_type')}")
        print(f"  Selection reasoning: {thinking.get('selection_reasoning')}")
    
    print("\n" + "=" * 60)
    print("Agent Selection Test Complete!")
    
    # Test the specific "mond" query
    print("\nDetailed test for 'mond' file search:")
    print("-" * 40)
    query = "Find all files on my computer related to mond"
    thinking = await orchestrator.think(query)
    
    print(f"Query: {query}")
    print(f"Identified type: {thinking['identified_type']}")
    print(f"Agents selected: {thinking['agents_to_use']}")
    print(f"Selection reasoning: {thinking['selection_reasoning']}")
    print(f"Analysis: {thinking['analysis']}")
    
    if 'ShellAgent' in thinking['agents_to_use']:
        print("✅ CORRECT: Shell Agent selected for filesystem search")
    else:
        print("❌ ERROR: Shell Agent NOT selected - File Agent cannot search your computer!")

if __name__ == "__main__":
    print("Chief Agent Selection Test")
    print("=" * 60)
    asyncio.run(test_agent_selection())