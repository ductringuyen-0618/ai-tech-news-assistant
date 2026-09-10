"""
extract_entities agent skill
============================

Wraps :meth:`EntityExtractionService.process_article`. The orchestrator
calls this when it needs the named entities mentioned in a specific
article — typically as input to ``query_knowledge_graph``, but also when
the user explicitly asks "who/what is in this story?".

The underlying service is idempotent (re-running on the same article
deletes prior mentions then re-inserts), so a tool retry never inflates
``entities.mention_count``.

Returns the entities the caller can consume directly, plus a count.
``process_article`` itself only returns an int (count persisted) so we
do a follow-up read of the entity rows for this article to assemble the
full payload.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from src.services.entity_extraction_service import EntityExtractionService


logger = logging.getLogger(__name__)


# Module-level singleton — service construction triggers a CREATE TABLE
# IF NOT EXISTS, which we want to amortise across calls.
_extractor: Optional[EntityExtractionService] = None


def _get_extractor() -> EntityExtractionService:
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractionService()
    return _extractor


def _list_entities_for_article(
    db_path: str, article_id: int
) -> List[Dict[str, Any]]:
    """Read entity rows for one article, joined via ``entity_mentions``.

    Returns rows in mention-position order so the most prominent
    actors (model puts them first) show up at the top of the list.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT e.id, e.name, e.type, e.mention_count, em.position
            FROM entity_mentions em
            JOIN entities e ON e.id = em.entity_id
            WHERE em.article_id = ?
            ORDER BY em.position ASC
            """,
            (article_id,),
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "name": r["name"],
            "type": r["type"],
            "mention_count": int(r["mention_count"] or 0),
        }
        for r in rows
    ]


@tool
async def extract_entities(article_id: int) -> str:
    """Extract and persist named entities (companies, people, products,
    technologies) for one article.

    Idempotent: re-running on the same article replaces prior mentions
    rather than duplicating them, so it's safe to call from a retry loop.
    Use this AFTER you've identified an article of interest via
    ``search_articles``; pipe the entity names to ``query_knowledge_graph``
    if you want to walk the co-mention network.

    Args:
        article_id: SQLite primary key of the article in ``articles``.

    Returns:
        A JSON string with shape::

            {
                "article_id": int,
                "entity_count": int,
                "entities": [
                    {"id": int, "name": str, "type": str,
                     "mention_count": int},
                    ...
                ]
            }

        On error::

            {"article_id": int, "entity_count": 0, "entities": [],
             "error": "..."}
    """
    try:
        aid = int(article_id)
    except (TypeError, ValueError):
        return json.dumps(
            {
                "article_id": article_id,
                "entity_count": 0,
                "entities": [],
                "error": f"invalid article_id: {article_id!r}",
            }
        )

    extractor = _get_extractor()

    try:
        persisted = await extractor.process_article(aid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "extract_entities: process_article failed for id=%s: %s",
            aid,
            exc,
        )
        return json.dumps(
            {
                "article_id": aid,
                "entity_count": 0,
                "entities": [],
                "error": f"extraction failed: {exc}",
            }
        )

    # ``process_article`` returns the count of mentions persisted; do a
    # follow-up read so the caller can see *which* entities those were.
    try:
        entities = _list_entities_for_article(extractor.db_path, aid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "extract_entities: post-extract read failed for id=%s: %s",
            aid,
            exc,
        )
        entities = []

    payload = {
        "article_id": aid,
        "entity_count": int(persisted) if persisted is not None else len(entities),
        "entities": entities,
    }
    return json.dumps(payload, ensure_ascii=False)
