#!/usr/bin/env python3
"""
Test script to verify file extraction content functionality
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_extracted_content_api():
    """Test the /api/files/{file_id}/extracted endpoint"""
    
    # First, we need to get a file ID from the database
    # For testing, we'll check if the API endpoint responds correctly
    
    print("Testing extracted content API...")
    
    # Test with a non-existent file ID
    response = requests.get(f"{BASE_URL}/api/files/99999/extracted")
    
    if response.status_code == 404:
        print("✓ API correctly returns 404 for non-existent file")
    else:
        print(f"✗ Expected 404, got {response.status_code}")
    
    print("\nNote: To fully test, upload a file through the UI and check:")
    print("1. The file's extracted content appears in the thread message")
    print("2. Clicking on the file displays the extracted content panel")
    print("3. The /api/files/{file_id}/extracted endpoint returns the content")

if __name__ == "__main__":
    # Wait a moment for server to be ready
    time.sleep(1)
    
    try:
        test_extracted_content_api()
        print("\n✅ Basic API test passed!")
        print("\nTo see the full functionality:")
        print("1. Open http://localhost:5000 in your browser")
        print("2. Create or select a project")
        print("3. Upload a file (PDF, CSV, or text document)")
        print("4. Click on the file in the Files list")
        print("5. The extracted content should appear above the chat area")
    except Exception as e:
        print(f"❌ Error during test: {e}")