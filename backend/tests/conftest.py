"""
Test Configuration
================

Common test configuration, fixtures, and utilities for the test suite.
"""

import asyncio
import importlib.util
import pytest
import tempfile
import os
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch


# Test database configuration
TEST_DB_PATH = ":memory:"  # Use in-memory SQLite for tests

# Patch settings to use in-memory database for all tests
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked requires_torch when torch is not importable."""
    if importlib.util.find_spec("torch") is not None:
        return
    skip_torch = pytest.mark.skip(reason="torch not installed in this environment")
    for item in items:
        if "requires_torch" in item.keywords:
            item.add_marker(skip_torch)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file for tests."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        db_path = tmp_file.name
    
    yield db_path
    
    # Cleanup with retry for Windows
    if os.path.exists(db_path):
        max_retries = 5
        for i in range(max_retries):
            try:
                os.unlink(db_path)
                break
            except (PermissionError, OSError):
                if i < max_retries - 1:
                    import time
                    time.sleep(0.1)  # Brief delay before retry
                else:
                    # Final attempt - ignore if still fails
                    try:
                        os.unlink(db_path)
                    except (PermissionError, OSError):
                        pass


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Mock embedding service for testing."""
    service = MagicMock()
    service.initialize = AsyncMock()
    service.generate_embeddings = AsyncMock()
    service.compute_similarity = AsyncMock()
    service.get_model_info = AsyncMock()
    service.health_check = AsyncMock()
    return service


@pytest.fixture
def mock_news_service() -> MagicMock:
    """Mock news service for testing."""
    service = MagicMock()
    service.initialize = AsyncMock()
    service.fetch_rss_feeds = AsyncMock()
    service.get_news_stats = AsyncMock()
    service.health_check = AsyncMock()
    return service


@pytest.fixture
def mock_summarization_service() -> MagicMock:
    """Mock summarization service for testing."""
    service = MagicMock()
    service.initialize = AsyncMock()
    service.summarize_content = AsyncMock()
    service.batch_summarize = AsyncMock()
    service.health_check = AsyncMock()
    return service


@pytest.fixture
def sample_article_data() -> dict:
    """Sample article data for testing."""
    return {
        "title": "Test Article Title",
        "url": "https://example.com/test-article",
        "content": "This is test article content with enough text to be meaningful for testing purposes.",
        "author": "Test Author",
        "source": "test-source.com",
        "categories": ["technology", "ai"],
        "metadata": {"test": True}
    }


@pytest.fixture
def sample_embedding_data() -> list:
    """Sample embedding data for testing."""
    return [0.1, 0.2, 0.3, 0.4, 0.5] * 100  # 500-dimensional vector


class AsyncContextManager:
    """Helper class for testing async context managers."""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# Common test data
SAMPLE_RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://feeds.feedburner.com/venturebeat/SZYF"
]

SAMPLE_EMBEDDING_RESPONSE = {
    "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5] * 100],
    "model_name": "test-model",
    "embedding_dim": 500,
    "processing_time": 0.1
}

SAMPLE_SIMILARITY_RESULTS = [
    {
        "id": "article:1",
        "similarity_score": 0.95,
        "metadata": {"title": "Similar Article 1"},
        "content_snippet": "This is a similar article..."
    },
    {
        "id": "article:2", 
        "similarity_score": 0.85,
        "metadata": {"title": "Similar Article 2"},
        "content_snippet": "Another similar article..."
    }
]
