"""
query_knowledge_graph agent skill
=================================

Walks the co-mention graph built by :class:`EntityExtractionService`. Two
entities have a co-mention edge if they appeared in the same article;
edge weight = number of articles that mention BOTH.

Schema reminder (created by ``EntityExtractionService._ensure_tables_exist``):

* ``entities(id, name, type, mention_count, created_at)``
* ``entity_mentions(id, article_id, entity_id, position)``

The walk:

1. Match the seed entity by case-insensitive name (or fall through to
   a substring match if no exact hit).
2. BFS up to ``depth`` hops over the co-mention edges. ``depth=1`` (the
   default) returns the seed plus its direct neighbours.
3. Cap at ``max_nodes=20`` and ``max_edges=50`` to bound the payload —
   highly-connected entities (e.g. "OpenAI") would otherwise return
   hundreds of nodes and overwhelm the orchestrator's context.

Output is a stable list-of-dicts shape suitable for a frontend graph
viz, but the immediate consumer is the LLM orchestrator: it reads node
names + edge weights and decides what to ``summarize_article`` next.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_core.tools import tool

from src.core.config import get_settings


logger = logging.getLogger(__name__)


# Hard caps — see module docstring for rationale.
MAX_NODES = 20
MAX_EDGES = 50
MIN_DEPTH = 1
MAX_DEPTH = 3  # Beyond 3 hops the graph becomes meaningless noise.


def _resolve_db_path() -> str:
    """Resolve the SQLite path the entity tables live in.

    Mirrors the resolution logic in :class:`EntityExtractionService` so
    this skill reads from the same DB the extractor wrote to.
    """
    settings = get_settings()
    return settings.get_database_file_path()


def _find_seed_entity(
    conn: sqlite3.Connection, term: str
) -> Optional[Dict[str, Any]]:
    """Find the seed entity for the walk.

    Tries exact (case-insensitive) match first, then falls back to a
    LIKE-based substring match (ordered by ``mention_count DESC`` so the
    most prominent matching entity wins).
    """
    row = conn.execute(
        "SELECT id, name, type, mention_count FROM entities "
        "WHERE LOWER(name) = LOWER(?) LIMIT 1",
        (term,),
    ).fetchone()
    if row is not None:
        return dict(row)

    like_term = f"%{term}%"
    row = conn.execute(
        "SELECT id, name, type, mention_count FROM entities "
        "WHERE LOWER(name) LIKE LOWER(?) "
        "ORDER BY mention_count DESC LIMIT 1",
        (like_term,),
    ).fetchone()
    if row is not None:
        return dict(row)
    return None


def _co_mention_neighbours(
    conn: sqlite3.Connection, entity_id: int
) -> List[Tuple[int, int]]:
    """Return ``[(neighbour_id, shared_article_count), ...]`` ordered by
    edge weight (descending).

    Two entities co-occur once per article that mentions BOTH, so the
    weight is just ``COUNT(DISTINCT article_id)`` over the join.
    """
    rows = conn.execute(
        """
        SELECT em2.entity_id AS neighbour_id,
               COUNT(DISTINCT em1.article_id) AS weight
        FROM entity_mentions em1
        JOIN entity_mentions em2
            ON em1.article_id = em2.article_id
            AND em2.entity_id != em1.entity_id
        WHERE em1.entity_id = ?
        GROUP BY em2.entity_id
        ORDER BY weight DESC
        """,
        (entity_id,),
    ).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


def _entity_row(
    conn: sqlite3.Connection, entity_id: int
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, name, type, mention_count FROM entities WHERE id = ?",
        (entity_id,),
    ).fetchone()
    return dict(row) if row else None


def _walk_graph(
    db_path: str, term: str, depth: int
) -> Dict[str, Any]:
    """BFS up to ``depth`` hops from the seed entity. Returns a payload
    dict with ``nodes`` and ``edges`` lists (or an ``error`` field)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        seed = _find_seed_entity(conn, term)
        if seed is None:
            return {
                "nodes": [],
                "edges": [],
                "seed": term,
                "error": f"no entity found matching {term!r}",
            }

        # BFS bookkeeping — store node ids we've already enqueued so we
        # don't double-process and don't blow past MAX_NODES.
        nodes_by_id: Dict[int, Dict[str, Any]] = {seed["id"]: dict(seed)}
        edges: List[Dict[str, Any]] = []
        seen_edge_keys: Set[Tuple[int, int]] = set()

        # Queue items: (entity_id, hops_consumed_so_far)
        queue: deque = deque([(seed["id"], 0)])

        while queue:
            current_id, hops = queue.popleft()
            if hops >= depth:
                # Don't expand further — but we'd have already added the
                # node when its parent enqueued it, so nothing to do.
                continue
            neighbours = _co_mention_neighbours(conn, current_id)
            for neigh_id, weight in neighbours:
                if len(edges) >= MAX_EDGES:
                    break
                # Edge key: order-independent so (a,b) and (b,a) collapse.
                edge_key = (min(current_id, neigh_id), max(current_id, neigh_id))
                if edge_key in seen_edge_keys:
                    continue
                seen_edge_keys.add(edge_key)

                # Materialise the neighbour node lazily.
                if neigh_id not in nodes_by_id:
                    if len(nodes_by_id) >= MAX_NODES:
                        # Don't add new nodes past the cap, but still
                        # don't add edges to non-existent nodes either.
                        continue
                    neigh_row = _entity_row(conn, neigh_id)
                    if neigh_row is None:
                        continue
                    nodes_by_id[neigh_id] = neigh_row
                    # Enqueue for further expansion if we still have hops.
                    queue.append((neigh_id, hops + 1))

                edges.append(
                    {
                        "source": int(edge_key[0]),
                        "target": int(edge_key[1]),
                        "weight": int(weight),
                    }
                )
            if len(edges) >= MAX_EDGES:
                break

        nodes_payload = [
            {
                "id": int(n["id"]),
                "name": n["name"],
                "type": n["type"],
                "mention_count": int(n["mention_count"] or 0),
                "is_seed": int(n["id"]) == int(seed["id"]),
            }
            for n in nodes_by_id.values()
        ]

        return {
            "nodes": nodes_payload,
            "edges": edges,
            "seed": seed["name"],
        }


