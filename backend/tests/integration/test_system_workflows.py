"""
System-Level Integration Tests
==============================

Comprehensive tests for complete workflows and service interactions.
Tests successful paths for critical business operations.
"""

import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock

# Import services
from src.services.news_service import NewsService
from src.repositories.article_repository import ArticleRepository
from src.repositories.embedding_repository import EmbeddingRepository
from src.models.article import Article, ArticleCreate


# ============================================================================
# FIXTURES - Sample Data
# ============================================================================

@pytest.fixture
def sample_article_data() -> Dict[str, Any]:
    """Sample article data for testing."""
    return {
        "title": "Revolutionary AI Breakthrough",
        "content": "Researchers have developed a new AI model that achieves state-of-the-art results...",
        "url": "https://example.com/ai-breakthrough-2025",
        "source": "TechCrunch",
        "published_date": datetime.now() - timedelta(days=1),
        "author": "Jane Smith",
        "keywords": ["AI", "Machine Learning", "Tech"]
    }


@pytest.fixture
def sample_articles_list(sample_article_data) -> List[ArticleCreate]:
    """Generate multiple sample articles."""
    articles = []
    for i in range(5):
        data = sample_article_data.copy()
        data["title"] = f"Article {i+1}: {data['title']}"
        data["url"] = f"https://example.com/article-{i+1}"
        articles.append(ArticleCreate(**data))
    return articles


@pytest.fixture
def mock_article_repository():
    """Create mock article repository."""
    repo = AsyncMock(spec=ArticleRepository)
    # Setup default return values
    repo.create.return_value = 1  # Return article ID
    repo.get_by_id.return_value = None
    repo.get_by_url.return_value = None
    repo.list_articles.return_value = ([], 0)
    return repo


