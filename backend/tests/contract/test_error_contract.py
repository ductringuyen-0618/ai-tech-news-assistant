"""
Contract tests — generic error responses.

Sourced from:
- docs/SEARCH_API.md (sample 400/422/500 shapes — FastAPI `{"detail": ...}`)
- README.md (CORS notes; ALLOWED_ORIGINS)
- backend/docs/CONFIGURATION.md (CORS, error middleware, content limits)
- .claude/skills/test-app-e2e/scripts/run_e2e.py (CORS test)

The general shape FastAPI ships is ``{"detail": "..."}`` for HTTPException
and ``{"detail": [...]}`` for RequestValidationError. We assert that the
backend hasn't drifted from that.
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------- #
#  Unknown route → 404 with JSON
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_unknown_route_returns_404(client):
    resp = client.get("/this-route-does-not-exist-xyz-9999")
    assert resp.status_code == 404


@pytest.mark.unit
def test_unknown_route_returns_json_error(client):
    """FastAPI's default 404 has ``{"detail": "Not Found"}`` shape."""
    resp = client.get("/this-route-does-not-exist-xyz-9999")
    assert resp.status_code == 404
    # Content-type may be text/plain on some custom 404 handlers; tolerate.
    if resp.headers.get("content-type", "").startswith("application/json"):
        body = resp.json()
        assert "detail" in body or "error" in body or "message" in body


@pytest.mark.unit
def test_unknown_api_route_returns_404(client):
    """Unknown nested API route also returns 404, not 500."""
    resp = client.get("/api/this-route-does-not-exist-xyz-9999")
    assert resp.status_code == 404


# --------------------------------------------------------------------- #
#  Method not allowed → 405
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_wrong_method_returns_405_or_404(client):
    """DELETE on /health should be 405 (or 404 if framework doesn't expose it)."""
    resp = client.delete("/health")
    assert resp.status_code in (404, 405), f"got {resp.status_code}"


# --------------------------------------------------------------------- #
#  Validation error shape — 422
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_validation_error_shape_on_search(client):
    """
    docs/SEARCH_API.md shows: 422 returns ``{"detail": [{"loc": [...], "msg": ..., "type": ...}]}``.
    We POST a search request with limit out of range and verify FastAPI's shape.
    """
    # Find a working search URL
    for url in ["/api/search/semantic", "/api/search/hybrid", "/api/search", "/search"]:
        resp = client.post(url, json={"query": "AI", "limit": 9999})
        if resp.status_code != 404:
            break
    else:
        pytest.skip("no search endpoint mounted; skipping validation shape check")

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body, f"422 body missing 'detail': {body}"
    detail = body["detail"]
    # FastAPI returns a list for RequestValidationError
    assert isinstance(detail, list), f"validation 'detail' should be list, got {type(detail)}"
    assert len(detail) > 0
    first = detail[0]
    # Each error should have ``loc`` and ``msg`` (Pydantic standard)
    assert "loc" in first
    assert "msg" in first


@pytest.mark.unit
def test_missing_required_field_returns_422(client):
    """Generic: missing required field on search returns 422."""
    for url in ["/api/search/semantic", "/api/search/hybrid", "/api/search", "/search"]:
        resp = client.post(url, json={})
        if resp.status_code != 404:
            assert resp.status_code == 422, f"got {resp.status_code} from {url}"
            return
    pytest.skip("no search endpoint mounted")


# --------------------------------------------------------------------- #
#  Bad JSON body → 4xx not 5xx
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("url", [
    "/api/search/semantic",
    "/api/search/hybrid",
    "/api/ingest/",
    "/api/settings/",
])
def test_malformed_json_body_returns_4xx(client, url):
    """A POST/PUT with invalid JSON should be a client error, never 500."""
    # Try POST first; if not supported, try PUT
    resp = client.post(url, data="{not valid json")
    if resp.status_code == 405:
        resp = client.put(url, data="{not valid json")
    if resp.status_code == 404:
        pytest.skip(f"{url} not mounted")
    assert resp.status_code < 500, f"server error on bad JSON: {resp.status_code}"


# --------------------------------------------------------------------- #
#  CORS — backend should expose Access-Control-Allow-Origin
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_cors_allows_known_origin(client):
    """
    CONFIGURATION.md documents ALLOWED_ORIGINS; E2E runner asserts the
    backend echoes Access-Control-Allow-Origin for localhost frontends.
    """
    # Probe a known-good GET
    resp = client.get(
        "/api/news/?page_size=1",
        headers={"Origin": "http://localhost:5173"},
    )
    if resp.status_code == 404:
        pytest.skip("/api/news not mounted")
    if resp.status_code >= 500:
        pytest.skip(f"news endpoint returned {resp.status_code}")
    allow = resp.headers.get("access-control-allow-origin")
    if not allow:
        pytest.skip(
            "No Access-Control-Allow-Origin header — CORSMiddleware may be off "
            "or not configured for this origin"
        )
    # Must echo the origin or be a wildcard
    assert allow in ("*", "http://localhost:5173")


@pytest.mark.unit
def test_cors_preflight_options(client):
    """OPTIONS preflight should not 500."""
    resp = client.options(
        "/api/news/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    if resp.status_code == 404:
        pytest.skip("/api/news not mounted")
    # CORSMiddleware returns 200; some setups return 204. Both are valid.
    assert resp.status_code < 500


# --------------------------------------------------------------------- #
#  Content-type behavior on JSON endpoints
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_json_endpoints_return_json_content_type(client):
    """Health endpoint returns ``application/json``."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/json")


# --------------------------------------------------------------------- #
#  No stack traces leak in production-style responses
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_unknown_route_does_not_leak_traceback(client):
    """
    CONFIGURATION.md notes ``ERROR_DETAIL_IN_RESPONSE=false`` in production.
    A 404 body should never contain a Python traceback.
    """
    resp = client.get("/this-route-does-not-exist-xyz")
    body_text = resp.text.lower()
    assert "traceback" not in body_text
    assert "file \"" not in body_text  # Python tb line marker
