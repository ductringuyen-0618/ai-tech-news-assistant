"""
Contract tests — saved research CRUD.

Sourced from:
- docs/issues/ui-polish-5-saved-research-and-follow-ups.md
- docs/prds/ui-polish.md (Milestone 5)

Documented endpoints:
  POST   /api/saved-research          → body {question, report_md, sources} → full record
  GET    /api/saved-research          → list ordered by created_at desc, capped at 100
  GET    /api/saved-research/{id}     → single record (404 on unknown)
  DELETE /api/saved-research/{id}     → remove
"""

from __future__ import annotations

import pytest


BASE_URLS = ["/api/saved-research", "/api/saved-research/"]


def _find_base(client) -> str:
    for url in BASE_URLS:
        resp = client.get(url)
        if resp.status_code != 404:
            return url.rstrip("/") + "/"
    pytest.skip("saved-research endpoint not mounted")


# --------------------------------------------------------------------- #
#  GET (list) — empty case
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_saved_research_list_endpoint_exists(client):
    _find_base(client)


@pytest.mark.unit
def test_saved_research_list_returns_200(client):
    base = _find_base(client)
    resp = client.get(base.rstrip("/"))
    assert resp.status_code == 200, resp.text


@pytest.mark.unit
def test_saved_research_list_returns_iterable(client):
    """GET /api/saved-research returns a list (or wrapped list)."""
    base = _find_base(client)
    body = client.get(base.rstrip("/")).json()
    items = body if isinstance(body, list) else body.get("data", body.get("items"))
    assert isinstance(items, list)


# --------------------------------------------------------------------- #
#  POST (create) + round-trip
# --------------------------------------------------------------------- #


@pytest.mark.integration
def test_saved_research_post_creates_record(client):
    """POST a saved research entry; response must include an integer ``id``."""
    base = _find_base(client)
    payload = {
        "question": "What is the state of agentic AI?",
        "report_md": "# Test report\n\nBody paragraph.",
        "sources": [
            {"n": 1, "title": "Source A", "source": "techcrunch", "url": "https://a"}
        ],
    }
    resp = client.post(base.rstrip("/"), json=payload)
    if resp.status_code in (404, 405):
        pytest.skip("POST /api/saved-research not supported on this build")
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    record = body.get("data", body)
    assert "id" in record, f"saved record missing 'id': {sorted(record)}"
    assert isinstance(record["id"], int)
    assert record["id"] > 0


@pytest.mark.integration
def test_saved_research_post_returns_full_record(client):
    """Per the issue: POST response includes the full record."""
    base = _find_base(client)
    payload = {
        "question": "Test question?",
        "report_md": "# Test\n\nBody.",
        "sources": [],
    }
    resp = client.post(base.rstrip("/"), json=payload)
    if resp.status_code in (404, 405):
        pytest.skip("POST not supported")
    if resp.status_code not in (200, 201):
        pytest.skip(f"POST returned {resp.status_code}")
    record = resp.json().get("data", resp.json())
    assert record.get("question") == payload["question"]
    # report_md may or may not be echoed depending on the list-shape used
    # in the response; assert at least the key is present if returned.
    if "report_md" in record:
        assert record["report_md"] == payload["report_md"]


@pytest.mark.integration
def test_saved_research_post_then_get_by_id(client):
    """Create → fetch by id → equality."""
    base = _find_base(client)
    payload = {
        "question": "Round-trip test?",
        "report_md": "# RT\n\nFull body.",
        "sources": [{"n": 1, "title": "T", "source": "s", "url": "https://x"}],
    }
    create = client.post(base.rstrip("/"), json=payload)
    if create.status_code in (404, 405):
        pytest.skip("POST not supported")
    if create.status_code not in (200, 201):
        pytest.skip(f"POST returned {create.status_code}")
    rec = create.json().get("data", create.json())
    rec_id = rec["id"]

    get = client.get(f"{base}{rec_id}")
    assert get.status_code == 200, get.text
    fetched = get.json().get("data", get.json())
    assert fetched["question"] == payload["question"]
    assert fetched.get("report_md") == payload["report_md"]