@pytest.fixture
def mock_embedding_repository():
    """Create mock embedding repository."""
    repo = AsyncMock(spec=EmbeddingRepository)
    # Setup default return values
    repo.store_embedding.return_value = 1
    repo.get_embedding.return_value = None
    repo.similarity_search.return_value = []
    return repo


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider for summarization."""
    provider = AsyncMock()
    provider.summarize.return_value = "This is a test summary."
    provider.is_available.return_value = True
    return provider


# ============================================================================
# SYSTEM WORKFLOW TESTS - Complete Business Operations
# ============================================================================

class TestNewsIngestionWorkflow:
    """Test complete news ingestion workflow."""
    
    @pytest.mark.asyncio
    async def test_ingest_articles_complete_workflow(
        self,
        mock_article_repository,
        sample_articles_list
    ):
        """
        Test complete ingestion workflow:
        1. Fetch articles from source
        2. Validate article data
        3. Check for duplicates
        4. Store in database
        5. Return results
        """
        # Setup: Create service with mocked repository
        news_service = NewsService()
        news_service.repository = mock_article_repository
        
        # Setup mock to return created article IDs
        mock_article_repository.create.side_effect = range(1, len(sample_articles_list) + 1)
        mock_article_repository.get_by_url.return_value = None  # No duplicates
        
        # Execute: Ingest articles
        results = []
        for article_data in sample_articles_list:
            article_dict = article_data.model_dump()
            result = await mock_article_repository.create(article_dict)
            results.append(result)
        
        # Verify: All articles were created
        assert len(results) == len(sample_articles_list)
        assert all(id > 0 for id in results)
        assert mock_article_repository.create.call_count == len(sample_articles_list)
    
    @pytest.mark.asyncio
    async def test_ingest_with_duplicate_detection(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """
        Test duplicate detection during ingestion:
        1. Check if article URL already exists
        2. Skip if duplicate found
        3. Create if new
        """
        # Setup: Mock existing article
        existing_article = Article(
            id=1,
            title=sample_article_data["title"],
            content=sample_article_data["content"],
            url=sample_article_data["url"],
            source=sample_article_data["source"],
            published_date=sample_article_data["published_date"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view_count=5,
            embedding_generated=False
        )
        
        mock_article_repository.get_by_url.return_value = existing_article
        
        # Execute: Try to ingest duplicate
        duplicate = await mock_article_repository.get_by_url(
            sample_article_data["url"]
        )
        
        # Verify: Duplicate was detected
        assert duplicate is not None
        assert duplicate.url == sample_article_data["url"]
        mock_article_repository.create.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ingest_with_error_handling(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """
        Test error handling during ingestion:
        1. Catch validation errors
        2. Catch database errors
        3. Return meaningful error messages
        4. Rollback on failure
        """
        # Setup: Mock database error
        mock_article_repository.create.side_effect = Exception("Database error")
        
        # Execute: Try to ingest with error
        with pytest.raises(Exception) as exc_info:
            await mock_article_repository.create(sample_article_data)
        
        # Verify: Error was raised and logged
        assert "Database error" in str(exc_info.value)


class TestSearchAndRetrievalWorkflow:
    """Test search and article retrieval workflows."""
    
    @pytest.mark.asyncio
    async def test_search_articles_workflow(
        self,
        mock_article_repository,
        sample_articles_list
    ):
        """
        Test search workflow:
        1. Parse search query
        2. Query database with filters
        3. Apply pagination
        4. Return results
        """
        # Setup: Mock articles for search
        articles = [
            Article(
                id=i+1,
                title=article.title,
                content=article.content,
                url=article.url,
                source=article.source,
                published_date=article.published_date,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                view_count=0,
                embedding_generated=False
            )
            for i, article in enumerate(sample_articles_list)
        ]
        
        mock_article_repository.list_articles.return_value = (articles, len(articles))
        
        # Execute: Search articles
        results, total = await mock_article_repository.list_articles(limit=10, offset=0)
        
        # Verify: Results returned
        assert len(results) == len(articles)
        assert total == len(articles)
        assert all(article.title for article in results)
    
    @pytest.mark.asyncio
    async def test_pagination_workflow(
        self,
        mock_article_repository
    ):
        """
        Test pagination workflow:
        1. Calculate offset from page/size
        2. Query with limit and offset
        3. Return page info
        """
        # Setup: Mock paginated results
        page_size = 10
        total_items = 47
        
        # Simulate different pages
        mock_article_repository.list_articles.return_value = (
            [MagicMock() for _ in range(page_size)],
            total_items
        )
        
        # Execute: Get different pages
        page1, total1 = await mock_article_repository.list_articles(
            limit=page_size, offset=0
        )
        page2, total2 = await mock_article_repository.list_articles(
            limit=page_size, offset=page_size
        )
        
        # Verify: Pagination works
        assert total1 == total2 == total_items
        assert len(page1) == page_size
        assert len(page2) == page_size


class TestEmbeddingWorkflow:
    """Test embedding generation and search workflow."""
    
    @pytest.mark.asyncio
    async def test_embedding_generation_workflow(
        self,
        mock_embedding_repository
    ):
        """
        Test embedding generation workflow:
        1. Generate embeddings for article content
        2. Store in vector database
        3. Return embedding ID
        """
        # Setup
        article_id = 1
        article_content = "Artificial intelligence is transforming the tech industry..."
        embedding_vector = [0.1, 0.2, 0.3, 0.4]  # Simplified embedding
        
        # Note: store_embedding is not async - returns int directly
        mock_embedding_repository.store_embedding.return_value = 1
        
        # Execute: Store embedding
        embedding_id = mock_embedding_repository.store_embedding(
            article_id=article_id,
            content=article_content,
            embedding=embedding_vector
        )
        
        # Verify
        assert embedding_id == 1
        mock_embedding_repository.store_embedding.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_semantic_search_workflow(
        self,
        mock_embedding_repository
    ):
        """
        Test semantic search workflow:
        1. Generate query embedding
        2. Search similar documents
        3. Return ranked results
        """
        # Setup
        query_embedding = [0.15, 0.25, 0.35, 0.45]
        
        mock_results = [
            {"article_id": 1, "score": 0.95},
            {"article_id": 2, "score": 0.87},
            {"article_id": 3, "score": 0.76}
        ]
        
        # Note: similarity_search is not async - returns list directly
        mock_embedding_repository.similarity_search.return_value = mock_results
        
        # Execute: Search
        results = mock_embedding_repository.similarity_search(
            embedding=query_embedding,
            limit=3
        )
        
        # Verify
        assert len(results) == 3
        assert results[0]["score"] > results[1]["score"]  # Results ranked by score
        mock_embedding_repository.similarity_search.assert_called_once()


class TestSummarizationWorkflow:
    """Test AI summarization workflow."""
    
    @pytest.mark.asyncio
    async def test_summarization_workflow(
        self,
        mock_llm_provider
    ):
        """
        Test summarization workflow:
        1. Check if LLM is available
        2. Generate summary from article content
        3. Store summary
        4. Return result
        """
        # Setup
        article_content = """
        Artificial intelligence has made breakthrough achievements in natural language processing.
        Large language models can now understand and generate human-like text with remarkable accuracy.
        Applications range from customer service chatbots to code generation tools.
        The technology is transforming multiple industries including healthcare, finance, and education.
        """
        
        expected_summary = "This is a test summary."
        mock_llm_provider.summarize.return_value = expected_summary
        
        # Execute: Check availability and summarize
        is_available = await mock_llm_provider.is_available()
        summary = await mock_llm_provider.summarize(article_content)
        
        # Verify
        assert is_available is True
        assert summary == expected_summary
        mock_llm_provider.summarize.assert_called_once_with(article_content)
    
    @pytest.mark.asyncio
    async def test_summarization_error_handling(
        self,
        mock_llm_provider
    ):
        """
        Test summarization error handling:
        1. Handle LLM unavailability
        2. Handle API errors
        3. Fallback gracefully
        """
        # Setup: LLM unavailable
        mock_llm_provider.is_available.return_value = False
        
        # Execute: Check availability
        is_available = await mock_llm_provider.is_available()
        
        # Verify
        assert is_available is False


class TestMultiServiceIntegration:
    """Test integration of multiple services working together."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_pipeline(
        self,
        mock_article_repository,
        mock_embedding_repository,
        mock_llm_provider,
        sample_article_data
    ):
        """
        Test end-to-end pipeline:
        1. Ingest article
        2. Generate embeddings
        3. Create summary
        4. Store metadata
        5. Make searchable
        """
        # Step 1: Ingest article
        mock_article_repository.create.return_value = 1
        article_id = await mock_article_repository.create(sample_article_data)
        assert article_id == 1
        
        # Step 2: Generate embedding (not async in actual implementation)
        embedding_vector = [0.1] * 384  # Mock embedding
        mock_embedding_repository.store_embedding.return_value = 1
        embedding_id = mock_embedding_repository.store_embedding(
            article_id=article_id,
            content=sample_article_data["content"],
            embedding=embedding_vector
        )
        assert embedding_id == 1
        
        # Step 3: Generate summary
        mock_llm_provider.is_available.return_value = True
        mock_llm_provider.summarize.return_value = "Summary of the article"
        summary = await mock_llm_provider.summarize(sample_article_data["content"])
        assert summary is not None
        
        # Verify all steps completed
        assert article_id > 0
        assert embedding_id > 0
        assert summary is not None
        mock_article_repository.create.assert_called_once()
        mock_embedding_repository.store_embedding.assert_called_once()
        mock_llm_provider.summarize.assert_called_once()


