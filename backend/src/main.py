"""
Main FastAPI Application
=======================

Entry point for the AI Tech News Assistant API.
Uses the refactored architecture with proper separation of concerns,
comprehensive error handling, and monitoring.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time

from src.core.config import get_settings
from src.core.logging import setup_logging, get_logger
from src.core.middleware import (
    ErrorHandlingMiddleware,
    HealthCheckMiddleware,
    create_custom_error_handlers
)
from src.api import api_router, root_router

# Setup logging first
setup_logging()
logger = get_logger(__name__)

# Get settings instance
settings = get_settings()

# Global health check middleware instance for metrics
health_middleware = None

# Global APScheduler instance (Milestone 3 retention cron). None when
# retention is disabled or we're running under ENVIRONMENT=test/testing.
_scheduler = None


def _should_start_scheduler() -> bool:
    """Decide whether to start the retention cron at app startup.

    Skipped when ``RETENTION_ENABLED=false`` or when the app is running
    in a test environment (the E2E suite triggers retention via the
    admin route in dry-run mode and must not race a background job).
    """
    from src.core.config import Environment

    if not getattr(settings, "retention_enabled", True):
        return False
    # Compare against the enum directly. ``str(Environment.TESTING)`` is
    # ``"Environment.TESTING"`` on Python 3.11+, so a string compare on
    # str(env) silently never matches "testing". Use the enum value.
    if getattr(settings, "environment", None) == Environment.TESTING:
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.

    Handles startup and shutdown tasks for the application.
    """
    global _scheduler

    # Startup
    logger.info(
        "Starting AI Tech News Assistant API",
        extra={
            "environment": settings.environment,
            "debug": settings.debug,
            "version": app.version
        }
    )

    # Log important configuration
    logger.info(
        "Application configuration loaded",
        extra={
            "database_path": settings.sqlite_database_path,
            "log_level": settings.log_level,
            "cors_origins": settings.allowed_origins,
            "error_middleware_enabled": settings.enable_error_middleware,
            "metrics_enabled": settings.enable_metrics
        }
    )

    # Ensure the SQLite schema exists. On a fresh Fly volume /data/news.db
    # doesn't exist at all. Instantiating ArticleRepository runs its
    # _ensure_tables_exist() which CREATE TABLE IF NOT EXISTS-es the
    # denormalised `articles` schema that BOTH the news API and the daily
    # ingestion orchestrator expect (both use raw sqlite3, NOT the
    # SQLAlchemy ORM models -- those are leftover from an earlier
    # iteration and live in src/database/models.py only for type hints).
    try:
        from src.repositories.article_repository import ArticleRepository
        ArticleRepository(db_path=settings.sqlite_database_path)
        logger.info("Database schema ensured (ArticleRepository init)")
    except Exception as exc:  # pragma: no cover
        logger.error(f"Database schema init failed: {type(exc).__name__}: {exc}")

    # Seed the Saved Research table on a fresh DB (design-review #4).
    # ``seed_if_empty`` is idempotent — a no-op once any row exists, so
    # this is safe to call on every boot. Wrapped in its own try/except
    # because a failure here must NOT take the API offline; worst case
    # the /saved page just shows the empty state.
    try:
        from src.repositories.saved_research_repository import (
            SavedResearchRepository,
        )
        saved_repo = SavedResearchRepository(settings.sqlite_database_path)
        inserted = saved_repo.seed_if_empty()
        if inserted > 0:
            logger.info(
                "Saved-research seed: inserted %d demo dispatch(es)",
                inserted,
            )
        else:
            logger.info(
                "Saved-research seed: table already populated; no-op"
            )
    except Exception as exc:  # pragma: no cover
        logger.error(
            "Saved-research seed failed: %s: %s",
            type(exc).__name__, exc,
        )

    # Retention cron (Milestone 3). Runs once on startup AND daily at
    # 00:00 UTC. The job itself is defined in
    # src.services.retention_service.run_retention_job.
    if _should_start_scheduler():
        try:
            from datetime import datetime, timedelta, timezone as _tz
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from src.services.retention_service import run_retention_job

            _scheduler = AsyncIOScheduler(timezone="UTC")
            _scheduler.add_job(
                run_retention_job,
                trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
                id="retention_daily",
                name="Daily article retention sweep",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            # Acceptance criterion: also run once on startup, shortly
            # after the app is up so we don't block the boot path.
            _scheduler.add_job(
                run_retention_job,
                trigger="date",
                run_date=datetime.now(_tz.utc) + timedelta(seconds=15),
                id="retention_startup",
                name="Startup article retention sweep",
                replace_existing=True,
                misfire_grace_time=60,
            )

            # Daily ingestion cron (Mission daily-ingestion M2). Runs
            # alongside the retention job; both share this same
            # AsyncIOScheduler instance so the coroutine can be passed
            # in directly (no asyncio.create_task / asyncio.run wrapping
            # required -- AsyncIOScheduler awaits coroutine jobs on its
            # own event loop).
            import os as _os
            from src.services.daily_ingestion_orchestrator import (
                run_daily_ingestion,
            )

            _ingestion_db_path = settings.get_database_path()
            _scheduler.add_job(
                run_daily_ingestion,
                trigger=CronTrigger(hour=5, minute=0, timezone="UTC"),
                id="daily_ingestion",
                name="Daily article ingestion",
                kwargs={"db_path": _ingestion_db_path},
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
            logger.info(
                "Daily ingestion scheduler started (daily 05:00 UTC, db=%s)",
                _ingestion_db_path,
            )

            # Dev affordance: when RUN_INGESTION_ON_BOOT=1, schedule a
            # one-shot run 60 seconds after boot so a fresh `uvicorn`
            # produces ingestion output without waiting until 05:00 UTC.
            # Off by default; production never sets this.
            if _os.environ.get("RUN_INGESTION_ON_BOOT") == "1":
                _scheduler.add_job(
                    run_daily_ingestion,
                    trigger="date",
                    run_date=datetime.now(_tz.utc) + timedelta(seconds=60),
                    id="ingestion_boot_run",
                    name="Boot ingestion run (RUN_INGESTION_ON_BOOT=1)",
                    kwargs={"db_path": _ingestion_db_path},
                    replace_existing=True,
                    misfire_grace_time=120,
                )
                logger.info(
                    "RUN_INGESTION_ON_BOOT=1 -- ingestion will run 60s after boot"
                )

            _scheduler.start()
            logger.info(
                "Retention scheduler started (days=%d, max=%d, daily 00:00 UTC + startup run in 15s)",
                settings.retention_days,
                settings.retention_max_deletes,
            )
        except Exception as exc:  # noqa: BLE001
            # APScheduler missing or scheduler init failed — log and keep
            # serving requests. Manual route still works.
            logger.error(
                "Failed to start retention scheduler: %s. Manual route still available.",
                exc,
            )
            _scheduler = None
    else:
        logger.info(
            "Retention scheduler disabled (enabled=%s, environment=%s)",
            getattr(settings, "retention_enabled", True),
            settings.environment,
        )

    yield

    # Shutdown
    logger.info("Shutting down AI Tech News Assistant API")
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Retention scheduler stopped")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error shutting down scheduler: %s", exc)


# Create FastAPI application with enhanced configuration
app = FastAPI(
    title="AI Tech News Assistant",
    description="AI-powered tech news aggregation, summarization, and search API with comprehensive error handling and monitoring",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    debug=settings.debug
)

# Add comprehensive error handling middleware
if settings.enable_error_middleware:
    app.add_middleware(ErrorHandlingMiddleware)
    logger.info("Error handling middleware enabled")

# Add health check middleware for monitoring
if settings.enable_metrics:
    health_middleware = HealthCheckMiddleware(app)
    app.add_middleware(HealthCheckMiddleware)
    logger.info("Health check middleware enabled")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"]  # Expose correlation ID to clients
)

