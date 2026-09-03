"""Unit tests for :func:`run_daily_ingestion` (Mission daily-ingestion M1).

Three tests, each pinned at a single behaviour from the M1 contract:

1. ``test_happy_path_all_phases_succeed`` -- every phase mock returns
   success. All four phases run, ``processed > 0`` in each, and the
   computed ``health_status`` is ``"green"``.

2. ``test_phase_2_crashes_does_not_kill_run`` -- summarization phase
   raises mid-pipeline. Phases 1, 3, 4 still run; phase 2 has errors
   populated and ``processed=0``; health_status is ``"yellow"``
   (exactly one failed phase, per spec §2 M4).

3. ``test_dry_run_no_writes`` -- every phase is invoked with
   ``dry_run=True``. No INSERT / UPDATE statement is issued against
   the test SQLite DB. We assert this by snapshotting the table row
   counts before and after and confirming they didn't move.

All four backing services are mocked at module-import scope: the
orchestrator imports them lazily *inside* each phase function, so
:func:`monkeypatch.setattr` patches the actual import target
(``src.database.base.SessionLocal``,
``src.services.summarization_service.SummarizationService``, etc.)
and the patched object is what each phase resolves at call time.
"""

from __future__ import annotations

import sqlite3
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.daily_ingestion_orchestrator import (
    DailyIngestionReport,
    PhaseReport,
    run_daily_ingestion,
)


# --------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------- #


@pytest.fixture
def tmp_db(tmp_path) -> str:
    """A SQLite file pre-seeded with three articles -- one already
    summarised, two pending. The three "pending" rows give every phase
    something to chew on.
    """
    db = tmp_path / "test_ingestion.db"
    with sqlite3.connect(db) as conn:
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
        conn.executemany(
            "INSERT INTO articles (title, url, content, summary) VALUES (?, ?, ?, ?)",
            [
                ("Article 1", "https://x/1", "Body of article 1." * 20, None),
                ("Article 2", "https://x/2", "Body of article 2." * 20, None),
                ("Article 3", "https://x/3", "Body of article 3." * 20, "already done"),
            ],
        )
        conn.commit()
    return str(db)


class _FakeIngestionResult:
    """Stand-in for :class:`IngestionService.IngestionResult`. The
    orchestrator only reads ``total_articles_saved``,
    ``errors_encountered``, and ``error_details``.
    """

    def __init__(self, saved: int = 5, errors: int = 0, error_details=None):
        self.total_articles_saved = saved
        self.errors_encountered = errors
        self.error_details = error_details or []


# --------------------------------------------------------------------- #
#  Helpers to wire up mocks against the orchestrator's lazy imports
# --------------------------------------------------------------------- #


