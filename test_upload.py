#!/usr/bin/env python3
"""
Test script for CedarPy file upload endpoint.
This script helps diagnose file upload issues by providing detailed error reporting.
"""

import requests
import sys

# Configuration
BASE_URL = "http://localhost:49207"
PROJECT_ID = 1
BRANCH_ID = 1

def test_upload():
    """Test file upload with detailed error reporting."""
    
    # Create test file content
    test_content = "Test file content for upload debugging"
    test_filename = "test_debug.txt"
    
    # Prepare the file for upload
    files = {
        'file': (test_filename, test_content, 'text/plain')
    }
    
    # Construct the upload URL
    url = f"{BASE_URL}/project/{PROJECT_ID}/files/upload"
    params = {'branch_id': BRANCH_ID}
    
    print(f"Testing upload to: {url}")
    print(f"Parameters: {params}")
    print(f"File: {test_filename}")
    print("-" * 50)
    
    try:
        # Make the request
        response = requests.post(url, params=params, files=files, allow_redirects=False)
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print("-" * 50)
        
        if response.status_code in [200, 303]:
            print("✓ Upload successful!")
            if 'Location' in response.headers:
                print(f"  Redirect to: {response.headers['Location']}")
        else:
            print(f"✗ Upload failed with status {response.status_code}")
            print(f"Response body:\n{response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(test_upload())