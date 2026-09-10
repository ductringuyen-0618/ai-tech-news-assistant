"""
M2.M6 Smoke test — ingestion via the shared summarize_article skill.
====================================================================

Goal
----
Confirm the orchestrator's new feature-flag path produces real summaries
when ``USE_AGENT_SKILL_SUMMARIZATION=True``, end-to-end against the live
Ollama backend the dev stack already has running.

Workflow
--------
1.  Pick 3 already-summarized articles from ``news.db``, backing up
    their existing summary text.
2.  NULL out their summary AND flip ``summary_generated = FALSE`` so the
    orchestrator picks them up on the next ``run_pending`` call.
3.  Run ``SummarizationOrchestrator.run_pending(limit=3)``.
4.  Confirm each article has a non-NULL ``summary`` again — and PRINT
    the title + first 200 chars of the new summary so a human can
    eyeball quality (the migration must produce summaries of comparable
    quality to the legacy path).
5.  Restore the original summary text on exit (so the corpus isn't
    perturbed by the smoke).

Run from ``backend/`` ::

    python scripts/smoke_ingest_via_skill.py

Caps wall-clock at 90s; exits with non-zero on failure.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List

# Make src importable when run as ``python scripts/...``.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from src.core.config import get_settings  # noqa: E402
from src.services.summarization_orchestrator import (  # noqa: E402
    SummarizationOrchestrator,
)


WALL_CLOCK_BUDGET_S = 90.0
LIMIT = 3


def _db_path() -> str:
    """Resolve the active SQLite path from settings (matches the rest of
    the codebase: strip the SQLAlchemy URL prefix when present).
    """
    raw = get_settings().get_database_path()
    if raw.startswith("sqlite:///"):
        return raw[len("sqlite:///"):]
    if raw.startswith("sqlite://"):
        return raw[len("sqlite://"):]
    return raw


def _pick_target_ids(db: str, n: int) -> List[Dict]:
    """Pick N already-summarized articles with non-trivial content.

    We choose summarized rows so the test path covers the cache MISS
    branch (we'll null the summary first). We also require ``content``
    long enough that the orchestrator won't skip-short.
    """
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, summary, summary_generated, length(content) AS clen
            FROM articles
            WHERE is_archived = FALSE
              AND summary IS NOT NULL
              AND length(summary) > 20
              AND content IS NOT NULL
              AND length(content) > 250
            ORDER BY length(content) DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [dict(r) for r in rows]


def _snapshot_queue(db: str) -> List[Dict]:
    """Snapshot every article whose ``summary_generated = 0`` so we can
    restore the queue state after the smoke. The orchestrator's queue
    semantics mean we need a clean queue for the targets to be picked.
    """
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, summary_generated FROM articles "
            "WHERE summary_generated = 0 AND is_archived = FALSE"
        ).fetchall()
    return [dict(r) for r in rows]


def _isolate_targets(db: str, target_ids: List[int]) -> None:
    """Clean the queue so ONLY the target articles are pending:
    1. Mark every OTHER article as ``summary_generated = TRUE``.
    2. NULL the targets' summary and flip ``summary_generated = FALSE``.
    This keeps the orchestrator's queue (`ORDER BY created_at ASC LIMIT N`)
    deterministic: it picks exactly the targets we want.
    """
    placeholders = ",".join("?" for _ in target_ids)
    with sqlite3.connect(db) as conn:
        # Step 1: mark non-targets as processed (won't touch their summary).
        conn.execute(
            f"UPDATE articles SET summary_generated = 1 "
            f"WHERE summary_generated = 0 AND id NOT IN ({placeholders})",
            target_ids,
        )
        # Step 2: null + queue the targets.
        conn.executemany(
            "UPDATE articles SET summary = NULL, summary_generated = 0 "
            "WHERE id = ?",
            [(i,) for i in target_ids],
        )
        conn.commit()


def _restore_summaries(db: str, backup: List[Dict], queue_snapshot: List[Dict]) -> None:
    """Restore the original summary AND mark summary_generated=TRUE for
    the targets, then restore the original ``summary_generated`` values
    on every other article so the global queue state is exactly what it
    was before the smoke.
    """
    with sqlite3.connect(db) as conn:
        # Restore target summaries and flag.
        conn.executemany(
            "UPDATE articles SET summary = ?, summary_generated = 1 "
            "WHERE id = ?",
            [(b["summary"], b["id"]) for b in backup],
        )
        # Roll back the queue isolation: anything that was 0 before our
        # run goes back to 0 (excluding targets, which we just set to 1).
        target_ids = {b["id"] for b in backup}
        rollback = [
            (q["id"],)
            for q in queue_snapshot
            if q["id"] not in target_ids
        ]
        if rollback:
            conn.executemany(
                "UPDATE articles SET summary_generated = 0 WHERE id = ?",
                rollback,
            )
        conn.commit()


def _read_summary(db: str, article_id: int) -> str:
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT summary FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
    return (row[0] if row else "") or ""


@contextmanager
def _restore_on_exit(db: str, backup: List[Dict], queue_snapshot: List[Dict]):
    try:
        yield
    finally:
        try:
            _restore_summaries(db, backup, queue_snapshot)
            print(f"[restore] Restored original summaries for "
                  f"{len(backup)} article(s) AND "
                  f"{len([q for q in queue_snapshot if q['id'] not in {b['id'] for b in backup}])} queued-non-target(s).")
        except Exception as exc:  # noqa: BLE001
            print(f"[restore] WARNING: restore failed: {exc}")


async def _run() -> int:
    settings = get_settings()
    db = _db_path()
    print(f"[smoke] DB path: {db}")
    print(f"[smoke] use_agent_skill_summarization = "
          f"{settings.use_agent_skill_summarization}")
    print(f"[smoke] Ollama host: {settings.ollama_host} (model: "
          f"{settings.ollama_model})")

    targets = _pick_target_ids(db, LIMIT)
    if len(targets) < LIMIT:
        print(f"[smoke] FAIL: only found {len(targets)} qualifying "
              f"articles, need {LIMIT}")
        return 2

    print(f"[smoke] Selected articles: {[t['id'] for t in targets]}")

    backup = [{"id": t["id"], "summary": t["summary"]} for t in targets]
    target_ids = [t["id"] for t in targets]

    # Snapshot the existing queue so we can roll it back exactly after
    # the smoke run. This is required because the orchestrator's queue
    # is FIFO over ``summary_generated = 0`` and any older "stuck"
    # articles would otherwise be picked up instead of our targets.
    queue_snapshot = _snapshot_queue(db)
    print(f"[smoke] Queue snapshot: {len(queue_snapshot)} article(s) "
          f"currently pending — will isolate the targets.")

    with _restore_on_exit(db, backup, queue_snapshot):
        _isolate_targets(db, target_ids)
        print(f"[smoke] Isolated targets ({target_ids}); running "
              f"orchestrator with limit={LIMIT}...")

        # Force the flag ON for this run regardless of env (defense in
        # depth — the smoke should exercise the M6 path).
        # NB: assignment is allowed because Settings.validate_assignment=True
        # would re-validate; we use object.__setattr__ to bypass safely.
        object.__setattr__(settings, "use_agent_skill_summarization", True)

        orch = SummarizationOrchestrator(
            db_path=db,
            concurrency=2,
            extract_entities=False,  # skip the post-hook for speed
        )

        t0 = time.monotonic()
        result = await asyncio.wait_for(
            orch.run_pending(limit=LIMIT), timeout=WALL_CLOCK_BUDGET_S
        )
        elapsed = time.monotonic() - t0
        print(f"[smoke] run_pending finished in {elapsed:.1f}s: "
              f"{result.to_dict()}")

        if elapsed > WALL_CLOCK_BUDGET_S:
            print(f"[smoke] FAIL: wall clock {elapsed:.1f}s > "
                  f"{WALL_CLOCK_BUDGET_S:.0f}s")
            return 3

        # Assertions: every target article must have a non-NULL summary.
        failures = []
        for t in targets:
            new_summary = _read_summary(db, t["id"]).strip()
            preview = new_summary[:200].replace("\n", " ")
            title_preview = (t["title"] or "")[:60].replace("\n", " ")
            print()
            print(f"  -- article {t['id']}: {title_preview}")
            print(f"     summary[:200]: {preview}")
            if not new_summary:
                failures.append(t["id"])

        if failures:
            print(f"[smoke] FAIL: articles with NULL/empty summary after run: "
                  f"{failures}")
            return 4

        # Sanity: at least one was actually re-summarised this run
        # (skipped_short is fine if the body was too short — but the
        # selection query required length > 400 so it shouldn't happen).
        if result.summarized < 1:
            print(f"[smoke] FAIL: orchestrator marked 0 summarized "
                  f"(requested={result.requested}, "
                  f"skipped={result.skipped_short}, failed={result.failed})")
            return 5

    print()
    print(f"[smoke] PASS — {result.summarized} article(s) summarised via "
          f"the agent skill in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(_run())
    sys.exit(rc)
