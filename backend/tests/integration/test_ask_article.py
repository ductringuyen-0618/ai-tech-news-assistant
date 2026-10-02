"""
Integration tests for the "Ask about this article" endpoint (proposal 004)
============================================================================

Covers the validation contract from
``docs/missions/coo/proposals/004-ask-this-article.md``:

1. ``test_ask_success`` -- a valid article id + question returns 200 with
   ``{"answer": str}``, and the prompt sent to
   ``SummarizationService._call_llm`` is built strictly from that article's
   own title/summary/source (never fetching or referencing another
   article).
2. ``test_ask_unknown_article_returns_404`` -- an unknown article id
   returns 404, not a 500.
3. ``test_ask_and_research_do_not_block_each_other`` -- concurrent
   ``POST /api/news/{id}/ask`` and ``POST /api/research`` calls never 429
   or block each other because of the other route's lock -- this endpoint
   never touches ``research.py``'s process-wide in-flight gate.

The LLM is fully mocked (``SummarizationService._call_llm`` is patched via a
dependency override) in every test -- no real network/LLM call is made.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import news as news_route
from src.api.routes import research as research_route
from src.models.article import Article
from src.repositories.article_repository import ArticleRepository
from src.services.summarization_service import SummarizationService


# ---------------------------------------------------------------------- #
#  Helpers
# ---------------------------------------------------------------------- #


def _make_article(article_id: int = 1) -> Article:
    return Article(
        id=article_id,
        title="Widgets Inc announces new gadget",
        content="Widgets Inc unveiled a new gadget today at its annual event.",
        summary="Widgets Inc launched a new gadget with a longer battery life.",
        source="widgetnews.example",
        url="https://widgetnews.example/gadget",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        view_count=0,
        embedding_generated=False,
    )


@pytest.fixture(autouse=True)
def _reset_ask_state():
    """Reset the module-level cache/rate-limit state before/after every test
    so tests don't leak into each other (a cache hit or a spent rate-limit
    bucket from one test must not affect the next)."""
    news_route._ask_cache.clear()
    news_route._ask_rate_limit_buckets.clear()
    yield
    news_route._ask_cache.clear()
    news_route._ask_rate_limit_buckets.clear()


@pytest.fixture(autouse=True)
def _reset_research_inflight_gate():
    """Reset research.py's single-in-flight gate before/after every test."""
    research_route._in_flight = False
    yield
    research_route._in_flight = False


def _build_news_app(article_repo, summarizer) -> FastAPI:
    """Standalone app mounting just the news router, same pattern as
    ``test_news_api.py``."""
    app = FastAPI()
    app.include_router(news_route.router)
    app.dependency_overrides[news_route.get_article_repository] = lambda: article_repo
    app.dependency_overrides[news_route.get_summarization_service] = lambda: summarizer
    return app


class _StubResearchAgent:
    """A minimal fake ``AgenticResearchService`` -- yields one "done" event
    after a short delay so the concurrency test has a real window during
    which the research route's in-flight gate is actually held."""

    def __init__(self, delay: float = 0.05):
        self._delay = delay

    async def run(self, question: str) -> AsyncGenerator[Dict[str, Any], None]:
        import asyncio

        await asyncio.sleep(self._delay)
        yield {"type": "phase", "data": "done", "report": "ok\n[1] s\n"}


# ---------------------------------------------------------------------- #
#  Tests
# ---------------------------------------------------------------------- #


