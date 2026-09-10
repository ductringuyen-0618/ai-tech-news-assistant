"""Unit tests for :func:`run_learning_ingestion` (proposal 003).

Mirrors ``test_daily_ingestion_orchestrator.py``'s monkeypatch pattern:
the fetch phase does ``from src.database.base import SessionLocal`` and
``from src.services.ingestion_service import IngestionService`` lazily
*inside* the function, so patches target those source modules directly.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from src.services.learning_ingestion import (
    LEARNING_CATEGORY,
    run_learning_ingestion,
)


class _FakeIngestionResult:
    def __init__(self, saved: int = 2, errors: int = 0, error_details=None):
        self.total_articles_saved = saved
        self.errors_encountered = errors
        self.error_details = error_details or []


@pytest.fixture
def tmp_db(tmp_path) -> str:
    """A SQLite file with the same ``articles`` shape the real repo
    uses, pre-seeded with rows for the keyword-filter pass to act on:
    one genuine agent-tooling item (should stay tagged), one off-topic
    item that a broad source mis-tagged (should get demoted).
    """
    db = tmp_path / "test_learning.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                content TEXT,
                summary TEXT,
                source TEXT,
                categories TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO articles (title, url, content, categories) VALUES (?, ?, ?, ?)",
            [
                (
                    "New MCP server for agent workflows",
                    "https://x/1",
                    "A skill pack for Claude Code.",
                    f'["{LEARNING_CATEGORY}"]',
                ),
                (
                    "GitHub raises funding round",
                    "https://x/2",
                    "Unrelated business news.",
                    f'["{LEARNING_CATEGORY}"]',
                ),
                (
                    "Already-demoted article",
                    "https://x/3",
                    "Nothing to do with agents.",
                    None,
                ),
            ],
        )
        conn.commit()
    return str(db)


def _install_fetch_mocks(monkeypatch, fetch_result=None):
    """Patch IngestionService + SessionLocal so the fetch step is a
    no-op (the keyword-filter pass under test runs against the
    pre-seeded ``tmp_db`` rows directly, not against fetch output)."""
    fake_service_inst = MagicMock()
    fake_service_inst.ingest_all = MagicMock(
        return_value=fetch_result or _FakeIngestionResult()
    )
    fake_service_inst.close = MagicMock()
    fake_service_cls = MagicMock(return_value=fake_service_inst)

    fake_session = MagicMock()
    fake_session_local = MagicMock(return_value=fake_session)

    import src.database.base as _base
    import src.services.ingestion_service as _ingsvc

    monkeypatch.setattr(_base, "SessionLocal", fake_session_local, raising=False)
    monkeypatch.setattr(
        _base, "create_session_factory", lambda: fake_session_local, raising=False
    )
    monkeypatch.setattr(_ingsvc, "IngestionService", fake_service_cls)
    return fake_service_inst


@pytest.mark.asyncio
async def test_fetch_uses_learning_source_config(monkeypatch, tmp_db):
    """The feed configs passed to ingest_all are tagged with
    LEARNING_CATEGORY, not the caller's raw source list."""
    fake_service = _install_fetch_mocks(monkeypatch)

    await run_learning_ingestion(
        tmp_db,
        sources=[{"name": "Test Feed", "url": "https://example.com/feed"}],
    )

    called_with = fake_service.ingest_all.call_args[0][0]
    assert called_with == [
        {"name": "Test Feed", "url": "https://example.com/feed", "category": LEARNING_CATEGORY}
    ]


@pytest.mark.asyncio
async def test_keyword_filter_demotes_non_matching_rows(monkeypatch, tmp_db):
    """After fetch, rows tagged LEARNING_CATEGORY that fail the content
    keyword filter get their category tag stripped; matching rows keep
    it; already-untagged rows are left alone."""
    _install_fetch_mocks(monkeypatch)

    report = await run_learning_ingestion(tmp_db, sources=[])

    with sqlite3.connect(tmp_db) as conn:
        rows = {
            row[0]: row[1]
            for row in conn.execute("SELECT url, categories FROM articles").fetchall()
        }

    assert rows["https://x/1"] == f'["{LEARNING_CATEGORY}"]'  # kept
    assert rows["https://x/2"] is None  # demoted -- off-topic
    assert rows["https://x/3"] is None  # untouched, was already NULL
    assert report.processed == 2  # from the mocked fetch result
    assert report.name == "learning_fetch"


@pytest.mark.asyncio
async def test_dry_run_skips_fetch_and_filter(monkeypatch, tmp_db):
    """dry_run=True must not touch the network or the DB."""
    fake_service = _install_fetch_mocks(monkeypatch)

    with sqlite3.connect(tmp_db) as conn:
        before = conn.execute("SELECT categories FROM articles ORDER BY id").fetchall()

    report = await run_learning_ingestion(tmp_db, dry_run=True)

    fake_service.ingest_all.assert_not_called()
    with sqlite3.connect(tmp_db) as conn:
        after = conn.execute("SELECT categories FROM articles ORDER BY id").fetchall()
    assert before == after
    assert report.processed == 0
