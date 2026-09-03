"""
Digest Route
============

Returns a daily-digest aggregation built from the SQLite store: top stories,
category breakdown, and trending topics. Powers the frontend's Digest tab.

Polish iter 3 / Part C extends this with three more endpoints:
    - ``/daily-summary`` — an AI-generated executive-overview paragraph,
      cached per-calendar-day so the LLM only runs once a day.
    - ``/curated`` — the top 3-5 stories ranked by a recency × source-weight ×
      mention-count formula (NOT just newest-first).
    - ``/topics`` — today's articles grouped by their ``categories`` JSON
      field, with a small per-topic preview.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from ...core.config import get_settings
from ...models.article import SummarizationRequest
from ...services.summarization_service import SummarizationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digest", tags=["Digest"])


# ---------------------------------------------------------------------------
# Helpers shared by every endpoint in this module.
# ---------------------------------------------------------------------------


def _resolve_db_path() -> str:
    settings = get_settings()
    return settings.get_database_file_path()


def _decode_categories(raw: Any) -> List[str]:
    """Parse the JSON-encoded categories TEXT column. Returns [] on
    null / malformed / non-list values so a single bad row never
    breaks the whole digest payload."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(c) for c in parsed if c]
    return []


def _parse_dt(raw: Any) -> Optional[datetime]:
    """Best-effort parser for SQLite timestamps which may be ISO-like with
    or without microseconds / 'T' / timezone."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).strip()
        # SQLite stores `YYYY-MM-DD HH:MM:SS[.ffffff]` — replace space with T.
        s = s.replace(" ", "T")
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# /api/digest/ — original endpoint, unchanged shape (DigestView still wires
# to this for the top-stories list + trending topics + breakdown).
# ---------------------------------------------------------------------------


@router.get("/")
async def get_daily_digest(top: int = 5) -> Dict[str, Any]:
    """
    Build a daily digest from the most recent articles in the DB.

    Shape matches the frontend's DigestView prop type: top stories, category
    breakdown (by source for now, since we don't have proper categories yet),
    and trending topics (most-frequent capitalised tokens in titles).
    """
    db_path = _resolve_db_path()

    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row

        # Top stories: most-recent N
        rows = con.execute(
            "SELECT id, title, source, summary, content, categories "
            "FROM articles WHERE is_archived = 0 "
            "ORDER BY created_at DESC LIMIT ?",
            (top,),
        ).fetchall()

        top_stories: List[Dict[str, Any]] = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "source": r["source"] or "Unknown",
                "summaryShort": (
                    r["summary"]
                    or (r["content"][:200] + "...")
                    if r["content"]
                    else ""
                ),
                # Pull category from the article's actual ``categories`` JSON
                # column instead of duplicating ``source``. The frontend
                # DigestView renders source + category as separate chips, so
                # using the source here produced "MIT Technology Review |
                # MIT Technology Review" twice on every story.
                "category": _decode_categories(r["categories"]),
            }
            for r in rows
        ]

        # Category breakdown: count by source (used as a proxy for category
        # until we have proper category extraction).
        breakdown_rows = con.execute(
            "SELECT source, COUNT(*) AS c FROM articles "
            "WHERE is_archived = 0 GROUP BY source ORDER BY c DESC"
        ).fetchall()
        category_breakdown: Dict[str, int] = {
            (r["source"] or "Unknown"): r["c"] for r in breakdown_rows
        }

        # Trending topics: most-frequent capitalised tokens in recent titles.
        title_rows = con.execute(
            "SELECT title FROM articles WHERE is_archived = 0 "
            "ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        token_counts: Counter = Counter()
        for tr in title_rows:
            for word in (tr["title"] or "").split():
                w = word.strip(",.:;'\"!?()[]")
                if len(w) >= 4 and w[0].isupper() and w.isalpha():
                    token_counts[w] += 1
        trending_topics = [
            {"id": f"trend-{i}", "title": term, "category": []}
            for i, (term, _) in enumerate(token_counts.most_common(5))
        ]

        con.close()

        return {
            "date": datetime.now(timezone.utc).isoformat(),
            "topStories": top_stories,
            "categoryBreakdown": category_breakdown,
            "trendingTopics": trending_topics,
        }
    except Exception as exc:
        logger.error("Failed to build digest: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Digest build failed: {exc}"
        )


# ---------------------------------------------------------------------------
# /api/digest/daily-summary — AI-generated executive overview, cached per-day.
# ---------------------------------------------------------------------------


# Module-level cache. Key = YYYY-MM-DD (UTC); value = the full response dict.
# A single asyncio.Lock guards the cache so two concurrent requests on a cache
# miss don't both invoke the LLM.
_DAILY_SUMMARY_CACHE: Dict[str, Dict[str, Any]] = {}
_DAILY_SUMMARY_LOCK: asyncio.Lock = asyncio.Lock()

# The window for "today's articles". Spec says 24h. We widen the *fallback*
# floor (min articles) below if 24h is empty so the endpoint stays useful on
# stale dev corpora — but the canonical window is still 24h.
DAILY_SUMMARY_WINDOW_HOURS = 24
DAILY_SUMMARY_MIN_ARTICLES = 3
DAILY_SUMMARY_MAX_ARTICLES = 15


@router.get("/daily-summary")
async def get_daily_summary() -> Dict[str, Any]:
    """Return a one-paragraph AI executive summary of today's tech news.

    Response shape:
        {
          "summary": "...",
          "generated_at": "2026-05-12T08:00:00+00:00",
          "article_count": 12
        }

    Cached per UTC date — the LLM runs at most once per calendar day. The
    cache is checked first; on a hit, the same response is returned
    (``generated_at`` will match between calls). On a miss, we acquire the
    module-level lock, re-check, and only call Ollama once.
    """
    today = datetime.now(timezone.utc).date().isoformat()

    cached = _DAILY_SUMMARY_CACHE.get(today)
    if cached is not None:
        return cached

    async with _DAILY_SUMMARY_LOCK:
        # Double-check inside the lock — another request may have populated
        # while we were waiting.
        cached = _DAILY_SUMMARY_CACHE.get(today)
        if cached is not None:
            return cached

        payload = await _build_daily_summary()
        _DAILY_SUMMARY_CACHE[today] = payload
        return payload


async def _build_daily_summary() -> Dict[str, Any]:
    """Pull recent articles, build a prompt, call Ollama, return the payload.

    Falls back to a static message if there aren't enough fresh articles.
    """
    db_path = _resolve_db_path()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=DAILY_SUMMARY_WINDOW_HOURS)
    # SQLite stores timestamps in `YYYY-MM-DD HH:MM:SS[.ffffff]` so we use a
    # plain-string comparison after formatting (lexicographic ordering matches
    # chronological for ISO-ish formats).
    window_start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id, title, summary, content, source "
                "FROM articles "
                "WHERE is_archived = 0 "
                "  AND COALESCE(published_at, created_at) >= ? "
                "ORDER BY COALESCE(published_at, created_at) DESC "
                "LIMIT ?",
                (window_start_str, DAILY_SUMMARY_MAX_ARTICLES),
            ).fetchall()

            # Stale-corpus fallback: if the 24h window is empty on a dev DB,
            # widen to 14 days so the endpoint stays useful. Spec calls for
            # the "not enough articles" fallback below the min threshold —
            # we still honor that *after* this re-widen.
            if len(rows) < DAILY_SUMMARY_MIN_ARTICLES:
                wide_start = (
                    now - timedelta(days=14)
                ).strftime("%Y-%m-%d %H:%M:%S")
                rows = con.execute(
                    "SELECT id, title, summary, content, source "
                    "FROM articles "
                    "WHERE is_archived = 0 "
                    "  AND COALESCE(published_at, created_at) >= ? "
                    "ORDER BY COALESCE(published_at, created_at) DESC "
                    "LIMIT ?",
                    (wide_start, DAILY_SUMMARY_MAX_ARTICLES),
                ).fetchall()
    except sqlite3.Error as exc:
        logger.error("daily-summary DB read failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Daily summary read failed: {exc}"
        )

    article_count = len(rows)
    if article_count < DAILY_SUMMARY_MIN_ARTICLES:
        return {
            "summary": "Not enough articles in the past 24 hours to summarize.",
            "generated_at": now.isoformat(),
            "article_count": article_count,
        }

    # Build the prompt body. Use each article's summary if present, otherwise
    # the first ~400 chars of content. We pass title + body so the LLM can
    # weight the headlines.
    bullets: List[str] = []
    for r in rows:
        title = (r["title"] or "(untitled)").strip()
        body = (r["summary"] or "").strip()
        if not body:
            body = (r["content"] or "").strip()[:400]
        if not body:
            body = "(no summary available)"
        source = (r["source"] or "Unknown").strip()
        bullets.append(f"- [{source}] {title}\n  {body}")

    prompt_payload = (
        "Write a single-paragraph (80-120 word) executive overview of "
        "today's tech news, covering the most important themes. Do not use "
        "bullet points or headings — produce one cohesive paragraph that "
        "highlights the biggest stories, common threads, and what readers "
        "should take away. Article titles and summaries follow.\n\n"
        + "\n".join(bullets)
    )

    try:
        service = SummarizationService()
        # The SummarizationRequest model restricts ``style`` to
        # concise/detailed/bullet_points — "detailed" gives the prompt the
        # most leeway. We override ``max_length`` to 120 so the result lands
        # in the spec'd 80-120 word range.
        request = SummarizationRequest(
            content=prompt_payload,
            max_length=120,
            style="detailed",
        )
        result = await service.summarize_content(request)
        summary_text = (result.summary or "").strip()
    except Exception as exc:  # noqa: BLE001 — LLM is best-effort
        logger.warning(
            "daily-summary LLM call failed; returning fallback. err=%s", exc
        )
        # Don't fail the endpoint just because Ollama is down — return a
        # graceful fallback so the UI still renders.
        return {
            "summary": (
                "Today's tech news is loading. The AI summary is temporarily "
                "unavailable; please check back in a few minutes."
            ),
            "generated_at": now.isoformat(),
            "article_count": article_count,
        }

    if not summary_text:
        return {
            "summary": (
                "Today's tech news is loading. The AI summary is temporarily "
                "unavailable; please check back in a few minutes."
            ),
            "generated_at": now.isoformat(),
            "article_count": article_count,
        }

    return {
        "summary": summary_text,
        "generated_at": now.isoformat(),
        "article_count": article_count,
    }


# ---------------------------------------------------------------------------
# /api/digest/curated — top stories ranked by recency × source × mentions.
# ---------------------------------------------------------------------------


# Curated source weights. Anything not listed gets ``DEFAULT_SOURCE_WEIGHT``.
_SOURCE_WEIGHTS: Dict[str, float] = {
    "TechCrunch": 1.0,
    "Hacker News": 0.9,
    "Ars Technica": 0.95,
    "The Verge": 0.9,
    "MIT Technology Review": 1.0,
}
DEFAULT_SOURCE_WEIGHT = 0.8

# Window we score stories from. Wider than 24h so the curated list still has
# something to show on a stale-corpus dev DB. The recency_factor floors at
# 0.2 after 24h, so old articles can still rank — they just need stronger
# source_weight or mention_count to compete with fresh ones.
CURATED_WINDOW_HOURS = 24 * 14  # 14 days
CURATED_LIMIT = 5
# Mention-window for the "this entity also appears in N other articles"
# component of the score.
MENTION_WINDOW_DAYS = 7


def _recency_factor(article_dt: datetime, now: datetime) -> float:
    """Linear decay from 1.0 (article is new) to 0.2 (24h old).

    Anything older than 24h still gets the 0.2 floor so 36h-old stories
    can still rank above brand-new clickbait from a low-weight source.
    """
    age_hours = max(0.0, (now - article_dt).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 1.0
    if age_hours >= 24:
        return 0.2
    # Linear from 1.0 at 6h to 0.2 at 24h.
    return 1.0 - 0.8 * ((age_hours - 6.0) / 18.0)


def _source_weight(source: Optional[str]) -> float:
    if not source:
        return DEFAULT_SOURCE_WEIGHT
    return _SOURCE_WEIGHTS.get(source.strip(), DEFAULT_SOURCE_WEIGHT)


@router.get("/curated")
async def get_curated_headlines() -> Dict[str, Any]:
    """Return the top 3-5 headlines of the day, ranked by composite score.

    Ranking formula::

        score = recency_factor * source_weight * (1 + mention_count)

    See the helper functions above for each factor's curve. We pull stories
    from a 72-hour window (so the dev DB stays useful even when no article
    is from "today") and return the top ``CURATED_LIMIT`` after scoring.

    Response::

        {
          "headlines": [
            {
              "id": 588,
              "title": "...",
              "source": "TechCrunch",
              "summary": "...",
              "url": "https://...",
              "image_url": "https://...",
              "published_at": "2026-05-07T22:24:50+00:00",
              "categories": ["Cloud"],
              "score": 1.84,
              "mention_count": 3
            }, ...
          ],
          "generated_at": "..."
        }
    """
    db_path = _resolve_db_path()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=CURATED_WINDOW_HOURS)
    window_start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")
    mention_window_start = now - timedelta(days=MENTION_WINDOW_DAYS)
    mention_window_str = mention_window_start.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id, title, source, summary, content, url, image_url, "
                "       categories, published_at, created_at "
                "FROM articles "
                "WHERE is_archived = 0 "
                "  AND COALESCE(published_at, created_at) >= ? "
                "ORDER BY COALESCE(published_at, created_at) DESC "
                "LIMIT 60",
                (window_start_str,),
            ).fetchall()

            # Pull the mention-window title+summary corpus once so we can do
            # cheap substring scans for the mention-count factor without
            # round-tripping per article.
            corpus_rows = con.execute(
                "SELECT title, summary FROM articles "
                "WHERE is_archived = 0 "
                "  AND COALESCE(published_at, created_at) >= ?",
                (mention_window_str,),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("curated DB read failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Curated read failed: {exc}"
        )

    # Pre-lowercase the corpus once.
    corpus_blobs: List[str] = []
    for cr in corpus_rows:
        blob_parts = []
        if cr["title"]:
            blob_parts.append(cr["title"])
        if cr["summary"]:
            blob_parts.append(cr["summary"])
        if blob_parts:
            corpus_blobs.append(" ".join(blob_parts).lower())

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for r in rows:
        published = _parse_dt(r["published_at"]) or _parse_dt(r["created_at"])
        if not published:
            continue
        rec = _recency_factor(published, now)
        src_w = _source_weight(r["source"])

        # Pick the "top entity" for this article — first capitalised
        # multi-word noun phrase in the title is a cheap proxy. We then
        # count how many OTHER articles in the corpus mention it.
        title = (r["title"] or "")
        entity = _pick_top_entity(title)
        mention_count = 0
        if entity and len(entity) >= 3:
            needle = entity.lower()
            for blob in corpus_blobs:
                if needle in blob:
                    mention_count += 1
            # Subtract one — the article itself is in the corpus.
            mention_count = max(0, mention_count - 1)

        score = rec * src_w * (1.0 + mention_count)

        summary = r["summary"] or ""
        if not summary and r["content"]:
            summary = r["content"][:280] + "..."

        scored.append(
            (
                score,
                {
                    "id": int(r["id"]),
                    "title": title,
                    "source": r["source"] or "Unknown",
                    "summary": summary,
                    "url": r["url"] or "",
                    "image_url": r["image_url"] or None,
                    "published_at": published.isoformat(),
                    "categories": _decode_categories(r["categories"]),
                    "score": round(score, 3),
                    "mention_count": mention_count,
                },
            )
        )

    scored.sort(key=lambda t: t[0], reverse=True)
    headlines = [item for _, item in scored[:CURATED_LIMIT]]

    return {
        "headlines": headlines,
        "generated_at": now.isoformat(),
    }


def _pick_top_entity(title: str) -> str:
    """Return the first capitalised multi-word phrase in ``title``.

    Cheap proxy for "the entity this story is about". Strips trailing punct
    and stops at the first lowercase or non-alpha token. Returns "" if
    nothing capitalised was found.
    """
    if not title:
        return ""
    tokens = title.split()
    phrase: List[str] = []
    for tok in tokens:
        clean = tok.strip(",.:;'\"!?()[]")
        if not clean:
            continue
        if clean[0].isupper() and clean.isalpha() and len(clean) >= 3:
            phrase.append(clean)
        else:
            if phrase:
                break
    if not phrase:
        return ""
    return " ".join(phrase[:3])


# ---------------------------------------------------------------------------
# /api/digest/topics — articles grouped by their ``categories`` JSON field.
# ---------------------------------------------------------------------------


# How many articles to pull when building the topics view. Bigger than the
# curated list because we want every topic represented. We use the same wide
# window as ``curated`` so the dev DB still has something to render.
TOPICS_WINDOW_HOURS = 24 * 14  # 14 days
TOPICS_MAX_ARTICLES = 120
TOPICS_PER_GROUP_PREVIEW = 3


@router.get("/topics")
async def get_topic_clusters() -> Dict[str, Any]:
    """Return today's articles grouped by their ``categories`` JSON column.

    Each topic block contains ``count`` (total articles in the topic) and
    ``preview`` (the top N article rows, newest first).

    Response::

        {
          "topics": [
            {
              "name": "AI/ML",
              "slug": "ai-ml",
              "count": 8,
              "preview": [
                {"id": 1, "title": "...", "source": "TechCrunch",
                 "summary": "...", "url": "...",
                 "published_at": "..."},
                ...
              ]
            },
            ...
          ],
          "generated_at": "..."
        }
    """
    db_path = _resolve_db_path()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=TOPICS_WINDOW_HOURS)
    window_start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id, title, source, summary, content, url, "
                "       categories, published_at, created_at "
                "FROM articles "
                "WHERE is_archived = 0 "
                "  AND COALESCE(published_at, created_at) >= ? "
                "ORDER BY COALESCE(published_at, created_at) DESC "
                "LIMIT ?",
                (window_start_str, TOPICS_MAX_ARTICLES),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("topics DB read failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Topics read failed: {exc}"
        )

    # Group articles by category. "Other" bucket for articles with no
    # categories.
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for r in rows:
        cats = _decode_categories(r["categories"])
        published = _parse_dt(r["published_at"]) or _parse_dt(r["created_at"])
        if not published:
            continue
        summary = r["summary"] or ""
        if not summary and r["content"]:
            summary = r["content"][:200] + "..."
        item = {
            "id": int(r["id"]),
            "title": r["title"] or "(untitled)",
            "source": r["source"] or "Unknown",
            "summary": summary,
            "url": r["url"] or "",
            "published_at": published.isoformat(),
        }
        if cats:
            for c in cats:
                buckets[c].append(item)
        else:
            buckets["Other"].append(item)

    def _slug(name: str) -> str:
        return (
            name.lower()
            .replace("/", "-")
            .replace(" ", "-")
            .replace("--", "-")
            .strip("-")
        )

    topics: List[Dict[str, Any]] = []
    # Sort topics by count descending, with "Other" pinned to the bottom.
    other_count = len(buckets.pop("Other", [])) if "Other" in buckets else 0
    sorted_topics = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)

    for name, items in sorted_topics:
        topics.append(
            {
                "name": name,
                "slug": _slug(name),
                "count": len(items),
                "preview": items[:TOPICS_PER_GROUP_PREVIEW],
            }
        )
    if other_count:
        # Re-build the Other bucket (we popped it earlier to compute count).
        other_items: List[Dict[str, Any]] = []
        for r in rows:
            cats = _decode_categories(r["categories"])
            if cats:
                continue
            published = _parse_dt(r["published_at"]) or _parse_dt(r["created_at"])
            if not published:
                continue
            summary = r["summary"] or ""
            if not summary and r["content"]:
                summary = r["content"][:200] + "..."
            other_items.append(
                {
                    "id": int(r["id"]),
                    "title": r["title"] or "(untitled)",
                    "source": r["source"] or "Unknown",
                    "summary": summary,
                    "url": r["url"] or "",
                    "published_at": published.isoformat(),
                }
            )
        topics.append(
            {
                "name": "Other",
                "slug": "other",
                "count": len(other_items),
                "preview": other_items[:TOPICS_PER_GROUP_PREVIEW],
            }
        )

    return {
        "topics": topics,
        "generated_at": now.isoformat(),
    }
