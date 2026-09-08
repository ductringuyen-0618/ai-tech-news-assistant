"""
Unit Tests for the Digest Route's Daily-Summary Cache
======================================================

Regression coverage for the cache-poisoning bug: a failed (or empty) LLM
call must NOT populate ``_DAILY_SUMMARY_CACHE`` for the day, since that
cache is keyed per-UTC-date and shared by every visitor until midnight.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

import src.api.routes.digest as digest
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
