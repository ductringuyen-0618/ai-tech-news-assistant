"""Integration tests for ``/api/admin/ingest`` + health endpoints.

Mission daily-ingestion M3 + M4:

1. ``test_ingest_missing_token_returns_401`` -- no ``X-Admin-Token``
   header -> 401.
2. ``test_ingest_wrong_token_returns_401`` -- non-matching token -> 401.
3. ``test_ingest_admin_token_unset_returns_503`` -- when the server
   has no ``ADMIN_TOKEN`` configured, all admin ingestion routes
   return 503. Prevents the silent-allow failure mode.
4. ``test_ingest_correct_token_runs_pipeline_dry_run`` -- valid token
   + ``?dry_run=true`` returns 200 and a valid ``DailyIngestionReport``
   shape (per-phase counts, health_status).
5. ``test_ingestion_health_returns_latest_run_and_trend`` -- the M4
   admin health endpoint returns the latest run dict + a trend list.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import admin as admin_module
from src.services.daily_ingestion_orchestrator import (
    DailyIngestionReport,
    PhaseReport,
)


# --------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------- #


@pytest.fixture
def client() -> TestClient:
    """Mount just the admin router for the test surface."""
    app = FastAPI()
    app.include_router(admin_module.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def _make_report(
    *, dry_run: bool = True, health: str = "green"
) -> DailyIngestionReport:
    """Build a canned :class:`DailyIngestionReport` for the route
    mock to return."""
    now = datetime.now(timezone.utc)
    phases = [
        PhaseReport(name="fetch", processed=3, failed=0, duration_ms=10),
        PhaseReport(name="summarize", processed=3, failed=0, duration_ms=15),
        PhaseReport(name="embed", processed=3, failed=0, duration_ms=12),
        PhaseReport(name="entity_extract", processed=3, failed=0, duration_ms=11),
    ]
    return DailyIngestionReport(
        started_at=now,
        finished_at=now,
        total_duration_ms=48,
        phases=phases,
        health_status=health,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------- #
#  Auth checks
# --------------------------------------------------------------------- #


def test_ingest_missing_token_returns_401(client, monkeypatch):
    """No ``X-Admin-Token`` header on a configured server -> 401."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-token-abc")
    res = client.post("/api/admin/ingest")
    assert res.status_code == 401
    assert "X-Admin-Token" in res.json().get("detail", "")


def test_ingest_wrong_token_returns_401(client, monkeypatch):
    """Token mismatch -> 401, regardless of the call payload."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-token-abc")
    res = client.post(
        "/api/admin/ingest",
        headers={"X-Admin-Token": "WRONG"},
    )
    assert res.status_code == 401


def test_ingest_admin_token_unset_returns_503(client, monkeypatch):
    """Server with no ``ADMIN_TOKEN`` configured -> 503.

    This is the "endpoint disabled" state; it must not allow
    anonymous access just because the operator forgot to set the env
    var.
    """
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    res = client.post(
        "/api/admin/ingest",
        headers={"X-Admin-Token": "anything"},
    )
    assert res.status_code == 503
    assert "ADMIN_TOKEN" in res.json().get("detail", "")


# --------------------------------------------------------------------- #
#  Happy path
# --------------------------------------------------------------------- #


def test_ingest_correct_token_runs_pipeline_dry_run(client, monkeypatch):
    """Valid token + ``?dry_run=true`` -> 200 + ``DailyIngestionReport``."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-token-abc")

    fake = _make_report(dry_run=True, health="green")

    async def fake_run(db_path, **kwargs):
        # The route forwards these as keyword args; confirm dry_run
        # came through.
        assert kwargs.get("dry_run") is True
        return fake

    monkeypatch.setattr(admin_module, "run_daily_ingestion", fake_run)

    res = client.post(
        "/api/admin/ingest?dry_run=true",
        headers={"X-Admin-Token": "test-token-abc"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["health_status"] == "green"
    assert body["dry_run"] is True
    assert {p["name"] for p in body["phases"]} == {
        "fetch", "summarize", "embed", "entity_extract"
    }
    assert body["total_duration_ms"] == 48


# --------------------------------------------------------------------- #
#  M4: admin health endpoint
# --------------------------------------------------------------------- #


def test_ingestion_health_returns_latest_run_and_trend(client, monkeypatch):
    """The M4 admin health endpoint returns ``{latest, trend, overall}``."""
    monkeypatch.setenv("ADMIN_TOKEN", "test-token-abc")

    canned_latest: Dict[str, Any] = {
        "id": 5,
        "started_at": "2026-05-13T05:00:00+00:00",
        "finished_at": "2026-05-13T05:01:00+00:00",
        "total_duration_ms": 60000,
        "health_status": "green",
        "dry_run": False,
        "report": {"phases": [{"name": "fetch", "processed": 7}]},
        "total_articles_fetched": 7,
    }
    canned_recent = [canned_latest]

    monkeypatch.setattr(
        admin_module, "_read_latest_ingestion_run", lambda _db: canned_latest
    )
    monkeypatch.setattr(
        admin_module,
        "_read_recent_ingestion_runs",
        lambda _db, *, days=7: canned_recent,
    )

    res = client.get(
        "/api/admin/ingestion/health",
        headers={"X-Admin-Token": "test-token-abc"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["overall"] == "green"
    assert body["latest"]["id"] == 5
    assert isinstance(body["trend"], list)
    assert body["trend"][0]["status"] == "green"
    assert body["trend"][0]["total_articles"] == 7
    assert body["trend"][0]["date"] == "2026-05-13"
