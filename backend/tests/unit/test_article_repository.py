"""
Unit Tests for Article Repository
================================

Tests for article repository data access operations.
"""

import pytest

from src.repositories.article_repository import ArticleRepository
from src.models.article import ArticleCreate, ArticleUpdate, ArticleSearchRequest
from src.core.exceptions import DatabaseError, NotFoundError


class TestArticleRepository:
    """Test cases for ArticleRepository."""
    
    @pytest.fixture
    def repository(self, temp_db_path):
        """Create repository instance with temporary database."""
        return ArticleRepository(db_path=temp_db_path)
    
    @pytest.mark.asyncio
    async def test_create_article(self, repository, sample_article_data):
        """Test creating a new article."""
        article_data = ArticleCreate(**sample_article_data)
        
        result = await repository.create(article_data)
        
        assert result.id is not None
        assert result.title == sample_article_data["title"]
        assert result.url == sample_article_data["url"]
        assert result.content == sample_article_data["content"]
        assert result.author == sample_article_data["author"]
        assert result.source == sample_article_data["source"]
    
    @pytest.mark.asyncio
    async def test_create_duplicate_url_fails(self, repository, sample_article_data):
        """Test that creating article with duplicate URL fails."""
        article_data = ArticleCreate(**sample_article_data)
        
        # Create first article
        await repository.create(article_data)
        
        # Attempt to create duplicate should fail
        with pytest.raises(DatabaseError, match="already exists"):
            await repository.create(article_data)
    
    @pytest.mark.asyncio
    async def test_get_by_id(self, repository, sample_article_data):
        """Test retrieving article by ID."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        result = await repository.get_by_id(created.id)
        
        assert result.id == created.id
        assert result.title == sample_article_data["title"]
        assert result.view_count == 1  # Should increment on view
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repository):
        """Test retrieving non-existent article raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await repository.get_by_id(999)
    
    @pytest.mark.asyncio
    async def test_get_by_url(self, repository, sample_article_data):
        """Test retrieving article by URL."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        result = await repository.get_by_url(sample_article_data["url"])
        
        assert result is not None
        assert result.id == created.id
        assert result.url == sample_article_data["url"]
    
    @pytest.mark.asyncio
    async def test_get_by_url_not_found(self, repository):
        """Test retrieving non-existent URL returns None."""
        result = await repository.get_by_url("https://nonexistent.com")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_article(self, repository, sample_article_data):
        """Test updating an existing article."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        update_data = ArticleUpdate(
            title="Updated Title",
            summary="New summary"
        )
        
        result = await repository.update(created.id, update_data)
        
        assert result.id == created.id
        assert result.title == "Updated Title"
        assert result.summary == "New summary"
        assert result.content == sample_article_data["content"]  # Unchanged
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_article(self, repository):
        """Test updating non-existent article raises NotFoundError."""
        update_data = ArticleUpdate(title="Updated Title")
        
        with pytest.raises(NotFoundError):
            await repository.update(999, update_data)
    
    @pytest.mark.asyncio
    async def test_delete_article(self, repository, sample_article_data):
        """Test soft deleting an article."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        result = await repository.delete(created.id)
        
        assert result is True
        
        # Article should not be found after deletion
        with pytest.raises(NotFoundError):
            await repository.get_by_id(created.id)
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_article(self, repository):
        """Test deleting non-existent article raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await repository.delete(999)
    
    @pytest.mark.asyncio
    async def test_list_articles_no_filter(self, repository, sample_article_data):
        """Test listing articles without filters."""
        # Create multiple articles
        for i in range(3):
            article_data = ArticleCreate(
                **{**sample_article_data, "url": f"https://example.com/article-{i}"}
            )
            await repository.create(article_data)
        
        articles, total_count, _ = await repository.list_articles(limit=10, offset=0)

        assert len(articles) == 3
        assert total_count == 3
        assert all(article.id is not None for article in articles)
    
    @pytest.mark.asyncio
    async def test_list_articles_with_pagination(self, repository, sample_article_data):
        """Test listing articles with pagination."""
        # Create 5 articles
        for i in range(5):
            article_data = ArticleCreate(
                **{**sample_article_data, "url": f"https://example.com/article-{i}"}
            )
            await repository.create(article_data)
        
        # Get first page
        articles, total_count, _ = await repository.list_articles(limit=2, offset=0)
        assert len(articles) == 2
        assert total_count == 5

        # Get second page
        articles, total_count, _ = await repository.list_articles(limit=2, offset=2)
        assert len(articles) == 2
        assert total_count == 5
    
    @pytest.mark.asyncio
    async def test_list_articles_with_source_filter(self, repository, sample_article_data):
        """Test listing articles filtered by source."""
        # Create articles with different sources
        sources = ["source1.com", "source2.com", "source1.com"]
        for i, source in enumerate(sources):
            article_data = ArticleCreate(
                **{**sample_article_data, "url": f"https://example.com/article-{i}", "source": source}
            )
            await repository.create(article_data)
        
        ArticleSearchRequest(source="source1.com")
        articles, total_count, _ = await repository.list_articles(source="source1.com")

        assert len(articles) == 2
        assert total_count == 2
        assert all(article.source == "source1.com" for article in articles)
    
    @pytest.mark.asyncio
    async def test_search_articles(self, repository, sample_article_data):
        """Test text search functionality."""
        # Create articles with different titles
        titles = ["AI Technology News", "Machine Learning Update", "Tech Industry Report"]
        for i, title in enumerate(titles):
            article_data = ArticleCreate(
                **{**sample_article_data, "url": f"https://example.com/article-{i}", "title": title}
            )
            await repository.create(article_data)
        
        results = await repository.search_articles("AI", limit=10)
        
        assert len(results) == 1
        assert "AI Technology News" in results[0].title
    
    @pytest.mark.asyncio
    async def test_list_articles_search_ranks_title_match_above_content_only(
        self, repository, sample_article_data
    ):
        """A title match should rank ahead of a content-only match, and the
        content-only match should carry a matched_snippet excerpt."""
        content_only = ArticleCreate(
            **{
                **sample_article_data,
                "url": "https://example.com/content-only",
                "title": "Completely Unrelated Headline",
                "content": (
                    "Some long article body that happens to mention "
                    "OpenAI once in passing, buried in the middle of "
                    "otherwise unrelated text about something else entirely."
                ),
            }
        )
        title_match = ArticleCreate(
            **{
                **sample_article_data,
                "url": "https://example.com/title-match",
                "title": "OpenAI Ships New Model",
                "content": "Details about the launch.",
            }
        )
        # Create content-only match first so recency ordering alone
        # wouldn't explain a title-match-first result.
        await repository.create(content_only)
        await repository.create(title_match)

        articles, total_count, _ = await repository.list_articles(
            query_text="OpenAI"
        )

        assert total_count == 2
        assert articles[0].title == "OpenAI Ships New Model"
        assert articles[0].matched_snippet is None
        assert articles[1].title == "Completely Unrelated Headline"
        assert articles[1].matched_snippet is not None
        assert "OpenAI" in articles[1].matched_snippet

    @pytest.mark.asyncio
    async def test_list_articles_search_cursor_pagination_does_not_drop_results(
        self, repository, sample_article_data
    ):
        """Regression test: paging a search query by cursor must not
        silently drop content-only matches that are newer than the last
        title match shown on an earlier page.

        The search ORDER BY ranks title matches (tier 0) ahead of all
        content-only matches (tier 1) regardless of created_at. A keyset
        cursor that only knows about (created_at, id) has no notion of
        that tier, so once a page ends on a tier-0 row, its predicate
        wrongly excludes every row with created_at >= that row's, even
        tier-1 rows that legitimately belong later in the correctly
        ordered result set. Fixed by paging search results by plain
        offset instead of keyset cursor.
        """
        # 2 title matches + 4 content-only matches, all mentioning
        # "OpenAI" -- created in this order so title matches land among
        # the newest rows and content-only matches span both older and
        # newer than them, which is what triggers the drop.
        for i in range(2):
            await repository.create(
                ArticleCreate(
                    **{
                        **sample_article_data,
                        "url": f"https://example.com/content-{i}",
                        "title": f"Unrelated Headline {i}",
                        "content": f"Body text mentioning OpenAI in passing, item {i}.",
                    }
                )
            )
        for i in range(2):
            await repository.create(
                ArticleCreate(
                    **{
                        **sample_article_data,
                        "url": f"https://example.com/title-{i}",
                        "title": f"OpenAI Announcement {i}",
                        "content": "Launch details.",
                    }
                )
            )
        for i in range(2, 4):
            await repository.create(
                ArticleCreate(
                    **{
                        **sample_article_data,
                        "url": f"https://example.com/content-{i}",
                        "title": f"Unrelated Headline {i}",
                        "content": f"Body text mentioning OpenAI in passing, item {i}.",
                    }
                )
            )

        seen_urls: set[str] = set()
        cursor = None
        for _ in range(10):  # generous upper bound on page count
            articles, _, cursor = await repository.list_articles(
                query_text="OpenAI", limit=2, cursor=cursor
            )
            seen_urls.update(a.url for a in articles)
            if cursor is None:
                break

        assert len(seen_urls) == 6, (
            "Paging through all pages of a search query should surface "
            f"every matching article exactly once; got {len(seen_urls)}: {seen_urls}"
        )

    @pytest.mark.asyncio
    async def test_create_article_has_credibility_score(
        self, repository, sample_article_data
    ):
        """Every article should get a real per-source credibility_score
        (0-100) instead of a hardcoded/missing value."""
        article_data = ArticleCreate(**sample_article_data)

        result = await repository.create(article_data)

        assert result.credibility_score is not None
        assert 0 <= result.credibility_score <= 100

    @pytest.mark.asyncio
    async def test_credibility_score_varies_by_source(
        self, repository, sample_article_data
    ):
        """credibility_score must actually vary by source tier, not just
        fall in [0, 100] -- that range alone wouldn't catch a regression
        back to a flat hardcoded value (e.g. the old flat 85)."""
        high_tier = await repository.create(
            ArticleCreate(
                **{
                    **sample_article_data,
                    "url": "https://example.com/high-tier",
                    "source": "MIT Technology Review",
                }
            )
        )
        low_tier = await repository.create(
            ArticleCreate(
                **{
                    **sample_article_data,
                    "url": "https://example.com/low-tier",
                    "source": "Some Unranked Blog",
                }
            )
        )

        assert high_tier.credibility_score != low_tier.credibility_score
        assert high_tier.credibility_score > low_tier.credibility_score

    @pytest.mark.asyncio
    async def test_get_articles_without_embeddings(self, repository, sample_article_data):
        """Test retrieving articles without embeddings."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        results = await repository.get_articles_without_embeddings()
        
        assert len(results) == 1
        assert results[0].id == created.id
        assert results[0].embedding_generated is False
    
    @pytest.mark.asyncio
    async def test_mark_embedding_generated(self, repository, sample_article_data):
        """Test marking article as having embeddings generated."""
        article_data = ArticleCreate(**sample_article_data)
        created = await repository.create(article_data)
        
        await repository.mark_embedding_generated(created.id)
        
        # Verify embedding_generated flag is updated
        articles = await repository.get_articles_without_embeddings()
        assert len(articles) == 0  # Should be empty since embedding is marked as generated
    
    @pytest.mark.asyncio
    async def test_get_stats(self, repository, sample_article_data):
        """Test retrieving article statistics."""
        # Create some test data
        article_data = ArticleCreate(**sample_article_data)
        await repository.create(article_data)
        
        stats = await repository.get_stats()
        
        assert isinstance(stats, dict)
        assert "total_articles" in stats
        assert "articles_with_summaries" in stats
        assert "articles_with_embeddings" in stats
        assert "top_sources" in stats
        assert stats["total_articles"] >= 1