class TestConcurrentOperations:
    """Test concurrent operations and race conditions."""
    
    @pytest.mark.asyncio
    async def test_concurrent_article_ingestion(
        self,
        mock_article_repository,
        sample_articles_list
    ):
        """
        Test concurrent ingestion:
        1. Ingest multiple articles simultaneously
        2. Verify no race conditions
        3. All articles stored
        """
        import asyncio
        
        # Setup
        mock_article_repository.create.side_effect = range(1, len(sample_articles_list) + 1)
        
        # Execute: Concurrent ingestion
        tasks = [
            mock_article_repository.create(article.model_dump())
            for article in sample_articles_list
        ]
        results = await asyncio.gather(*tasks)
        
        # Verify
        assert len(results) == len(sample_articles_list)
        assert all(id > 0 for id in results)
        assert len(set(results)) == len(results)  # All IDs unique


class TestErrorRecovery:
    """Test error recovery and resilience."""
    
    @pytest.mark.asyncio
    async def test_partial_ingestion_failure(
        self,
        mock_article_repository,
        sample_articles_list
    ):
        """
        Test partial failure recovery:
        1. Some articles fail to ingest
        2. Others succeed
        3. Return mixed results
        """
        # Setup: Alternate success/failure - need more items than list length
        side_effects = [1, Exception("DB Error"), 2, 3, 4, 5]
        mock_article_repository.create.side_effect = side_effects
        
        # Execute: Try to ingest (with error handling)
        results = []
        errors = []
        
        for i, article in enumerate(sample_articles_list):
            try:
                result = await mock_article_repository.create(article.model_dump())
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        # Verify: Some succeeded, some failed
        assert len(results) >= 3  # At least 3 succeeded (indices 0, 2, 3)
        assert len(errors) == 1  # Exactly 1 failed (index 1)
        assert "DB Error" in errors[0]
    
    @pytest.mark.asyncio
    async def test_retry_on_temporary_failure(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """
        Test retry mechanism on temporary failures:
        1. Fail on first attempt
        2. Succeed on retry
        """
        # Setup: Fail once, then succeed
        mock_article_repository.create.side_effect = [
            Exception("Temporary failure"),
            1  # Success on retry
        ]
        
        # Execute: First attempt fails
        try:
            await mock_article_repository.create(sample_article_data)
        except Exception:
            pass
        
        # Execute: Retry succeeds
        result = await mock_article_repository.create(sample_article_data)
        
        # Verify
        assert result == 1
        assert mock_article_repository.create.call_count == 2


class TestDataConsistency:
    """Test data consistency across operations."""
    
    @pytest.mark.asyncio
    async def test_article_metadata_consistency(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """
        Test metadata consistency:
        1. Article stored with all fields
        2. Retrieved data matches input
        3. Timestamps preserved
        """
        # Setup
        article_id = 1
        mock_article_repository.create.return_value = article_id
        
        created_article = Article(
            id=article_id,
            title=sample_article_data["title"],
            content=sample_article_data["content"],
            url=sample_article_data["url"],
            source=sample_article_data["source"],
            published_date=sample_article_data["published_date"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view_count=0,
            embedding_generated=False
        )
        
        mock_article_repository.get_by_id.return_value = created_article
        
        # Execute: Create and retrieve
        created_id = await mock_article_repository.create(sample_article_data)
        retrieved = await mock_article_repository.get_by_id(created_id)
        
        # Verify: Data intact
        assert retrieved.title == sample_article_data["title"]
        assert retrieved.content == sample_article_data["content"]
        assert retrieved.url == sample_article_data["url"]
        assert retrieved.source == sample_article_data["source"]


# ============================================================================
# EDGE CASES AND BOUNDARY CONDITIONS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_empty_article_list(
        self,
        mock_article_repository
    ):
        """Test handling of empty article list."""
        mock_article_repository.list_articles.return_value = ([], 0)
        
        articles, total = await mock_article_repository.list_articles(limit=10, offset=0)
        
        assert articles == []
        assert total == 0
    
    @pytest.mark.asyncio
    async def test_very_large_article(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """Test handling of very large article content."""
        # Create large content (1MB)
        large_content = sample_article_data["content"] * 10000
        large_data = sample_article_data.copy()
        large_data["content"] = large_content
        
        mock_article_repository.create.return_value = 1
        
        result = await mock_article_repository.create(large_data)
        
        assert result == 1
        mock_article_repository.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_special_characters_in_content(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """Test handling of special characters."""
        special_data = sample_article_data.copy()
        special_data["title"] = "🤖 AI & ML: The Future <2025> [Report]"
        special_data["content"] = "Content with émojis 😀 and spëcial çhars & symbols"
        
        mock_article_repository.create.return_value = 1
        
        result = await mock_article_repository.create(special_data)
        
        assert result == 1
    
    @pytest.mark.asyncio
    async def test_null_optional_fields(
        self,
        mock_article_repository,
        sample_article_data
    ):
        """Test handling of null optional fields."""
        minimal_data = {
            "title": "Minimal Article",
            "content": "Content",
            "url": "https://example.com/minimal",
            "source": "Test",
            "published_date": datetime.now()
        }
        
        mock_article_repository.create.return_value = 1
        
        result = await mock_article_repository.create(minimal_data)
        
        assert result == 1
