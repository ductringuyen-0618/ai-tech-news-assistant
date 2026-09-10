"""Unit tests for :mod:`src.services.front_page_precompute`.

Five tests, each pinned at a single behaviour of the precompute
contract:

1. ``test_compute_front_page_basic`` -- seed 10 articles from 3
   sources; assert lead has highest score + image_url, deck has 3
   source-diverse cards, sections cover the seeded categories.

2. ``test_compute_front_page_handles_empty_db`` -- no articles;
   returns snapshot with ``lead=None``, ``deck=[]``, ``sections=[]``,
   correctly populated zero counts, no crash.

3. ``test_load_snapshot_returns_persisted`` -- compute then load;
   loaded payload (JSON-roundtripped) matches what was persisted.

4. ``test_source_diversity_enforced_in_deck`` -- 5 articles, all
   from the same source. Deck still fills up to 3 by falling back to
   next-best after exhausting source-unique candidates.

5. ``test_compute_runs_inside_orchestrator`` -- patch
   ``compute_front_page`` and run :func:`run_daily_ingestion`; assert
   the function was called exactly once with the resolved db_path.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.services.front_page_precompute import (
    FrontPageSnapshot,
    compute_front_page,
    load_latest_snapshot,
)


# --------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------- #


def _make_articles_table(conn: sqlite3.Connection) -> None:
    """Reproduce the production ``articles`` schema (the bits we read)."""
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            content TEXT,
            summary TEXT,
            author TEXT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            categories TEXT,
            metadata TEXT,
            is_archived BOOLEAN DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            embedding_generated BOOLEAN DEFAULT 0,
            summary_generated BOOLEAN DEFAULT 0,
            image_url TEXT
        )
        """
    )


