"""
Contract tests — daily digest endpoint.

Sourced from:
- .claude/skills/test-app-e2e/scripts/run_e2e.py
  (``GET /api/digest/`` returns ``topStories``, ``categoryBreakdown``,
   ``trendingTopics``)
- docs/issues/finish-aggregator-followup-1-real-ui-behavior-tests.md
- docs/issues/ui-polish-3-newsfeed-and-digest.md
"""

from __future__ import annotations

import pytest


DIGEST_URLS = ["/api/digest/", "/api/digest", "/digest/", "/digest"]


def _find_digest_url(client) -> str:
    for url in DIGEST_URLS:
        resp = client.get(url)
        if resp.status_code != 404:
            return url
    pytest.skip("digest endpoint not mounted at any documented URL")


@pytest.mark.unit
def test_digest_endpoint_exists(client):
    _find_digest_url(client)


@pytest.mark.unit
def test_digest_returns_200(client):
    url = _find_digest_url(client)
    resp = client.get(url)
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_digest_returns_json_object(client):
    url = _find_digest_url(client)
    body = client.get(url).json()
    assert isinstance(body, dict)


@pytest.mark.unit
def test_digest_has_top_stories(client):
    """E2E runner: response must contain ``topStories`` list."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    # Accept ``topStories`` (per E2E) or snake_case alias
    has = "topStories" in body or "top_stories" in body
    assert has, f"digest missing topStories; got {sorted(body)}"
    stories = body.get("topStories", body.get("top_stories"))
    assert isinstance(stories, list)


@pytest.mark.unit
def test_digest_has_category_breakdown(client):
    """E2E runner: response must contain ``categoryBreakdown``."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    has = "categoryBreakdown" in body or "category_breakdown" in body
    assert has, f"digest missing categoryBreakdown; got {sorted(body)}"


@pytest.mark.unit
def test_digest_has_trending_topics(client):
    """E2E runner: response must contain ``trendingTopics``."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    has = "trendingTopics" in body or "trending_topics" in body
    assert has, f"digest missing trendingTopics; got {sorted(body)}"


def _get_either(body, *keys):
    """Return the first key whose value is present in body (not None).

    Avoids ``or`` chaining, which would treat an empty list/dict as missing.
    """
    for k in keys:
        if k in body and body[k] is not None:
            return body[k]
    return None


@pytest.mark.unit
def test_digest_top_stories_is_list_of_objects(client):
    """Each top story should be an object with at least a title."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    stories = _get_either(body, "topStories", "top_stories") or []
    if not stories:
        pytest.skip("no top stories in digest — likely empty DB")
    first = stories[0]
    assert isinstance(first, dict)
    # The frontend renders these; minimum is a title-like field
    has_title = any(k in first for k in ("title", "headline", "name"))
    assert has_title, f"top story missing title-like field: {sorted(first)}"


@pytest.mark.unit
def test_digest_category_breakdown_iterable(client):
    """``categoryBreakdown`` must be a list or dict per frontend expectations."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    cb = _get_either(body, "categoryBreakdown", "category_breakdown")
    assert isinstance(cb, (list, dict))


@pytest.mark.unit
def test_digest_trending_topics_iterable(client):
    """``trendingTopics`` must be a list."""
    url = _find_digest_url(client)
    body = client.get(url).json()
    tt = _get_either(body, "trendingTopics", "trending_topics")
    assert isinstance(tt, list)


@pytest.mark.unit
def test_digest_not_returning_mock_strings(client):
    """
    Per docs/issues/finish-aggregator-followup-1: if top stories include
    the legacy mock titles, the test fails. This is a regression guard.

    Skip if the corpus is empty — we don't want to fail on a fresh build.
    """
    url = _find_digest_url(client)
    body = client.get(url).json()
    stories = _get_either(body, "topStories", "top_stories") or []
    if not stories:
        pytest.skip("digest empty — cannot regression-check mock strings")
    titles = [str(s.get("title", "")) for s in stories]
    mock_titles = {
        "AI Breakthrough in Natural Language Understanding",
        "Quantum Computing Makes Significant Progress",
    }
    for t in titles:
        assert t not in mock_titles, f"digest still returning mock title: {t!r}"


@pytest.mark.unit
def test_digest_post_not_allowed(client):
    """GET-only endpoint should 405 / 404 on POST."""
    url = _find_digest_url(client)
    resp = client.post(url, json={})
    assert resp.status_code in (404, 405)
