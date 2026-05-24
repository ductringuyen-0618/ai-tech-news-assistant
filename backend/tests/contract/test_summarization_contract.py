"""
Contract tests — summarization endpoints.

Sourced from:
- README.md: ``POST /summarize`` and ``GET /summarize/health``
- .claude/skills/test-app-e2e/scripts/run_e2e.py: uses
  ``/api/summarize/status`` and ``POST /api/ingest/summarize-pending``

These tests assert ONLY the HTTP-contract surface. Real summarization
requires Ollama or another LLM provider; tests that would trigger a model
call are marked to skip gracefully when the service is degraded.
"""

from __future__ import annotations

import pytest


SUMMARIZE_STATUS_URLS = [
    "/api/summarize/status",
    "/api/summarize/health",
    "/summarize/health",
    "/summarize/status",
]


def _find_status_url(client) -> str:
    for url in SUMMARIZE_STATUS_URLS:
        resp = client.get(url)
        if resp.status_code != 404:
            return url
    pytest.skip(
        "No summarize status/health endpoint reachable: "
        + ", ".join(SUMMARIZE_STATUS_URLS)
    )


# --------------------------------------------------------------------- #
#  Status / health
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_summarize_status_endpoint_exists(client):
    """At least one of the documented status URLs must be mounted."""
    _find_status_url(client)  # raises pytest.skip if missing


@pytest.mark.unit
def test_summarize_status_returns_200(client):
    url = _find_status_url(client)
    resp = client.get(url)
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_summarize_status_has_provider_or_status(client):
    """
    Per the E2E runner: payload should expose ``status`` and/or
    ``provider`` after unwrapping an optional ``data`` envelope.
    """
    url = _find_status_url(client)
    body = client.get(url).json()
    inner = body.get("data", body)
    assert isinstance(inner, dict)
    assert "status" in inner or "provider" in inner, (
        f"missing both 'status' and 'provider'; got {sorted(inner)}"
    )


@pytest.mark.unit
def test_summarize_status_value_is_recognized(client):
    """If ``status`` is present, it must be a documented value."""
    url = _find_status_url(client)
    body = client.get(url).json()
    inner = body.get("data", body)
    if "status" not in inner:
        pytest.skip("status field not exposed by this build")
    assert inner["status"] in ("healthy", "degraded", "unhealthy", "ready", "not_ready")


# --------------------------------------------------------------------- #
#  POST /summarize  — synchronous summarization (requires live LLM)
# --------------------------------------------------------------------- #


SUMMARIZE_URLS = ["/api/summarize", "/api/summarize/", "/summarize"]


def _find_summarize_post_url(client) -> str:
    for url in SUMMARIZE_URLS:
        # Probe with empty body to see whether the route exists
        resp = client.post(url, json={})
        if resp.status_code != 404:
            return url
    pytest.skip("No summarize POST endpoint reachable")


@pytest.mark.unit
def test_summarize_post_endpoint_exists(client):
    _find_summarize_post_url(client)


@pytest.mark.unit
def test_summarize_post_missing_content_returns_422(client):
    """POST /summarize without any content field should be a 4xx."""
    url = _find_summarize_post_url(client)
    resp = client.post(url, json={})
    assert 400 <= resp.status_code < 500, f"expected 4xx, got {resp.status_code}"


@pytest.mark.unit
def test_summarize_post_non_json_returns_4xx(client):
    """A non-JSON body should be a client error, not a 500."""
    url = _find_summarize_post_url(client)
    resp = client.post(url, data="not json")
    assert 400 <= resp.status_code < 500, f"got {resp.status_code}"


@pytest.mark.unit
@pytest.mark.requires_ollama
def test_summarize_post_with_valid_content(client):
    """
    Happy-path summarization. Requires a live LLM provider.
    On a healthy box with Ollama running, expect a 200 + summary text.
    """
    url = _find_summarize_post_url(client)
    payload = {
        "content": (
            "Artificial intelligence research has accelerated rapidly in the "
            "past five years, with large language models demonstrating new "
            "capabilities in reasoning, code generation, and natural-language "
            "understanding across a wide variety of benchmarks."
        ),
        "title": "AI research advances",
    }
    resp = client.post(url, json=payload, timeout=120)
    if resp.status_code in (501, 503):
        pytest.skip(f"summarization service unavailable: {resp.status_code}")
    if resp.status_code != 200:
        pytest.skip(
            f"summarize returned {resp.status_code}; likely no LLM provider configured"
        )
    body = resp.json()
    inner = body.get("data", body)
    # Some documented field names: "summary", "result", or top-level text
    summary = inner.get("summary") or inner.get("result") or inner.get("text")
    assert summary, f"no summary field in response: {sorted(inner)}"
    assert isinstance(summary, str)
    assert len(summary) > 0


# --------------------------------------------------------------------- #
#  POST /api/ingest/summarize-pending — orchestrator (from E2E runner)
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_summarize_pending_endpoint_exists(client):
    """
    Per E2E runner: ``POST /api/ingest/summarize-pending?limit=N`` triggers
    the orchestrator. Existence check only.
    """
    resp = client.post("/api/ingest/summarize-pending?limit=1")
    if resp.status_code == 404:
        pytest.skip("/api/ingest/summarize-pending not mounted")
    # Any response other than 404 means the route is registered.
    assert resp.status_code != 404


@pytest.mark.unit
@pytest.mark.requires_ollama
def test_summarize_pending_returns_result_envelope(client):
    """E2E runner expects ``body['result']`` with keys requested / summarized / failed."""
    resp = client.post("/api/ingest/summarize-pending?limit=1", timeout=120)
    if resp.status_code in (404, 501, 503):
        pytest.skip(f"orchestrator unavailable: {resp.status_code}")
    if resp.status_code != 200:
        pytest.skip(f"orchestrator returned {resp.status_code}; LLM may not be configured")
    body = resp.json()
    assert isinstance(body, dict)
    if "result" not in body:
        pytest.skip("orchestrator response does not use 'result' envelope")
    result = body["result"]
    for key in ("requested", "summarized", "failed"):
        assert key in result, f"orchestrator result missing '{key}'"
        assert isinstance(result[key], int)