def _seed_article(
    conn: sqlite3.Connection,
    *,
    title: str,
    url: str,
    source: str,
    hours_ago: float,
    categories: list[str],
    image: str | None = "https://img.example/x.jpg",
    summary: str = "A short summary body.",
) -> int:
    pub = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    cur = conn.execute(
        """
        INSERT INTO articles
            (title, url, content, summary, published_at, source, categories, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            url,
            "Body content " * 30,
            summary,
            pub,
            source,
            json.dumps(categories),
            image,
        ),
    )
    return int(cur.lastrowid)


@pytest.fixture
def empty_db(tmp_path) -> str:
    db = tmp_path / "empty.db"
    with sqlite3.connect(db) as conn:
        _make_articles_table(conn)
        conn.commit()
    return str(db)


@pytest.fixture
def seeded_db(tmp_path) -> str:
    """10 articles, 4 sources, 3 categories, varying recency.

    Four sources ensures the deck's source-diversity contract has
    enough material to satisfy lead + 3 unique deck sources.
    """
    db = tmp_path / "seeded.db"
    with sqlite3.connect(db) as conn:
        _make_articles_table(conn)
        sources = ["TechCrunch", "ArsTechnica", "TheVerge", "Wired"]
        cats = ["AI/ML", "Cloud", "Security"]
        for i in range(10):
            _seed_article(
                conn,
                title=f"Story {i}",
                url=f"https://example.com/{i}",
                source=sources[i % 4],
                hours_ago=float(i * 2),
                categories=[cats[i % 3]],
            )
        conn.commit()
    return str(db)


# --------------------------------------------------------------------- #
#  Test 1: happy path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compute_front_page_basic(seeded_db):
    """Lead has top score + image; deck is 3 source-diverse cards;
    sections cover the seeded categories."""
    snap = await compute_front_page(seeded_db)

    assert isinstance(snap, FrontPageSnapshot)
    assert snap.lead is not None
    assert snap.lead.image_url  # required for lead in normal path
    assert snap.lead.score > 0
    # Deck contract.
    assert len(snap.deck) == 3
    deck_sources = {d.source.lower() for d in snap.deck}
    # Source diversity within the deck.
    assert len(deck_sources) == 3
    # Each deck source differs from the lead.
    assert snap.lead.source.lower() not in deck_sources
    # Sections cover the seeded categories (some may be empty after
    # lead+deck consumed their top story; we just require >=1).
    assert len(snap.sections) >= 1
    # Article counts populated.
    assert snap.article_counts["total"] == 10
    assert snap.article_counts["in_24h"] >= 0
    assert snap.article_counts["in_7d"] == 10


# --------------------------------------------------------------------- #
#  Test 2: empty DB
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compute_front_page_handles_empty_db(empty_db):
    """Empty articles table -> usable snapshot with null lead, empty
    deck/sections, zero counts. No crash."""
    snap = await compute_front_page(empty_db)

    assert snap.lead is None
    assert snap.deck == []
    assert snap.sections == []
    assert snap.trending_entities == []
    assert snap.article_counts == {"total": 0, "in_24h": 0, "in_7d": 0}


# --------------------------------------------------------------------- #
#  Test 3: load round-trips persisted snapshot byte-for-byte
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_load_snapshot_returns_persisted(seeded_db):
    """compute -> load round-trips the snapshot (JSON identical)."""
    computed = await compute_front_page(seeded_db)
    loaded = load_latest_snapshot(seeded_db)
    assert loaded is not None
    # Re-serialise both via to_dict() and compare. asdict() output is
    # order-stable for dataclasses so equal dicts <=> equal JSON.
    assert json.dumps(loaded.to_dict(), sort_keys=True) == json.dumps(
        computed.to_dict(), sort_keys=True
    )


# --------------------------------------------------------------------- #
#  Test 4: source-diversity fallback
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_source_diversity_enforced_in_deck(tmp_path):
    """5 articles, all from one source: deck still fills (falling
    back to next-best when source-unique candidates run out)."""
    db = str(tmp_path / "monosource.db")
    with sqlite3.connect(db) as conn:
        _make_articles_table(conn)
        for i in range(5):
            _seed_article(
                conn,
                title=f"TC Story {i}",
                url=f"https://tc.example/{i}",
                source="TechCrunch",
                hours_ago=float(i),
                categories=["AI/ML"],
            )
        conn.commit()

    snap = await compute_front_page(db)
    assert snap.lead is not None
    # Deck should still have items even though no source-unique cards
    # exist beyond the lead. Cap is 3; we have 4 remaining articles.
    assert len(snap.deck) == 3
    # All from same source (fallback path).
    assert all(d.source == "TechCrunch" for d in snap.deck)


# --------------------------------------------------------------------- #
#  Test 5: orchestrator integration
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compute_runs_inside_orchestrator(monkeypatch, seeded_db):
    """run_daily_ingestion (with phases 1-4 mocked / disabled) invokes
    compute_front_page exactly once with the resolved db_path."""
    from src.services import front_page_precompute as fpp
    from src.services.daily_ingestion_orchestrator import run_daily_ingestion

    calls: list[str] = []

    async def fake_compute(db_path: str):
        calls.append(db_path)
        # Return a minimal snapshot object the phase code can sum over.
        return fpp.FrontPageSnapshot(
            snapshot_date="2099-01-01",
            computed_at="2099-01-01T00:00:00+00:00",
            lead=None,
            deck=[],
            sections=[],
            trending_entities=[],
            article_counts={"total": 0, "in_24h": 0, "in_7d": 0},
        )

    monkeypatch.setattr(fpp, "compute_front_page", fake_compute)

    # Stub out phase 1 fetch's heavy deps and disable phases 2-4 so
    # this test only exercises the front_page wiring.
    import src.database.base as _base
    import src.services.ingestion_service as _ingsvc

    class _Result:
        total_articles_saved = 0
        errors_encountered = 0
        error_details: list = []

    fake_svc_inst = MagicMock()
    fake_svc_inst.ingest_all = MagicMock(return_value=_Result())
    fake_svc_inst.close = MagicMock()
    fake_svc_cls = MagicMock(return_value=fake_svc_inst)
    monkeypatch.setattr(_ingsvc, "IngestionService", fake_svc_cls)
    monkeypatch.setattr(_base, "SessionLocal", MagicMock(return_value=MagicMock()), raising=False)
    monkeypatch.setattr(_base, "create_session_factory", lambda: None, raising=False)

    report = await run_daily_ingestion(
        seeded_db,
        summarize=False,
        embed=False,
        extract_entities=False,
        precompute_front_page=True,
    )

    # Exactly one call into compute_front_page, against our seeded DB.
    assert calls == [seeded_db]
    # And the new phase appears in the report.
    assert any(p.name == "front_page" for p in report.phases)
