"""Front-page precompute.

Runs once per day (immediately after ingestion completes) to bake the
News Feed front page composition into a single JSON blob in
``front_page_snapshots``. The frontend's ``GET /api/news/front-page``
reads this snapshot in one query instead of recomputing lead-story +
deck selection on every request.

Selection algorithm
-------------------
* **Lead**: from articles published in last 24h (fallback 48h, then
  7d). Must have a non-empty ``image_url`` if one is available among
  the candidates. Score = ``credibility * 1.0 + recency * 0.5 +
  novelty * 0.3`` where recency is ``exp(-hours_old/24)`` and novelty
  is the fraction of the article's entities that haven't appeared in
  any of the recent prior leads.
* **Deck (3 cards)**: next 3 articles by score, enforcing source
  diversity -- each deck card must come from a different source than
  the lead AND the other deck cards. If <3 source-unique candidates
  exist, fall back to next-best score regardless of source.
* **Sections**: remaining articles grouped by primary category. Each
  section keeps top 6 by score so the payload stays bounded.
* **Trending entities**: top 8 entities by mention count in last 7d
  (best-effort -- silently empty if the entity tables don't exist).

Snapshots are keyed by ``snapshot_date`` (YYYY-MM-DD UTC). Re-running
on the same day overwrites the row via SQLite ``ON CONFLICT``.

This module uses raw ``sqlite3`` (not the SQLAlchemy session) for the
same reason the orchestrator does: the schema is hand-rolled across
several services and going through the ORM would lie about what's
actually in the DB.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
#  Dataclasses (the snapshot wire shape)
# --------------------------------------------------------------------- #


@dataclass
class FrontPageArticle:
    id: int
    title: str
    url: str
    source: str
    published_at: str
    image_url: Optional[str]
    summary_short: str
    summary_medium: str
    categories: list[str]
    credibility_score: int
    score: float
    # Per-component breakdown so a debugger / admin tool can see why
    # the lead won; keys are "credibility", "recency", "novelty".
    score_components: dict[str, float] = field(default_factory=dict)


@dataclass
class FrontPageSection:
    category: str
    articles: list[FrontPageArticle]


@dataclass
class FrontPageSnapshot:
    snapshot_date: str  # YYYY-MM-DD
    computed_at: str    # ISO timestamp
    lead: Optional[FrontPageArticle]
    deck: list[FrontPageArticle]
    sections: list[FrontPageSection]
    trending_entities: list[dict[str, Any]]
    article_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------- #
#  Schema bootstrap
# --------------------------------------------------------------------- #


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS front_page_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_front_page_snapshot_date
    ON front_page_snapshots(snapshot_date DESC);
"""


def _ensure_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------- #
#  Scoring helpers
# --------------------------------------------------------------------- #


# Per-source credibility tiers (0-100 badge scale). Established outlets
# with original reporting / editorial review score higher than
# aggregators; PR-driven or unrecognised sources fall back to a
# neutral-low default rather than a flat "everyone is equally
# trustworthy" number. Keys are lower-cased source names so lookups are
# case-insensitive (source strings come from RSS feed config / DB rows
# with inconsistent casing).
_SOURCE_CREDIBILITY: dict[str, int] = {
    "mit technology review": 95,
    "ars technica": 90,
    "o'reilly radar": 85,
    "the verge": 80,
    "techcrunch": 75,
    "hacker news": 70,
}
_DEFAULT_CREDIBILITY = 65


def _credibility_score(source: str) -> int:
    """Per-source credibility badge (0-100). Unknown sources get a
    conservative default rather than being assumed equally trustworthy."""
    return _SOURCE_CREDIBILITY.get((source or "").strip().lower(), _DEFAULT_CREDIBILITY)


