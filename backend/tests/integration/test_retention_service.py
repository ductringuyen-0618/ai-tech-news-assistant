"""Integration test for the retention sweep on real data.

The retention service itself is already wired into APScheduler at
00:00 UTC daily (see ``src/main.py``) -- this test only verifies the
on-disk behaviour we depend on:

* Articles older than ``RETENTION_DAYS`` (default 30) are deleted.
* Articles inside the retention window are preserved.
* The :class:`RetentionResult` reports accurate ``scanned`` /
  ``deleted_articles`` counts.

We seed a tmp SQLite DB with three articles (1 / 29 / 31 days old),
point the service at it, and call ``run(dry_run=False)``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from src.services.retention_service import RetentionService


def _make_articles_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            content TEXT,
            summary TEXT,
            author TEXT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            categories TEXT,
            metadata TEXT,
            is_archived BOOLEAN DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            embedding_generated BOOLEAN DEFAULT 0,
            summary_generated BOOLEAN DEFAULT 0,
            image_url TEXT
        )
        """
    )


def _seed(conn: sqlite3.Connection, *, title: str, url: str, days_ago: int) -> int:
    pub = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur = conn.execute(
        "INSERT INTO articles (title, url, content, published_at) "
        "VALUES (?, ?, ?, ?)",
        (title, url, "body", pub),
    )
    return int(cur.lastrowid)


def test_retention_deletes_articles_older_than_30_days(tmp_path):
    """Seed 1-day, 29-day, 31-day-old rows. Run the sweep.

    Assert the 31-day-old row is gone, the other two survive, and
    the returned :class:`RetentionResult` reports ``scanned=1``
    (only the 31-day row is older than the cutoff) and
    ``deleted_articles=1``.
    """
    db = tmp_path / "retention.db"
    with sqlite3.connect(db) as conn:
        _make_articles_table(conn)
        recent_id = _seed(conn, title="Fresh", url="https://x/1", days_ago=1)
        edge_id = _seed(conn, title="Edge", url="https://x/2", days_ago=29)
        stale_id = _seed(conn, title="Stale", url="https://x/3", days_ago=31)
        conn.commit()

    service = RetentionService(
        db_path=str(db),
        retention_days=30,
        max_deletes=500,
    )
    result = service.run(dry_run=False)

    # Only the 31-day-old row was past the cutoff.
    assert result.scanned == 1
    assert result.deleted_articles == 1
    assert result.candidate_ids == [stale_id]
    assert result.dry_run is False

    # On-disk: two articles remain, the stale one is gone.
    with sqlite3.connect(db) as conn:
        remaining = {
            int(r[0])
            for r in conn.execute("SELECT id FROM articles").fetchall()
        }
    assert remaining == {recent_id, edge_id}
    assert stale_id not in remaining
