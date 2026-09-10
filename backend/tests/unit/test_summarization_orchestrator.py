"""
Unit tests for SummarizationOrchestrator (M2.M6)
================================================

Cover the feature-flag fork added in Milestone 6:

* When ``settings.use_agent_skill_summarization == True`` (default),
  the orchestrator dispatches the shared ``agent_skills.summarize_article``
  skill. The skill handles cache + write-back; the orchestrator only
  flips ``summary_generated``.
* When the flag is False, the legacy
  ``SummarizationService.summarize_content`` direct-call path runs.

Both branches share the entity-extraction post-hook, the
short-article skip path, and the never-raises contract.

The skill is mocked at module level: we replace
``summarization_orchestrator._summarize_one_via_skill`` indirectly by
patching the import target ``src.services.agent_skills.summarize_article``.
The legacy branch is exercised with a stub ``SummarizationService``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.summarization_orchestrator import (
    SummarizationOrchestrator,
)


# ---------------------------------------------------------------------- #
#  Test doubles
# ---------------------------------------------------------------------- #


@dataclass
class _FakeArticle:
    id: int
    title: str
    content: str
    summary: Optional[str] = None


class _FakeRepo:
    """Just enough of ArticleRepository for the orchestrator's call sites."""

    def __init__(self, articles: List[_FakeArticle], db_path: str = ":memory:"):
        self._articles = articles
        self.db_path = db_path
        self.marked: List[tuple] = []

    async def get_articles_without_summary(self, limit: int = 50):
        return list(self._articles)

    async def mark_summary_generated(self, article_id, summary=None):
        self.marked.append((article_id, summary))
        return True


class _FakeSummarizationService:
    """Stub that yields a deterministic summary."""

    model = "llama3.2"

    def __init__(self, summary_text: str = "FAKE_LEGACY_SUMMARY"):
        self._summary_text = summary_text
        self.calls: List[Any] = []

    async def summarize_content(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            summary=self._summary_text,
            original_length=len(getattr(request, "content", "") or ""),
            summary_length=len(self._summary_text),
            processing_time=0.01,
            word_count=10,
        )


class _FakeEntityService:
    """Stub entity extractor; records calls."""

    def __init__(self):
        self.calls: List[int] = []

    async def process_article(self, article_id: int) -> int:
        self.calls.append(article_id)
        return 0


def _build_orchestrator(
    articles: List[_FakeArticle],
    *,
    service: Optional[_FakeSummarizationService] = None,
    entity_service: Optional[_FakeEntityService] = None,
) -> tuple[SummarizationOrchestrator, _FakeRepo, _FakeSummarizationService, _FakeEntityService]:
    repo = _FakeRepo(articles)
    svc = service or _FakeSummarizationService()
    ent = entity_service or _FakeEntityService()
    orch = SummarizationOrchestrator(
        repository=repo,
        service=svc,
        entity_service=ent,
        extract_entities=True,
        concurrency=1,  # deterministic ordering for assertions
    )
    return orch, repo, svc, ent


# ---------------------------------------------------------------------- #
#  Tests — feature flag ON (skill path, the default after M6)
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_skill_path_invokes_summarize_article_skill(monkeypatch):
    """Flag=True: the orchestrator must dispatch the skill via ainvoke().

    The skill itself handles writeback to ``articles.summary``; the
    orchestrator only flips ``summary_generated``. Verify the skill is
    invoked with the correct kwargs and the legacy service is NOT.
    """
    article = _FakeArticle(
        id=42,
        title="Bumble announces removing the swipe",
        content="A" * 500,  # well over MIN_CONTENT_FOR_SUMMARY (200)
    )
    orch, repo, svc, ent = _build_orchestrator([article])

    # Force the flag ON regardless of env.
    from src.core import config as _config

    monkeypatch.setattr(
        _config.get_settings(), "use_agent_skill_summarization", True
    )

    # Mock the skill — the orchestrator imports it lazily inside the
    # method, so we patch the attribute on the module that defines it.
    skill_payload = json.dumps(
        {
            "article_id": 42,
            "summary": "Bumble removed the swipe.",
            "cache_hit": False,
        }
    )
    fake_ainvoke = AsyncMock(return_value=skill_payload)

    fake_skill = MagicMock()
    fake_skill.ainvoke = fake_ainvoke

    with patch(
        "src.services.agent_skills.summarize_article.summarize_article",
        fake_skill,
    ):
        result = await orch.run_pending(limit=10)

    # Skill was called with the right args.
    fake_ainvoke.assert_awaited_once()
    call_kwargs = fake_ainvoke.await_args.args[0]
    assert call_kwargs == {"article_id": 42, "focus_question": None}

    # Legacy service was NOT called.
    assert svc.calls == [], "legacy SummarizationService should be untouched"

    # The orchestrator flipped summary_generated WITHOUT re-writing summary
    # (the skill already wrote it). So marked is called with summary=None.
    assert repo.marked == [(42, None)]

    # Entity extraction post-hook fired.
    assert ent.calls == [42]

    # Result accounting.
    assert result.summarized == 1
    assert result.failed == 0