# Add custom exception handlers for specific types
custom_handlers = create_custom_error_handlers()
for exception_type, handler in custom_handlers.items():
    app.add_exception_handler(exception_type, handler)

logger.info("Custom exception handlers registered")

# Include routers
app.include_router(root_router)  # Health and root endpoints
app.include_router(api_router)   # Main API endpoints

logger.info("API routes registered")


# Add metrics endpoint if enabled
if settings.enable_metrics and health_middleware:
    @app.get(settings.metrics_endpoint)
    async def get_metrics():
        """Get application health metrics."""
        return health_middleware.get_metrics()


# Enhanced startup event logging
@app.on_event("startup")
async def startup_event():
    """Log startup completion with timing."""
    logger.info(
        "Application startup completed",
        extra={
            "startup_time": time.time(),
            "pid": __import__("os").getpid()
        }
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event."""
    logger.info(
        "Application shutdown initiated",
        extra={
            "shutdown_time": time.time()
        }
    )


if __name__ == "__main__":
    import uvicorn

    # Enhanced uvicorn configuration
    uvicorn_config = {
        "app": "src.main:app",
        "host": settings.host,
        "port": settings.port,
        "reload": settings.debug and settings.environment == "development",
        "log_level": settings.log_level.lower(),
        "access_log": True,
        "server_header": False,  # Don't expose server details
        "date_header": False     # Don't add date header
    }

    logger.info(
        "Starting uvicorn server",
        extra={
            "host": settings.host,
            "port": settings.port,
            "reload": uvicorn_config["reload"],
            "log_level": settings.log_level
        }
    )

    # Run the application
    uvicorn.run(**uvicorn_config)
