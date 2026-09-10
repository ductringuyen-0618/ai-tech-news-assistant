"""Learning-feed ingestion (proposal 003 -- "Trending AI Agent Skills").

Fetches the small, curated set of agent-tooling feeds in
``settings.learning_rss_sources``, tags matching entries with the
reserved ``Agent Skills`` category, and applies a content-level keyword
filter (see :mod:`learning_filter`) on top of it so a broad source
doesn't flood the Learning tab with off-topic items.

Deliberately reuses the existing pipeline rather than building a
parallel one:

* Fetching/inserting goes through the same :class:`IngestionService`
  every other feed uses (dedupe-by-URL, category->``categories`` JSON
  column sync all come for free -- see ``_process_entry`` there).
* Summarization, embedding, and entity extraction are NOT duplicated
  here. ``run_daily_ingestion``'s phases 2-4 already process every row
  missing a summary/embedding/entities regardless of category, so a
  newly-fetched Learning row is picked up for free the next time the
  (already-scheduled) daily ingestion cycle runs.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Dict, List, Optional

from .daily_ingestion_orchestrator import PhaseReport, _resolve_db_path, _run_phase
from .learning_filter import is_learning_content

logger = logging.getLogger(__name__)

# Reserved category tag for Learning-feed items. Deliberately distinct
# from the existing "AI Agents" topic chip (general AI-agent industry
# news) -- this one is specifically for tooling/technique content, and
# is what ``GET /api/learning/`` filters on.
LEARNING_CATEGORY = "Agent Skills"


def _build_learning_feed_configs(
    sources: Optional[List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    """Resolve the feed list (explicit override or config default) into
    the ``{name, url, category}`` shape :meth:`IngestionService.ingest_all`
    expects, all pinned to :data:`LEARNING_CATEGORY`.
    """
    if sources is None:
        from ..core.config import get_settings

        sources = get_settings().learning_rss_sources
    return [
        {"name": s["name"], "url": s["url"], "category": LEARNING_CATEGORY}
        for s in sources
    ]


def _demote_non_learning_rows(db_path: str) -> int:
    """Strip the Learning category tag from rows that fail the
    content-level keyword filter.

    A demoted row isn't deleted -- it just stops carrying the
    ``Agent Skills`` tag, so it no longer shows up in ``GET
    /api/learning/`` but remains a normal ingested article. Idempotent:
    re-running against already-demoted rows (``categories`` already
    NULL) is a no-op, since they no longer match the ``LIKE`` filter.

    Returns the number of rows demoted.
    """
    demoted = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
        if "categories" not in cols:
            return 0
        rows = conn.execute(
            "SELECT id, title, content FROM articles WHERE categories LIKE ?",
            (f'%"{LEARNING_CATEGORY}"%',),
        ).fetchall()
        for row in rows:
            if not is_learning_content(row["title"] or "", row["content"] or ""):
                conn.execute(
                    "UPDATE articles SET categories = NULL WHERE id = ?",
                    (row["id"],),
                )
                demoted += 1
        conn.commit()
    return demoted


async def _phase_learning_fetch(
    *,
    report: PhaseReport,
    db_path: str,
    sources: Optional[List[Dict[str, str]]],
    dry_run: bool,
) -> None:
    """Fetch the curated Learning sources and apply the keyword filter.

    Mirrors ``daily_ingestion_orchestrator._phase_fetch``'s
    SessionLocal/IngestionService wiring so writes go through the exact
    same path (and therefore the exact same dedupe + categories-column
    sync) as the regular daily fetch.
    """
    if dry_run:
        logger.info("[learning_fetch] dry_run=True; skipping network fetch")
        return

    from src.database.base import SessionLocal, create_session_factory
    from src.services.ingestion_service import IngestionService

    if SessionLocal is None:
        create_session_factory()
    from src.database.base import SessionLocal as _SessionLocal

    if _SessionLocal is None:
        report.add_error("SessionLocal not initialised after factory call")
        return

    feed_configs = _build_learning_feed_configs(sources)
    session = _SessionLocal()
    try:
        service = IngestionService(session)
        try:
            result = await asyncio.to_thread(service.ingest_all, feed_configs)
        finally:
            service.close()

        report.processed = int(getattr(result, "total_articles_saved", 0) or 0)
        report.failed = int(getattr(result, "errors_encountered", 0) or 0)
        for detail in getattr(result, "error_details", []) or []:
            err = detail.get("error") if isinstance(detail, dict) else str(detail)
            if err:
                report.add_error(str(err)[:200])
    finally:
        try:
            session.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("session close failed", exc_info=True)

    try:
        demoted = _demote_non_learning_rows(db_path)
        if demoted:
            logger.info("[learning_fetch] demoted %d non-matching row(s)", demoted)
    except Exception as exc:  # noqa: BLE001 - filter pass must not fail the run
        report.add_error(f"keyword filter pass failed: {exc}"[:200])
        logger.warning("[learning_fetch] keyword filter pass failed: %s", exc)


async def run_learning_ingestion(
    db_path: str,
    *,
    sources: Optional[List[Dict[str, str]]] = None,
    dry_run: bool = False,
) -> PhaseReport:
    """Fetch + keyword-filter the Learning feed's curated sources.

    Parameters
    ----------
    db_path
        Path to the SQLite database (or ``sqlite:///...`` URL form).
    sources
        Optional override for ``settings.learning_rss_sources``, in the
        same ``{name, url, description}`` shape. Mainly for tests.
    dry_run
        When True, skips the network fetch entirely and returns a
        report with ``processed=0``.
    """
    resolved_db = _resolve_db_path(db_path)
    return await _run_phase(
        "learning_fetch",
        _phase_learning_fetch,
        db_path=resolved_db,
        sources=sources,
        dry_run=dry_run,
    )
