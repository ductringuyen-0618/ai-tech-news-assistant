"""
App Startup Tests
================

Tests to verify the application can start up properly.
Used by CI pipeline to validate build integrity.
"""

import pytest
from unittest.mock import patch
from pathlib import Path
import sys

# Add the backend directory to the path
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def test_import_main_modules():
    """Test that main application modules can be imported."""
    try:
        from src.core.config import Settings  # noqa: F401
        from src.models.article import Article  # noqa: F401
        from src.repositories.article_repository import ArticleRepository  # noqa: F401
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import main modules: {e}")


def test_config_initialization():
    """Test that configuration can be initialized."""
    from src.core.config import Settings
    
    # Test with default settings
    settings = Settings()
    assert settings is not None
    assert hasattr(settings, 'sqlite_database_path')
    assert hasattr(settings, 'default_llm_provider')


def test_database_repository_init(tmp_path):
    """Test that ArticleRepository can be initialized against a real SQLite DB."""
    from src.repositories.article_repository import ArticleRepository

    db_path = str(tmp_path / "init_check.db")
    repo = ArticleRepository(db_path)
    assert repo is not None
    assert repo.db_path == db_path


def test_article_model_creation():
    """Test that article models can be created."""
    from src.models.article import Article, ArticleCreate
    
    # Test ArticleCreate
    article_create = ArticleCreate(
        title="Test Article",
        content="Test content",
        source="test-source",
        url="https://example.com/test"
    )
    assert article_create.title == "Test Article"
    assert article_create.source == "test-source"
    
    # Test Article with minimal fields
    article = Article(
        id=1,
        title="Test Article",
        source="test-source",
        url="https://example.com/test"
    )
    assert article.id == 1
    assert article.title == "Test Article"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
