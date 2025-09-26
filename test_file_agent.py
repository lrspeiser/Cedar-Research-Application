#!/usr/bin/env python3
"""
Test script for FileAgent functionality
Tests file download and metadata extraction
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the cedar_orchestrator to path
sys.path.insert(0, str(Path(__file__).parent))

from cedar_orchestrator.advanced_orchestrator import FileAgent, AgentResult

async def test_file_agent():
    """Test the FileAgent with various inputs"""
    
    # Initialize FileAgent (no LLM for basic testing)
    file_agent = FileAgent(llm_client=None)
    
    print("Testing FileAgent...")
    print("=" * 60)
    
    # Test 1: No file or URL
    print("\nTest 1: No file or URL in query")
    result = await file_agent.process("Hello, how are you?")
    print(f"Result: {result.result[:200]}")
    print(f"Confidence: {result.confidence}")
    
    # Test 2: URL download (using a small test file)
    print("\nTest 2: Download from URL")
    test_url = "https://raw.githubusercontent.com/python/cpython/main/README.rst"
    result = await file_agent.process(f"Please download {test_url}")
    print(f"Result: {result.result[:500]}")
    print(f"Confidence: {result.confidence}")
    
    # Check if file was downloaded
    download_dir = os.path.expanduser("~/CedarDownloads")
    if os.path.exists(download_dir):
        files = os.listdir(download_dir)
        print(f"\nFiles in download directory: {files[-5:] if len(files) > 5 else files}")
    
    # Test 3: Local file path
    print("\nTest 3: Local file path")
    test_file = __file__  # This script itself
    result = await file_agent.process(f"Analyze the file at {test_file}")
    print(f"Result: {result.result[:500]}")
    print(f"Confidence: {result.confidence}")
    
    # Test 4: Multiple URLs
    print("\nTest 4: Multiple items")
    result = await file_agent.process(
        f"Download https://httpbin.org/json and analyze {test_file}"
    )
    print(f"Result preview: {result.result[:500]}")
    print(f"Confidence: {result.confidence}")
    
    print("\n" + "=" * 60)
    print("FileAgent tests completed successfully!")

if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_file_agent())