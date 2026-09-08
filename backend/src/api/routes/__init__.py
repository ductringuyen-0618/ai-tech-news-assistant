"""
API Routes Package
================

Main router that combines all route modules for the AI Tech News Assistant API.
Provides a clean, organized structure for API endpoints with proper tagging
and documentation.
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# Create routers
api_router = APIRouter(prefix="/api")
root_router = APIRouter()

# Import and include routes with error handling
def _safe_include_router(router, module_name, router_name):
    """Safely import and include a router, logging errors."""
    try:
        module = __import__(f"src.api.routes.{module_name}", fromlist=[router_name])
        route_router = getattr(module, router_name)
        router.include_router(route_router)
        logger.info(f"Loaded {module_name} router")
        return True
    except Exception as e:
        logger.error(f"Failed to load {module_name} router: {e}")
        return False

# Load health router (root level, no /api prefix)
_safe_include_router(root_router, "health", "router")

# Load API routers
_safe_include_router(api_router, "news", "router")
_safe_include_router(api_router, "summarization", "router")
_safe_include_router(api_router, "embeddings", "router")
_safe_include_router(api_router, "search", "router")
_safe_include_router(api_router, "ingestion", "router")
_safe_include_router(api_router, "rag", "router")
_safe_include_router(api_router, "digest", "router")
_safe_include_router(api_router, "settings", "router")
_safe_include_router(api_router, "admin", "router")
_safe_include_router(api_router, "knowledge_graph", "router")
_safe_include_router(api_router, "research", "router")
_safe_include_router(api_router, "saved_research", "router")
_safe_include_router(api_router, "subscribers", "router")

logger.info("API routers initialization complete")

__all__ = ["api_router", "root_router"]
