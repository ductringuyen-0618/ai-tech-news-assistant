"""
Admin Routes
============

Operator-facing endpoints for manual maintenance.

Currently exposes:
- ``POST /api/admin/retention/run?dry_run=<bool>`` -- trigger the retention
  service on demand. Useful for the first prod run (always do
  ``dry_run=true`` first), and as the hook used by the E2E test suite to
  verify retention without waiting for the daily cron.
- ``POST /api/admin/wipe?confirm=WIPE`` -- destructive: delete every row in
  ``articles``, ``embeddings``, ``embedding_metadata`` and
  ``article_categories``. Used by ``scripts/reset_data.sh`` to reset a
  deploy to a clean state. Refuses to do anything unless the literal
  string ``WIPE`` is passed; this is a deliberate, in-the-loop guardrail
  to make accidental hits via curl history or browser autocomplete
  obvious.
- ``POST /api/admin/ingest?dry_run=<bool>`` -- (Mission daily-ingestion M3)
  trigger the daily ingestion pipeline on demand. Returns the full
  :class:`DailyIngestionReport` so the caller (frontend dashboard,
  GitHub Actions workflow, on-call operator) can see exactly what
  happened. Gated by an ``X-Admin-Token`` HMAC header check against the
  ``ADMIN_TOKEN`` env var; if that env var is unset the endpoint
  returns 503 rather than silently allowing anyone in.
- ``GET  /api/admin/ingestion/health`` -- (M4) the latest ingestion
  run plus a 7-day trend, read from the ``ingestion_runs`` audit table
  the orchestrator writes after every run.

Auth model
----------
The retention/wipe routes pre-date the daily-ingestion mission and rely
on the upstream reverse-proxy / firewall for protection. The new
ingestion routes use a stupid-simple shared-secret check:
``X-Admin-Token`` header must HMAC-equal the ``ADMIN_TOKEN`` env var.
No user table, no JWT, no session -- this is an internal operator
endpoint, not a user-facing API.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from ...core.config import get_settings
from ...services.daily_ingestion_orchestrator import (
    DailyIngestionReport,
    run_daily_ingestion,
)
from ...services.retention_service import RetentionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])




# --------------------------------------------------------------------- #
#  Auth (Mission daily-ingestion M3)
# --------------------------------------------------------------------- #


def require_admin_token(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> str:
    """Constant-time compare ``X-Admin-Token`` against ``ADMIN_TOKEN``.

    Returns the validated token on success. Raises:

    * 503 when ``ADMIN_TOKEN`` is unset on the server -- this is the
      "endpoint disabled" state. Prevents the failure mode where a
      missing env var silently makes every request succeed.
    * 401 when the header is missing or does not match.

    The compare uses :func:`hmac.compare_digest` so a timing attack
    cannot leak the token byte-by-byte.
    """
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints disabled (ADMIN_TOKEN not configured)",
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Token header",
        )
    return x_admin_token


# --------------------------------------------------------------------- #
#  Retention + wipe routes (pre-existing)
# --------------------------------------------------------------------- #


@router.post("/retention/run")
async def run_retention(
    dry_run: bool = Query(
        default=False,
        description=(
            "If true, log/return what would be deleted without committing. "
            "Recommended for the first call against a fresh DB."
        ),
    ),
) -> Dict[str, Any]:
    """Trigger a retention pass on demand."""
    try:
        service = RetentionService()
        result = service.run(dry_run=dry_run)
        return {"status": "ok", "data": result.to_dict()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual retention run failed")
        raise HTTPException(
            status_code=500,
            detail=f"Retention run failed: {exc}",
        )


@router.post("/wipe")
async def wipe_database(
    confirm: str = Query(
        default="",
        description=(
            "Must be the literal string 'WIPE' for the call to proceed. "
            "Anything else returns 400 without touching the DB."
        ),
    ),
) -> Dict[str, Any]:
    """Hard-delete every article and its dependent rows.

    Idempotent -- running on an already-empty DB returns zero counts and
    leaves tables in place. Tables that don't exist on this DB are
    skipped rather than crashing, so the call also works on a fresh
    install before the first ingest.
    """
    if confirm != "WIPE":
        raise HTTPException(
            status_code=400,
            detail=(
                "Refusing to wipe: query param 'confirm' must be the "
                "literal string 'WIPE'."
            ),
        )

    settings = get_settings()
    db_path = settings.get_database_file_path()

    counts: Dict[str, int] = {
        "articles": 0,
        "embeddings": 0,
        "embedding_metadata": 0,
        "article_categories": 0,
    }

    con = sqlite3.connect(db_path)
    try:
        # CASCADE on declared FKs (embedding_metadata -> embeddings)
        con.execute("PRAGMA foreign_keys = ON")

        # Order matters: dependents first, then articles. Each table is
        # wrapped in its own try so a missing table on a fresh DB is a
        # warning, not a 500. Mirrors the pattern in RetentionService.
        for table in (
            "embedding_metadata",
            "embeddings",
            "article_categories",
            "articles",
        ):
            try:
                cur = con.execute(f"DELETE FROM {table}")
                counts[table] = cur.rowcount or 0
            except sqlite3.OperationalError as exc:
                logger.warning("Skipping %s during wipe: %s", table, exc)

        con.commit()
        logger.warning(
            "Admin WIPE complete: articles=%d embeddings=%d "
            "embedding_metadata=%d article_categories=%d (db=%s)",
            counts["articles"],
            counts["embeddings"],
            counts["embedding_metadata"],
            counts["article_categories"],
            db_path,
        )
    except Exception:
        con.rollback()
        logger.exception("Admin WIPE failed; rolling back")
        raise HTTPException(status_code=500, detail="Wipe failed; see logs")
    finally:
        con.close()

    return {
        "status": "ok",
        "data": {
            "db_path": db_path,
            "deleted": counts,
            "total_deleted": sum(counts.values()),
        },
    }


# --------------------------------------------------------------------- #
#  Daily ingestion trigger (Mission daily-ingestion M3)
# --------------------------------------------------------------------- #


@router.post("/ingest")
async def trigger_ingestion(
    _: str = Depends(require_admin_token),
    dry_run: bool = Query(
        default=False,
        description=(
            "If true, every phase counts its work-set but writes nothing. "
            "Used to smoke-test the pipeline without consuming Ollama / "
            "Groq budget."
        ),
    ),
    summarize: bool = Query(default=True),
    embed: bool = Query(default=True),
    extract_entities: bool = Query(default=True),
) -> Dict[str, Any]:
    """Trigger a daily ingestion run on demand.

    Returns the full :class:`DailyIngestionReport` (per-phase counts,
    durations, first-5 error strings, ``health_status``). Returns the
    dict form because :class:`DailyIngestionReport` is a dataclass, not
    a Pydantic model -- :func:`fastapi.encoders.jsonable_encoder` would
    work, but the dataclass already exposes a ``to_dict`` method we can
    just call.

    Phases toggle on/off via the corresponding query flags; the
    defaults match the production cron job.
    """
    settings = get_settings()
    db_path = settings.get_database_file_path()
    report = await run_daily_ingestion(
        db_path,
        summarize=summarize,
        embed=embed,
        extract_entities=extract_entities,
        dry_run=dry_run,
    )
    return report.to_dict()


# --------------------------------------------------------------------- #
#  Ingestion health (Mission daily-ingestion M4)
# --------------------------------------------------------------------- #


def _read_latest_ingestion_run(db_path: str) -> Optional[Dict[str, Any]]:
    """Return the most recent row from ``ingestion_runs`` as a dict,
    or ``None`` if the table is empty / missing.

    The orchestrator creates the table on every run; we tolerate its
    absence here in case the health endpoint is hit before any run
    has ever completed.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT id, started_at, finished_at, total_duration_ms,
                       health_status, dry_run, report_json
                FROM ingestion_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row is None:
                return None
            return _row_to_run_dict(row)
    except sqlite3.OperationalError:
        # Table missing -- no run has ever completed.
        return None


