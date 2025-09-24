"""
Core functionality tests for CedarPy application
"""

import requests
import time
import json
from typing import Dict, Tuple, Any
from test_config import BASE_URL, ENDPOINTS, TEST_TIMEOUT, TEST_CONFIG, get_headers

class CoreFunctionalityTests:
    """Test core web interface and API functionality"""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.passed = []
        self.failed = []
        self.session = requests.Session()
        self.session.headers.update(get_headers())
    
    def test_server_running(self) -> Tuple[bool, str]:
        """Test if the server is running and responding"""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                return True, "Server is running and responding"
            else:
                return False, f"Server returned status code: {response.status_code}"
        except requests.ConnectionError:
            return False, "Could not connect to server - is CedarPy running?"
        except Exception as e:
            return False, f"Error checking server: {str(e)}"
    
    def test_home_page_loads(self) -> Tuple[bool, str]:
        """Test if home page loads with expected content"""
        try:
            response = self.session.get(f"{self.base_url}{ENDPOINTS['home']}", timeout=TEST_TIMEOUT)
            if response.status_code != 200:
                return False, f"Home page returned status: {response.status_code}"
            
            # Check for expected content
            content = response.text.lower()
            expected_elements = ["cedar", "project", "create"]
            missing = [elem for elem in expected_elements if elem not in content]
            
            if missing:
                return False, f"Home page missing expected elements: {missing}"
            
            return True, "Home page loads with expected content"
        except Exception as e:
            return False, f"Error loading home page: {str(e)}"
    
    def test_api_health_check(self) -> Tuple[bool, str]:
        """Test if API health endpoint responds correctly"""
        try:
            # Try the health endpoint if it exists
            health_url = f"{self.base_url}/api/health"
            response = self.session.get(health_url, timeout=TEST_TIMEOUT)
            
            if response.status_code == 404:
                # Try alternative endpoints
                response = self.session.get(f"{self.base_url}/api/projects", timeout=TEST_TIMEOUT)
                if response.status_code in [200, 201, 204]:
                    return True, "API is responding (via projects endpoint)"
            elif response.status_code == 200:
                return True, "Health check endpoint responding"
            
            return False, f"API health check failed with status: {response.status_code}"
        except Exception as e:
            return False, f"Error checking API health: {str(e)}"
    
    def test_static_routes(self) -> Tuple[bool, str]:
        """Test if key static routes are accessible"""
        failed_routes = []
        
        for name, path in ENDPOINTS.items():
            if name in ["api_health", "api_projects"]:
                continue  # Skip API endpoints
            
            try:
                response = self.session.get(f"{self.base_url}{path}", timeout=TEST_TIMEOUT)
                if response.status_code not in [200, 302]:  # 302 for redirects
                    failed_routes.append(f"{name}:{response.status_code}")
            except Exception as e:
                failed_routes.append(f"{name}:error")
        
        if failed_routes:
            return False, f"Failed routes: {', '.join(failed_routes)}"
        
        return True, "All static routes accessible"
    
    def test_api_projects_endpoint(self) -> Tuple[bool, str]:
        """Test if projects API endpoint works"""
        try:
            response = self.session.get(f"{self.base_url}/api/projects", timeout=TEST_TIMEOUT)
            
            if response.status_code == 404:
                # Try alternative format
                response = self.session.get(f"{self.base_url}/projects", 
                                          headers={"Accept": "application/json"},
                                          timeout=TEST_TIMEOUT)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, (list, dict)):
                        return True, f"Projects API working, returned {type(data).__name__}"
                except json.JSONDecodeError:
                    # May return HTML instead of JSON
                    if "project" in response.text.lower():
                        return True, "Projects endpoint working (HTML response)"
            
            return False, f"Projects API returned status: {response.status_code}"
        except Exception as e:
            return False, f"Error accessing projects API: {str(e)}"
    
    def test_create_project_form(self) -> Tuple[bool, str]:
        """Test if project creation form is available"""
        try:
            # Check if we can access project creation page
            response = self.session.get(f"{self.base_url}/projects/new", timeout=TEST_TIMEOUT)
            
            if response.status_code == 404:
                # Try the main projects page
                response = self.session.get(f"{self.base_url}/projects", timeout=TEST_TIMEOUT)
            
            if response.status_code == 200:
                content = response.text.lower()
                if "create" in content or "new project" in content:
                    return True, "Project creation interface available"
            
            return False, "Could not find project creation interface"
        except Exception as e:
            return False, f"Error checking project creation: {str(e)}"
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all core functionality tests"""
        tests = [
            ("Server Running", self.test_server_running),
            ("Home Page", self.test_home_page_loads),
            ("API Health", self.test_api_health_check),
            ("Static Routes", self.test_static_routes),
            ("Projects API", self.test_api_projects_endpoint),
            ("Create Project Form", self.test_create_project_form),
        ]
        
        results = {
            "passed": [],
            "failed": [],
            "total": len(tests),
            "details": []
        }
        
        for test_name, test_func in tests:
            try:
                passed, message = test_func()
                result = {
                    "name": test_name,
                    "passed": passed,
                    "message": message
                }
                
                if passed:
                    results["passed"].append(test_name)
                    if TEST_CONFIG["verbose"]:
                        print(f"✓ {test_name}: {message}")
                else:
                    results["failed"].append(test_name)
                    print(f"✗ {test_name}: {message}")
                
                results["details"].append(result)
            except Exception as e:
                results["failed"].append(test_name)
                results["details"].append({
                    "name": test_name,
                    "passed": False,
                    "message": f"Unexpected error: {str(e)}"
                })
                print(f"✗ {test_name}: Unexpected error - {str(e)}")
        
        results["success_rate"] = len(results["passed"]) / results["total"] * 100 if results["total"] > 0 else 0
        
        return results

if __name__ == "__main__":
    tester = CoreFunctionalityTests()
    results = tester.run_all_tests()
    
    print(f"\n{'='*50}")
    print(f"Core Functionality Test Results:")
    print(f"Passed: {len(results['passed'])}/{results['total']}")
    print(f"Success Rate: {results['success_rate']:.1f}%")
    if results['failed']:
        print(f"Failed Tests: {', '.join(results['failed'])}")