import sys
sys.path.insert(0, '.')

try:
    from src.api.routes import api_router, root_router  # noqa: F401
    print(f" Routes loaded: {len(api_router.routes)} API routes")
    
    # List all RAG routes
    rag_routes = [r for r in api_router.routes if '/rag' in str(r.path)]
    print(f" RAG routes found: {len(rag_routes)}")
    for route in rag_routes:
        print(f"  - {list(route.methods)} {route.path}")
    
    print("\n All imports successful!")
except Exception as e:
    print(f" Error: {e}")
    import traceback
    traceback.print_exc()