class TestAskAboutArticle:
    def test_ask_success(self, sample_article_data):
        article = _make_article(1)

        article_repo = AsyncMock(spec=ArticleRepository)
        article_repo.get_by_id.return_value = article

        summarizer = AsyncMock(spec=SummarizationService)
        summarizer._call_llm.return_value = ("It launched with a longer battery life.", 8)

        app = _build_news_app(article_repo, summarizer)
        client = TestClient(app)

        response = client.post(
            "/news/1/ask",
            json={"question": "What did Widgets Inc launch?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {"answer": "It launched with a longer battery life."}

        # The prompt sent to _call_llm must be built from this article's
        # own content only -- never fetching or referencing another article.
        article_repo.get_by_id.assert_awaited_once_with(1)
        summarizer._call_llm.assert_awaited_once()
        prompt_arg = summarizer._call_llm.await_args.args[0]
        assert article.title in prompt_arg
        assert article.summary in prompt_arg
        assert article.source in prompt_arg
        assert "What did Widgets Inc launch?" in prompt_arg

    def test_ask_unknown_article_returns_404(self):
        from src.core.exceptions import NotFoundError

        article_repo = AsyncMock(spec=ArticleRepository)
        article_repo.get_by_id.side_effect = NotFoundError("Article not found")

        summarizer = AsyncMock(spec=SummarizationService)

        app = _build_news_app(article_repo, summarizer)
        client = TestClient(app)

        response = client.post("/news/999/ask", json={"question": "anything?"})

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        summarizer._call_llm.assert_not_awaited()

    def test_ask_repeats_question_hits_cache_not_llm_again(self):
        """Same (article_id, normalized question) should only call the LLM
        once -- the second call is served from the in-memory cache."""
        article = _make_article(1)
        article_repo = AsyncMock(spec=ArticleRepository)
        article_repo.get_by_id.return_value = article

        summarizer = AsyncMock(spec=SummarizationService)
        summarizer._call_llm.return_value = ("Cached answer.", 2)

        app = _build_news_app(article_repo, summarizer)
        client = TestClient(app)

        r1 = client.post("/news/1/ask", json={"question": "  What Happened?  "})
        r2 = client.post("/news/1/ask", json={"question": "what happened?"})

        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json() == {"answer": "Cached answer."}
        summarizer._call_llm.assert_awaited_once()

    def test_ask_and_research_do_not_block_each_other(self):
        """A burst of concurrent /api/news/{id}/ask calls must never touch
        or be blocked by /api/research's in-flight lock, and vice versa."""
        article = _make_article(1)
        article_repo = AsyncMock(spec=ArticleRepository)
        article_repo.get_by_id.return_value = article

        summarizer = AsyncMock(spec=SummarizationService)
        summarizer._call_llm.return_value = ("An answer.", 3)

        app = FastAPI()
        app.include_router(news_route.router, prefix="/api")
        app.include_router(research_route.router, prefix="/api")
        app.dependency_overrides[news_route.get_article_repository] = lambda: article_repo
        app.dependency_overrides[news_route.get_summarization_service] = lambda: summarizer

        stub_agent = _StubResearchAgent(delay=0.1)
        original_build_service = research_route._build_service
        research_route._build_service = lambda: stub_agent
        try:
            client = TestClient(app)

            results: Dict[str, Any] = {}

            def _do_research():
                results["research"] = client.post(
                    "/api/research", json={"question": "what's new?"}
                )

            def _do_ask():
                results["ask"] = client.post(
                    "/api/news/1/ask", json={"question": "what happened?"}
                )

            t_research = threading.Thread(target=_do_research)
            t_ask = threading.Thread(target=_do_ask)

            # Start research first so its in-flight gate is actually held
            # while the ask request races in behind it.
            t_research.start()
            time.sleep(0.02)
            t_ask.start()

            t_research.join(timeout=5)
            t_ask.join(timeout=5)

            assert "research" in results and "ask" in results
            assert results["ask"].status_code == 200, results["ask"].text
            assert results["ask"].json() == {"answer": "An answer."}
            assert results["research"].status_code == 200, results["research"].text
        finally:
            research_route._build_service = original_build_service

    def test_ask_rate_limit_returns_429_after_threshold(self):
        """More than the per-client threshold within the window trips the
        rate limit, which the app's registered exception handler turns
        into a 429 -- verified directly against the helper since this
        standalone test app doesn't register the production exception
        handlers."""
        from src.core.exceptions import RateLimitError

        for _ in range(news_route._ASK_RATE_LIMIT_MAX_REQUESTS):
            news_route._enforce_ask_rate_limit("client-a")

        with pytest.raises(RateLimitError):
            news_route._enforce_ask_rate_limit("client-a")

        # A different client key is unaffected.
        news_route._enforce_ask_rate_limit("client-b")
