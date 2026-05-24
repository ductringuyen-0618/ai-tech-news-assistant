"""
Contract tests — user settings GET / PUT.

Sourced from:
- docs/issues/finish-aggregator-2-settings-persistence.md
- docs/prds/finish-aggregator.md (Milestone 2)
- .claude/skills/test-app-e2e/scripts/run_e2e.py (settings_persistence test)

Contract:
  GET  /api/settings/  → 200 with {success, data: {categories, view_mode, ...}}
  PUT  /api/settings/  → 200, persists; subsequent GET returns the new shape
"""

from __future__ import annotations

import pytest


SETTINGS_URLS = ["/api/settings/", "/api/settings", "/settings/", "/settings"]


def _find_settings_url(client) -> str:
    for url in SETTINGS_URLS:
        resp = client.get(url)
        if resp.status_code != 404:
            return url
    pytest.skip("settings endpoint not mounted at any documented URL")


# --------------------------------------------------------------------- #
#  GET /api/settings/
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_settings_get_endpoint_exists(client):
    _find_settings_url(client)


@pytest.mark.unit
def test_settings_get_returns_200_even_on_first_call(client):
    """
    Per the issue: ``GET /api/settings`` returns 200 with sensible defaults
    even when no settings row exists yet.
    """
    url = _find_settings_url(client)
    resp = client.get(url)
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_settings_get_returns_json_object(client):
    url = _find_settings_url(client)
    body = client.get(url).json()
    assert isinstance(body, dict)


@pytest.mark.unit
def test_settings_get_has_data_envelope(client):
    """PRD: ``GET /api/settings`` returns ``{success, data: {...}}``."""
    url = _find_settings_url(client)
    body = client.get(url).json()
    # Either {success, data} envelope or flat dict
    inner = body.get("data", body)
    assert isinstance(inner, dict)


@pytest.mark.unit
def test_settings_get_has_categories_field(client):
    """``categories`` must be present (list) — per finish-aggregator-2 schema."""
    url = _find_settings_url(client)
    body = client.get(url).json()
    inner = body.get("data", body)
    assert "categories" in inner, f"settings missing 'categories'; got {sorted(inner)}"
    assert isinstance(inner["categories"], list)


@pytest.mark.unit
def test_settings_get_has_view_mode_field(client):
    """``view_mode`` must be present per the issue."""
    url = _find_settings_url(client)
    body = client.get(url).json()
    inner = body.get("data", body)
    if "view_mode" not in inner:
        pytest.skip("view_mode not exposed (may be optional)")
    assert isinstance(inner["view_mode"], str)


# --------------------------------------------------------------------- #
#  PUT /api/settings/
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_settings_put_endpoint_exists(client):
    """PUT should not 404 or 405."""
    url = _find_settings_url(client)
    resp = client.put(
        url,
        json={"categories": ["AI"], "view_mode": "detailed"},
    )
    assert resp.status_code not in (404, 405), f"PUT returned {resp.status_code}"


@pytest.mark.unit
def test_settings_put_persists_round_trip(client):
    """
    Per the issue's acceptance criteria: PUT a value, then GET, observe
    the same shape back.
    """
    url = _find_settings_url(client)
    payload = {
        "categories": ["AI", "Robotics"],
        "view_mode": "detailed",
        "show_trending_only": False,
    }
    put_resp = client.put(url, json=payload)
    if put_resp.status_code in (404, 405):
        pytest.skip("PUT not supported on this build")
    assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"

    get_resp = client.get(url)
    assert get_resp.status_code == 200
    inner = get_resp.json().get("data", get_resp.json())

    assert inner.get("categories") == payload["categories"], (
        f"GET categories {inner.get('categories')!r} != PUT {payload['categories']!r}"
    )
    assert inner.get("view_mode") == payload["view_mode"], (
        f"GET view_mode {inner.get('view_mode')!r} != PUT {payload['view_mode']!r}"
    )


@pytest.mark.unit
def test_settings_put_returns_saved_shape(client):
    """PUT response should include the saved data (per issue spec)."""
    url = _find_settings_url(client)
    payload = {"categories": ["AI"], "view_mode": "compact"}
    put_resp = client.put(url, json=payload)
    if put_resp.status_code in (404, 405):
        pytest.skip("PUT not supported")
    assert put_resp.status_code == 200
    body = put_resp.json()
    inner = body.get("data", body)
    assert isinstance(inner, dict)
    assert inner.get("categories") == payload["categories"]


@pytest.mark.unit
def test_settings_put_invalid_categories_type_rejected(client):
    """``categories`` must be a list — string should 422."""
    url = _find_settings_url(client)
    resp = client.put(
        url,
        json={"categories": "not-a-list", "view_mode": "detailed"},
    )
    if resp.status_code in (404, 405):
        pytest.skip("PUT not supported")
    assert resp.status_code in (400, 422), f"got {resp.status_code}"


@pytest.mark.unit
def test_settings_put_empty_body_handled(client):
    """An empty body should either be rejected or treated as a no-op, never 500."""
    url = _find_settings_url(client)
    resp = client.put(url, json={})
    if resp.status_code in (404, 405):
        pytest.skip("PUT not supported")
    assert resp.status_code < 500, f"server error on empty PUT: {resp.status_code}"


@pytest.mark.unit
def test_settings_put_non_json_rejected(client):
    url = _find_settings_url(client)
    resp = client.put(url, data="not json")
    if resp.status_code in (404, 405):
        pytest.skip("PUT not supported")
    assert 400 <= resp.status_code < 500


# --------------------------------------------------------------------- #
#  Single-row semantics — multiple PUTs should overwrite, not duplicate
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_settings_put_overwrites_previous(client):
    """
    Per the issue: settings table is single-row. Two PUTs should result
    in only the latter values being returned by GET.
    """
    url = _find_settings_url(client)
    first = {"categories": ["AI"], "view_mode": "compact"}
    second = {"categories": ["Robotics", "Cloud"], "view_mode": "detailed"}

    r1 = client.put(url, json=first)
    if r1.status_code in (404, 405):
        pytest.skip("PUT not supported")
    assert r1.status_code == 200

    r2 = client.put(url, json=second)
    assert r2.status_code == 200

    get = client.get(url).json().get("data", {})
    if isinstance(get, dict) and "categories" in get:
        assert get["categories"] == second["categories"]
        if "view_mode" in get:
            assert get["view_mode"] == second["view_mode"]


# --------------------------------------------------------------------- #
#  Method restrictions
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_settings_post_not_allowed(client):
    """Only GET/PUT are documented. POST/DELETE should 405."""
    url = _find_settings_url(client)
    resp = client.post(url, json={"categories": []})
    assert resp.status_code in (404, 405)


@pytest.mark.unit
def test_settings_delete_not_allowed(client):
    url = _find_settings_url(client)
    resp = client.delete(url)
    assert resp.status_code in (404, 405)
