#!/usr/bin/env python3
"""
Main test runner for CedarPy application
Runs all test suites and generates a comprehensive report
"""

import sys
import os
import json
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_config import BASE_URL, TEST_CONFIG
from tests.test_core_functionality import CoreFunctionalityTests
from tests.test_project_management import ProjectManagementTests
from tests.test_websocket_chat import run_websocket_tests

class CedarPyTestRunner:
    """Main test runner that orchestrates all test suites"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.results = {
            "timestamp": self.start_time.isoformat(),
            "base_url": BASE_URL,
            "suites": {},
            "summary": {}
        }
        self.app_process = None
    
    def check_app_running(self) -> bool:
        """Check if CedarPy app is running"""
        import requests
        try:
            response = requests.get(f"{BASE_URL}/", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def start_app_if_needed(self) -> bool:
        """Start the CedarPy app if it's not running"""
        if self.check_app_running():
            print("✓ CedarPy app is already running")
            return True
        
        print("Starting CedarPy app...")
        try:
            # Try to start the app
            app_path = "/Applications/CedarPy.app/Contents/MacOS/CedarPy"
            if not os.path.exists(app_path):
                # Try local dist folder
                app_path = os.path.expanduser("~/Projects/cedarpy/dist/CedarPy.app/Contents/MacOS/CedarPy")
            
            if os.path.exists(app_path):
                self.app_process = subprocess.Popen([app_path], 
                                                   stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL)
                # Wait for app to start
                for i in range(30):  # Wait up to 30 seconds
                    time.sleep(1)
                    if self.check_app_running():
                        print("✓ CedarPy app started successfully")
                        return True
                    if i % 5 == 0:
                        print(f"  Waiting for app to start... ({i}s)")
                
                print("✗ CedarPy app failed to start within 30 seconds")
                return False
            else:
                print(f"✗ CedarPy app not found at expected locations")
                print("  Please start the app manually or install it first")
                return False
                
        except Exception as e:
            print(f"✗ Failed to start CedarPy app: {str(e)}")
            return False
    
    def run_core_tests(self) -> Dict[str, Any]:
        """Run core functionality tests"""
        print("\n" + "="*60)
        print("Running Core Functionality Tests...")
        print("="*60)
        
        tester = CoreFunctionalityTests()
        results = tester.run_all_tests()
        self.results["suites"]["core"] = results
        
        print(f"\nCore Tests: {len(results['passed'])}/{results['total']} passed")
        return results
    
    def run_project_tests(self) -> Dict[str, Any]:
        """Run project management tests"""
        print("\n" + "="*60)
        print("Running Project Management Tests...")
        print("="*60)
        
        tester = ProjectManagementTests()
        results = tester.run_all_tests()
        self.results["suites"]["projects"] = results
        
        print(f"\nProject Tests: {len(results['passed'])}/{results['total']} passed")
        return results
    
    def run_websocket_tests(self) -> Dict[str, Any]:
        """Run WebSocket chat tests"""
        print("\n" + "="*60)
        print("Running WebSocket Chat Tests...")
        print("="*60)
        
        results = run_websocket_tests()
        self.results["suites"]["websocket"] = results
        
        print(f"\nWebSocket Tests: {len(results['passed'])}/{results['total']} passed")
        return results
    
    def generate_summary(self):
        """Generate overall test summary"""
        total_tests = 0
        total_passed = 0
        total_failed = 0
        all_failed_tests = []
        
        for suite_name, suite_results in self.results["suites"].items():
            total_tests += suite_results["total"]
            total_passed += len(suite_results["passed"])
            total_failed += len(suite_results["failed"])
            
            for test_name in suite_results["failed"]:
                all_failed_tests.append(f"{suite_name}::{test_name}")
        
        self.results["summary"] = {
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "success_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
            "failed_tests": all_failed_tests,
            "duration": str(datetime.now() - self.start_time)
        }
    
    def save_report(self, filename: str = None):
        """Save test report to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.json"
        
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"\n✓ Test report saved to: {filepath}")
        except Exception as e:
            print(f"\n✗ Failed to save report: {str(e)}")
    
    def print_final_summary(self):
        """Print final test summary"""
        summary = self.results["summary"]
        
        print("\n" + "="*60)
        print("FINAL TEST SUMMARY")
        print("="*60)
        print(f"Timestamp: {self.results['timestamp']}")
        print(f"Base URL: {self.results['base_url']}")
        print(f"Duration: {summary['duration']}")
        print()
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['total_passed']} ✓")
        print(f"Failed: {summary['total_failed']} ✗")
        print(f"Success Rate: {summary['success_rate']:.1f}%")
        
        if summary['failed_tests']:
            print("\nFailed Tests:")
            for test in summary['failed_tests']:
                print(f"  ✗ {test}")
        
        # Overall result
        print("\n" + "="*60)
        if summary['success_rate'] == 100:
            print("✓✓✓ ALL TESTS PASSED! ✓✓✓")
        elif summary['success_rate'] >= 80:
            print("✓ Most tests passed (>80%)")
        elif summary['success_rate'] >= 50:
            print("⚠ Some tests passed (>50%)")
        else:
            print("✗ Many tests failed (<50%)")
        print("="*60)
    
    def cleanup(self):
        """Clean up resources"""
        if self.app_process:
            print("\nStopping CedarPy app...")
            try:
                self.app_process.terminate()
                self.app_process.wait(timeout=5)
            except:
                try:
                    self.app_process.kill()
                except:
                    pass
    
    def run_all(self, start_app: bool = False, save_report: bool = True):
        """Run all test suites"""
        try:
            # Check or start app
            if start_app:
                if not self.start_app_if_needed():
                    print("\n⚠ WARNING: CedarPy app is not running!")
                    print("Some tests may fail. Start the app and try again.")
                    response = input("Continue anyway? (y/N): ").strip().lower()
                    if response != 'y':
                        return False
            elif not self.check_app_running():
                print("\n⚠ WARNING: CedarPy app is not running!")
                print("Please start the app first or use --start-app flag")
                return False
            
            # Run test suites
            self.run_core_tests()
            time.sleep(1)  # Brief pause between suites
            
            self.run_project_tests()
            time.sleep(1)
            
            if not TEST_CONFIG["skip_ws_tests"]:
                self.run_websocket_tests()
            else:
                print("\n⚠ Skipping WebSocket tests (disabled in config)")
            
            # Generate summary
            self.generate_summary()
            
            # Save report
            if save_report:
                self.save_report()
            
            # Print summary
            self.print_final_summary()
            
            return self.results["summary"]["success_rate"] == 100
            
        except KeyboardInterrupt:
            print("\n\n⚠ Test run interrupted by user")
            return False
        except Exception as e:
            print(f"\n✗ Unexpected error during test run: {str(e)}")
            return False
        finally:
            if start_app:
                self.cleanup()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run CedarPy comprehensive tests")
    parser.add_argument("--start-app", action="store_true", 
                      help="Start CedarPy app if not running")
    parser.add_argument("--verbose", "-v", action="store_true",
                      help="Enable verbose output")
    parser.add_argument("--no-report", action="store_true",
                      help="Don't save test report to file")
    parser.add_argument("--skip-ws", action="store_true",
                      help="Skip WebSocket tests")
    parser.add_argument("--skip-llm", action="store_true",
                      help="Skip LLM-dependent tests")
    
    args = parser.parse_args()
    
    # Update config based on args
    if args.verbose:
        os.environ["TEST_VERBOSE"] = "true"
    if args.skip_ws:
        os.environ["SKIP_WS_TESTS"] = "true"
    if args.skip_llm:
        os.environ["SKIP_LLM_TESTS"] = "true"
    
    # Reload config to pick up env changes
    from tests.test_config import TEST_CONFIG
    
    print("🧪 CedarPy Test Suite")
    print("="*60)
    print(f"Configuration:")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Verbose: {TEST_CONFIG['verbose']}")
    print(f"  Skip WebSocket: {TEST_CONFIG['skip_ws_tests']}")
    print(f"  Skip LLM: {TEST_CONFIG['skip_llm_tests']}")
    print("="*60)
    
    runner = CedarPyTestRunner()
    success = runner.run_all(
        start_app=args.start_app,
        save_report=not args.no_report
    )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()