def _install_phase_mocks(
    monkeypatch,
    *,
    fetch_result=None,
    summarize_fn=None,
    embed_fn=None,
    entity_fn=None,
):
    """Patch the four services the orchestrator lazily imports.

    Because the orchestrator does ``from src.services.x import Y``
    *inside* each phase function, we patch the symbol on its source
    module so the freshly resolved import picks up our fake.
    """

    # --- Phase 1: IngestionService + SessionLocal ----------------------
    fake_service_cls = MagicMock()
    fake_service_inst = MagicMock()
    fake_service_inst.ingest_all = MagicMock(
        return_value=fetch_result or _FakeIngestionResult(saved=5)
    )
    fake_service_inst.close = MagicMock()
    fake_service_cls.return_value = fake_service_inst

    fake_session = MagicMock()
    fake_session_local = MagicMock(return_value=fake_session)

    # Patch source modules. ``create_session_factory`` is also patched so
    # the orchestrator's bootstrap call is a no-op.
    import src.database.base as _base
    import src.services.ingestion_service as _ingsvc

    monkeypatch.setattr(_base, "SessionLocal", fake_session_local, raising=False)
    monkeypatch.setattr(
        _base, "create_session_factory", lambda: fake_session_local, raising=False
    )
    monkeypatch.setattr(_ingsvc, "IngestionService", fake_service_cls)

    # --- Phase 2: SummarizationService.summarize_content --------------
    fake_summ_cls = MagicMock()
    fake_summ_inst = MagicMock()
    fake_summ_inst.summarize_content = AsyncMock(
        side_effect=summarize_fn
        or (lambda req: _summary_obj("MOCK SUMMARY"))
    )
    fake_summ_cls.return_value = fake_summ_inst

    import src.services.summarization_service as _summ
    monkeypatch.setattr(_summ, "SummarizationService", fake_summ_cls)

    # --- Phase 3: shared EmbeddingService singleton --------------------
    fake_svc_inst = MagicMock()
    fake_svc_inst.model_name = "all-MiniLM-L6-v2"
    fake_svc_inst.initialize = AsyncMock(return_value=None)

    _vector_fn = embed_fn or (lambda texts: [[0.1] * 384 for _ in texts])

    def _fake_generate_embeddings(request):
        vectors = _vector_fn(request.texts)
        resp = MagicMock()
        resp.embeddings = vectors
        resp.model_name = "all-MiniLM-L6-v2"
        return resp

    fake_svc_inst.generate_embeddings = AsyncMock(
        side_effect=_fake_generate_embeddings
    )

    import src.services.embedding_service as _emb
    monkeypatch.setattr(
        _emb, "get_shared_embedding_service", lambda: fake_svc_inst
    )

    # --- Phase 4: EntityExtractionService.process_article -------------
    fake_ent_cls = MagicMock()
    fake_ent_inst = MagicMock()
    fake_ent_inst.process_article = AsyncMock(
        side_effect=entity_fn or (lambda article_id: 3)
    )
    fake_ent_cls.return_value = fake_ent_inst

    import src.services.entity_extraction_service as _ent
    monkeypatch.setattr(_ent, "EntityExtractionService", fake_ent_cls)

    return {
        "ingestion": fake_service_inst,
        "summarize": fake_summ_inst,
        "embed": fake_svc_inst,
        "entity": fake_ent_inst,
    }


def _summary_obj(text: str):
    """Minimal stand-in for ``ArticleSummary`` -- the orchestrator only
    reads ``.summary``."""
    obj = MagicMock()
    obj.summary = text
    return obj


def _phase(report: DailyIngestionReport, name: str) -> PhaseReport:
    """Find a phase report by name -- helper for assertions."""
    match = [p for p in report.phases if p.name == name]
    assert match, f"phase {name!r} missing from report"
    return match[0]


# --------------------------------------------------------------------- #
#  Test 1: happy path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_happy_path_all_phases_succeed(monkeypatch, tmp_db):
    """All four phases mock-succeed -> green health, processed > 0
    in every phase, durations recorded."""
    _install_phase_mocks(monkeypatch)

    report = await run_daily_ingestion(tmp_db)

    assert isinstance(report, DailyIngestionReport)
    assert {p.name for p in report.phases} == {
        "fetch",
        "summarize",
        "embed",
        "entity_extract",
        "front_page",
    }
    assert _phase(report, "fetch").processed == 5
    # Two unsummarised articles in the fixture.
    assert _phase(report, "summarize").processed == 2
    # All three articles need embeddings.
    assert _phase(report, "embed").processed == 3
    # All three need entity extraction.
    assert _phase(report, "entity_extract").processed == 3
    # Every phase has a duration recorded.
    for p in report.phases:
        assert p.duration_ms >= 0
        assert p.errors == []
    assert report.health_status == "green"
    assert report.dry_run is False


