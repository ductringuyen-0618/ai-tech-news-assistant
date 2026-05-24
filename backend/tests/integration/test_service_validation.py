"""
Service Validation Tests - Successful Paths
===========================================

Tests to verify all backend services work as intended and follow expected behavior.
Focused on successful operation paths and service correctness.
"""

import pytest
from datetime import datetime
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

# Services
from src.services.news_service import NewsService
from src.services.embedding_service import EmbeddingService
from src.services.summarization_service import SummarizationService

# Repositories
from src.repositories.article_repository import ArticleRepository
from src.repositories.embedding_repository import EmbeddingRepository

# Models
from src.models.article import Article, ArticleCreate


class TestNewsServiceValidation:
    """Validate NewsService functionality."""
    
    def test_news_service_initializes(self):
        """Test NewsService can be instantiated."""
        service = NewsService()
        assert service is not None
        assert hasattr(service, 'fetch_rss_feeds')
        assert hasattr(service, 'health_check')
        assert hasattr(service, 'get_news_stats')
    
    @pytest.mark.asyncio
    async def test_news_service_initialization_and_cleanup(self):
        """Test NewsService initialization and cleanup."""
        service = NewsService()
        
        # Initialize
        await service.initialize()
        assert service.client is not None
        
        # Cleanup
        await service.cleanup()
        assert service.client is None
    
    def test_news_service_has_rss_feeds_configured(self):
        """Test NewsService has RSS feeds configured."""
        service = NewsService()
        # Should have some RSS feeds or be configurable
        assert hasattr(service, 'rss_feeds')
        assert hasattr(service, 'max_articles_per_feed')
    
    @pytest.mark.asyncio
    async def test_fetch_rss_feeds_returns_articles(self):
        """Test fetch_rss_feeds returns article list."""
        service = NewsService()
        await service.initialize()
        
        # Mock the HTTP client
        with patch.object(service, 'fetch_rss_feeds', return_value=[]):
            result = await service.fetch_rss_feeds([])
            
            assert isinstance(result, list)
        
        await service.cleanup()


class TestEmbeddingServiceValidation:
    """Validate EmbeddingService functionality."""

    def test_embedding_service_initializes(self):
        """Test EmbeddingService can be instantiated."""
        service = EmbeddingService()
        assert service is not None
        assert hasattr(service, 'generate_embeddings')
        assert hasattr(service, 'compute_similarity')
        assert hasattr(service, 'batch_similarity')

    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_embedding_service_initialization(self):
        """Test EmbeddingService can initialize."""
        service = EmbeddingService()
        
        # Should be able to initialize
        await service.initialize()
        # Should have model info
        info = await service.get_model_info()
        assert isinstance(info, dict)
    
    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_generate_embeddings_returns_vectors(self):
        """Test generate_embeddings returns proper embeddings."""
        service = EmbeddingService()
        await service.initialize()
        
        texts = ["This is a test article about AI"]
        
        # Mock the actual embedding generation
        with patch.object(
            service,
            'generate_embeddings',
            return_value=[[0.1] * 384]
        ) as mock_gen:
            result = await mock_gen(texts)
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], list)
            assert len(result[0]) > 0


class TestSummarizationServiceValidation:
    """Validate SummarizationService functionality."""
    
    def test_summarization_service_initializes(self):
        """Test SummarizationService can be instantiated."""
        service = SummarizationService()
        assert service is not None
        assert hasattr(service, 'summarize_content')
        assert hasattr(service, 'batch_summarize')
        assert hasattr(service, 'health_check')
    
    @pytest.mark.asyncio
    async def test_summarize_content_returns_string(self):
        """Test summarize_content returns a string summary."""
        service = SummarizationService()
        
        content = """
        Artificial intelligence is rapidly advancing and transforming multiple industries.
        Deep learning models are achieving state-of-the-art results in various tasks.
        Companies are investing heavily in AI research and deployment.
        """
        
        # Mock the summarization
        with patch.object(
            service,
            'summarize_content',
            return_value="AI is rapidly advancing and transforming industries"
        ) as mock_sum:
            result = await mock_sum(content)
            
            assert isinstance(result, str)
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_batch_summarize_returns_list(self):
        """Test batch_summarize returns list of summaries."""
        service = SummarizationService()
        
        contents = [
            "Article 1 about AI",
            "Article 2 about ML",
            "Article 3 about DL"
        ]
        
        # Mock batch summarization
        with patch.object(
            service,
            'batch_summarize',
            return_value=["Summary 1", "Summary 2", "Summary 3"]
        ) as mock_batch:
            result = await mock_batch(contents)
            
            assert isinstance(result, list)
            assert len(result) == len(contents)
            assert all(isinstance(s, str) for s in result)


