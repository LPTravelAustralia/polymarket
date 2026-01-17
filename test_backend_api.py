#!/usr/bin/env python3
"""
Backend API Test Suite
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_endpoint(method, path, description):
    """Test a single endpoint"""
    try:
        url = f"{BASE_URL}{path}"
        if method == "GET":
            response = requests.get(url, timeout=5)
        else:
            response = requests.post(url, timeout=5)
        
        status = "✅" if response.status_code == 200 else "⚠️"
        print(f"{status} {description}")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    for key in list(data.keys())[:3]:
                        print(f"   - {key}: {str(data[key])[:60]}")
            except:
                print(f"   Response: {str(response.text)[:100]}")
        print()
        return response.status_code == 200
    except Exception as e:
        print(f"❌ {description}")
        print(f"   Error: {str(e)}")
        print()
        return False

def main():
    print("=" * 60)
    print("POLYMARKET BACKEND API TEST SUITE")
    print("=" * 60)
    print()
    
    # Wait for server
    print("Waiting for backend to be ready...")
    for i in range(30):
        try:
            requests.get(f"{BASE_URL}/", timeout=1)
            print("✓ Backend is ready!")
            break
        except:
            time.sleep(0.5)
    
    print()
    tests = [
        ("GET", "/", "Health Check"),
        ("GET", "/api/status", "Bot Status"),
        ("GET", "/api/stats/summary", "Trading Stats Summary"),
        ("GET", "/api/markets?limit=5", "Get Markets (limit 5)"),
        ("GET", "/api/activity?limit=3", "Activity Log (limit 3)"),
        ("GET", "/openapi.json", "OpenAPI Schema"),
    ]
    
    passed = 0
    failed = 0
    
    for method, path, desc in tests:
        if test_endpoint(method, path, desc):
            passed += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    print()
    if failed == 0:
        print("✅ ALL TESTS PASSED!")
        print()
        print("Backend is fully operational:")
        print("  • REST API: http://localhost:8000/api")
        print("  • Swagger UI: http://localhost:8000/docs")
        print("  • OpenAPI Schema: http://localhost:8000/openapi.json")
        print("  • WebSocket: ws://localhost:8000/ws")
    else:
        print(f"⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    main()
