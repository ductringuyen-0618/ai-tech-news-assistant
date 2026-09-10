"""
Integration Tests for Learning API Routes
==========================================

Mirrors ``test_news_api.py``'s pattern (bare FastAPI app + dependency
override on the repository) for ``GET /api/learning/``.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from src.api.routes.learning import router, get_article_repository
from src.repositories.article_repository import ArticleRepository
from src.services.learning_ingestion import LEARNING_CATEGORY


@pytest.fixture
def client():
    """Create test client for learning routes."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def mock_repo(client):
    """Mock the article repository via FastAPI dependency override."""
    article_repo = AsyncMock(spec=ArticleRepository)
    client.app.dependency_overrides[get_article_repository] = lambda: article_repo
    yield article_repo
    client.app.dependency_overrides.clear()


class TestLearningRoutes:
    def test_get_learning_items_success(self, client, mock_repo, sample_article_data):
        """A populated Learning feed returns items and pagination info,
        filtered by the reserved LEARNING_CATEGORY tag."""
        from src.models.article import Article
        from datetime import datetime

        data = dict(sample_article_data)
        data["categories"] = [LEARNING_CATEGORY]
        mock_article = Article(
            id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            view_count=0,
            embedding_generated=False,
            **data,
        )
        mock_repo.list_articles.return_value = ([mock_article], 1, None)

        response = client.get("/learning/")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["categories"] == [LEARNING_CATEGORY]
        assert body["pagination"]["total_items"] == 1

        # The category filter must be the reserved Learning tag, not a
        # caller-suppliable value -- this endpoint has no `category` query
        # param, unlike /api/news/.
        call_kwargs = mock_repo.list_articles.call_args[1]
        assert call_kwargs["categories"] == [LEARNING_CATEGORY]

    def test_get_learning_items_empty(self, client, mock_repo):
        """Empty state: no Learning items yet."""
        mock_repo.list_articles.return_value = ([], 0, None)

        response = client.get("/learning/")

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total_items"] == 0
        assert body["pagination"]["total_pages"] == 0
        assert body["pagination"]["has_next"] is False

    def test_get_learning_items_pagination_params(self, client, mock_repo):
        """page/page_size map to the same limit/offset convention as
        /api/news/."""
        mock_repo.list_articles.return_value = ([], 0, None)

        response = client.get("/learning/?page=2&page_size=10")

        assert response.status_code == 200
        call_kwargs = mock_repo.list_articles.call_args[1]
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 10

    def test_get_learning_items_repository_error_returns_500(self, client, mock_repo):
        """A repository failure surfaces as a 500, not an unhandled
        exception -- matches /api/news/'s error-handling contract."""
        mock_repo.list_articles.side_effect = RuntimeError("db unavailable")

        response = client.get("/learning/")

        assert response.status_code == 500