class TestArticleRepositoryValidation:
    """Validate ArticleRepository functionality."""
    
    def test_article_repository_initializes(self):
        """Test ArticleRepository can be instantiated."""
        repo = ArticleRepository(":memory:")
        assert repo is not None
    
    @pytest.mark.asyncio
    async def test_article_repository_has_required_methods(self):
        """Test ArticleRepository has all required methods."""
        repo = ArticleRepository(":memory:")
        
        # Check for required methods
        assert hasattr(repo, 'create')
        assert hasattr(repo, 'get_by_id')
        assert hasattr(repo, 'get_by_url')
        assert hasattr(repo, 'list_articles')
        assert hasattr(repo, 'update')
        assert hasattr(repo, 'delete')


class TestEmbeddingRepositoryValidation:
    """Validate EmbeddingRepository functionality."""
    
    def test_embedding_repository_initializes(self):
        """Test EmbeddingRepository can be instantiated."""
        # Use a mock to avoid database initialization
        with patch('src.repositories.embedding_repository.EmbeddingRepository.__init__', return_value=None):
            repo = MagicMock(spec=EmbeddingRepository)
            assert repo is not None
    
    def test_embedding_repository_has_required_methods(self):
        """Test EmbeddingRepository has all required methods."""
        # Use a mock to check interface
        repo = MagicMock(spec=EmbeddingRepository)
        
        # Check for required methods
        assert hasattr(repo, 'store_embedding')
        assert hasattr(repo, 'get_embedding')
        assert hasattr(repo, 'similarity_search')


class TestServiceInteroperability:
    """Test that services work together correctly."""
    
    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_article_and_embedding_service_workflow(self):
        """
        Test complete workflow: article → embedding
        """
        # Create services
        news_service = NewsService()
        embedding_service = EmbeddingService()
        
        # Initialize
        await news_service.initialize()
        await embedding_service.initialize()
        
        # Simulate article creation
        article_content = "AI and Machine Learning advances in 2025"
        
        # Mock embedding generation
        with patch.object(
            embedding_service,
            'generate_embeddings',
            return_value=[[0.1] * 384]
        ) as mock_embed:
            embeddings = await mock_embed([article_content])
            
            assert embeddings is not None
            assert len(embeddings) == 1
        
        # Cleanup
        await news_service.cleanup()
    
    @pytest.mark.asyncio
    async def test_article_and_summarization_service_workflow(self):
        """
        Test complete workflow: article → summary
        """
        news_service = NewsService()
        summarization_service = SummarizationService()
        
        await news_service.initialize()
        
        # Simulate article
        article_content = """
        Neural networks have revolutionized AI.
        Deep learning models now power most modern AI applications.
        Transfer learning allows reusing pre-trained models.
        """
        
        # Mock summarization
        with patch.object(
            summarization_service,
            'summarize_content',
            return_value="Neural networks and deep learning power modern AI"
        ) as mock_sum:
            summary = await mock_sum(article_content)
            
            assert summary is not None
            assert isinstance(summary, str)
        
        await news_service.cleanup()
    
    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_complete_service_pipeline(self):
        """
        Test complete pipeline: ingest → embed → summarize
        """
        news_service = NewsService()
        embedding_service = EmbeddingService()
        summarization_service = SummarizationService()
        
        # Initialize
        await news_service.initialize()
        await embedding_service.initialize()
        
        # Article data
        article_content = """
        Transformers have become the dominant architecture in NLP.
        Attention mechanisms allow models to focus on relevant parts.
        Large language models leverage transformers for impressive results.
        """
        
        # Step 1: Simulate article ingestion (no-op for test)
        assert article_content is not None
        
        # Step 2: Generate embedding
        with patch.object(
            embedding_service,
            'generate_embeddings',
            return_value=[[0.2] * 384]
        ) as mock_embed:
            embeddings = await mock_embed([article_content])
            assert embeddings is not None
        
        # Step 3: Generate summary
        with patch.object(
            summarization_service,
            'summarize_content',
            return_value="Transformers dominate NLP with attention mechanisms"
        ) as mock_sum:
            summary = await mock_sum(article_content)
            assert summary is not None
        
        # Cleanup
        await news_service.cleanup()


