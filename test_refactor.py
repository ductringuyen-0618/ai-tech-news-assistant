"""
Test the refactored /api/news endpoint with direct psycopg2
"""
import os
import sys
from dotenv import load_dotenv

# Load DATABASE_URL from backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

print("=" * 60)
print("Testing refactored /api/news endpoint (psycopg2)")
print("=" * 60)

# Test the database connection and query directly
print("\n1. Testing direct database connection...")
try:
    import psycopg
    
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # psycopg3 uses connection string directly
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            # Test query
            cursor.execute("SELECT COUNT(*) FROM articles")
            count = cursor.fetchone()[0]
            print(f"   ✓ Connected to database")
            print(f"   ✓ Total articles in DB: {count}")
            
            # Test paginated query
            cursor.execute("""
                SELECT id, title, content, url, source, author, published_date, created_at
                FROM articles
                ORDER BY published_date DESC
                LIMIT 5 OFFSET 0
            """)
            articles = cursor.fetchall()
            print(f"   ✓ Fetched {len(articles)} articles")
            if articles:
                print(f"   ✓ First article: {articles[0][1][:50]}...")
    
    print("   ✓ Database test PASSED\n")
    
except Exception as e:
    print(f"   ✗ Database test FAILED: {e}\n")
    sys.exit(1)

# Test the actual endpoint
print("2. Testing FastAPI endpoint...")
try:
    # Add backend to path and import
    backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
    sys.path.insert(0, backend_dir)
    
    # Import the app
    from main import app
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    # Test health endpoint
    response = client.get("/health")
    print(f"   Health check: {response.status_code}")
    assert response.status_code == 200, "Health check failed"
    
    # Test /api/news endpoint
    response = client.get("/api/news?page=1&page_size=5")
    print(f"   /api/news status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Total articles: {data.get('total', 0)}")
        print(f"   ✓ Items returned: {len(data.get('items', []))}")
        if data.get('items'):
            print(f"   ✓ First article: {data['items'][0]['title'][:50]}...")
        print("   ✓ API endpoint test PASSED\n")
    else:
        print(f"   ✗ API returned {response.status_code}")
        print(f"   Error: {response.text[:200]}")
        sys.exit(1)
        
except Exception as e:
    print(f"   ✗ API test FAILED: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("✓ ALL TESTS PASSED - Safe to commit!")
print("=" * 60)
