"""Run backend and test it"""
import subprocess
import time
import requests
import os
import sys
from dotenv import load_dotenv

# Load DATABASE_URL (and anything else) from backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

print("Starting backend server...")
# Start uvicorn in a subprocess
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
server_process = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'src.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd=backend_dir,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Wait for server to start
print("Waiting for server to start...")
time.sleep(5)

BASE_URL = "http://127.0.0.1:8000"

try:
    print("\n=== Testing Backend API ===\n")
    
    # Test 1: Health check
    print("1. Testing /health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 2: Get news articles
    print("\n2. Testing /api/news endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/api/news?page=1&page_size=5", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Total articles: {data.get('total', 0)}")
            print(f"   Articles returned: {len(data.get('articles', []))}")
            if data.get('articles'):
                first = data['articles'][0]
                print(f"\n   First article:")
                print(f"     Title: {first.get('title', 'N/A')[:80]}")
                print(f"     Source: {first.get('source', 'N/A')}")
                print(f"     URL: {first.get('url', 'N/A')[:60]}")
        else:
            print(f"   Error Response: {response.text[:500]}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 3: Search endpoint
    print("\n3. Testing /api/search endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/api/search?query=AI", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Results found: {len(data.get('results', []))}")
        else:
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print("\n=== Test Complete ===\n")

finally:
    # Stop the server
    print("\nStopping backend server...")
    server_process.terminate()
    server_process.wait(timeout=5)
    print("Server stopped.")
