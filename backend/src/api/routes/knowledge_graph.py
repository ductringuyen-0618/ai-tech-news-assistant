"""
Knowledge Graph Route
=====================

Serves the data behind the frontend's Knowledge Graph tab. Returns the top-N
named entities (by mention count) and the co-mention edges between them.

The shape is intentionally NOT wrapped in BaseResponse — the frontend reads
``response.nodes`` and ``response.edges`` directly. Keep it that way.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from ...core.config import get_settings


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge-graph", tags=["KnowledgeGraph"])


# Hard cap on what we'll return regardless of what the caller asks for.
# The canvas in the frontend is fine up to ~150 nodes; past that the
# force-directed layout pegs the CPU.
MAX_LIMIT = 150
DEFAULT_LIMIT = 50

# Edge threshold: only include co-mentions seen in this many distinct
# articles. The issue asks for >= 2 — single-article co-mentions are usually
# the model spraying related entities at one story.
MIN_CO_MENTION_ARTICLES = 2


def _resolve_db_path() -> str:
    settings = get_settings()
    return settings.get_database_file_path()


def _ensure_entity_tables(conn: sqlite3.Connection) -> None:
    """No-op if tables already exist; otherwise create empty stubs.

    This means the endpoint stays 200-OK even before any extraction has
    run (returns ``{nodes: [], edges: []}``), which is what the frontend
    expects on a fresh DB.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            mention_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            position INTEGER,
            UNIQUE(article_id, entity_id)
        )
        """
    )


@router.get("/")
async def get_knowledge_graph(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """
    Return the top-``limit`` entities by mention count + their co-mention edges.

    Response shape (consumed directly by ``KnowledgeGraph.tsx``):

    ::

        {
          "nodes": [{"id": "1", "name": "OpenAI", "type": "company",
                     "mention_count": 14}, ...],
          "edges": [{"source": "1", "target": "7", "weight": 3}, ...],
          "total_entities": 42
        }

    ``nodes`` is sorted descending by ``mention_count``. ``edges`` only
    includes pairs co-mentioned in ``MIN_CO_MENTION_ARTICLES`` or more
    distinct articles, and only between nodes that made the top-N cut.
    """
    db_path = _resolve_db_path()

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_entity_tables(conn)

            entity_rows = conn.execute(
                "SELECT id, name, type, mention_count "
                "FROM entities "
                "WHERE mention_count > 0 "
                "ORDER BY mention_count DESC, name ASC "
                "LIMIT ?",
                (limit,),
            ).fetchall()

            total_entities = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE mention_count > 0"
            ).fetchone()[0]

            nodes: List[Dict[str, Any]] = [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "type": row["type"],
                    "mention_count": int(row["mention_count"]),
                }
                for row in entity_rows
            ]

            edges: List[Dict[str, Any]] = []
            if len(nodes) >= 2:
                node_ids = [int(n["id"]) for n in nodes]
                # Build the IN clause safely with placeholders.
                placeholders = ",".join("?" * len(node_ids))
                # Self-join on entity_mentions to find co-mentions.
                # COUNT(DISTINCT article_id) is the edge weight.
                query = (
                    f"SELECT em1.entity_id AS a, em2.entity_id AS b, "
                    f"COUNT(DISTINCT em1.article_id) AS w "
                    f"FROM entity_mentions em1 "
                    f"JOIN entity_mentions em2 "
                    f"  ON em1.article_id = em2.article_id "
                    f"  AND em1.entity_id < em2.entity_id "
                    f"WHERE em1.entity_id IN ({placeholders}) "
                    f"  AND em2.entity_id IN ({placeholders}) "
                    f"GROUP BY em1.entity_id, em2.entity_id "
                    f"HAVING COUNT(DISTINCT em1.article_id) >= ? "
                    f"ORDER BY w DESC"
                )
                params = node_ids + node_ids + [MIN_CO_MENTION_ARTICLES]
                edge_rows = conn.execute(query, params).fetchall()
                edges = [
                    {
                        "source": str(row["a"]),
                        "target": str(row["b"]),
                        "weight": int(row["w"]),
                    }
                    for row in edge_rows
                ]

        return {
            "nodes": nodes,
            "edges": edges,
            "total_entities": int(total_entities),
        }
    except sqlite3.Error as exc:
        logger.error("Knowledge graph query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Knowledge graph query failed: {exc}"
        )


# ---------------------------------------------------------------------------
# Polish iter 3 / Part B — entity detail + trending entities.
# ---------------------------------------------------------------------------


@router.get("/entity/{entity_id}")
async def get_entity_detail(entity_id: int) -> Dict[str, Any]:
    """Return per-entity drill-down data for the KG side drawer.

    Shape:
        {
          "id": 42,
          "name": "OpenAI",
          "type": "Company",
          "mention_count": 12,
          "first_mention_at": "2026-04-15T10:23:00",
          "co_mentions": [{"id": 11, "name": "Sam Altman", "count": 8}, ...],
          "articles": [{"id": 588, "title": "...", "source": "TechCrunch",
                        "url": "https://...", "published_at": "..."}, ...]
        }

    Co-mentions: top 5 entities most frequently co-mentioned in the same
    articles, sorted desc by co-mention count.

    Articles: every article that mentions this entity, newest-first, up to 25.
    """
    db_path = _resolve_db_path()

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_entity_tables(conn)

            entity_row = conn.execute(
                "SELECT id, name, type, mention_count "
                "FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
            if not entity_row:
                raise HTTPException(status_code=404, detail="Entity not found")

            # First mention timestamp — join mentions to articles for the
            # earliest published_at (fall back to created_at).
            first_row = conn.execute(
                "SELECT MIN(COALESCE(a.published_at, a.created_at)) AS first_at "
                "FROM entity_mentions em "
                "JOIN articles a ON a.id = em.article_id "
                "WHERE em.entity_id = ?",
                (entity_id,),
            ).fetchone()
            first_mention_at = first_row["first_at"] if first_row else None

            # Top-5 co-mentioned entities, sorted by shared-article count.
            co_rows = conn.execute(
                "SELECT e.id AS id, e.name AS name, e.type AS type, "
                "       COUNT(DISTINCT em2.article_id) AS count "
                "FROM entity_mentions em1 "
                "JOIN entity_mentions em2 ON em1.article_id = em2.article_id "
                "                          AND em2.entity_id != em1.entity_id "
                "JOIN entities e ON e.id = em2.entity_id "
                "WHERE em1.entity_id = ? "
                "GROUP BY em2.entity_id "
                "ORDER BY count DESC, e.name ASC "
                "LIMIT 5",
                (entity_id,),
            ).fetchall()
            co_mentions = [
                {
                    "id": int(r["id"]),
                    "name": r["name"],
                    "type": r["type"],
                    "count": int(r["count"]),
                }
                for r in co_rows
            ]

            # Articles mentioning this entity, newest first.
            article_rows = conn.execute(
                "SELECT a.id AS id, a.title AS title, a.source AS source, "
                "       a.url AS url, a.published_at AS published_at, "
                "       a.created_at AS created_at "
                "FROM entity_mentions em "
                "JOIN articles a ON a.id = em.article_id "
                "WHERE em.entity_id = ? AND a.is_archived = 0 "
                "ORDER BY COALESCE(a.published_at, a.created_at) DESC "
                "LIMIT 25",
                (entity_id,),
            ).fetchall()
            articles = [
                {
                    "id": int(r["id"]),
                    "title": r["title"] or "(untitled)",
                    "source": r["source"] or "Unknown",
                    "url": r["url"] or "",
                    "published_at": r["published_at"] or r["created_at"],
                }
                for r in article_rows
            ]

        return {
            "id": int(entity_row["id"]),
            "name": entity_row["name"],
            "type": entity_row["type"],
            "mention_count": int(entity_row["mention_count"]),
            "first_mention_at": first_mention_at,
            "co_mentions": co_mentions,
            "articles": articles,
        }
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.error("Entity detail query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Entity detail query failed: {exc}"
        )


@router.get("/trending")
async def get_trending_entities(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=5, ge=1, le=25),
) -> Dict[str, Any]:
    """Top entities by recency-weighted mention count over the past ``days``.

    Weighting: each mention counts 1.0 if its article is from today, decaying
    linearly to 0.1 at the window edge. Then we sort by that score desc.

    Shape:
        {
          "entities": [
            {"id": 42, "name": "OpenAI", "type": "company",
             "mention_count": 12, "score": 9.4}, ...
          ],
          "window_days": 7
        }
    """
    db_path = _resolve_db_path()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    window_start_iso = window_start.isoformat()

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_entity_tables(conn)

            # Pull every mention within the window joined to its article date.
            # We compute the score in Python so the decay curve is explicit
            # and easy to tweak. Result rows: (entity_id, article_date).
            rows = conn.execute(
                "SELECT em.entity_id AS entity_id, "
                "       COALESCE(a.published_at, a.created_at) AS dt "
                "FROM entity_mentions em "
                "JOIN articles a ON a.id = em.article_id "
                "WHERE COALESCE(a.published_at, a.created_at) >= ? "
                "  AND a.is_archived = 0",
                (window_start_iso,),
            ).fetchall()

            scores: Dict[int, float] = {}
            raw_counts: Dict[int, int] = {}
            for r in rows:
                eid = int(r["entity_id"])
                dt_str = r["dt"]
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError):
                    dt = now
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
                # Linear decay from 1.0 to 0.1 across the window.
                if days <= 0:
                    weight = 1.0
                else:
                    weight = max(0.1, 1.0 - 0.9 * (age_days / days))
                scores[eid] = scores.get(eid, 0.0) + weight
                raw_counts[eid] = raw_counts.get(eid, 0) + 1

            if not scores:
                return {"entities": [], "window_days": days}

            # Pick the top ``limit`` IDs by score.
            top_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:limit]
            placeholders = ",".join("?" * len(top_ids))
            entity_rows = conn.execute(
                f"SELECT id, name, type, mention_count "
                f"FROM entities WHERE id IN ({placeholders})",
                top_ids,
            ).fetchall()
            by_id = {int(r["id"]): r for r in entity_rows}

            entities: List[Dict[str, Any]] = []
            for eid in top_ids:
                row = by_id.get(eid)
                if not row:
                    continue
                entities.append(
                    {
                        "id": int(row["id"]),
                        "name": row["name"],
                        "type": row["type"],
                        # mention_count_window — mentions inside the window.
                        "mention_count": raw_counts.get(eid, 0),
                        "score": round(scores[eid], 2),
                    }
                )

        return {"entities": entities, "window_days": days}
    except sqlite3.Error as exc:
        logger.error("Trending entities query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Trending entities query failed: {exc}"
        )
