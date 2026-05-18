"""
Saved Research Repository
=========================

Data-access layer for the ``saved_research`` table (M3.M5). Mirrors the
lightweight ``sqlite3``-direct style used by
:class:`~src.repositories.settings_repository.SettingsRepository` and
:class:`~src.repositories.article_repository.ArticleRepository` — the
table is auto-created on first touch via ``CREATE TABLE IF NOT EXISTS``
so it works against both a fresh and an existing ``news.db``.

The ``sources_json`` column stores the sources list as JSON text. We
convert at the repository boundary so callers (routes, tests) always
deal in native Python lists of dicts.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


# Saved-research cap. Documented in the route docstring so callers know
# the policy without spelunking. Capped because saved_research can grow
# without bound on long-term use — the 100-row LRU keeps the table small.
MAX_SAVED_ROWS = 100


class SavedResearchRepository:
    """Repository for the ``saved_research`` table."""

    def __init__(self, db_path: str):
        # Accept either a SQLAlchemy URL or a bare path, matching the
        # convention used elsewhere in the repository layer.
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "")
        else:
            self.db_path = db_path
        self._ensure_table_exists()

    # ------------------------------------------------------------------ #
    #  Schema
    # ------------------------------------------------------------------ #

    def _ensure_table_exists(self) -> None:
        """Create the ``saved_research`` table if absent.

        The ``CREATE TABLE IF NOT EXISTS`` guard makes this safe against
        both a freshly-initialized DB and an existing ``news.db`` from a
        prior milestone.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_research (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    report_md TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    # ------------------------------------------------------------------ #
    #  CRUD
    # ------------------------------------------------------------------ #

    def create(
        self,
        question: str,
        report_md: str,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Insert a saved-research row.

        The ``sources`` argument may be ``None`` or an empty list — both
        are stored as ``"[]"`` so reads always parse cleanly.

        Returns the new row id.
        """
        sources_json = json.dumps(sources or [])
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO saved_research (question, report_md, sources_json) "
                "VALUES (?, ?, ?)",
                (question, report_md, sources_json),
            )
            conn.commit()
            new_id = cursor.lastrowid
            assert new_id is not None  # AUTOINCREMENT always returns an id
            return int(new_id)

    def list_all(self, limit: int = MAX_SAVED_ROWS) -> List[Tuple[int, str, str]]:
        """List rows ordered by ``created_at`` DESC, capped at ``limit``.

        Returns lightweight tuples of ``(id, question, created_at)``.
        Designed for the Saved sidebar list view, which doesn't need to
        pay for the markdown report on every row.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, question, created_at FROM saved_research "
                "ORDER BY datetime(created_at) DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                (int(r["id"]), r["question"], r["created_at"]) for r in rows
            ]

    def count(self) -> int:
        """Return the total number of saved-research rows."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM saved_research"
            ).fetchone()
            return int(row[0])

    def get_by_id(self, row_id: int) -> Optional[Dict[str, Any]]:
        """Fetch the full record for ``row_id``, or ``None`` if missing.

        Sources are parsed from JSON back into a list of dicts at this
        boundary so callers don't have to.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, question, report_md, sources_json, created_at "
                "FROM saved_research WHERE id = ?",
                (row_id,),
            ).fetchone()
            if not row:
                return None
            try:
                sources = json.loads(row["sources_json"]) if row["sources_json"] else []
                if not isinstance(sources, list):
                    sources = []
            except (json.JSONDecodeError, TypeError):
                sources = []
            return {
                "id": int(row["id"]),
                "question": row["question"],
                "report_md": row["report_md"],
                "sources": sources,
                "created_at": row["created_at"],
            }

    def delete_by_id(self, row_id: int) -> bool:
        """Remove a row by id. Returns True if a row was deleted."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM saved_research WHERE id = ?", (row_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_oldest(self) -> bool:
        """Delete the oldest row by ``created_at``. Used to enforce the
        100-row cap during POST. Returns True if a row was deleted.

        Ties on ``created_at`` (rare in practice — same-second inserts)
        are broken by the smallest ``id`` so the eviction order is
        deterministic.
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM saved_research "
                "ORDER BY datetime(created_at) ASC, id ASC LIMIT 1"
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "DELETE FROM saved_research WHERE id = ?", (row[0],)
            )
            conn.commit()
            return True

    # ------------------------------------------------------------------ #
    #  Seed (design-review #4) — first-touch demo dispatches.
    # ------------------------------------------------------------------ #

    def seed_if_empty(self) -> int:
        """Seed example saved-research dispatches when the table is empty.

        Idempotent: a no-op once any row exists in the table. Inserts a
        small, hand-written corpus so the portfolio-site `/saved` page
        renders a realistic File Room instead of "No saved research yet"
        on a fresh deploy. The seed fixtures live in
        :mod:`src.repositories.seed_data.saved_research_seeds` to keep
        the repository file readable.

        Returns the number of rows inserted (0 when the table was
        already non-empty, ``len(SEED_DISPATCHES)`` on a cold start).
        """
        if self.count() > 0:
            return 0
        # Inline import so we don't pay the cost of loading the seed
        # corpus on every repository construction.
        from .seed_data.saved_research_seeds import SEED_DISPATCHES

        inserted = 0
        for dispatch in SEED_DISPATCHES:
            self.create(
                question=dispatch["question"],
                report_md=dispatch["report_md"],
                sources=dispatch.get("sources", []),
            )
            inserted += 1
        return inserted
