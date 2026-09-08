"""
Summarization Orchestrator
==========================

Bridges the ingestion pipeline and the SummarizationService.

The ingestion side stores raw articles in SQLite without AI summaries; this
orchestrator finds articles flagged "needs summary" (either `summary IS NULL`
or `summary_generated = FALSE`), runs them through `SummarizationService` one
batch at a time, and writes the result back via `ArticleRepository`.

It is used in two places:

1. As a **post-ingest hook**: the /api/ingest route schedules
   `run_pending(...)` as a FastAPI BackgroundTask after a successful ingest.
2. As a **backfill CLI**: `scripts/backfill_summaries.py` calls `run_pending`
   directly to summarise the existing articles already in the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from ..core.exceptions import LLMError, ValidationError
from ..models.article import SummarizationRequest
from ..repositories.article_repository import ArticleRepository
from .entity_extraction_service import EntityExtractionService
from .summarization_service import SummarizationService

logger = logging.getLogger(__name__)


# Articles shorter than this won't get a summary - the original is already
# short enough to read directly.
MIN_CONTENT_FOR_SUMMARY = 200


@dataclass
class SummarizationRunResult:
    """Outcome of a single orchestration run."""

    requested: int = 0
    summarized: int = 0
    skipped_short: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "requested": self.requested,
            "summarized": self.summarized,
            "skipped_short": self.skipped_short,
            "failed": self.failed,
            "errors": self.errors[:10],  # cap noise
        }


class SummarizationOrchestrator:
    """
    Drive `SummarizationService` over a queue of unsummarized articles.

    Construction is cheap (no I/O); call `run_pending()` to do the work.
    """

    def __init__(
        self,
        repository: Optional[ArticleRepository] = None,
        service: Optional[SummarizationService] = None,
        db_path: Optional[str] = None,
        max_summary_length: int = 200,
        concurrency: int = 2,
        entity_service: Optional[EntityExtractionService] = None,
        extract_entities: bool = True,
    ):
        """
        Args:
            repository: Article repo to read/write from. If omitted, one is
                constructed using `db_path` (or the configured default).
            service: Summarization service. If omitted, a fresh one is built
                from settings (Ollama by default).
            db_path: Optional override for the repo's SQLite path. Only used
                when `repository` is None.
            max_summary_length: Target summary length in words.
            concurrency: How many articles to summarize in parallel. Keep this
                low (1-3) for local Ollama on CPU; higher values mostly just
                cause the model to thrash.
        """
        if repository is None:
            from ..core.config import get_settings

            settings = get_settings()
            path = db_path or settings.get_database_file_path()
            repository = ArticleRepository(path)

        self.repo = repository
        self.service = service or SummarizationService()
        self.max_summary_length = max_summary_length
        self.concurrency = max(1, concurrency)

        # Entity extraction is best-effort. If construction fails (e.g.
        # the DB path is in a weird place during tests), log and skip.
        self.extract_entities = extract_entities
        self.entity_service: Optional[EntityExtractionService] = entity_service
        if self.extract_entities and self.entity_service is None:
            try:
                self.entity_service = EntityExtractionService(
                    db_path=getattr(self.repo, "db_path", None)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not initialise EntityExtractionService: %s "
                    "(entity extraction disabled for this run)",
                    exc,
                )
                self.extract_entities = False
                self.entity_service = None

    # ------------------------------------------------------------------ #
    #  Public entry point
    # ------------------------------------------------------------------ #

    async def run_pending(self, limit: int = 50) -> SummarizationRunResult:
        """
        Find articles needing summaries and process them.

        Args:
            limit: Maximum number of articles to process in this run. The
                ingest hook uses a small value (e.g. 20); the backfill script
                may pass a larger number.

        Returns:
            SummarizationRunResult describing what happened.
        """
        result = SummarizationRunResult()
        articles = await self.repo.get_articles_without_summary(limit=limit)
        result.requested = len(articles)

        if not articles:
            logger.info("No articles pending summarization")
            return result

        logger.info(
            "Summarizing %d article(s) with model=%s",
            len(articles),
            self.service.model,
        )

        # Process with a small worker pool so we don't fan out to N tasks
        # against a single Ollama instance.
        sem = asyncio.Semaphore(self.concurrency)

        async def _worker(article) -> None:
            async with sem:
                await self._summarize_one(article, result)

        await asyncio.gather(*(_worker(a) for a in articles))

        logger.info("Summarization run complete: %s", result.to_dict())
        return result

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #

    async def _summarize_one(self, article, result: SummarizationRunResult) -> None:
        """Summarize one article and persist the result. Never raises.

        Behaviour switches on ``settings.use_agent_skill_summarization``
        (Mission 2, Milestone 6):

        * **True (default)** — dispatch the shared
          ``agent_skills.summarize_article`` skill. The skill performs the
          cache lookup, runs the LLM on miss, AND writes the result back
          to ``articles.summary``. The orchestrator's remaining job is to
          flip ``summary_generated = TRUE`` and run the entity-extraction
          post-hook.
        * **False** — legacy direct-call path through
          :class:`SummarizationService`. Kept verbatim as an emergency
          rollback; queued for deletion in the post-M6 cleanup PR.
        """
        article_id = getattr(article, "id", None)
        title = (getattr(article, "title", "") or "")[:80]

        # Pick the best text to summarize. Some sources only fill `summary`
        # (the RSS description); fall back to that if `content` is empty.
        text = getattr(article, "content", None) or getattr(
            article, "summary", None
        ) or ""

        if not text or len(text) < MIN_CONTENT_FOR_SUMMARY:
            logger.debug(
                "Skipping article %s (%r) - too short to summarize (%d chars)",
                article_id,
                title,
                len(text),
            )
            # Mark as processed so we don't keep re-trying short articles.
            try:
                await self.repo.mark_summary_generated(article_id, summary=None)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not mark article %s as processed: %s", article_id, exc
                )
            result.skipped_short += 1
            return

        # ---------------------------------------------------------------- #
        #  Feature-flag fork. Default: dispatch the shared agent skill.
        # ---------------------------------------------------------------- #
        from ..core.config import get_settings

        use_skill = bool(getattr(get_settings(), "use_agent_skill_summarization", True))

        if use_skill:
            ok = await self._summarize_one_via_skill(article_id, title, result)
        else:
            ok = await self._summarize_one_via_service(
                article_id, title, text, result
            )

        if not ok:
            return

        # Post-summary hook: entity extraction. Best-effort — never fails
        # the article, just logs.
        if self.extract_entities and self.entity_service is not None:
            try:
                count = await self.entity_service.process_article(article_id)
                logger.debug(
                    "Extracted %d entities for article %s", count, article_id
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Entity extraction failed for article %s: %s",
                    article_id,
                    exc,
                )

    async def _summarize_one_via_skill(
        self,
        article_id,
        title: str,
        result: SummarizationRunResult,
    ) -> bool:
        """M2.M6 path: dispatch the shared ``summarize_article`` skill.

        The skill is responsible for the cache lookup, the LLM call on
        miss, AND the ``articles.summary`` write-back. After it returns
        we only need to flip the ``summary_generated`` flag so this
        article isn't re-queued on the next ingest run.

        Returns True on success (caller will run entity extraction),
        False on failure (caller skips entity extraction).
        """
        # Local import keeps the module loadable in environments where
        # langchain isn't installed (legacy CLI paths). The skill is
        # only imported when the flag is True.
        from .agent_skills.summarize_article import summarize_article

        try:
            raw = await summarize_article.ainvoke(
                {"article_id": int(article_id), "focus_question": None}
            )
        except Exception as exc:  # noqa: BLE001 - last-resort
            msg = f"Article {article_id} ({title!r}) skill crashed: {exc}"
            logger.error(msg, exc_info=True)
            result.failed += 1
            result.errors.append(msg)
            return False

        # The tool always returns a JSON string. Parse and validate.
        try:
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, ValueError) as exc:
            msg = f"Article {article_id} ({title!r}) bad skill payload: {exc}"
            logger.warning(msg)
            result.failed += 1
            result.errors.append(msg)
            return False

        if payload.get("error"):
            msg = (
                f"Article {article_id} ({title!r}) skill error: "
                f"{payload['error']}"
            )
            logger.warning(msg)
            result.failed += 1
            result.errors.append(msg)
            return False

        summary_text = (payload.get("summary") or "").strip()
        if not summary_text:
            msg = f"Article {article_id} ({title!r}) skill returned empty summary"
            logger.warning(msg)
            result.failed += 1
            result.errors.append(msg)
            return False

        # The skill already wrote ``summary`` back to the row on cache
        # miss. We only need to flip the processed flag — pass summary=None
        # so we DON'T double-write the column.
        try:
            await self.repo.mark_summary_generated(article_id, summary=None)
            result.summarized += 1
            logger.debug(
                "Summarized article %s via skill (cache_hit=%s, %d chars)",
                article_id,
                payload.get("cache_hit", False),
                len(summary_text),
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Article {article_id} flag write-back failed: {exc}"
            logger.error(msg, exc_info=True)
            result.failed += 1
            result.errors.append(msg)
            return False

        return True

    async def _summarize_one_via_service(
        self,
        article_id,
        title: str,
        text: str,
        result: SummarizationRunResult,
    ) -> bool:
        """Legacy path: call ``SummarizationService.summarize_content``.

        Preserved verbatim from before M6 as an emergency-rollback
        hatch. Toggle ``USE_AGENT_SKILL_SUMMARIZATION=false`` in the env
        to fall back. Slated for deletion in the post-M6 cleanup PR
        (see ticket Acceptance Criterion §last bullet).
        """
        request = SummarizationRequest(
            content=text,
            max_length=self.max_summary_length,
        )

        try:
            summary = await self.service.summarize_content(request)
        except (LLMError, ValidationError) as exc:
            msg = f"Article {article_id} ({title!r}) failed: {exc}"
            logger.warning(msg)
            result.failed += 1
            result.errors.append(msg)
            return False
        except Exception as exc:  # noqa: BLE001 - last-resort
            msg = f"Article {article_id} ({title!r}) crashed: {exc}"
            logger.error(msg, exc_info=True)
            result.failed += 1
            result.errors.append(msg)
            return False

        try:
            await self.repo.mark_summary_generated(
                article_id, summary=summary.summary
            )
            result.summarized += 1
            logger.debug(
                "Summarized article %s (%d -> %d chars in %.2fs)",
                article_id,
                summary.original_length,
                summary.summary_length,
                summary.processing_time,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Article {article_id} write-back failed: {exc}"
            logger.error(msg, exc_info=True)
            result.failed += 1
            result.errors.append(msg)
            return False

        return True
