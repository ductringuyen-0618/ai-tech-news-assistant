"""
Backfill ``article_embeddings`` for the corpus (M2.M6, Piece D)
================================================================

Why
---
``SearchService._vector_search`` (``backend/src/services/search_service.py``)
joins ``articles`` with an ``article_embeddings`` table on
``article_id``. When that table is missing or empty, the join returns
zero rows and the agent's ``search_articles`` skill silently degrades
to SQL LIKE text search. This script populates the table so vector
search is actually exercised in the M2.M4 pipeline.

What it does
------------
1.  Connect to ``news.db`` (whichever DB ``settings.database_path``
    resolves to).
2.  Create ``article_embeddings`` if missing — schema matches what
    ``SearchService`` already queries::

        CREATE TABLE article_embeddings (
            article_id   INTEGER PRIMARY KEY,
            embedding    TEXT NOT NULL,    -- JSON array of 384 floats
            model_name   TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        )

3.  For every article with non-NULL ``content`` or ``summary``, generate
    a 384-dim ``all-MiniLM-L6-v2`` embedding via
    ``vectorstore.embeddings.EmbeddingGenerator``. Upsert into
    ``article_embeddings``.
4.  Print progress every 10 articles. Print final stats.

Idempotent: re-running over already-backfilled articles re-generates
and overwrites their embeddings.

Run from ``backend/`` ::

    python scripts/backfill_embeddings.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from src.core.config import get_settings  # noqa: E402
from vectorstore.embeddings import EmbeddingGenerator  # noqa: E402


def _db_path() -> str:
    raw = get_settings().get_database_path()
    if raw.startswith("sqlite:///"):
        return raw[len("sqlite:///"):]
    if raw.startswith("sqlite://"):
        return raw[len("sqlite://"):]
    return raw


def _ensure_table(db: str) -> None:
    """Create ``article_embeddings`` if missing — schema mirrors what
    ``SearchService._vector_search`` and ``_get_index_statistics`` expect.
    """
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS article_embeddings (
                article_id    INTEGER PRIMARY KEY,
                embedding     TEXT NOT NULL,
                model_name    TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles(id)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_article_embeddings_article_id "
            "ON article_embeddings(article_id)"
        )
        conn.commit()


def _fetch_articles(db: str) -> List[Tuple[int, str, str]]:
    """Return ``(id, title, text_to_embed)`` for every non-archived
    article whose ``content`` OR ``summary`` is non-empty.
    """
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT id,
                   COALESCE(title, '') AS title,
                   COALESCE(NULLIF(content, ''), NULLIF(summary, ''), '') AS text
            FROM articles
            WHERE is_archived = 0
              AND COALESCE(NULLIF(content, ''), NULLIF(summary, ''), '') != ''
            ORDER BY id ASC
            """
        ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _upsert_embedding(
    db: str,
    article_id: int,
    embedding: List[float],
    model_name: str,
) -> None:
    """INSERT OR REPLACE one row and flip articles.embedding_generated.

    The stats endpoint (``ArticleRepository.get_stats``) reports
    ``articles_with_embeddings`` from BOTH the side-table count AND the
    legacy ``articles.embedding_generated`` column; we update both so
    every reader sees the same answer.
    """
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO article_embeddings
                (article_id, embedding, model_name, embedding_dim, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(article_id) DO UPDATE SET
                embedding = excluded.embedding,
                model_name = excluded.model_name,
                embedding_dim = excluded.embedding_dim,
                created_at = excluded.created_at
            """,
            (article_id, json.dumps(embedding), model_name, len(embedding)),
        )
        # Legacy flag — kept truthful so /api/news/stats and any consumer
        # of the ``articles.embedding_generated`` column see the upsert.
        try:
            conn.execute(
                "UPDATE articles SET embedding_generated = 1, "
                "    updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (article_id,),
            )
        except sqlite3.OperationalError:
            # Column doesn't exist on very old volumes; not fatal —
            # the side-table row is the source of truth either way.
            pass
        conn.commit()


async def main() -> int:
    db = _db_path()
    print(f"[backfill] DB: {db}")
    _ensure_table(db)
    print("[backfill] article_embeddings table ready")

    articles = _fetch_articles(db)
    print(f"[backfill] {len(articles)} article(s) with body to embed")

    if not articles:
        print("[backfill] Nothing to do.")
        return 0

    gen = EmbeddingGenerator()  # uses default all-MiniLM-L6-v2
    print(f"[backfill] Loading model {gen.model_name} on {gen.device} ...")
    await gen.load_model()
    print(f"[backfill] Model loaded (dim={gen.embedding_dim})")

    t0 = time.monotonic()
    processed = 0
    failures = 0

    # Encode in batches for speed.
    BATCH = 16
    for i in range(0, len(articles), BATCH):
        chunk = articles[i:i + BATCH]
        ids = [a[0] for a in chunk]
        # Mirror manage_embeddings.py: combine title + body for better recall.
        texts = [
            (f"{title}\n\n{body}".strip() if title else body)
            for (_, title, body) in chunk
        ]

        try:
            embeddings = await gen.generate_embeddings(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[backfill] batch {i // BATCH + 1} FAILED: {exc}")
            failures += len(chunk)
            continue

        for aid, vec in zip(ids, embeddings):
            try:
                _upsert_embedding(db, aid, vec.tolist(), gen.model_name)
                processed += 1
                if processed % 10 == 0:
                    print(f"[backfill]   {processed}/{len(articles)} "
                          f"({(time.monotonic() - t0):.1f}s)")
            except Exception as exc:  # noqa: BLE001
                print(f"[backfill]   upsert id={aid} FAILED: {exc}")
                failures += 1

    elapsed = time.monotonic() - t0
    print()
    print(f"[backfill] DONE — processed={processed}, failed={failures}, "
          f"wall_clock={elapsed:.1f}s")

    # Final table check.
    with sqlite3.connect(db) as conn:
        n_rows = conn.execute(
            "SELECT COUNT(*) FROM article_embeddings"
        ).fetchone()[0]
    print(f"[backfill] article_embeddings now has {n_rows} row(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
