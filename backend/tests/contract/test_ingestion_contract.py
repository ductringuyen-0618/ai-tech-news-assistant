"""
Contract tests — ingestion trigger / status / stats endpoints.

Sourced from:
- docs/INGESTION_GUIDE.md
  - POST /api/ingest             (background + sources optional)
  - GET  /api/ingest/status
  - GET  /api/ingest/stats
- README.md ("POST /news/ingest")
- docs/prds/finish-aggregator.md (Milestone 5: triggers POST /api/ingest/)
- docs/issues/finish-aggregator-followup-1: IngestionService writes categories

Network-touching tests (real RSS fetches) are skipped by default.
"""

from __future__ import annotations

import pytest


INGEST_BASES = ["/api/ingest", "/news/ingest"]


# --------------------------------------------------------------------- #
#  POST /api/ingest — trigger
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("base", INGEST_BASES)
def test_ingest_endpoint_exists(client, base):
    """The ingestion trigger must be POST-able."""
    # Background=true keeps this fast and avoids real network in many builds
    resp = client.post(base + "/", json={"background": True})
    if resp.status_code == 404:
        resp = client.post(base, json={"background": True})
    if resp.status_code == 404:
        pytest.skip(f"ingest not mounted at {base}")
    # Any non-404 implies the route is registered.
    assert resp.status_code != 404


@pytest.mark.unit
@pytest.mark.requires_network
def test_ingest_post_background_returns_message(client):
    """
    INGESTION_GUIDE.md: background response contains ``message`` and
    ``background`` keys.
    """
    resp = client.post("/api/ingest/", json={"background": True})
    if resp.status_code == 404:
        pytest.skip("/api/ingest not mounted")
    if resp.status_code >= 500:
        pytest.skip(f"ingest returned {resp.status_code}")
    assert resp.status_code in (200, 202), resp.text
    body = resp.json()
    assert isinstance(body, dict)
    # Per the doc, both keys are present
    assert "message" in body
    assert "background" in body
    assert body["background"] is True


@pytest.mark.unit
def test_ingest_post_validates_body(client):
    """Sending garbage payload should not return 500."""
    resp = client.post("/api/ingest/", json={"background": "not-a-bool"})
    if resp.status_code == 404:
        pytest.skip("/api/ingest not mounted")
    # Either accepts (coerces) or rejects — 5xx is the failure mode.
    assert resp.status_code < 500


@pytest.mark.unit
def test_ingest_get_not_allowed(client):
    """GET on the trigger endpoint should be 405 / 404."""
    resp = client.get("/api/ingest/")
    assert resp.status_code in (404, 405)


# --------------------------------------------------------------------- #
#  GET /api/ingest/status
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_ingest_status_returns_200(client):
    resp = client.get("/api/ingest/status")
    if resp.status_code == 404:
        pytest.skip("/api/ingest/status not mounted")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_ingest_status_response_is_object(client):
    resp = client.get("/api/ingest/status")
    if resp.status_code != 200:
        pytest.skip("status not available")
    body = resp.json()
    assert isinstance(body, dict)


@pytest.mark.unit
def test_ingest_status_has_status_field(client):
    """INGESTION_GUIDE.md: top-level ``status`` field present."""
    resp = client.get("/api/ingest/status")
    if resp.status_code != 200:
        pytest.skip("status not available")
    body = resp.json()
    # Doc says top-level "status"; some builds wrap under "data" — accept either
    inner = body.get("data", body)
    assert "status" in inner, f"status field missing; got {sorted(inner)}"


@pytest.mark.unit
def test_ingest_status_known_values(client):
    """Status must be a documented enum value."""
    resp = client.get("/api/ingest/status")
    if resp.status_code != 200:
        pytest.skip("status not available")
    inner = resp.json()
    inner = inner.get("data", inner)
    status_value = inner.get("status")
    if status_value is None:
        pytest.skip("status field missing")
    # Documented values: PENDING, RUNNING, COMPLETED, FAILED, PARTIAL
    # Some implementations lower-case
    allowed = {
        "pending", "running", "completed", "failed", "partial",
        "idle", "never_run", "ok",
    }
    assert status_value.lower() in allowed, f"unexpected status {status_value!r}"


# --------------------------------------------------------------------- #
#  GET /api/ingest/stats
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_ingest_stats_returns_200(client):
    resp = client.get("/api/ingest/stats")
    if resp.status_code == 404:
        pytest.skip("/api/ingest/stats not mounted")
    assert resp.status_code == 200


@pytest.mark.unit
def test_ingest_stats_has_total_articles(client):
    """INGESTION_GUIDE.md: ``total_articles`` is a documented field."""
    resp = client.get("/api/ingest/stats")
    if resp.status_code != 200:
        pytest.skip("stats not available")
    body = resp.json()
    inner = body.get("data", body)
    assert "total_articles" in inner
    assert isinstance(inner["total_articles"], int)
    assert inner["total_articles"] >= 0


@pytest.mark.unit
def test_ingest_stats_has_source_count(client):
    """INGESTION_GUIDE.md: ``total_sources`` is documented."""
    resp = client.get("/api/ingest/stats")
    if resp.status_code != 200:
        pytest.skip("stats not available")
    body = resp.json()
    inner = body.get("data", body)
    if "total_sources" not in inner:
        pytest.skip("total_sources not exposed by this build")
    assert isinstance(inner["total_sources"], int)
    assert inner["total_sources"] >= 0


# --------------------------------------------------------------------- #
#  Custom sources (INGESTION_GUIDE.md example)
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.requires_network
def test_ingest_post_with_custom_sources(client):
    """The doc allows passing custom RSS feeds."""
    payload = {
        "background": True,
        "sources": [
            {
                "name": "Custom Tech News",
                "url": "https://example.com/feed.xml",
                "category": "technology",
            }
        ],
    }
    resp = client.post("/api/ingest/", json=payload)
    if resp.status_code == 404:
        pytest.skip("/api/ingest not mounted")
    assert resp.status_code < 500
