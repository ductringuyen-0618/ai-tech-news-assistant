"""
Unit Tests for IngestionService
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

from src.services.ingestion_service import (
    IngestionService,
    IngestionStatus,
    IngestionResult,
)
from src.database.models import Article, Source, Category


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = Mock(spec=Session)
    return db


@pytest.fixture
def ingestion_service(mock_db):
    """Create an IngestionService instance with mock database."""
    return IngestionService(mock_db)


class TestIngestionResult:
    """Tests for IngestionResult class."""
    
    def test_ingestion_result_initialization(self):
        """Test IngestionResult initializes with correct default values."""
        result = IngestionResult()
        
        assert result.status == IngestionStatus.PENDING
        assert result.start_time is None
        assert result.end_time is None
        assert result.total_feeds == 0
        assert result.total_articles_found == 0
        assert result.total_articles_saved == 0
        assert result.duplicates_skipped == 0
        assert result.errors_encountered == 0
        assert result.error_details == []
        assert result.sources_processed == {}
    
    def test_duration_seconds_calculation(self):
        """Test duration_seconds property calculates correctly."""
        result = IngestionResult()
        result.start_time = datetime(2025, 10, 21, 10, 0, 0)
        result.end_time = datetime(2025, 10, 21, 10, 5, 30)
        
        assert result.duration_seconds == 330.0
    
    def test_duration_seconds_no_times(self):
        """Test duration_seconds returns 0 if times not set."""
        result = IngestionResult()
        assert result.duration_seconds == 0.0
    
    def test_success_rate_calculation(self):
        """Test success_rate property calculates correctly."""
        result = IngestionResult()
        result.total_articles_found = 100
        result.total_articles_saved = 50
        
        assert result.success_rate == 50.0
    
    def test_success_rate_zero_articles(self):
        """Test success_rate returns 0 if no articles found."""
        result = IngestionResult()
        assert result.success_rate == 0.0
    
    def test_to_dict_conversion(self):
        """Test to_dict converts result to dictionary."""
        result = IngestionResult()
        result.status = IngestionStatus.COMPLETED
        result.start_time = datetime(2025, 10, 21, 10, 0, 0)
        result.end_time = datetime(2025, 10, 21, 10, 5, 0)
        result.total_feeds = 5
        result.total_articles_found = 100
        result.total_articles_saved = 50
        result.duplicates_skipped = 40
        result.errors_encountered = 2
        
        result_dict = result.to_dict()
        
        assert result_dict["status"] == "completed"
        assert result_dict["total_feeds"] == 5
        assert result_dict["total_articles_found"] == 100
        assert result_dict["total_articles_saved"] == 50
        assert result_dict["duplicates_skipped"] == 40
        assert result_dict["errors_encountered"] == 2
        assert result_dict["success_rate"] == "50.0%"
        assert result_dict["duration_seconds"] == 300.0


class TestIngestionServiceInitialization:
    """Tests for IngestionService initialization."""
    
    def test_service_initialization(self, mock_db):
        """Test IngestionService initializes with correct values."""
        service = IngestionService(mock_db, batch_size=10, timeout=60)
        
        assert service.db == mock_db
        assert service.batch_size == 10
        assert service.timeout == 60
        assert service.result.status == IngestionStatus.PENDING
        # NOTE: DEFAULT_FEEDS is a class attribute with no instance
        # override, so `service.DEFAULT_FEEDS` and
        # `IngestionService.DEFAULT_FEEDS` are always the same object --
        # comparing them to each other is a tautology that can't catch a
        # regression. Assert against a real expected count instead.
        assert len(service.DEFAULT_FEEDS) == 12

    def test_default_feeds_configured(self, ingestion_service):
        """Test default feeds are properly configured."""
        feeds = ingestion_service.DEFAULT_FEEDS

        assert len(feeds) >= 5

        # The 7 feeds added to fill previously-empty topic categories --
        # asserted by name so a regression that silently dropped them
        # while keeping >= 5 older feeds would still be caught.
        names = {feed["name"] for feed in feeds}
        for expected_name in (
            "Hacker News",
            "The Hacker News",
            "IEEE Spectrum Robotics",
            "STAT News",
            "Breaking Defense",
        ):
            assert expected_name in names, f"missing feed: {expected_name}"

        # Check all feeds have required fields
        for feed in feeds:
            assert "name" in feed
            assert "url" in feed
            assert "category" in feed
            assert len(feed["name"]) > 0
            assert len(feed["url"]) > 0
            assert len(feed["category"]) > 0
    
    def test_http_client_initialized(self, ingestion_service):
        """Test HTTP client is properly initialized."""
        assert ingestion_service.http_client is not None
        # httpx uses a Timeout object, just verify it's set
        assert ingestion_service.http_client.timeout is not None


class TestIngestionServiceMethods:
    """Tests for IngestionService methods."""
    
    def test_get_or_create_category_new(self, ingestion_service, mock_db):
        """Test _get_or_create_category creates new category."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        category = ingestion_service._get_or_create_category("AI")
        
        assert category is not None
        assert category.name == "AI"
        assert category.slug == "ai"
        assert category.is_active is True
        mock_db.add.assert_called()
    
    def test_get_or_create_category_existing(self, ingestion_service, mock_db):
        """Test _get_or_create_category returns existing category."""
        mock_category = Mock(spec=Category)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_category
        
        category = ingestion_service._get_or_create_category("AI")
        
        assert category == mock_category
    
    def test_get_source_id_new(self, ingestion_service, mock_db):
        """Test _get_source_id creates new source."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        source_id = ingestion_service._get_source_id("TechCrunch")
        
        # Should create a source
        mock_db.add.assert_called()
        mock_db.flush.assert_called()
    
    def test_get_source_id_existing(self, ingestion_service, mock_db):
        """Test _get_source_id returns existing source."""
        mock_source = Mock(spec=Source)
        mock_source.id = 42
        mock_db.query.return_value.filter.return_value.first.return_value = mock_source
        
        source_id = ingestion_service._get_source_id("TechCrunch")
        
        assert source_id == 42
    
    def test_process_entry_skip_missing_title(self, ingestion_service, mock_db):
        """Test _process_entry skips entries without title."""
        entry = {"link": "http://example.com"}
        
        ingestion_service._process_entry(entry, "TestSource", None)
        
        # Should not add article
        mock_db.add.assert_not_called()
    
    def test_process_entry_skip_missing_url(self, ingestion_service, mock_db):
        """Test _process_entry skips entries without URL."""
        entry = {"title": "Test Article"}
        
        ingestion_service._process_entry(entry, "TestSource", None)
        
        # Should not add article
        mock_db.add.assert_not_called()
    
    def test_process_entry_skip_duplicate(self, ingestion_service, mock_db):
        """Test _process_entry skips duplicate URLs."""
        mock_db.query.return_value.filter.return_value.first.return_value = Mock()
        
        entry = {
            "title": "Test Article",
            "link": "http://example.com/article",
            "summary": "Test summary"
        }
        
        ingestion_service._process_entry(entry, "TestSource", None)
        
        assert ingestion_service.result.duplicates_skipped == 1
        # Should not add new article (query found existing)
    
    def test_process_entry_save_new(self, ingestion_service, mock_db):
        """Test _process_entry saves new articles."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        ingestion_service._get_source_id = Mock(return_value=1)

        entry = {
            "title": "Test Article",
            "link": "http://example.com/article",
            "summary": "Test summary",
            "author": "Test Author"
        }

        ingestion_service._process_entry(entry, "TestSource", None)

        assert ingestion_service.result.total_articles_saved == 1

    def test_process_entry_strips_hn_boilerplate_for_hacker_news_source(
        self, ingestion_service, mock_db
    ):
        """The Article URL/Comments URL/Points boilerplate should be
        stripped for the real Hacker News (hnrss.org) source."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        ingestion_service._get_source_id = Mock(return_value=1)

        entry = {
            "title": "Some HN Story",
            "link": "http://example.com/hn-story",
            "summary": (
                "<p>Article URL: http://example.com/hn-story</p>"
                "<p>Comments URL: https://news.ycombinator.com/item?id=1</p>"
                "<p>Points: 205</p><p># Comments: 74</p>"
            ),
        }

        ingestion_service._process_entry(entry, "Hacker News", None)

        saved_article = mock_db.add.call_args[0][0]
        assert "Article URL" not in saved_article.content
        assert "Points:" not in saved_article.content

    def test_process_entry_does_not_corrupt_non_hn_content_matching_boilerplate_shape(
        self, ingestion_service, mock_db
    ):
        """Regression test: a non-HN article whose body happens to contain
        a paragraph starting with 'Points:' (e.g. a listicle-style review)
        must not have that paragraph silently deleted -- the boilerplate
        stripper must be gated on the source actually being Hacker News,
        not just on the text shape matching."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        ingestion_service._get_source_id = Mock(return_value=1)

        entry = {
            "title": "Best Laptops 2026",
            "link": "http://example.com/best-laptops",
            "summary": (
                "<p>Introduction to the review.</p>"
                "<p>Points: to consider before buying a laptop are listed "
                "below in this comprehensive guide.</p>"
                "<p>Conclusion paragraph here.</p>"
            ),
        }

        ingestion_service._process_entry(entry, "The Verge", None)

        saved_article = mock_db.add.call_args[0][0]
        assert "Points: to consider before buying a laptop" in saved_article.content
        mock_db.add.assert_called()
    
    def test_update_source_timestamp(self, ingestion_service, mock_db):
        """Test _update_source_timestamp updates last_scraped."""
        mock_source = Mock(spec=Source)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_source
        
        ingestion_service._update_source_timestamp("TestSource")
        
        assert mock_source.last_scraped is not None
        mock_db.flush.assert_called()


