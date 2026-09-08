"""
Settings Repository
==================

Data access for the ``settings`` table. Mirrors the lightweight
``sqlite3``-direct style used by ``digest.py`` and ``article_repository.py``
rather than going through SQLAlchemy sessions, since:

* the running backend doesn't call ``Base.metadata.create_all()`` at startup
* this is a small, relationship-free table
* the repository auto-creates/migrates the table on first touch via
  ``CREATE TABLE IF NOT EXISTS`` + additive ``ALTER TABLE``, matching how
  ``ArticleRepository`` bootstraps

Rows are keyed by ``client_id`` (a frontend-generated UUID sent via the
``X-Client-Id`` header). Callers that don't pass a ``client_id`` fall back to
the legacy singleton row (``id=1``, ``client_id`` NULL) so behavior for
callers that haven't been updated yet is unchanged.

The SQLAlchemy ``Settings`` model in ``database.models`` describes the same
shape and is included for typing / future migrations, but isn't used here at
runtime.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


SETTINGS_ROW_ID = 1  # Legacy singleton primary key, used when no client_id is given.


class SettingsRepository:
    """Repository for per-client settings rows (with a legacy singleton fallback)."""

    def __init__(self, db_path: str):
        # Mirror ArticleRepository: accept a SQLAlchemy URL or a bare path.
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "")
        else:
            self.db_path = db_path
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY,
                    categories TEXT,
                    view_mode TEXT NOT NULL DEFAULT 'detailed',
                    show_trending_only INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()
            }
            if "client_id" not in existing_cols:
                conn.execute("ALTER TABLE settings ADD COLUMN client_id TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_settings_client_id "
                "ON settings(client_id) WHERE client_id IS NOT NULL"
            )

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        categories = None
        if row["categories"]:
            try:
                categories = json.loads(row["categories"])
            except (json.JSONDecodeError, TypeError):
                categories = None

        return {
            "categories": categories,
            "view_mode": row["view_mode"],
            "show_trending_only": bool(row["show_trending_only"]),
            "updated_at": row["updated_at"],
        }

    def get(self, client_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Return the settings row for ``client_id`` as a dict, or the legacy
        singleton row when ``client_id`` is ``None``. Returns ``None`` if no
        matching row has been written yet (caller falls back to defaults).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if client_id:
                row = conn.execute(
                    "SELECT id, categories, view_mode, show_trending_only, updated_at "
                    "FROM settings WHERE client_id = ?",
                    (client_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, categories, view_mode, show_trending_only, updated_at "
                    "FROM settings WHERE id = ?",
                    (SETTINGS_ROW_ID,),
                ).fetchone()

            if not row:
                return None
            return self._row_to_dict(row)

    def upsert(
        self,
        *,
        client_id: Optional[str] = None,
        categories: Optional[list] = None,
        view_mode: Optional[str] = None,
        show_trending_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Upsert the settings row for ``client_id`` (or the legacy singleton
        row when ``client_id`` is ``None``). Fields left as ``None`` keep
        their current (or default) value. Returns the post-write state.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if client_id:
                existing = conn.execute(
                    "SELECT id, categories, view_mode, show_trending_only "
                    "FROM settings WHERE client_id = ?",
                    (client_id,),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id, categories, view_mode, show_trending_only "
                    "FROM settings WHERE id = ?",
                    (SETTINGS_ROW_ID,),
                ).fetchone()

            now_iso = datetime.now(timezone.utc).isoformat()

            if existing is None:
                # First write — insert with whatever was supplied; falling
                # back to None for categories so GET-with-no-row defaults
                # logic remains the *only* place defaults live.
                cats_json = (
                    json.dumps(categories) if categories is not None else None
                )
                vm = view_mode if view_mode is not None else "detailed"
                trending = (
                    1 if (show_trending_only is True) else 0
                )
                if client_id:
                    # Never collide with the reserved legacy singleton id.
                    new_id = conn.execute(
                        "SELECT COALESCE(MAX(id), 1) + 1 FROM settings"
                    ).fetchone()[0]
                    conn.execute(
                        "INSERT INTO settings (id, client_id, categories, view_mode, "
                        "show_trending_only, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id, client_id, cats_json, vm, trending, now_iso),
                    )
                else:
                    conn.execute(
                        "INSERT INTO settings (id, categories, view_mode, "
                        "show_trending_only, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (SETTINGS_ROW_ID, cats_json, vm, trending, now_iso),
                    )
            else:
                # Merge: keep existing values for any field not supplied.
                if categories is not None:
                    cats_json = json.dumps(categories)
                else:
                    cats_json = existing["categories"]
                vm = view_mode if view_mode is not None else existing["view_mode"]
                if show_trending_only is None:
                    trending = existing["show_trending_only"]
                else:
                    trending = 1 if show_trending_only else 0
                conn.execute(
                    "UPDATE settings SET categories = ?, view_mode = ?, "
                    "show_trending_only = ?, updated_at = ? WHERE id = ?",
                    (cats_json, vm, trending, now_iso, existing["id"]),
                )
            conn.commit()

        result = self.get(client_id=client_id)
        # ``get`` always returns a row here since we just wrote one.
        assert result is not None
        return result