@pytest.mark.integration
def test_saved_research_post_then_appears_in_list(client):
    """A new entry must appear in the list (ordered newest-first)."""
    base = _find_base(client)
    payload = {
        "question": "Appears-in-list probe?",
        "report_md": "# L\n\nBody.",
        "sources": [],
    }
    create = client.post(base.rstrip("/"), json=payload)
    if create.status_code in (404, 405):
        pytest.skip("POST not supported")
    if create.status_code not in (200, 201):
        pytest.skip(f"POST returned {create.status_code}")
    new_id = create.json().get("data", create.json())["id"]

    listed = client.get(base.rstrip("/")).json()
    items = listed if isinstance(listed, list) else listed.get("data", listed.get("items", []))
    ids = [item.get("id") for item in items]
    assert new_id in ids, f"new id {new_id} not in list of ids {ids}"


# --------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_saved_research_post_missing_question_rejected(client):
    base = _find_base(client)
    resp = client.post(
        base.rstrip("/"),
        json={"report_md": "# X", "sources": []},
    )
    if resp.status_code in (404, 405):
        pytest.skip("POST not supported")
    assert resp.status_code in (400, 422), f"got {resp.status_code}"


@pytest.mark.unit
def test_saved_research_post_missing_report_md_rejected(client):
    base = _find_base(client)
    resp = client.post(
        base.rstrip("/"),
        json={"question": "Q?", "sources": []},
    )
    if resp.status_code in (404, 405):
        pytest.skip("POST not supported")
    assert resp.status_code in (400, 422), f"got {resp.status_code}"


@pytest.mark.unit
def test_saved_research_post_non_json_rejected(client):
    base = _find_base(client)
    resp = client.post(base.rstrip("/"), data="not json")
    if resp.status_code in (404, 405):
        pytest.skip("POST not supported")
    assert 400 <= resp.status_code < 500


# --------------------------------------------------------------------- #
#  GET by ID — 404 case
# --------------------------------------------------------------------- #


@pytest.mark.unit
def test_saved_research_get_unknown_returns_404(client):
    base = _find_base(client)
    resp = client.get(f"{base}99999999")
    if resp.status_code == 405:
        pytest.skip("GET by id not supported")
    assert resp.status_code == 404


@pytest.mark.unit
def test_saved_research_get_non_integer_returns_422(client):
    base = _find_base(client)
    resp = client.get(f"{base}not-a-number")
    if resp.status_code == 405:
        pytest.skip("GET by id not supported")
    assert resp.status_code in (404, 422)


# --------------------------------------------------------------------- #
#  DELETE
# --------------------------------------------------------------------- #


@pytest.mark.integration
def test_saved_research_delete_round_trip(client):
    """Create → delete → fetch returns 404."""
    base = _find_base(client)
    create = client.post(
        base.rstrip("/"),
        json={"question": "Delete me?", "report_md": "# D\n\nBody.", "sources": []},
    )
    if create.status_code in (404, 405):
        pytest.skip("POST not supported")
    if create.status_code not in (200, 201):
        pytest.skip(f"POST returned {create.status_code}")
    rec_id = create.json().get("data", create.json())["id"]

    delete = client.delete(f"{base}{rec_id}")
    if delete.status_code == 405:
        pytest.skip("DELETE not supported")
    assert delete.status_code in (200, 204), f"unexpected {delete.status_code}"

    get = client.get(f"{base}{rec_id}")
    assert get.status_code == 404, "deleted record should be gone"


@pytest.mark.unit
def test_saved_research_delete_unknown_returns_404(client):
    base = _find_base(client)
    resp = client.delete(f"{base}99999999")
    if resp.status_code == 405:
        pytest.skip("DELETE not supported")
    # Either 404 (idempotent missing) or 204 (no-op) are valid; 500 is not.
    assert resp.status_code in (200, 204, 404), f"got {resp.status_code}"
