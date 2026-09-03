"""
Retention Service
=================

Hard-deletes articles older than ``RETENTION_DAYS`` and any rows that hang
off them (embeddings, embedding_metadata, article_categories). Wired up to
a daily APScheduler job in ``src/main.py`` and exposed as an admin route in
``src/api/routes/admin.py``.

Design notes:
* Uses raw ``sqlite3`` rather than the ORM. The schema in ``news.db`` is
  hand-rolled (see ``ArticleRepository._ensure_tables_exist``) and does not
  match the SQLAlchemy declarative models, so the ORM path would lie about
  what it's deleting. The actual ``embeddings`` table has no FK to
  ``articles`` (it stores ``content_id`` as TEXT) and ``article_categories``
  has FKs without ``ON DELETE CASCADE``. Per the milestone brief we delete
  dependents explicitly here — simpler than a schema rebuild on a live DB.
* Per-run delete cap (``RETENTION_MAX_DELETES``) protects against runaway
  deletes if someone sets ``RETENTION_DAYS=0`` by mistake.
* Dry-run mode logs and returns what *would* be deleted without committing.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    """Outcome of a retention run."""

    dry_run: bool
    cutoff_iso: str
    retention_days: int
    max_deletes: int
    scanned: int = 0
    candidate_ids: List[int] = field(default_factory=list)
    deleted_articles: int = 0
    deleted_embeddings: int = 0
    deleted_embedding_metadata: int = 0
    deleted_article_categories: int = 0

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "cutoff_iso": self.cutoff_iso,
            "retention_days": self.retention_days,
            "max_deletes": self.max_deletes,
            "scanned": self.scanned,
            "would_delete" if self.dry_run else "deleted_ids": list(self.candidate_ids),
            "deleted_articles": self.deleted_articles,
            "deleted_embeddings": self.deleted_embeddings,
            "deleted_embedding_metadata": self.deleted_embedding_metadata,
            "deleted_article_categories": self.deleted_article_categories,
        }


def _resolve_db_path(raw: str) -> str:
    """Match the prefix-strip pattern used by ArticleRepository."""
    if raw.startswith("sqlite:///"):
        return raw.replace("sqlite:///", "")
    return raw


class RetentionService:
    """Hard-delete articles older than ``RETENTION_DAYS``.

    Both the daily cron and the admin route call ``run()``.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        retention_days: Optional[int] = None,
        max_deletes: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        # Resolve via the single shared helper (DATABASE_URL, else
        # SQLITE_DATABASE_PATH) so this always agrees with every other
        # DB access path in the app.
        self.db_path = _resolve_db_path(db_path) if db_path else settings.get_database_file_path()
        self.retention_days = (
            retention_days
            if retention_days is not None
            else settings.retention_days
        )
        self.max_deletes = (
            max_deletes if max_deletes is not None else settings.retention_max_deletes
        )

    def run(self, dry_run: bool = False) -> RetentionResult:
        """Run a retention pass.

        Logs ``scanned``, candidate IDs, and the final deleted count. In
        dry-run mode no rows are removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        cutoff_iso = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        result = RetentionResult(
            dry_run=dry_run,
            cutoff_iso=cutoff_iso,
            retention_days=self.retention_days,
            max_deletes=self.max_deletes,
        )

        con = sqlite3.connect(self.db_path)
        try:
            con.row_factory = sqlite3.Row
            # Enable cascades for any FKs that DO declare ON DELETE CASCADE
            # (e.g. embedding_metadata -> embeddings).
            con.execute("PRAGMA foreign_keys = ON")

            # Find candidates. Articles with NULL published_at are kept —
            # we can't tell if they're old or just not parsed, and the
            # design doc only commits to time-based deletion.
            cur = con.execute(
                "SELECT id, url, published_at FROM articles "
                "WHERE published_at IS NOT NULL AND published_at < ? "
                "ORDER BY published_at ASC LIMIT ?",
                (cutoff_iso, self.max_deletes),
            )
            rows = cur.fetchall()
            result.scanned = len(rows)
            result.candidate_ids = [int(r["id"]) for r in rows]

            logger.info(
                "Retention scan: cutoff=%s days=%d max=%d -> %d candidate(s) %s",
                cutoff_iso,
                self.retention_days,
                self.max_deletes,
                result.scanned,
                result.candidate_ids[:20],
            )

            if not result.candidate_ids:
                return result

            if dry_run:
                logger.info(
                    "Retention dry-run: would delete %d article(s); no rows committed",
                    len(result.candidate_ids),
                )
                return result

            # Live delete. Embeddings store article id as TEXT in content_id
            # for content_type='article', so cast IDs to str for that match.
            placeholders = ",".join("?" for _ in result.candidate_ids)
            id_params = list(result.candidate_ids)
            id_str_params = [str(i) for i in result.candidate_ids]

            # 1. embedding_metadata via embeddings (CASCADE handles this when
            #    we delete the embeddings row — the FK already declares it).
            # 2. embeddings (no FK to articles in this schema, so manual).
            try:
                cur = con.execute(
                    f"DELETE FROM embeddings WHERE content_type='article' "
                    f"AND content_id IN ({placeholders})",
                    id_str_params,
                )
                result.deleted_embeddings = cur.rowcount or 0
            except sqlite3.OperationalError as exc:
                # Table may not exist on a fresh dev DB; non-fatal.
                logger.warning("Skipping embeddings delete: %s", exc)

            # 3. article_categories (no CASCADE in current schema)
            try:
                cur = con.execute(
                    f"DELETE FROM article_categories WHERE article_id IN ({placeholders})",
                    id_params,
                )
                result.deleted_article_categories = cur.rowcount or 0
            except sqlite3.OperationalError as exc:
                logger.warning("Skipping article_categories delete: %s", exc)

            # 4. Finally, the articles themselves.
            cur = con.execute(
                f"DELETE FROM articles WHERE id IN ({placeholders})",
                id_params,
            )
            result.deleted_articles = cur.rowcount or 0

            con.commit()
            logger.info(
                "Retention live run: deleted %d article(s), %d embedding(s), "
                "%d category-link(s)",
                result.deleted_articles,
                result.deleted_embeddings,
                result.deleted_article_categories,
            )
        except Exception:
            con.rollback()
            logger.exception("Retention run failed; rolling back")
            raise
        finally:
            con.close()

        return result


def run_retention_job() -> None:
    """Entry point for the APScheduler cron.

    Kept module-level so APScheduler can serialize it cleanly. Catches and
    logs everything — the scheduler must never raise into the event loop.
    """
    try:
        service = RetentionService()
        result = service.run(dry_run=False)
        logger.info(
            "Daily retention job complete: deleted=%d scanned=%d",
            result.deleted_articles,
            result.scanned,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Daily retention job crashed")