def _read_recent_ingestion_runs(
    db_path: str, *, days: int = 7
) -> List[Dict[str, Any]]:
    """Return up to ``days`` most recent runs (one per calendar day,
    keeping the latest for each day) so callers get a stable trend
    series rather than every run.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # For each day, pick the row with the newest started_at.
            # This lets multiple runs/day collapse to the latest one in
            # the trend view without obscuring the overall picture.
            cur = conn.execute(
                """
                SELECT id, started_at, finished_at, total_duration_ms,
                       health_status, dry_run, report_json
                FROM ingestion_runs
                WHERE started_at >= ?
                ORDER BY started_at DESC
                """,
                (cutoff,),
            )
            rows = [_row_to_run_dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []

    # Bucket by date string, keep newest per day.
    by_day: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        day = (r.get("started_at") or "")[:10]
        if not day:
            continue
        if day not in by_day:
            by_day[day] = r
    return sorted(
        by_day.values(), key=lambda r: r.get("started_at") or "", reverse=True
    )


def _row_to_run_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert an ``ingestion_runs`` row into the API shape."""
    try:
        report = json.loads(row["report_json"]) if row["report_json"] else None
    except (TypeError, ValueError):
        report = None
    total_articles = 0
    if report and isinstance(report.get("phases"), list):
        for p in report["phases"]:
            if p.get("name") == "fetch":
                total_articles = int(p.get("processed") or 0)
                break
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "total_duration_ms": row["total_duration_ms"],
        "health_status": row["health_status"],
        "dry_run": bool(row["dry_run"]),
        "report": report,
        "total_articles_fetched": total_articles,
    }


@router.get("/ingestion/health")
async def ingestion_health(
    _: str = Depends(require_admin_token),
) -> Dict[str, Any]:
    """Return the latest ingestion run + a 7-day trend.

    Response shape::

        {
            "latest": { ...full DailyIngestionReport row... } | None,
            "trend": [ {date, status, started_at, total_articles}, ... ],
            "overall": "green" | "yellow" | "red" | "unknown"
        }

    "overall" reflects the latest run's health_status, or "unknown" if
    no runs have completed yet.
    """
    settings = get_settings()
    db_path = settings.get_database_file_path()

    latest = _read_latest_ingestion_run(db_path)
    recent = _read_recent_ingestion_runs(db_path, days=7)

    trend = [
        {
            "date": (r.get("started_at") or "")[:10],
            "status": r.get("health_status") or "unknown",
            "started_at": r.get("started_at"),
            "total_articles": r.get("total_articles_fetched", 0),
        }
        for r in recent
    ]

    overall = (latest or {}).get("health_status", "unknown")

    return {
        "latest": latest,
        "trend": trend,
        "overall": overall,
    }