@tool
async def query_knowledge_graph(entity_or_topic: str, depth: int = 1) -> str:
    """Walk the entity co-mention graph from a seed entity name.

    Two entities are connected if they were mentioned in the same
    article; edge weight is the number of articles that mention both.
    Use this AFTER ``extract_entities`` has populated the graph for the
    relevant articles, OR to discover what's adjacent to a known entity
    (e.g. "OpenAI" -> Sam Altman, ChatGPT, Microsoft, ...).

    Args:
        entity_or_topic: Seed entity name. Tries exact (case-insensitive)
            match first; falls back to substring match (most-mentioned
            wins).
        depth: BFS hop budget. ``1`` = seed + direct neighbours, ``2`` =
            two hops, etc. Clamped to [1, 3]; deeper walks return mostly
            noise. Defaults to 1.

    Returns:
        A JSON string with shape::

            {
                "nodes": [
                    {"id": int, "name": str, "type": str,
                     "mention_count": int, "is_seed": bool},
                    ...
                ],
                "edges": [
                    {"source": int, "target": int, "weight": int},
                    ...
                ],
                "seed": str        # the resolved seed name
            }

        Capped at 20 nodes and 50 edges. On no-match::

            {"nodes": [], "edges": [], "seed": "...",
             "error": "no entity found matching ..."}
    """
    term = (entity_or_topic or "").strip()
    if not term:
        return json.dumps(
            {
                "nodes": [],
                "edges": [],
                "seed": "",
                "error": "entity_or_topic is empty",
            }
        )

    try:
        d = int(depth)
    except (TypeError, ValueError):
        d = 1
    d = max(MIN_DEPTH, min(d, MAX_DEPTH))

    db_path = _resolve_db_path()

    try:
        payload = _walk_graph(db_path, term, d)
    except sqlite3.OperationalError as exc:
        # Most likely: the entity tables don't exist yet (no entities have
        # been extracted in this DB). Return an empty result, not an error
        # — the agent should be able to handle "no graph yet" gracefully.
        logger.info(
            "query_knowledge_graph: no graph tables yet (%s); returning empty",
            exc,
        )
        return json.dumps(
            {
                "nodes": [],
                "edges": [],
                "seed": term,
                "error": "knowledge graph is empty (no entities extracted yet)",
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "query_knowledge_graph: walk failed for term=%r: %s", term, exc
        )
        return json.dumps(
            {
                "nodes": [],
                "edges": [],
                "seed": term,
                "error": f"graph walk failed: {exc}",
            }
        )

    return json.dumps(payload, ensure_ascii=False)
