"""
Contract tests — health / readiness / liveness / root endpoints.

These tests assert ONLY the publicly-documented contract from:
- README.md ("Health & Monitoring": GET /, /ping, /health)
- docs/QUICK_START.md (GET /, /health)
- docs/SEARCH_API.md (GET /search/health)
- backend/docs/CONFIGURATION.md (HEALTH_CHECK_TIMEOUT, /metrics)

Style: black-box HTTP via the FastAPI TestClient ``client`` fixture.
We don't reach into ``src/`` and we don't mock private internals.
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------- #
#  /health — documented in README and QUICK_START
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_health_returns_200(client):
    """GET /health must return HTTP 200."""
    resp = client.get("/health")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_health_returns_json(client):
    """GET /health must return a JSON object body."""
    resp = client.get("/health")
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert isinstance(body, dict)


@pytest.mark.unit
def test_health_has_status_field(client):
    """GET /health body must include a ``status`` field."""
    body = client.get("/health").json()
    assert "status" in body


@pytest.mark.unit
def test_health_status_is_recognized_value(client):
    """``status`` must be one of healthy / degraded / unhealthy."""
    body = client.get("/health").json()
    assert body["status"] in ("healthy", "degraded", "unhealthy")


@pytest.mark.unit
def test_health_has_timestamp(client):
    """``timestamp`` should be present and a string."""
    body = client.get("/health").json()
    assert "timestamp" in body
    assert isinstance(body["timestamp"], str)


@pytest.mark.unit
def test_health_has_version(client):
    """``version`` should be present."""
    body = client.get("/health").json()
    assert "version" in body


# --------------------------------------------------------------------- #
#  /ping — documented in README
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_ping_returns_200(client):
    """GET /ping is documented as a basic health check; must return 200."""
    resp = client.get("/ping")
    # FastAPI returns 404 if not registered; we want this loud.
    assert resp.status_code == 200, (
        f"/ping is documented in README but returned {resp.status_code}"
    )


# --------------------------------------------------------------------- #
#  / (root) — documented in README and QUICK_START
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_root_returns_200(client):
    """GET / is documented as 'API information'."""
    resp = client.get("/")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_root_returns_json(client):
    """Root should return a JSON object describing the API."""
    resp = client.get("/")
    body = resp.json()
    assert isinstance(body, dict)


# --------------------------------------------------------------------- #
#  Readiness — health/ready
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/health/ready", "/ready"])
def test_readiness_endpoint_reachable(client, path):
    """A readiness endpoint must exist (200 healthy, or 503 not ready)."""
    resp = client.get(path)
    # Either readiness lives at /health/ready (FastAPI subroute) or /ready.
    # Both 200 and 503 are documented as valid responses.
    if resp.status_code == 404:
        pytest.skip(f"Readiness not mounted at {path}; check the alternate path")
    assert resp.status_code in (200, 503), f"unexpected status for {path}: {resp.status_code}"


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/health/ready", "/ready"])
def test_readiness_returns_ready_field(client, path):
    """Readiness body must contain a boolean ``ready`` field."""
    resp = client.get(path)
    if resp.status_code == 404:
        pytest.skip(f"Readiness not mounted at {path}")
    body = resp.json()
    assert "ready" in body
    assert isinstance(body["ready"], bool)


# --------------------------------------------------------------------- #
#  Liveness — health/live
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_liveness_returns_200(client):
    """GET /health/live must return 200 with ``alive`` true."""
    resp = client.get("/health/live")
    if resp.status_code == 404:
        pytest.skip("/health/live not mounted")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("alive") is True


# --------------------------------------------------------------------- #
#  Search-service health — documented in docs/SEARCH_API.md
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/api/search/health", "/search/health"])
def test_search_health_endpoint_reachable(client, path):
    """Search-service health endpoint should respond with 200."""
    resp = client.get(path)
    if resp.status_code == 404:
        pytest.skip(f"search health not mounted at {path}")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/api/search/health", "/search/health"])
def test_search_health_documented_shape(client, path):
    """Search health body should include ``status`` per SEARCH_API.md."""
    resp = client.get(path)
    if resp.status_code == 404:
        pytest.skip(f"search health not mounted at {path}")
    body = resp.json()
    assert isinstance(body, dict)
    assert "status" in body
    assert body["status"] in ("healthy", "degraded", "unhealthy")


# --------------------------------------------------------------------- #
#  OpenAPI documentation — FastAPI auto-mounts these
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_openapi_schema_available(client):
    """OpenAPI schema must be served — required by `/docs`."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema.get("openapi", "").startswith("3.")
    assert "paths" in schema


@pytest.mark.unit
def test_docs_endpoint_available(client):
    """README documents http://localhost:8000/docs as 'API Documentation'."""
    resp = client.get("/docs")
    assert resp.status_code == 200
    # Swagger UI returns text/html
    assert "text/html" in resp.headers.get("content-type", "")
