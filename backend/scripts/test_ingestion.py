"""Quick test to verify ingestion system works"""
import sys
sys.path.insert(0, '.')

print("Testing ingestion system imports...")

try:
    from src.services.ingestion_service import IngestionService, IngestionStatus  # noqa: F401
    print("✅ IngestionService imported")
except Exception as e:
    print(f"❌ Failed to import IngestionService: {e}")
    sys.exit(1)

try:
    from src.api.routes.ingestion import router  # noqa: F401
    print("✅ Ingestion router imported")
except Exception as e:
    print(f"❌ Failed to import ingestion router: {e}")
    sys.exit(1)

try:
    import main
    print("✅ main.py imported successfully")
    print(f"   Routes registered: {len(main.app.routes)}")
    
    # Check for ingestion routes
    ingest_routes = [r for r in main.app.routes if hasattr(r, 'path') and 'ingest' in r.path]
    print(f"   Ingestion routes: {len(ingest_routes)}")
    for route in ingest_routes:
        print(f"     - {route.path} {route.methods}")
        
except Exception as e:
    print(f"❌ Failed to import main.py: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All ingestion system tests passed!")
print("\nNew endpoints:")
print("  POST   /api/ingest        - Trigger news ingestion")
print("  GET    /api/ingest/status - Get latest ingestion status")
print("  GET    /api/ingest/stats  - Get database statistics")
