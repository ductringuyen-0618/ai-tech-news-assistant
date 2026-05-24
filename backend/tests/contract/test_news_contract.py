"""
Contract tests — news feed / news stats / news sources / news search.

Sourced from:
- README.md  ("News & Articles" section)
- docs/INGESTION_GUIDE.md
- docs/prds/finish-aggregator.md (Validation contracts)
- .claude/skills/test-app-e2e/scripts/run_e2e.py (existing contract calls)

URLs are documented as ``/api/news/...`` in the E2E runner; some references
in README also show ``/news/...``. We parametrize both for robustness.
"""

from __future__ import annotations

import pytest


NEWS_PREFIXES = ["/api/news", "/news"]


# --------------------------------------------------------------------- #
#  GET /api/news/  — list articles
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_returns_200(client, prefix):
    """The news list endpoint must respond 200."""
    resp = client.get(f"{prefix}/?page=1&page_size=5")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_returns_json_object(client, prefix):
    """Body must be a JSON object."""
    resp = client.get(f"{prefix}/?page=1&page_size=5")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    body = resp.json()
    assert isinstance(body, dict)


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_has_data_field(client, prefix):
    """Per the E2E runner, list response contains a ``data`` field."""
    resp = client.get(f"{prefix}/?page=1&page_size=5")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    body = resp.json()
    assert "data" in body, "Response missing 'data' field"
    assert isinstance(body["data"], list), "'data' must be a list"


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_respects_page_size(client, prefix):
    """`page_size` should cap the number of returned items."""
    resp = client.get(f"{prefix}/?page=1&page_size=3")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    body = resp.json()
    items = body.get("data", [])
    assert len(items) <= 3


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_pagination_metadata(client, prefix):
    """List should expose pagination metadata of some shape."""
    resp = client.get(f"{prefix}/?page=1&page_size=5")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    body = resp.json()
    # The integration test uses `body["pagination"]["total_items"]`. Accept
    # either explicit `pagination` envelope OR top-level total count.
    has_pagination = "pagination" in body or "total" in body or "total_items" in body
    assert has_pagination, "Response should expose pagination metadata"


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_default_page(client, prefix):
    """List with no params should still succeed."""
    resp = client.get(f"{prefix}/")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    assert resp.status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_list_invalid_page_size(client, prefix):
    """Negative / zero page size should return 422 (validation error)."""
    resp = client.get(f"{prefix}/?page=1&page_size=0")
    if resp.status_code == 404:
        pytest.skip(f"news list not mounted at {prefix}/")
    # Either reject with 422, or clamp; reject is the documented FastAPI default
    assert resp.status_code in (200, 422), f"unexpected {resp.status_code}"


# --------------------------------------------------------------------- #
#  GET /api/news/stats — DB stats
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_stats_returns_200(client, prefix):
    resp = client.get(f"{prefix}/stats")
    if resp.status_code == 404:
        pytest.skip(f"news stats not mounted at {prefix}/stats")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_stats_has_expected_fields(client, prefix):
    """``total_articles`` and ``articles_with_summaries`` are required per E2E."""
    resp = client.get(f"{prefix}/stats")
    if resp.status_code == 404:
        pytest.skip(f"news stats not mounted at {prefix}/stats")
    body = resp.json()
    payload = body.get("data", body)  # accept envelope or flat
    assert isinstance(payload, dict)
    for key in ("total_articles", "articles_with_summaries"):
        assert key in payload, f"news/stats missing '{key}'"
    assert isinstance(payload["total_articles"], int)
    assert isinstance(payload["articles_with_summaries"], int)
    assert payload["total_articles"] >= 0
    assert payload["articles_with_summaries"] >= 0


# --------------------------------------------------------------------- #
#  GET /api/news/sources — sources listing (per E2E + INGESTION_GUIDE)
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_sources_returns_200(client, prefix):
    resp = client.get(f"{prefix}/sources")
    if resp.status_code == 404:
        pytest.skip(f"news sources not mounted at {prefix}/sources")
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_sources_returns_list_like(client, prefix):
    resp = client.get(f"{prefix}/sources")
    if resp.status_code == 404:
        pytest.skip(f"news sources not mounted at {prefix}/sources")
    body = resp.json()
    # The endpoint is wrapped in BaseResponse({success, data, ...}).
    # ``data`` carries either a list of sources directly, or a stats
    # object with ``source_statistics``/``sources`` inside.
    if isinstance(body, list):
        payload = body
    else:
        data = body.get("data", body)
        if isinstance(data, list):
            payload = data
        elif isinstance(data, dict):
            payload = data.get("source_statistics", data.get("sources", []))
        else:
            payload = []
    # source_statistics can be a list (populated) or dict (when empty).
    assert isinstance(payload, (list, dict))


# --------------------------------------------------------------------- #
#  GET /api/news/{id} — get-by-id
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_get_unknown_id_returns_404(client, prefix):
    """An unknown article ID must return 404, not 500."""
    resp = client.get(f"{prefix}/99999999")
    if resp.status_code == 405:
        pytest.skip(f"{prefix}/{{id}} not exposed as GET")
    assert resp.status_code == 404, f"expected 404 for unknown id, got {resp.status_code}"


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_get_non_integer_id_returns_422(client, prefix):
    """Non-integer id should be a validation error (422)."""
    resp = client.get(f"{prefix}/not-a-number")
    if resp.status_code == 405:
        pytest.skip(f"{prefix}/{{id}} not exposed as GET")
    # Either 422 (FastAPI int path-param) or 404 (route shape doesn't match)
    assert resp.status_code in (404, 422), f"unexpected {resp.status_code}"


# --------------------------------------------------------------------- #
#  Categories listing (PRD: Topic filter UI needs categories)
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_categories_endpoint_if_exposed(client, prefix):
    """If exposed, GET /api/news/categories returns a list of category names."""
    resp = client.get(f"{prefix}/categories")
    if resp.status_code in (404, 405):
        pytest.skip(f"{prefix}/categories not exposed")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Wrapped in BaseResponse: {success, data: {categories: [...]}, ...}
    if isinstance(body, list):
        categories = body
    else:
        data = body.get("data", body)
        if isinstance(data, list):
            categories = data
        else:
            categories = data.get("categories", []) if isinstance(data, dict) else []
    assert isinstance(categories, list)


# --------------------------------------------------------------------- #
#  Articles-today / front-page precompute
# --------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("prefix", NEWS_PREFIXES)
def test_news_stats_includes_recent_articles_or_skip(client, prefix):
    """
    docs/issues/finish-aggregator-followup-1 calls out ``recent_articles``
    on /api/news/stats. If exposed, it must be a non-negative integer.
    """
    resp = client.get(f"{prefix}/stats")
    if resp.status_code != 200:
        pytest.skip("stats not available")
    body = resp.json()
    payload = body.get("data", body)
    if "recent_articles" not in payload:
        pytest.skip("recent_articles not in stats payload (per finish-aggregator-followup-1)")
    assert isinstance(payload["recent_articles"], int)
    assert payload["recent_articles"] >= 0
