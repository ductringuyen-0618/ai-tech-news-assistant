"""
Database Base Configuration
==========================

SQLAlchemy base configuration and database connection management.
"""

import logging
from typing import Generator
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Create the SQLAlchemy base class
Base = declarative_base()

# Database metadata for migrations
metadata = MetaData()

# Global variables for database connections
engine = None
SessionLocal = None


def get_database_url() -> str:
    """Get database URL from configuration."""
    settings = get_settings()
    
    # Get database_type value (handle both Enum and string)
    db_type = settings.database_type
    if hasattr(db_type, 'value'):
        db_type = db_type.value
    
    if db_type == "sqlite":
        # Use the single shared resolution helper (DATABASE_URL, else
        # SQLITE_DATABASE_PATH, default "./data/articles.db") instead of
        # hardcoding a different default file here -- this used to default
        # to "sqlite:///./data/ai_news.db" while every other DB access
        # path (news, search, ingest stats, etc.) resolved to
        # "./data/articles.db" via settings.get_database_path(), so a
        # fresh checkout with no .env wrote articles to one SQLite file
        # and read them from another. It also ensures the parent
        # directory exists, so callers don't need to.
        return settings.get_database_sqlalchemy_url()
    elif db_type == "postgresql":
        return settings.database_url or "postgresql://user:password@localhost/ai_news"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def create_database_engine():
    """Create SQLAlchemy engine based on configuration."""
    global engine
    
    database_url = get_database_url()
    logger.info(f"Creating database engine for: {database_url}")
    
    if database_url.startswith("sqlite"):
        # SQLite configuration
        engine = create_engine(
            database_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            poolclass=StaticPool,
            pool_pre_ping=True,
            echo=get_settings().debug,
        )
    else:
        # PostgreSQL configuration
        engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=get_settings().debug,
        )
    
    return engine


def create_session_factory():
    """Create SQLAlchemy session factory."""
    global SessionLocal
    
    if engine is None:
        create_database_engine()
    
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    
    return SessionLocal


def init_db():
    """Initialize database tables."""
    global engine
    
    if engine is None:
        create_database_engine()
    
    # Import all models to ensure they are registered with Base
    from . import models  # noqa: F401
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully")


def close_db():
    """Close database connections."""
    global engine, SessionLocal
    
    if engine:
        engine.dispose()
        engine = None
    
    SessionLocal = None
    logger.info("Database connections closed")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session.
    
    Yields:
        Session: SQLAlchemy database session
    """
    if SessionLocal is None:
        create_session_factory()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Health check function
def check_database_health() -> dict:
    """
    Check database connection health.
    
    Returns:
        dict: Health status information
    """
    try:
        if engine is None:
            create_database_engine()
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute("SELECT 1").scalar()
            
        return {
            "status": "healthy",
            "database_type": get_settings().database_type.value,
            "connection_test": result == 1,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_type": get_settings().database_type.value,
        }
