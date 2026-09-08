"""
Subscriber Repository
=====================

Data access for the ``subscribers`` table (digest email capture). Mirrors
the lightweight ``sqlite3``-direct style used by ``settings_repository.py``
and ``digest.py`` rather than going through SQLAlchemy sessions:

* the running backend doesn't call ``Base.metadata.create_all()`` at startup
* this is a simple table with no relationships
* the repository auto-creates the table on first touch via
  ``CREATE TABLE IF NOT EXISTS``, matching ``SettingsRepository``

The SQLAlchemy ``Subscriber`` model in ``database.models`` describes the same
shape and is included for typing / future migrations, but isn't used here at
runtime.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class SubscriberRepository:
    """Repository for the ``subscribers`` table."""

    def __init__(self, db_path: str):
        # Mirror SettingsRepository/ArticleRepository: accept a SQLAlchemy
        # URL or a bare path.
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "")
        else:
            self.db_path = db_path
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_subscribers_email "
                "ON subscribers (email)"
            )

    def subscribe(self, email: str) -> Dict[str, Any]:
        """
        Insert a new subscriber, or idempotently return the existing row if
        that email is already subscribed (re-activating it if it had been
        deactivated). Never raises on a duplicate — the caller always gets a
        success shape back.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            existing = conn.execute(
                "SELECT id, email, subscribed_at, is_active FROM subscribers "
                "WHERE email = ?",
                (email,),
            ).fetchone()

            if existing is not None:
                if not existing["is_active"]:
                    conn.execute(
                        "UPDATE subscribers SET is_active = 1, "
                        "subscribed_at = ? WHERE id = ?",
                        (now_iso, existing["id"]),
                    )
                    conn.commit()
                    return self._get_by_id(conn, existing["id"])
                return {
                    "id": existing["id"],
                    "email": existing["email"],
                    "subscribed_at": existing["subscribed_at"],
                    "is_active": bool(existing["is_active"]),
                }

            cursor = conn.execute(
                "INSERT INTO subscribers (email, subscribed_at, is_active) "
                "VALUES (?, ?, 1)",
                (email, now_iso),
            )
            conn.commit()
            return self._get_by_id(conn, cursor.lastrowid)

    def _get_by_id(self, conn: sqlite3.Connection, subscriber_id: int) -> Dict[str, Any]:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, email, subscribed_at, is_active FROM subscribers "
            "WHERE id = ?",
            (subscriber_id,),
        ).fetchone()
        return {
            "id": row["id"],
            "email": row["email"],
            "subscribed_at": row["subscribed_at"],
            "is_active": bool(row["is_active"]),
        }

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, email, subscribed_at, is_active FROM subscribers "
                "WHERE email = ?",
                (email,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "email": row["email"],
                "subscribed_at": row["subscribed_at"],
                "is_active": bool(row["is_active"]),
            }

    def count_active(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE is_active = 1"
            ).fetchone()
            return int(row[0]) if row else 0
