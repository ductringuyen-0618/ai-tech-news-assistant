"""
Unit Tests for the Digest Route's Daily-Summary Cache
======================================================

Regression coverage for the cache-poisoning bug: a failed (or empty) LLM
call must NOT populate ``_DAILY_SUMMARY_CACHE`` for the day, since that
cache is keyed per-UTC-date and shared by every visitor until midnight.
"""

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.digest as digest
from src.api.routes.digest import router as digest_router
from src.repositories.article_repository import ArticleRepository
from src.models.article import ArticleCreate


async def _seed_articles(repository: ArticleRepository, count: int = 5) -> None:
    for i in range(count):
        await repository.create(
            ArticleCreate(
                title=f"Test Article {i}",
                url=f"https://example.com/article-{i}",
                content="Some tech news content, long enough to summarize.",
                summary="A short summary.",
                source="Test Source",
            )
        )


@pytest.fixture(autouse=True)
def _clear_digest_cache():
    """Every test starts and ends with an empty module-level cache."""
    digest._DAILY_SUMMARY_CACHE.clear()
    yield
    digest._DAILY_SUMMARY_CACHE.clear()


@pytest.fixture
def repository(temp_db_path):
    return ArticleRepository(db_path=temp_db_path)


@pytest.fixture
def rss_client():
    """A minimal app exposing just the digest router, for hitting /digest/rss
    over real HTTP (needed for the ``Request``/``base_url`` the endpoint
    takes)."""
    app = FastAPI()
    app.include_router(digest_router, prefix="/api")
    return TestClient(app)


@pytest.mark.asyncio
async def test_llm_failure_is_not_cached(repository, temp_db_path):
    """A failed LLM call must return the fallback but leave the cache empty
    so the next request retries the LLM instead of being stuck all day."""
    await _seed_articles(repository)

    with patch.object(digest, "_resolve_db_path", return_value=temp_db_path), \
         patch.object(digest, "SummarizationService") as mock_service_cls:
        mock_service_cls.return_value.summarize_content = AsyncMock(
            side_effect=RuntimeError("LLM unreachable")
        )

        response = await digest.get_daily_summary()

    assert "temporarily unavailable" in response["summary"]
    today = datetime.now(timezone.utc).date().isoformat()
    assert today not in digest._DAILY_SUMMARY_CACHE


@pytest.mark.asyncio
async def test_llm_success_is_cached(repository, temp_db_path):
    """A genuine successful LLM response should populate the cache so the
    LLM only runs once per day."""
    await _seed_articles(repository)

    class _FakeResult:
        summary = "A cohesive paragraph about today's tech news."

    with patch.object(digest, "_resolve_db_path", return_value=temp_db_path), \
         patch.object(digest, "SummarizationService") as mock_service_cls:
        mock_service_cls.return_value.summarize_content = AsyncMock(
            return_value=_FakeResult()
        )

        response = await digest.get_daily_summary()

    assert response["summary"] == _FakeResult.summary
    today = datetime.now(timezone.utc).date().isoformat()
    assert digest._DAILY_SUMMARY_CACHE.get(today) == response


@pytest.mark.asyncio
async def test_failure_then_success_self_heals_same_day(repository, temp_db_path):
    """Simulates the reported bug: a failure on the first request of the day
    must not poison later requests once the LLM becomes reachable again."""
    await _seed_articles(repository)

    with patch.object(digest, "_resolve_db_path", return_value=temp_db_path), \
         patch.object(digest, "SummarizationService") as mock_service_cls:
        mock_service_cls.return_value.summarize_content = AsyncMock(
            side_effect=RuntimeError("LLM unreachable")
        )
        first = await digest.get_daily_summary()

    assert "temporarily unavailable" in first["summary"]

    class _FakeResult:
        summary = "Recovered summary once the LLM is back."

    with patch.object(digest, "_resolve_db_path", return_value=temp_db_path), \
         patch.object(digest, "SummarizationService") as mock_service_cls:
        mock_service_cls.return_value.summarize_content = AsyncMock(
            return_value=_FakeResult()
        )
        second = await digest.get_daily_summary()

    assert second["summary"] == _FakeResult.summary