# --------------------------------------------------------------------- #
#  Test 2: mid-pipeline failure isolation
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_phase_2_crashes_does_not_kill_run(monkeypatch, tmp_db):
    """Summarize raises -> phase 2 reports errors+processed=0 but
    phases 1, 3, 4 still run. Health flips to yellow (one failed
    phase, per spec §2 M4)."""

    async def boom(req):
        raise RuntimeError("ollama is on fire")

    _install_phase_mocks(monkeypatch, summarize_fn=boom)

    report = await run_daily_ingestion(tmp_db)

    fetch = _phase(report, "fetch")
    summ = _phase(report, "summarize")
    emb = _phase(report, "embed")
    ent = _phase(report, "entity_extract")

    # Phase 1 ran.
    assert fetch.processed == 5
    # Phase 2 crashed *per item*. Two pending articles -> two failures.
    assert summ.processed == 0
    assert summ.failed == 2
    assert len(summ.errors) > 0
    assert any("ollama is on fire" in e for e in summ.errors)
    # Phases 3 + 4 still ran.
    assert emb.processed == 3
    assert ent.processed == 3
    # Exactly one phase failed entirely (summarize: processed=0 AND
    # errors non-empty) -> yellow.
    assert report.health_status == "yellow"


# --------------------------------------------------------------------- #
#  Test 3: dry_run writes nothing
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dry_run_no_writes(monkeypatch, tmp_db):
    """``dry_run=True`` -> no INSERT / UPDATE against the DB.

    We assert this by snapshotting row counts on the three tables the
    orchestrator could mutate (``articles``,
    ``article_embeddings`` if it exists, ``entity_mentions`` if it
    exists) before and after the run. They must not move.
    """
    _install_phase_mocks(monkeypatch)

    def _snapshot() -> dict:
        with sqlite3.connect(tmp_db) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            snap = {
                "articles": conn.execute(
                    "SELECT COUNT(*) FROM articles"
                ).fetchone()[0],
                "articles_with_summary": conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL"
                ).fetchone()[0],
            }
            if "article_embeddings" in tables:
                snap["article_embeddings"] = conn.execute(
                    "SELECT COUNT(*) FROM article_embeddings"
                ).fetchone()[0]
            if "entity_mentions" in tables:
                snap["entity_mentions"] = conn.execute(
                    "SELECT COUNT(*) FROM entity_mentions"
                ).fetchone()[0]
        return snap

    before = _snapshot()
    report = await run_daily_ingestion(tmp_db, dry_run=True)
    after = _snapshot()

    # Every phase ran (work-set was *computed*) but processed=0
    # because we skipped the actual writes.
    assert report.dry_run is True
    for p in report.phases:
        assert p.processed == 0, (
            f"phase {p.name} wrote something during dry_run: processed={p.processed}"
        )
        assert p.failed == 0

    # Row counts did not move on any pre-existing table. The
    # orchestrator does CREATE TABLE IF NOT EXISTS for
    # ``article_embeddings`` even on a dry run (it's a no-op write
    # against schema, not data), so we only check counts for tables
    # that existed in ``before`` -- anything created during the run
    # is fine as long as it's empty.
    for key, count in before.items():
        assert after[key] == count, (
            f"{key} row count changed in dry_run: {count} -> {after[key]}"
        )

    if "article_embeddings" in after:
        assert after["article_embeddings"] == before.get("article_embeddings", 0)


# --------------------------------------------------------------------- #
#  Test 4: M4 audit row persisted after a run
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ingestion_runs_row_persisted_after_run(monkeypatch, tmp_db):
    """After ``run_daily_ingestion`` completes, exactly one row appears
    in the ``ingestion_runs`` audit table containing the report JSON
    and the computed ``health_status`` (Mission daily-ingestion M4).
    """
    _install_phase_mocks(monkeypatch)

    report = await run_daily_ingestion(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute(
            "SELECT health_status, dry_run, total_duration_ms, report_json "
            "FROM ingestion_runs ORDER BY id DESC"
        ).fetchall()

    assert len(rows) == 1, f"expected 1 ingestion_runs row, got {len(rows)}"
    health, dry_run_flag, dur_ms, report_json = rows[0]
    assert health == report.health_status
    assert dry_run_flag == 0  # SQLite stores BOOLEAN as 0/1
    assert dur_ms >= 0

    import json as _json
    parsed = _json.loads(report_json)
    assert parsed["health_status"] == report.health_status
    assert {p["name"] for p in parsed["phases"]} == {
        "fetch", "summarize", "embed", "entity_extract", "front_page"
    }