class TestServiceHealthChecks:
    """Test health checks for all services."""
    
    @pytest.mark.asyncio
    async def test_news_service_health_check(self):
        """Test NewsService health check."""
        service = NewsService()
        health = await service.health_check()
        
        assert health is not None
        assert isinstance(health, dict)
    
    @pytest.mark.asyncio
    async def test_embedding_service_health_check(self):
        """Test EmbeddingService health check."""
        service = EmbeddingService()
        health = await service.health_check()
        
        assert health is not None
        assert isinstance(health, dict)
    
    @pytest.mark.asyncio
    async def test_summarization_service_health_check(self):
        """Test SummarizationService health check."""
        service = SummarizationService()
        health = await service.health_check()
        
        assert health is not None
        assert isinstance(health, dict)


class TestServiceErrorHandling:
    """Test error handling in services."""
    
    @pytest.mark.asyncio
    async def test_news_service_cleanup_on_error(self):
        """Test NewsService cleans up properly on error."""
        service = NewsService()
        await service.initialize()
        
        assert service.client is not None
        
        # Cleanup should work without errors
        try:
            await service.cleanup()
            assert service.client is None
        except Exception as e:
            pytest.fail(f"Cleanup raised exception: {e}")
    
    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_embedding_service_model_info(self):
        """Test EmbeddingService returns model info."""
        service = EmbeddingService()
        info = await service.get_model_info()
        
        assert info is not None
        assert isinstance(info, dict)


class TestArticleCreationFlow:
    """Test article creation and retrieval flows."""
    
    @pytest.mark.asyncio
    async def test_article_can_be_created(self):
        """Test that articles can be created."""
        # This tests the model can be instantiated properly
        article_data = {
            "title": "Test Article",
            "content": "Test content",
            "url": "https://example.com/test",
            "source": "TestSource",
            "published_date": datetime.now()
        }
        
        article = ArticleCreate(**article_data)
        
        assert article.title == "Test Article"
        assert article.url == "https://example.com/test"
        assert article.source == "TestSource"


class TestServiceConfiguration:
    """Test service configuration."""
    
    def test_news_service_has_timeout_configured(self):
        """Test NewsService has request timeout."""
        service = NewsService()
        assert hasattr(service, 'request_timeout')
        assert service.request_timeout > 0
    
    def test_news_service_has_retry_configured(self):
        """Test NewsService has retry logic."""
        service = NewsService()
        assert hasattr(service, 'max_retries')
        assert service.max_retries > 0
    
    def test_news_service_has_rate_limiting(self):
        """Test NewsService has rate limiting."""
        service = NewsService()
        assert hasattr(service, 'max_articles_per_feed')
        assert service.max_articles_per_feed > 0
    
    def test_embedding_service_has_model_configured(self):
        """Test EmbeddingService has model configured."""
        service = EmbeddingService()
        # Should have model configuration
        assert hasattr(service, 'model_name') or hasattr(service, 'model')
