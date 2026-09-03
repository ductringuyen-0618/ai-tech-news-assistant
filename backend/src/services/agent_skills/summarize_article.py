"""
summarize_article agent skill
=============================

Cache-aware summarization for one article. The orchestrator dispatches
this skill (typically via the M3 ``SubagentPool``) once per article it
wants to reason about.

Cache-reuse heuristic (deliberately simple — see issue M2.M2 §"Important"):

* If the article's ``articles.summary`` column is non-null AND
  ``focus_question is None``: return ``cache_hit=True`` immediately. NO
  Ollama call.
* Otherwise: read the article body, call
  :meth:`SummarizationService.summarize_content`, write the result back to
  ``articles.summary`` (only on cache MISS), return ``cache_hit=False``.

The heuristic does NOT try to be clever about prefix-matching focus
questions — that's a v2 concern (and would need a ``summary_meta`` JSON
column the PRD explicitly defers).

Every Ollama-bound call is wrapped in a structured-log context manager
(start/end/duration/token_count) so latency regressions are visible
without reaching for a tracer. Mirrors the pattern in
:py:meth:`AgenticResearchService._ollama_call`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from src.core.config import get_settings
from src.models.article import ArticleUpdate, SummarizationRequest
from src.repositories.article_repository import ArticleRepository
from src.services.summarization_service import SummarizationService


logger = logging.getLogger(__name__)


# Module-level singletons. The repository's ``__init__`` is cheap (only a
# CREATE TABLE IF NOT EXISTS) but doing it once per agent run keeps the
# tool snappy.
_repository: Optional[ArticleRepository] = None
_summarizer: Optional[SummarizationService] = None


def _get_repository() -> ArticleRepository:
    global _repository
    if _repository is None:
        settings = get_settings()
        _repository = ArticleRepository(db_path=settings.get_database_file_path())
    return _repository


def _get_summarizer() -> SummarizationService:
    global _summarizer
    if _summarizer is None:
        _summarizer = SummarizationService()
    return _summarizer


@asynccontextmanager
async def _ollama_call(label: str, model: str):
    """Structured-log frame around an Ollama call.

    Mirrors :py:meth:`AgenticResearchService._ollama_call` so that grepping
    for ``ollama_call.start`` finds every LLM round-trip in the system,
    not just the orchestrator's. The body writes a token count into the
    yielded ``info`` dict before exit so the end-log carries it.
    """
    call_id = uuid.uuid4().hex[:8]
    info: Dict[str, Any] = {"token_count": 0}
    t0 = time.monotonic()
    logger.info(
        "ollama_call.start id=%s label=%s model=%s",
        call_id,
        label,
        model,
    )
    try:
        yield info
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "ollama_call.end id=%s label=%s status=error "
            "duration_ms=%d token_count=%d error=%s",
            call_id,
            label,
            duration_ms,
            int(info.get("token_count") or 0),
            exc,
        )
        raise
    else:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "ollama_call.end id=%s label=%s status=ok "
            "duration_ms=%d token_count=%d",
            call_id,
            label,
            duration_ms,
            int(info.get("token_count") or 0),
        )


@tool
async def summarize_article(
    article_id: int, focus_question: Optional[str] = None
) -> str:
    """Produce a concise summary of a single article, with cache reuse.

    If the article already has a stored summary AND no ``focus_question``
    was passed, returns the cached text immediately (no LLM call). When a
    ``focus_question`` is supplied, the model regenerates the summary so
    it can address the specific angle — but the regenerated text is NOT
    written back to the cache (the cache stores neutral summaries only).

    Args:
        article_id: SQLite primary key of the article in ``articles``.
        focus_question: Optional natural-language angle the summary
            should emphasise (e.g. "How does this affect open-source
            developers?"). When set, the cache is bypassed.

    Returns:
        A JSON string with shape::

            {
                "article_id": int,
                "summary": str,
                "cache_hit": bool       # True iff we reused a stored summary
            }

        On any error::

            {"article_id": int, "summary": "", "error": "...",
             "cache_hit": false}
    """
    try:
        aid = int(article_id)
    except (TypeError, ValueError):
        return json.dumps(
            {
                "article_id": article_id,
                "summary": "",
                "cache_hit": False,
                "error": f"invalid article_id: {article_id!r}",
            }
        )

    repo = _get_repository()

    # ------------------------------------------------------------------ #
    #  Cache lookup — only honoured when no focus_question is set.
    # ------------------------------------------------------------------ #
    if not focus_question:
        try:
            cached = await repo.get_summary_only(aid)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "summarize_article: cache lookup failed for id=%s: %s",
                aid,
                exc,
            )
            cached = None
        if cached:
            logger.info(
                "summarize_article: cache_hit id=%s len=%d",
                aid,
                len(cached),
            )
            return json.dumps(
                {
                    "article_id": aid,
                    "summary": cached,
                    "cache_hit": True,
                }
            )

    # ------------------------------------------------------------------ #
    #  Cache miss — fetch body and call the LLM.
    # ------------------------------------------------------------------ #
    try:
        body = await repo.get_content_only(aid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "summarize_article: failed to read article %s: %s", aid, exc
        )
        return json.dumps(
            {
                "article_id": aid,
                "summary": "",
                "cache_hit": False,
                "error": f"could not read article body: {exc}",
            }
        )

    if not body or not body.strip():
        return json.dumps(
            {
                "article_id": aid,
                "summary": "",
                "cache_hit": False,
                "error": "article has no body to summarise",
            }
        )

    # Weave the focus question into the prompt by prepending it to the
    # body. ``SummarizationService`` prompt-builds from ``request.content``
    # and we don't want to widen its API for this single skill — a header
    # the LLM reads first is enough to redirect emphasis.
    if focus_question and focus_question.strip():
        framed = (
            f"FOCUS QUESTION: {focus_question.strip()}\n"
            "Tailor the summary so it directly addresses the focus question.\n"
            "\n"
            f"{body}"
        )
    else:
        framed = body

    summarizer = _get_summarizer()
    request = SummarizationRequest(content=framed, style="concise")

    try:
        async with _ollama_call("summarize_article", summarizer.model) as info:
            result = await summarizer.summarize_content(request)
            # Record token count for the structured-log frame.
            info["token_count"] = int(getattr(result, "word_count", 0) or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "summarize_article: Ollama call failed for id=%s: %s", aid, exc
        )
        return json.dumps(
            {
                "article_id": aid,
                "summary": "",
                "cache_hit": False,
                "error": f"summarization failed: {exc}",
            }
        )

    summary_text = (getattr(result, "summary", None) or "").strip()
    if not summary_text:
        return json.dumps(
            {
                "article_id": aid,
                "summary": "",
                "cache_hit": False,
                "error": "summarizer returned empty text",
            }
        )

    # ------------------------------------------------------------------ #
    #  Write-back: ONLY on a cache miss with no focus_question (the cache
    #  stores neutral summaries; focus-question variants are ephemeral).
    # ------------------------------------------------------------------ #
    if not focus_question:
        try:
            await repo.update(
                aid, ArticleUpdate(summary=summary_text)
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: a write-back failure should not fail the tool —
            # the LLM still gets its answer, the next call just re-pays
            # the Ollama cost. Log loudly.
            logger.warning(
                "summarize_article: write-back failed for id=%s: %s",
                aid,
                exc,
            )

    return json.dumps(
        {
            "article_id": aid,
            "summary": summary_text,
            "cache_hit": False,
        }
    )