@pytest.mark.asyncio
async def test_skill_path_handles_skill_error_payload(monkeypatch):
    """Flag=True: skill returns ``{"error": ...}`` -> orchestrator records
    a failure and does NOT mark summary_generated.
    """
    article = _FakeArticle(id=99, title="x", content="A" * 500)
    orch, repo, svc, ent = _build_orchestrator([article])

    from src.core import config as _config

    monkeypatch.setattr(
        _config.get_settings(), "use_agent_skill_summarization", True
    )

    error_payload = json.dumps(
        {"article_id": 99, "summary": "", "cache_hit": False, "error": "boom"}
    )
    fake_ainvoke = AsyncMock(return_value=error_payload)

    fake_skill = MagicMock()
    fake_skill.ainvoke = fake_ainvoke

    with patch(
        "src.services.agent_skills.summarize_article.summarize_article",
        fake_skill,
    ):
        result = await orch.run_pending(limit=10)

    assert result.summarized == 0
    assert result.failed == 1
    assert repo.marked == []  # never marked as processed on hard fail
    assert ent.calls == []  # post-hook skipped on failure


# ---------------------------------------------------------------------- #
#  Tests — feature flag OFF (legacy path, rollback hatch)
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_legacy_path_calls_summarization_service(monkeypatch):
    """Flag=False: the orchestrator must call SummarizationService.summarize_content,
    write the summary back via ``mark_summary_generated`` with the
    summary text, and skip the skill entirely.
    """
    article = _FakeArticle(id=7, title="Legacy article", content="B" * 500)
    orch, repo, svc, ent = _build_orchestrator([article])

    from src.core import config as _config

    monkeypatch.setattr(
        _config.get_settings(), "use_agent_skill_summarization", False
    )

    # Patch the skill so we can assert it was NOT called.
    fake_ainvoke = AsyncMock(return_value="{}")
    fake_skill = MagicMock()
    fake_skill.ainvoke = fake_ainvoke

    with patch(
        "src.services.agent_skills.summarize_article.summarize_article",
        fake_skill,
    ):
        result = await orch.run_pending(limit=10)

    # Legacy service was called exactly once.
    assert len(svc.calls) == 1

    # Skill was NOT called.
    fake_ainvoke.assert_not_awaited()

    # Summary writeback happened via the legacy mark_summary_generated
    # path — note summary text IS passed in this branch.
    assert repo.marked == [(7, "FAKE_LEGACY_SUMMARY")]

    # Post-hook fired.
    assert ent.calls == [7]
    assert result.summarized == 1


# ---------------------------------------------------------------------- #
#  Tests — shared behaviour (independent of the flag)
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_short_articles_are_skipped_in_skill_path(monkeypatch):
    """Articles below MIN_CONTENT_FOR_SUMMARY (200 chars) must be marked
    processed without dispatching the skill.
    """
    article = _FakeArticle(id=1, title="tiny", content="too short")
    orch, repo, svc, ent = _build_orchestrator([article])

    from src.core import config as _config

    monkeypatch.setattr(
        _config.get_settings(), "use_agent_skill_summarization", True
    )

    fake_ainvoke = AsyncMock()
    fake_skill = MagicMock()
    fake_skill.ainvoke = fake_ainvoke

    with patch(
        "src.services.agent_skills.summarize_article.summarize_article",
        fake_skill,
    ):
        result = await orch.run_pending(limit=10)

    fake_ainvoke.assert_not_awaited()
    # Marked as processed with summary=None (the short-skip behavior).
    assert repo.marked == [(1, None)]
    assert result.skipped_short == 1
    assert result.summarized == 0


@pytest.mark.asyncio
async def test_empty_queue_returns_zeroed_result(monkeypatch):
    orch, repo, svc, ent = _build_orchestrator([])
    from src.core import config as _config

    monkeypatch.setattr(
        _config.get_settings(), "use_agent_skill_summarization", True
    )
    result = await orch.run_pending(limit=10)
    assert result.requested == 0
    assert result.summarized == 0
    assert repo.marked == []
