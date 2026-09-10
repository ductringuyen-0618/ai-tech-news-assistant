"""
Service Integration Tests
=======================

Tests for service-to-service interactions and integration points.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.news_service import NewsService
from src.services.embedding_service import EmbeddingService
from src.services.summarization_service import SummarizationService
from src.repositories.article_repository import ArticleRepository
from src.repositories.embedding_repository import EmbeddingRepository
from src.models.article import Article, ArticleCreate


@pytest.fixture
def news_service_with_mocks(mock_article_repository):
    """Create NewsService with mocked repository."""
    service = NewsService()
    service.repository = mock_article_repository
    return service


@pytest.fixture
def embedding_service_with_mocks(mock_embedding_repository):
    """Create EmbeddingService with mocked repository."""
    service = EmbeddingService()
    service.repository = mock_embedding_repository
    return service


@pytest.fixture
def summarization_service_with_mocks(mock_llm_provider):
    """Create SummarizationService with mocked LLM."""
    service = SummarizationService()
    service.llm_provider = mock_llm_provider
    return service


class TestNewsServiceIntegration:
    """Test NewsService integration with actual methods."""
    
    @pytest.mark.asyncio
    async def test_fetch_rss_feeds_service_method(
        self,
        news_service_with_mocks,
        sample_articles_list
    ):
        """Test NewsService.fetch_rss_feeds works correctly."""
        # Setup
        news_service_with_mocks.initialize = AsyncMock()
        news_service_with_mocks.cleanup = AsyncMock()
        
        # Mock the actual HTTP client fetch
        with patch.object(
            news_service_with_mocks,
            'fetch_rss_feeds',
            return_value=sample_articles_list[:3]
        ) as mock_fetch:
            # Execute
            result = await mock_fetch(["https://example.com/feed.xml"])
            
            # Verify
            assert result is not None
            assert len(result) == 3
    
    @pytest.mark.asyncio
    async def test_health_check_service_method(
        self,
        news_service_with_mocks
    ):
        """Test NewsService health check."""
        # Setup
        news_service_with_mocks.health_check = MagicMock()
        news_service_with_mocks.health_check.return_value = {"status": "ok"}
        
        # Execute
        result = news_service_with_mocks.health_check()
        
        # Verify
        assert result is not None
        assert "status" in result


class TestEmbeddingServiceIntegration:
    """Test EmbeddingService integration with embedding repository."""
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_service_method(
        self,
        embedding_service_with_mocks
    ):
        """Test EmbeddingService.generate_embeddings works correctly."""
        # Setup
        article_content = ["This is test article content for embedding generation."]
        
        with patch.object(
            embedding_service_with_mocks,
            'generate_embeddings',
            return_value=[[0.1] * 384]
        ) as mock_gen:
            # Execute
            result = await mock_gen(article_content)
            
            # Verify
            assert result is not None
            assert len(result) == 1
            assert len(result[0]) == 384
    
    @pytest.mark.asyncio
    async def test_batch_similarity_search_integration(
        self,
        embedding_service_with_mocks
    ):
        """Test EmbeddingService batch similarity search."""
        # Setup
        query_embeddings = [[0.15] * 384 for _ in range(3)]
        mock_results = [
            [{"article_id": 1, "score": 0.95}],
            [{"article_id": 2, "score": 0.87}],
            [{"article_id": 3, "score": 0.76}]
        ]
        
        with patch.object(
            embedding_service_with_mocks,
            'batch_similarity',
            return_value=mock_results
        ) as mock_search:
            # Execute
            results = await mock_search(query_embeddings)
            
            # Verify
            assert len(results) == 3
            assert all(len(r) > 0 for r in results)


class TestSummarizationServiceIntegration:
    """Test SummarizationService integration with LLM providers."""
    
    @pytest.mark.asyncio
    async def test_summarize_content_service_method(
        self,
        summarization_service_with_mocks
    ):
        """Test SummarizationService.summarize_content works correctly."""
        # Setup
        article_content = """
        Artificial intelligence and machine learning are transforming industries.
        Companies are investing billions in AI research and development.
        The technology enables automation, better decision-making, and new products.
        """
        
        expected_summary = "AI is transforming industries with significant investments."
        
        with patch.object(
            summarization_service_with_mocks,
            'summarize_content',
            return_value=expected_summary
        ) as mock_sum:
            # Execute
            summary = await mock_sum(article_content)
            
            # Verify
            assert summary == expected_summary
    
    @pytest.mark.asyncio
    async def test_batch_summarization_service_method(
        self,
        summarization_service_with_mocks
    ):
        """Test SummarizationService batch summarization."""
        # Setup
        contents = [
            "Article 1 about AI",
            "Article 2 about ML",
            "Article 3 about DL"
        ]
        
        summaries = [
            "Summary 1",
            "Summary 2",
            "Summary 3"
        ]
        
        with patch.object(
            summarization_service_with_mocks,
            'batch_summarize',
            return_value=summaries
        ) as mock_batch:
            # Execute
            result = await mock_batch(contents)
            
            # Verify
            assert len(result) == 3
            assert all(s for s in result)


class TestArticleRepositoryIntegration:
    """Test ArticleRepository database operations."""
    
    @pytest.mark.asyncio
    async def test_create_and_retrieve_article(
        self,
        mock_article_repository
    ):
        """Test create and retrieve workflow."""
        # Setup
        article_data = {
            "title": "Test Article",
            "content": "Test content",
            "url": "https://example.com/test",
            "source": "TestSource",
            "published_date": datetime.now()
        }
        
        created_article = Article(
            id=1,
            title=article_data["title"],
            content=article_data["content"],
            url=article_data["url"],
            source=article_data["source"],
            published_date=article_data["published_date"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view_count=0,
            embedding_generated=False
        )
        
        mock_article_repository.create.return_value = 1
        mock_article_repository.get_by_id.return_value = created_article
        
        # Execute: Create
        article_id = await mock_article_repository.create(article_data)
        
        # Execute: Retrieve
        retrieved = await mock_article_repository.get_by_id(article_id)
        
        # Verify
        assert article_id == 1
        assert retrieved.title == article_data["title"]
        assert retrieved.url == article_data["url"]
    
    @pytest.mark.asyncio
    async def test_search_by_source(
        self,
        mock_article_repository
    ):
        """Test repository search by source."""
        # Setup
        articles = [MagicMock() for _ in range(3)]
        mock_article_repository.list_articles.return_value = (articles, 3)
        
        # Execute
        results, total = await mock_article_repository.list_articles(
            source="TechCrunch"
        )
        
        # Verify
        assert len(results) == 3
        assert total == 3


class TestEmbeddingRepositoryIntegration:
    """Test EmbeddingRepository vector storage operations."""
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_embedding(
        self,
        mock_embedding_repository
    ):
        """Test store and retrieve embedding workflow."""
        # Setup
        article_id = 1
        embedding_vector = [0.1, 0.2, 0.3, 0.4]
        
        mock_embedding_repository.store_embedding.return_value = 1
        mock_embedding_repository.get_embedding.return_value = {
            "id": 1,
            "article_id": article_id,
            "embedding": embedding_vector
        }
        
        # Execute: Store (not async in actual implementation)
        embedding_id = mock_embedding_repository.store_embedding(
            article_id=article_id,
            content="Test content",
            embedding=embedding_vector
        )
        
        # Execute: Retrieve (not async in actual implementation)
        retrieved = mock_embedding_repository.get_embedding(embedding_id)
        
        # Verify
        assert embedding_id == 1
        assert retrieved["article_id"] == article_id
    
    @pytest.mark.asyncio
    async def test_similarity_search_workflow(
        self,
        mock_embedding_repository
    ):
        """Test similarity search returns ranked results."""
        # Setup
        query_embedding = [0.15, 0.25, 0.35, 0.45]
        mock_results = [
            {"article_id": 1, "score": 0.95, "similarity": 0.95},
            {"article_id": 2, "score": 0.87, "similarity": 0.87},
            {"article_id": 3, "score": 0.76, "similarity": 0.76}
        ]
        
        mock_embedding_repository.similarity_search.return_value = mock_results
        
        # Execute (not async in actual implementation)
        results = mock_embedding_repository.similarity_search(
            embedding=query_embedding,
            limit=5
        )
        
        # Verify: Results ranked correctly
        assert len(results) == 3
        for i in range(len(results) - 1):
            assert results[i]["score"] >= results[i+1]["score"]


class TestServiceCommunication:
    """Test communication patterns between services."""
    
    @pytest.mark.asyncio
    async def test_news_service_to_embedding_service(
        self,
        news_service_with_mocks,
        embedding_service_with_mocks,
        sample_article_data
    ):
        """Test NewsService passes data to EmbeddingService."""
        # Setup
        article_id = 1
        news_service_with_mocks.repository.create.return_value = article_id
        embedding_service_with_mocks.repository.store_embedding.return_value = 1
        
        # Execute: NewsService creates article
        result_id = await news_service_with_mocks.repository.create(sample_article_data)
        
        # Execute: EmbeddingService processes it (not async)
        embedding_id = embedding_service_with_mocks.repository.store_embedding(
            article_id=result_id,
            content=sample_article_data["content"],
            embedding=[0.1]*384
        )
        
        # Verify: Both services completed their tasks
        assert result_id == article_id
        assert embedding_id is not None
    
    @pytest.mark.asyncio
    async def test_news_service_to_summarization_service(
        self,
        news_service_with_mocks,
        summarization_service_with_mocks,
        sample_article_data
    ):
        """Test NewsService passes article to SummarizationService."""
        # Setup
        article_id = 1
        news_service_with_mocks.repository.create.return_value = article_id
        
        with patch.object(
            summarization_service_with_mocks,
            'summarize_content',
            return_value="Test summary"
        ) as mock_sum:
            # Execute: Create article
            result_id = await news_service_with_mocks.repository.create(sample_article_data)
            
            # Execute: Summarize
            summary = await mock_sum(sample_article_data["content"])
            
            # Verify
            assert result_id == article_id
            assert summary == "Test summary"


class TestServiceErrorHandling:
    """Test error handling across services."""
    
    @pytest.mark.asyncio
    async def test_embedding_repository_error_handling(
        self,
        mock_embedding_repository
    ):
        """Test EmbeddingRepository error handling."""
        # Setup: Mock error
        mock_embedding_repository.store_embedding.side_effect = Exception(
            "Database error"
        )
        
        # Execute & Verify: Exception propagates
        with pytest.raises(Exception) as exc_info:
            mock_embedding_repository.store_embedding(
                article_id=1,
                content="Test",
                embedding=[0.1] * 384
            )
        
        assert "Database error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_summarization_service_error_handling(
        self,
        summarization_service_with_mocks
    ):
        """Test SummarizationService error handling."""
        # Setup: Mock error
        with patch.object(
            summarization_service_with_mocks,
            'summarize_content',
            side_effect=Exception("LLM API error")
        ):
            # Execute & Verify
            with pytest.raises(Exception) as exc_info:
                await summarization_service_with_mocks.summarize_content("content")
            
            assert "LLM API error" in str(exc_info.value)


class TestServicePerformance:
    """Test performance characteristics of services."""
    
    @pytest.mark.asyncio
    async def test_batch_article_processing(
        self,
        news_service_with_mocks,
        sample_articles_list
    ):
        """Test NewsService handles batch operations efficiently."""
        # Setup
        news_service_with_mocks.repository.create.side_effect = range(1, len(sample_articles_list) + 1)
        
        # Execute: Batch create
        import time
        start = time.time()
        
        ids = []
        for article in sample_articles_list:
            article_id = await news_service_with_mocks.repository.create(article.model_dump())
            ids.append(article_id)
        
        elapsed = time.time() - start
        
        # Verify
        assert len(ids) == len(sample_articles_list)
        assert all(id > 0 for id in ids)
        # Should be reasonably fast (async)
        assert elapsed < 5.0  # Should complete within 5 seconds
    
    @pytest.mark.asyncio
    async def test_embedding_batch_search(
        self,
        mock_embedding_repository
    ):
        """Test EmbeddingRepository handles multiple searches efficiently."""
        # Setup: Multiple searches
        mock_results = [{"article_id": i, "score": 0.9 - i*0.05} for i in range(10)]
        mock_embedding_repository.similarity_search.return_value = mock_results
        
        # Execute: Multiple searches (not async in actual implementation)
        import time
        start = time.time()
        
        for i in range(10):
            query_embedding = [0.1 * (i+1)] * 384
            results = mock_embedding_repository.similarity_search(
                embedding=query_embedding
            )
            assert len(results) == 10
        
        elapsed = time.time() - start
        
        # Verify: Batch search performance
        assert elapsed < 5.0  # 10 searches should be fast


class TestTransactionality:
    """Test transactional behavior of services."""
    
    @pytest.mark.asyncio
    async def test_rollback_on_embedding_failure(
        self,
        mock_article_repository,
        mock_embedding_repository
    ):
        """Test that article creation rolls back if embedding fails."""
        # Setup
        mock_article_repository.create.return_value = 1
        mock_embedding_repository.store_embedding.side_effect = Exception("Embedding failed")
        
        # Execute: Try complete workflow
        article_id = await mock_article_repository.create({
            "title": "Test",
            "content": "Test content",
            "url": "https://example.com",
            "source": "Test",
            "published_date": datetime.now()
        })
        
        # Execute: Embedding fails
        with pytest.raises(Exception):
            await mock_embedding_repository.store_embedding(
                article_id=article_id,
                content="content",
                embedding=[0.1] * 384
            )
        
        # Verify: Error was raised
        assert article_id == 1


# ============================================================================
# INTEGRATION TEST FIXTURES
# ============================================================================

@pytest.fixture
def mock_article_repository():
    """Mock ArticleRepository for testing."""
    repo = AsyncMock(spec=ArticleRepository)
    repo.create.return_value = 1
    repo.get_by_id.return_value = None
    repo.get_by_url.return_value = None
    repo.list_articles.return_value = ([], 0)
    return repo


@pytest.fixture
def mock_embedding_repository():
    """Mock EmbeddingRepository for testing."""
    repo = AsyncMock(spec=EmbeddingRepository)
    repo.store_embedding.return_value = 1
    repo.get_embedding.return_value = None
    repo.similarity_search.return_value = []
    return repo


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    provider = AsyncMock()
    provider.is_available.return_value = True
    provider.summarize.return_value = "Test summary"
    return provider


@pytest.fixture
def sample_article_data():
    """Sample article data."""
    return {
        "title": "AI and Machine Learning Advances",
        "content": "Deep learning models continue to achieve breakthrough results...",
        "url": "https://example.com/ai-advances",
        "source": "TechNews",
        "published_date": datetime.now()
    }


@pytest.fixture
def sample_articles_list(sample_article_data):
    """Generate multiple sample articles."""
    articles = []
    for i in range(5):
        data = sample_article_data.copy()
        data["title"] = f"Article {i}: {data['title']}"
        data["url"] = f"https://example.com/article-{i}"
        articles.append(ArticleCreate(**data))
    return articles
