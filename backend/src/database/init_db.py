"""
Database Initialization Script
=============================

Initialize the SQLAlchemy database with proper configuration,
run migrations, and handle data migration from old SQLite database.
"""

import logging
from pathlib import Path

from ..core.config import get_settings
from ..database.base import init_db, check_database_health
from ..database.session import get_database_stats
from ..services.migration_service import run_migration_if_needed

logger = logging.getLogger(__name__)


def ensure_data_directory():
    """Ensure the data directory exists."""
    settings = get_settings()
    if settings.database_type.value == "sqlite":
        # Extract directory from the database URL. Resolved via the same
        # shared helper as database/base.py's engine so this never drifts
        # to a different default file (see get_database_sqlalchemy_url).
        db_url = settings.get_database_sqlalchemy_url()
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            data_dir = Path(db_path).parent
            data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured data directory exists: {data_dir}")


def initialize_database():
    """
    Initialize the database with tables and run migrations.
    
    Returns:
        bool: True if initialization was successful
    """
    try:
        logger.info("Initializing database...")
        
        # Ensure data directory exists
        ensure_data_directory()
        
        # Initialize database tables
        init_db()
        logger.info("Database tables initialized successfully")
        
        # Check database health
        health = check_database_health()
        if health["status"] != "healthy":
            logger.error(f"Database health check failed: {health}")
            return False
        
        logger.info("Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def run_database_migration():
    """
    Run database migration from old SQLite to new SQLAlchemy database.
    
    Returns:
        bool: True if migration was successful or not needed
    """
    try:
        logger.info("Checking for database migration...")
        
        migration_run = run_migration_if_needed()
        if migration_run:
            logger.info("Database migration completed successfully")
        else:
            logger.info("No migration needed")
        
        return True
        
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        return False


def populate_default_data():
    """
    Populate database with default data (sources, categories, etc.).
    
    Returns:
        bool: True if successful
    """
    try:
        from ..database.session import get_db_transaction
        from ..database.models import SourceModel, CategoryModel
        
        logger.info("Populating default data...")
        
        with get_db_transaction() as session:
            # Check if we already have data
            source_count = session.query(SourceModel).count()
            category_count = session.query(CategoryModel).count()
            
            if source_count > 0 and category_count > 0:
                logger.info("Database already has default data")
                return True
            
            # Default news sources
            default_sources = [
                {
                    "name": "TechCrunch",
                    "url": "https://techcrunch.com",
                    "rss_url": "https://techcrunch.com/feed/",
                    "description": "Technology and startup news",
                    "is_active": True
                },
                {
                    "name": "The Verge",
                    "url": "https://theverge.com",
                    "rss_url": "https://www.theverge.com/rss/index.xml",
                    "description": "Technology, science, art, and culture",
                    "is_active": True
                },
                {
                    "name": "Ars Technica",
                    "url": "https://arstechnica.com",
                    "rss_url": "https://feeds.arstechnica.com/arstechnica/index",
                    "description": "Technology news and analysis",
                    "is_active": True
                },
                {
                    "name": "Hacker News",
                    "url": "https://news.ycombinator.com",
                    "description": "Social news website focusing on computer science and entrepreneurship",
                    "is_active": True
                }
            ]
            
            # Default categories
            default_categories = [
                {"name": "Artificial Intelligence", "slug": "ai", "color": "#FF6B6B"},
                {"name": "Machine Learning", "slug": "ml", "color": "#4ECDC4"},
                {"name": "Software Development", "slug": "dev", "color": "#45B7D1"},
                {"name": "Cybersecurity", "slug": "security", "color": "#96CEB4"},
                {"name": "Cloud Computing", "slug": "cloud", "color": "#FFEAA7"},
                {"name": "Mobile Technology", "slug": "mobile", "color": "#DDA0DD"},
                {"name": "Web Development", "slug": "web", "color": "#98D8C8"},
                {"name": "Data Science", "slug": "data", "color": "#F7DC6F"},
                {"name": "DevOps", "slug": "devops", "color": "#BB8FCE"},
                {"name": "Blockchain", "slug": "blockchain", "color": "#85C1E9"}
            ]
            
            # Add sources
            if source_count == 0:
                for source_data in default_sources:
                    source = SourceModel(**source_data)
                    session.add(source)
                logger.info(f"Added {len(default_sources)} default sources")
            
            # Add categories
            if category_count == 0:
                for category_data in default_categories:
                    category = CategoryModel(**category_data)
                    session.add(category)
                logger.info(f"Added {len(default_categories)} default categories")
        
        logger.info("Default data populated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to populate default data: {e}")
        return False


def get_database_info():
    """
    Get database information and statistics.
    
    Returns:
        dict: Database information
    """
    try:
        health = check_database_health()
        stats = get_database_stats()
        
        return {
            "health": health,
            "stats": stats,
            "database_type": get_settings().database_type.value,
            "database_url": get_settings().database_url or "default"
        }
        
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return {"error": str(e)}


def setup_database():
    """
    Complete database setup including initialization, migration, and default data.
    
    Returns:
        bool: True if setup was successful
    """
    try:
        logger.info("Starting complete database setup...")
        
        # Step 1: Initialize database structure
        if not initialize_database():
            logger.error("Database initialization failed")
            return False
        
        # Step 2: Run migration from old database if needed
        if not run_database_migration():
            logger.error("Database migration failed")
            return False
        
        # Step 3: Populate default data
        if not populate_default_data():
            logger.error("Default data population failed")
            return False
        
        # Step 4: Final health check
        health = check_database_health()
        if health["status"] != "healthy":
            logger.error(f"Final database health check failed: {health}")
            return False
        
        # Step 5: Log final statistics
        stats = get_database_stats()
        logger.info(f"Database setup completed successfully. Stats: {stats}")
        
        return True
        
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        return False


if __name__ == "__main__":
    # Configure logging for script execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run database setup
    success = setup_database()
    
    if success:
        print("Database setup completed successfully!")
        
        # Display database info
        info = get_database_info()
        print(f"Database Type: {info.get('database_type', 'unknown')}")
        print(f"Health Status: {info.get('health', {}).get('status', 'unknown')}")
        print(f"Statistics: {info.get('stats', {})}")
    else:
        print("Database setup failed!")
        exit(1)
