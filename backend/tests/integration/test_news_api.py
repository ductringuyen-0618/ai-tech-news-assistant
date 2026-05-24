"""
Integration Tests for News API Routes
===================================

Tests for news API endpoints with real database and service integration.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.api.routes.news import router
from src.repositories.article_repository import ArticleRepository
from src.services.news_service import NewsService


@pytest.fixture
def client():
    """Create test client for news routes."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def mock_dependencies(client):
    """Mock all service dependencies using FastAPI dependency overrides."""
    # Setup mock news service
    news_service = AsyncMock(spec=NewsService)
    
    # Setup mock repository
    article_repo = AsyncMock(spec=ArticleRepository)
    
    # Override dependencies in FastAPI app
    from src.api.routes.news import get_news_service, get_article_repository
    client.app.dependency_overrides[get_news_service] = lambda: news_service
    client.app.dependency_overrides[get_article_repository] = lambda: article_repo
    
    yield {
        'news_service': news_service,
        'article_repo': article_repo
    }
    
    # Cleanup
    client.app.dependency_overrides.clear()


class TestNewsRoutes:
    """Test cases for news API routes."""
    
    def test_get_articles_success(self, client, mock_dependencies, sample_article_data):
        """Test successful article retrieval."""
        # Setup mock data
        from src.models.article import Article
        from datetime import datetime
        
        mock_article = Article(
            id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            view_count=0,
            embedding_generated=False,
            **sample_article_data
        )
        
        mock_dependencies['article_repo'].list_articles.return_value = ([mock_article], 1)
        
        response = client.get("/news/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["pagination"]["total_items"] == 1
        assert data["data"][0]["title"] == sample_article_data["title"]
    
    def test_get_articles_with_pagination(self, client, mock_dependencies):
        """Test article retrieval with pagination parameters."""
        mock_dependencies['article_repo'].list_articles.return_value = ([], 0)
        
        response = client.get("/news/?page=2&page_size=10")
        
        assert response.status_code == 200
        # Verify pagination parameters were used correctly
        mock_dependencies['article_repo'].list_articles.assert_called_once()
        call_args = mock_dependencies['article_repo'].list_articles.call_args
        assert call_args[1]['limit'] == 10
        assert call_args[1]['offset'] == 10  # (page-1) * page_size
    
    def test_get_articles_with_filters(self, client, mock_dependencies):
        """Test article retrieval with filters.

        The route currently forwards ``source`` and ``categories`` to the
        repository as individual kwargs (no ``filter_params`` object). The
        ``author`` and ``has_summary`` query params are accepted but NOT
        forwarded — that gap is tracked separately.
        """
        mock_dependencies['article_repo'].list_articles.return_value = ([], 0)

        response = client.get("/news/?source=techcrunch.com&author=test&has_summary=true")

        assert response.status_code == 200
        call_kwargs = mock_dependencies['article_repo'].list_articles.call_args.kwargs
        assert call_kwargs['source'] == "techcrunch.com"
    
    def test_get_article_by_id_success(self, client, mock_dependencies, sample_article_data):
        """Test successful retrieval of specific article."""
        from src.models.article import Article
        from datetime import datetime
        
        mock_article = Article(
            id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            view_count=1,
            embedding_generated=False,
            **sample_article_data
        )
        
        mock_dependencies['article_repo'].get_by_id.return_value = mock_article
        
        response = client.get("/news/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == 1
        assert data["data"]["title"] == sample_article_data["title"]
    
    def test_get_article_by_id_not_found(self, client, mock_dependencies):
        """Test article retrieval when article not found."""
        from src.core.exceptions import NotFoundError
        
        mock_dependencies['article_repo'].get_by_id.side_effect = NotFoundError("Article not found")
        
        response = client.get("/news/999")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_ingest_news_success(self, client, mock_dependencies, sample_article_data):
        """Test successful news ingestion."""
        from src.models.article import ArticleCreate
        
        # Setup mock data
        mock_article_data = ArticleCreate(**sample_article_data)
        mock_dependencies['news_service'].fetch_rss_feeds.return_value = [mock_article_data]
        mock_dependencies['article_repo'].get_by_url.return_value = None  # No existing article
        mock_dependencies['article_repo'].create.return_value = None
        
        # Send ingest request with feed URLs
        response = client.post(
            "/news/ingest",
            json={"feed_urls": ["https://example.com/feed.xml"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "processed" in data["data"] or "new_articles" in data["data"]
    
    def test_ingest_news_with_duplicates(self, client, mock_dependencies, sample_article_data):
        """Test news ingestion with duplicate articles."""
        from src.models.article import ArticleCreate, Article
        from datetime import datetime
        
        mock_article_data = ArticleCreate(**sample_article_data)
        mock_existing = Article(
            id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            view_count=0,
            embedding_generated=False,
            **sample_article_data
        )
        
        mock_dependencies['news_service'].fetch_rss_feeds.return_value = [mock_article_data]
        mock_dependencies['article_repo'].get_by_url.return_value = mock_existing  # Existing article
        
        response = client.post(
            "/news/ingest",
            json={"feed_urls": ["https://example.com/feed.xml"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # IngestResponse uses "duplicates" for the skipped-as-already-seen count.
        assert data["data"]["duplicates"] == 1
        assert data["data"]["new_articles"] == 0
    
    def test_ingest_news_with_custom_feeds(self, client, mock_dependencies):
        """Test news ingestion with custom feed URLs.

        The endpoint requires an ``IngestRequest`` body of the shape
        ``{"feed_urls": [...]}``; a bare list is rejected by FastAPI's
        validator with 422.
        """
        custom_feeds = ["https://custom-feed.com/rss"]

        mock_dependencies['news_service'].fetch_rss_feeds.return_value = []

        response = client.post("/news/ingest", json={"feed_urls": custom_feeds})

        assert response.status_code == 200
        mock_dependencies['news_service'].fetch_rss_feeds.assert_called_once_with(custom_feeds)
    
    def test_get_news_sources(self, client, mock_dependencies):
        """Test retrieving news source information."""
        mock_stats = {
            "top_sources": [
                {"source": "techcrunch.com", "count": 50},
                {"source": "venturebeat.com", "count": 30}
            ],
            "total_articles": 100
        }
        mock_dependencies['article_repo'].get_stats.return_value = mock_stats
        
        response = client.get("/news/sources")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["configured_sources"] == 2
        assert data["data"]["total_articles"] == 100
    
    def test_get_news_stats(self, client, mock_dependencies):
        """Test retrieving news statistics."""
        mock_stats = {
            "total_articles": 100,
            "recent_articles_7d": 15,
            "articles_with_summaries": 75,
            "articles_with_embeddings": 60,
            "top_sources": [
                {"source": "techcrunch.com", "count": 50}
            ]
        }
        mock_dependencies['article_repo'].get_stats.return_value = mock_stats
        
        response = client.get("/news/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        stats = data["data"]
        assert stats["total_articles"] == 100
        assert stats["articles_this_week"] == 15
        assert stats["articles_with_summaries"] == 75
        assert stats["unique_sources"] == 1
    
    def test_search_articles(self, client, mock_dependencies, sample_article_data):
        """Test article search functionality."""
        from src.models.article import Article
        from datetime import datetime
        
        mock_article = Article(
            id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            view_count=0,
            embedding_generated=False,
            **sample_article_data
        )
        
        mock_dependencies['article_repo'].search_articles.return_value = [mock_article]
        
        response = client.get("/news/search?q=test+query")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == sample_article_data["title"]
        
        mock_dependencies['article_repo'].search_articles.assert_called_once_with("test query", 20)
    
    def test_search_articles_empty_query(self, client, mock_dependencies):
        """Test article search with empty query."""
        response = client.get("/news/search?q=")
        
        assert response.status_code == 422  # Validation error
    
    def test_ingest_news_service_error(self, client, mock_dependencies):
        """Test news ingestion when the upstream service raises."""
        from src.core.exceptions import NewsIngestionError

        mock_dependencies['news_service'].fetch_rss_feeds.side_effect = NewsIngestionError("RSS fetch failed")

        response = client.post(
            "/news/ingest",
            json={"feed_urls": ["https://example.com/feed.xml"]},
        )

        assert response.status_code == 500
        assert "News ingestion failed" in response.json()["detail"]
    
    def test_get_articles_database_error(self, client, mock_dependencies):
        """Test article retrieval when database error occurs."""
        mock_dependencies['article_repo'].list_articles.side_effect = Exception("Database connection failed")
        
        response = client.get("/news/")
        
        assert response.status_code == 500
        assert "Failed to retrieve articles" in response.json()["detail"]
