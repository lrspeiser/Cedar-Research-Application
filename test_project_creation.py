#!/usr/bin/env python3
"""
Test script to verify project creation works without errors.
"""

import sys
import time
import requests
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_project_creation():
    """Test creating a new project."""
    
    print("Testing project creation...")
    
    # Create a unique project name
    project_name = f"Test Project {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Send POST request to create project
    try:
        response = requests.post(
            f"{BASE_URL}/projects/create",
            data={"title": project_name},
            allow_redirects=False
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        
        if response.status_code == 303:  # Redirect
            redirect_url = response.headers.get('Location', '')
            print(f"✓ Project created successfully! Redirected to: {redirect_url}")
            
            # Extract project ID from redirect URL
            if "/project/" in redirect_url:
                project_id = redirect_url.split("/project/")[1].split("?")[0]
                print(f"✓ Project ID: {project_id}")
                
                # Test if we can access the project page
                project_response = requests.get(f"{BASE_URL}{redirect_url}")
                if project_response.status_code == 200:
                    print("✓ Project page accessible")
                    return True
                else:
                    print(f"✗ Failed to access project page: {project_response.status_code}")
                    return False
            else:
                print("✗ Unexpected redirect URL format")
                return False
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to server. Make sure the app is running on port 8000.")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("CedarPy Project Creation Test")
    print("=" * 60)
    print()
    
    # Check if server is running
    try:
        response = requests.get(BASE_URL)
        if response.status_code != 200:
            print(f"✗ Server returned status {response.status_code}")
            sys.exit(1)
        print("✓ Server is running")
    except requests.exceptions.ConnectionError:
        print("✗ Server is not running. Please start the app first:")
        print("  cd /Users/leonardspeiser/Projects/cedarpy")
        print("  python -m uvicorn main:app --reload --port 8000")
        sys.exit(1)
    
    print()
    
    # Run the test
    if test_project_creation():
        print()
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print()
        print("✗ Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()