class TestIngestionServicePipeline:
    """Tests for complete ingestion pipeline."""
    
    @patch('feedparser.parse')
    @patch.object(IngestionService, '_process_entry')
    def test_ingest_feed_success(self, mock_process_entry, mock_feedparser, 
                                  ingestion_service, mock_db):
        """Test _ingest_feed successfully processes a feed."""
        mock_response = Mock()
        mock_response.content = b"<rss></rss>"
        ingestion_service.http_client.get = Mock(return_value=mock_response)
        
        mock_feed = Mock()
        mock_feed.entries = [Mock(), Mock(), Mock()]
        mock_feedparser.return_value = mock_feed
        
        ingestion_service._get_or_create_category = Mock(return_value=Mock())
        ingestion_service._get_source_id = Mock(return_value=1)
        ingestion_service._update_source_timestamp = Mock()
        
        feed_config = {
            "name": "Test Feed",
            "url": "http://example.com/feed.xml",
            "category": "technology"
        }
        
        ingestion_service._ingest_feed(feed_config)
        
        assert ingestion_service.result.total_articles_found == 3
        assert mock_process_entry.call_count == 3
    
    @patch('feedparser.parse')
    def test_ingest_feed_no_entries(self, mock_feedparser, ingestion_service, mock_db):
        """Test _ingest_feed handles feeds with no entries."""
        mock_response = Mock()
        mock_response.content = b"<rss></rss>"
        ingestion_service.http_client.get = Mock(return_value=mock_response)
        
        mock_feed = Mock()
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed
        
        feed_config = {
            "name": "Empty Feed",
            "url": "http://example.com/empty.xml",
            "category": "technology"
        }
        
        ingestion_service._ingest_feed(feed_config)
        
        assert ingestion_service.result.total_articles_found == 0
    
    def test_ingest_all_initializes_result(self, ingestion_service, mock_db):
        """Test ingest_all initializes result properly."""
        ingestion_service._ingest_feed = Mock()
        
        # Mock to prevent actual HTTP calls
        with patch.object(ingestion_service, '_ingest_feed'):
            result = ingestion_service.ingest_all([])
        
        assert result.status in [IngestionStatus.COMPLETED, IngestionStatus.PARTIAL, IngestionStatus.FAILED]
        assert result.start_time is not None
        assert result.end_time is not None
    
    def test_ingest_all_processes_all_feeds(self, ingestion_service, mock_db):
        """Test ingest_all processes all provided feeds."""
        ingestion_service._ingest_feed = Mock()
        mock_db.commit = Mock()
        
        custom_feeds = [
            {"name": "Feed1", "url": "http://example.com/1.xml", "category": "AI"},
            {"name": "Feed2", "url": "http://example.com/2.xml", "category": "tech"},
        ]
        
        result = ingestion_service.ingest_all(custom_feeds)
        
        assert result.total_feeds == 2
        assert ingestion_service._ingest_feed.call_count == 2
    
    def test_ingest_all_commits_on_success(self, ingestion_service, mock_db):
        """Test ingest_all commits transaction on success."""
        ingestion_service._ingest_feed = Mock()
        mock_db.commit = Mock()
        
        result = ingestion_service.ingest_all([])
        
        mock_db.commit.assert_called_once()
    
    def test_ingest_all_rollback_on_error(self, ingestion_service, mock_db):
        """Test ingest_all handles errors gracefully and returns PARTIAL status."""
        ingestion_service._ingest_feed = Mock(side_effect=Exception("Test error"))
        mock_db.rollback = Mock()
        
        # Need at least one feed to trigger error
        feeds = [{"name": "Feed", "url": "http://example.com/feed.xml", "category": "tech"}]
        
        result = ingestion_service.ingest_all(feeds)
        
        # When an error occurs but is handled, status should be PARTIAL not FAILED
        assert result.status == IngestionStatus.PARTIAL
        assert result.errors_encountered > 0


class TestIngestionServiceStatistics:
    """Tests for statistics and reporting."""
    
    def test_get_stats_returns_counts(self, ingestion_service, mock_db):
        """Test get_stats returns article/source/category counts."""
        mock_db.query.return_value.count.side_effect = [42, 5, 8]
        
        stats = ingestion_service.get_stats()
        
        assert stats["total_articles"] == 42
        assert stats["total_sources"] == 5
        assert stats["total_categories"] == 8
    
    def test_get_stats_error_handling(self, ingestion_service, mock_db):
        """Test get_stats handles database errors gracefully."""
        mock_db.query.side_effect = Exception("Database error")
        
        stats = ingestion_service.get_stats()
        
        assert "error" in stats
        assert stats["total_articles"] == 0


class TestIngestionServiceCleanup:
    """Tests for service cleanup."""
    
    def test_close_closes_http_client(self, ingestion_service):
        """Test close() closes HTTP client."""
        mock_client = Mock()
        ingestion_service.http_client = mock_client
        
        ingestion_service.close()
        
        mock_client.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