class TestDigestRssFeed:
    """Coverage for GET /api/digest/rss."""

    async def _seed_with_summaries(self, repository, count=3):
        """Like ``_seed_articles``, but also writes ``summary`` via
        ``mark_summary_generated`` -- ``ArticleRepository.create()`` itself
        never persists the ``summary`` column, so a plain ``_seed_articles``
        call always leaves it NULL."""
        articles = []
        for i in range(count):
            article = await repository.create(
                ArticleCreate(
                    title=f"Test Article {i}",
                    url=f"https://example.com/article-{i}",
                    content="Some tech news content, long enough to summarize.",
                    source="Test Source",
                )
            )
            await repository.mark_summary_generated(
                article.id, summary=f"Summary {i}"
            )
            articles.append(article)
        return articles

    def test_returns_valid_rss_with_one_item_per_story(
        self, repository, temp_db_path, rss_client
    ):
        asyncio.run(self._seed_with_summaries(repository, count=3))

        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            response = rss_client.get("/api/digest/rss")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/rss+xml")

        root = ET.fromstring(response.text)
        channel = root.find("channel")
        assert channel is not None
        items = channel.findall("item")
        assert len(items) == 3

        descriptions = {item.find("description").text for item in items}
        assert descriptions == {"Summary 0", "Summary 1", "Summary 2"}

        for item in items:
            title = item.find("title")
            description = item.find("description")
            pub_date = item.find("pubDate")
            guid = item.find("guid")
            assert title is not None and title.text
            assert description is not None and description.text
            assert pub_date is not None and pub_date.text
            assert guid is not None and guid.text

        # Same guid across repeated requests for the same article.
        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            second_response = rss_client.get("/api/digest/rss")
        second_guids = [
            item.find("guid").text
            for item in ET.fromstring(second_response.text).find("channel").findall("item")
        ]
        first_guids = [item.find("guid").text for item in items]
        assert second_guids == first_guids

    def test_escapes_special_characters_in_titles(
        self, repository, temp_db_path, rss_client
    ):
        async def _seed():
            article = await repository.create(
                ArticleCreate(
                    title="Rust & C++ <benchmarks> compared",
                    url="https://example.com/rust-vs-cpp",
                    content="Body",
                    source="Test Source",
                )
            )
            await repository.mark_summary_generated(
                article.id, summary="A & B < C > D"
            )

        asyncio.run(_seed())

        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            response = rss_client.get("/api/digest/rss")

        assert response.status_code == 200
        # Must still parse as well-formed XML despite raw &, <, > in content.
        root = ET.fromstring(response.text)
        item = root.find("channel").find("item")
        assert item.find("title").text == "Rust & C++ <benchmarks> compared"
        assert item.find("description").text == "A & B < C > D"

    def test_empty_db_returns_valid_empty_channel(
        self, repository, temp_db_path, rss_client
    ):
        # ``repository`` fixture creates the schema (via ArticleRepository's
        # own CREATE TABLE IF NOT EXISTS) without seeding any rows.
        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            response = rss_client.get("/api/digest/rss")

        assert response.status_code == 200
        root = ET.fromstring(response.text)
        channel = root.find("channel")
        assert channel is not None
        assert channel.findall("item") == []
        assert channel.find("title").text == "TechPulse Daily Digest"

    def test_no_headers_required(self, repository, temp_db_path, rss_client):
        """Feed reader software won't send X-Client-Id or any auth header."""
        asyncio.run(
            _seed_articles(repository, count=1)
        )

        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            response = rss_client.get("/api/digest/rss", headers={})

        assert response.status_code == 200

    def test_json_digest_shape_unchanged(self, repository, temp_db_path):
        """The underlying query gained columns for the RSS feed -- make sure
        the existing /api/digest/ response shape stays byte-for-byte the
        same for the frontend's DigestView."""
        asyncio.run(
            _seed_articles(repository, count=2)
        )

        with patch.object(digest, "_resolve_db_path", return_value=temp_db_path):
            response = asyncio.run(digest.get_daily_digest(top=2))

        assert set(response.keys()) == {
            "date",
            "topStories",
            "categoryBreakdown",
            "trendingTopics",
        }
        for story in response["topStories"]:
            assert set(story.keys()) == {
                "id",
                "title",
                "source",
                "summaryShort",
                "category",
            }