def _truncate(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse an ISO timestamp tolerating ``Z`` suffix and naive form."""
    if not ts:
        return None
    try:
        cleaned = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
        dt = datetime.fromisoformat(cleaned)
    except (TypeError, ValueError):
        # Some legacy rows store "YYYY-MM-DD HH:MM:SS" without TZ.
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _recency_factor(published_at_str: str, now: datetime) -> float:
    """exp-style decay; ~1.0 at 0h, ~0.6 at 12h, ~0.4 at 24h, ~0.05 at 72h."""
    pub = _parse_iso(published_at_str)
    if pub is None:
        return 0.0
    hours_old = max(0.0, (now - pub).total_seconds() / 3600.0)
    return math.exp(-hours_old / 24.0)


def _entity_novelty(article_id: int, prior_marker_set: set[str], conn: sqlite3.Connection) -> float:
    """Fraction of this article's entities NOT in the prior-lead marker set.

    Best-effort: if ``entity_mentions`` doesn't exist we return 0.5 as
    a neutral mid-point so novelty neither helps nor punishes scoring.
    """
    try:
        rows = conn.execute(
            "SELECT DISTINCT entity_id FROM entity_mentions WHERE article_id = ?",
            (article_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return 0.5
    if not rows:
        return 0.0
    these = {f"ent:{r[0]}" for r in rows}
    novel = these - prior_marker_set
    return len(novel) / len(these) if these else 0.0


def _get_recent_lead_markers(conn: sqlite3.Connection, lookback_days: int = 7) -> set[str]:
    """Pull entity / category markers from recent prior daily leads.

    Used to penalise repeated leads about the same entity. We try the
    entity-level marker first ('ent:<id>') and fall back to a category
    proxy ('cat:<name>') when the snapshot has no entity reference.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    try:
        rows = conn.execute(
            "SELECT payload_json FROM front_page_snapshots WHERE snapshot_date >= ?",
            (cutoff,),
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    seen: set[str] = set()
    for (payload,) in rows:
        try:
            snap = json.loads(payload)
            lead = snap.get("lead") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        for cat in lead.get("categories", []) or []:
            seen.add(f"cat:{cat}")
    return seen


# --------------------------------------------------------------------- #
#  Row -> dataclass mapping
# --------------------------------------------------------------------- #


def _parse_categories(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(c) for c in parsed if c]
    except (TypeError, ValueError):
        pass
    if isinstance(raw, str):
        return [c.strip() for c in raw.split(",") if c.strip()]
    return []


def _row_to_front_page_article(
    row: sqlite3.Row, score: float, components: dict[str, float]
) -> FrontPageArticle:
    body = ((row["summary"] if "summary" in row.keys() else None)
            or (row["content"] if "content" in row.keys() else None)
            or "").strip()
    return FrontPageArticle(
        id=int(row["id"]),
        title=row["title"] or "",
        url=row["url"] or "",
        source=row["source"] or "",
        published_at=row["published_at"] or "",
        image_url=row["image_url"] if "image_url" in row.keys() else None,
        summary_short=_truncate(body, 280),
        summary_medium=_truncate(body, 800),
        categories=_parse_categories(row["categories"]),
        credibility_score=_credibility_score(row["source"]),
        score=round(score, 4),
        score_components={k: round(v, 4) for k, v in components.items()},
    )


# --------------------------------------------------------------------- #
#  Candidate selection
# --------------------------------------------------------------------- #


def _fetch_candidate_rows(conn: sqlite3.Connection, hours: int) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # row_factory is set by caller (compute_front_page). We re-set
    # here defensively so this helper is callable in isolation.
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, title, url, source, published_at, image_url,
               summary, content, categories
        FROM articles
        WHERE published_at >= ?
          AND title IS NOT NULL AND title != ''
          AND COALESCE(is_archived, 0) = 0
        ORDER BY published_at DESC
        """,
        (cutoff,),
    ).fetchall()


def _score_candidates(
    rows: list[sqlite3.Row],
    prior_markers: set[str],
    conn: sqlite3.Connection,
    now: datetime,
) -> list[tuple[float, dict[str, float], sqlite3.Row]]:
    scored: list[tuple[float, dict[str, float], sqlite3.Row]] = []
    for row in rows:
        credibility = _credibility_score(row["source"]) / 100.0
        recency = _recency_factor(row["published_at"], now)
        novelty = _entity_novelty(int(row["id"]), prior_markers, conn)
        score = credibility * 1.0 + recency * 0.5 + novelty * 0.3
        components = {
            "credibility": credibility,
            "recency": recency,
            "novelty": novelty,
        }
        scored.append((score, components, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _pick_lead_and_deck(
    scored: list[tuple[float, dict[str, float], sqlite3.Row]],
    require_image: bool = True,
) -> tuple[
    Optional[tuple[float, dict[str, float], sqlite3.Row]],
    list[tuple[float, dict[str, float], sqlite3.Row]],
]:
    """Pick lead (top score, ideally with image) + 3 source-diverse deck cards."""
    if not scored:
        return None, []

    lead: Optional[tuple[float, dict[str, float], sqlite3.Row]] = None
    used_sources: set[str] = set()

    # First pass: lead must have a non-empty image when require_image=True.
    for cand in scored:
        row = cand[2]
        if require_image and not row["image_url"]:
            continue
        lead = cand
        used_sources.add((row["source"] or "").lower())
        break

    if lead is None and require_image:
        # No imaged candidate exists -- fall back to image-agnostic pick.
        return _pick_lead_and_deck(scored, require_image=False)
    if lead is None:
        return None, []

    # Build a 3-card deck enforcing source uniqueness vs. lead + each other.
    deck: list[tuple[float, dict[str, float], sqlite3.Row]] = []
    for cand in scored:
        if cand is lead:
            continue
        src = (cand[2]["source"] or "").lower()
        if src in used_sources:
            continue
        deck.append(cand)
        used_sources.add(src)
        if len(deck) == 3:
            break

    # Fallback: if we can't fill 3 source-unique slots (small corpus
    # with one dominant source) take next-best regardless of source.
    if len(deck) < 3:
        deck_ids = {id(c) for c in deck}
        for cand in scored:
            if cand is lead or id(cand) in deck_ids:
                continue
            deck.append(cand)
            deck_ids.add(id(cand))
            if len(deck) == 3:
                break

    return lead, deck


# --------------------------------------------------------------------- #
#  Trending entities + sections
# --------------------------------------------------------------------- #


def _trending_entities(
    conn: sqlite3.Connection, days: int = 7, limit: int = 8
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.name, e.entity_type, COUNT(em.id) AS mentions
            FROM entities e
            JOIN entity_mentions em ON em.entity_id = e.id
            JOIN articles a ON a.id = em.article_id
            WHERE a.published_at >= ?
            GROUP BY e.id
            ORDER BY mentions DESC, e.name ASC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "type": r[2], "mentions": int(r[3])}
            for r in rows
        ]
    except sqlite3.OperationalError:
        # entities / entity_mentions don't exist on a fresh DB. Empty
        # trending list is the correct contract here.
        return []


def _section_for_category(
    scored: list[tuple[float, dict[str, float], sqlite3.Row]],
    used_ids: set[int],
    category: str,
    top_n: int = 6,
) -> Optional[FrontPageSection]:
    arts: list[FrontPageArticle] = []
    for score, components, row in scored:
        aid = int(row["id"])
        if aid in used_ids:
            continue
        cats = _parse_categories(row["categories"])
        if category not in cats:
            continue
        arts.append(_row_to_front_page_article(row, score, components))
        used_ids.add(aid)
        if len(arts) >= top_n:
            break
    if not arts:
        return None
    return FrontPageSection(category=category, articles=arts)


def _top_categories(conn: sqlite3.Connection, limit: int = 4) -> list[str]:
    """Discover the most-frequent categories in the corpus.

    We can't trust a hand-curated chip list; the orchestrator may have
    pulled in new feed taxonomies. Cheap-and-correct: scan all rows,
    aggregate counts, return top N.
    """
    cat_freq: dict[str, int] = {}
    try:
        rows = conn.execute(
            "SELECT categories FROM articles "
            "WHERE categories IS NOT NULL AND categories != '' "
            "  AND COALESCE(is_archived, 0) = 0"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    for (raw,) in rows:
        for c in _parse_categories(raw):
            cat_freq[c] = cat_freq.get(c, 0) + 1
    return [c for c, _n in sorted(cat_freq.items(), key=lambda x: (-x[1], x[0]))[:limit]]


# --------------------------------------------------------------------- #
#  Public entry points
# --------------------------------------------------------------------- #


async def compute_front_page(db_path: str) -> FrontPageSnapshot:
    """Compute and persist today's front-page snapshot.

    Idempotent: re-running on the same UTC day overwrites the existing
    row via ``ON CONFLICT(snapshot_date)``. The function is declared
    ``async`` because the orchestrator phase runner awaits it; the
    body itself is CPU-only sqlite work.
    """
    _ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        # ---- Corpus counts (cheap; surfaced in payload for the UI) ----
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        in_24h = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE published_at >= ?",
            (cutoff_24h,),
        ).fetchone()[0]
        cutoff_7d = (now - timedelta(days=7)).isoformat()
        in_7d = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE published_at >= ?",
            (cutoff_7d,),
        ).fetchone()[0]

        # ---- Pick the candidate window: 24h, fallback 48h, then 7d ----
        rows = _fetch_candidate_rows(conn, 24)
        if len(rows) < 4:
            rows = _fetch_candidate_rows(conn, 48)
        if len(rows) < 4:
            rows = _fetch_candidate_rows(conn, 168)

        prior_markers = _get_recent_lead_markers(conn)
        scored = _score_candidates(rows, prior_markers, conn, now)

        lead_tuple, deck_tuples = _pick_lead_and_deck(scored)

        if lead_tuple is not None:
            score, components, row = lead_tuple
            lead_obj: Optional[FrontPageArticle] = _row_to_front_page_article(
                row, score, components
            )
        else:
            lead_obj = None

        deck_objs = [
            _row_to_front_page_article(r, s, c) for s, c, r in deck_tuples
        ]

        # ---- Sections from remaining rows, ordered by category freq ----
        used_ids: set[int] = set()
        if lead_obj:
            used_ids.add(lead_obj.id)
        for d in deck_objs:
            used_ids.add(d.id)

        sections: list[FrontPageSection] = []
        for cat in _top_categories(conn, limit=4):
            sec = _section_for_category(scored, used_ids, cat, top_n=6)
            if sec:
                sections.append(sec)

        snapshot = FrontPageSnapshot(
            snapshot_date=today,
            computed_at=now.isoformat(),
            lead=lead_obj,
            deck=deck_objs,
            sections=sections,
            trending_entities=_trending_entities(conn),
            article_counts={
                "total": int(total),
                "in_24h": int(in_24h),
                "in_7d": int(in_7d),
            },
        )

        # UPSERT on snapshot_date so today's recomputes overwrite.
        conn.execute(
            """
            INSERT INTO front_page_snapshots (snapshot_date, payload_json, computed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                payload_json = excluded.payload_json,
                computed_at = excluded.computed_at
            """,
            (today, json.dumps(snapshot.to_dict()), now.isoformat()),
        )
        conn.commit()

        logger.info(
            "[front_page] computed lead=%s deck=%d sections=%d trending=%d in_24h=%d",
            (lead_obj.title[:40] if lead_obj else "(none)"),
            len(deck_objs),
            len(sections),
            len(snapshot.trending_entities),
            in_24h,
        )
        return snapshot
    finally:
        conn.close()


def load_latest_snapshot(
    db_path: str, snapshot_date: Optional[str] = None
) -> Optional[FrontPageSnapshot]:
    """Load a persisted snapshot from ``front_page_snapshots``.

    ``snapshot_date=None`` returns the most recent row (the typical
    front-page read path). Returns ``None`` when no row exists --
    callers must decide whether to live-compute on the fly.
    """
    _ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        if snapshot_date:
            row = conn.execute(
                "SELECT payload_json FROM front_page_snapshots WHERE snapshot_date = ?",
                (snapshot_date,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT payload_json FROM front_page_snapshots "
                "ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return _snapshot_from_dict(json.loads(row[0]))
    finally:
        conn.close()


def _snapshot_from_dict(data: dict[str, Any]) -> FrontPageSnapshot:
    def _article(d: Optional[dict]) -> Optional[FrontPageArticle]:
        if d is None:
            return None
        return FrontPageArticle(**d)

    sections = [
        FrontPageSection(
            category=s["category"],
            articles=[a for a in (_article(x) for x in s.get("articles", [])) if a is not None],
        )
        for s in (data.get("sections") or [])
    ]
    deck = [a for a in (_article(x) for x in (data.get("deck") or [])) if a is not None]
    return FrontPageSnapshot(
        snapshot_date=data["snapshot_date"],
        computed_at=data["computed_at"],
        lead=_article(data.get("lead")),
        deck=deck,
        sections=sections,
        trending_entities=data.get("trending_entities") or [],
        article_counts=data.get("article_counts") or {},
    )


__all__ = [
    "FrontPageArticle",
    "FrontPageSection",
    "FrontPageSnapshot",
    "compute_front_page",
    "load_latest_snapshot",
]
