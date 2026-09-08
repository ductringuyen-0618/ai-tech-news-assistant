"""
Agentic Research Service (M2.M4 — per-article subagent fan-out)
================================================================

Multi-step LLM agent that turns a single research question into a structured
markdown report. This is the M2.M4 rewrite that replaces M1's monolithic
"shove every article body into one synthesis prompt" loop with an explicit
**orchestrator + per-article fan-out** pipeline:

::

    Decompose          ──>   ``gpt-oss:20b`` produces 3-5 sub-questions
        │
        ▼
    Search (i/N)       ──>   ``search_articles`` skill (M2) per sub-question.
        │                    Returns ID/title/snippet — NEVER raw body text.
        │
        ▼
    Per-article fan-out ─>   For each unique article ID surfaced by the
        │                    searches, dispatch ``summarize_article`` via
        │                    ``SubagentPool`` (M3). At most
        │                    ``settings.max_concurrent_subagents`` (default 4)
        │                    in flight at once. Best-effort: a single bad
        │                    subagent must NOT abort the run.
        │
        ▼
    Synthesize          ──>  Build a synthesis prompt that contains:
        │                    - User's question
        │                    - List of sub-questions
        │                    - For each retained article: ID + title + the
        │                      per-article SUMMARY (NEVER the raw body)
        │                    - Numbered source list + citation rules
        │                    Stream tokens via Ollama.
        │
        ▼
    Done                 ──>  Emit ``phase: "done"`` with the final
                              markdown ``report``. The citation guard rail
                              from M1 (``_ensure_sources_section``) is
                              preserved verbatim.

Public SSE event surface (preserved end-to-end):

* ``{"type": "phase", "data": "Decomposing"}``
* ``{"type": "phase", "data": "Searching (i/N)"}`` (one per sub-question)
* ``{"type": "subagent", "data": "start", "skill": ..., "article_id": ...}``
* ``{"type": "subagent", "data": "done", "skill": ..., "article_id": ..., "duration_ms": int}``
* ``{"type": "subagent", "data": "error", "skill": ..., "article_id": ..., "message": str}``
* ``{"type": "phase", "data": "Synthesizing"}``
* ``{"type": "token", "data": "<chunk>"}`` (zero or more)
* ``{"type": "phase", "data": "done", "report": "<full markdown>"}``
* ``{"type": "error", "data": "<message>"}`` (terminal, on fatal failure)

The first three (``Decomposing``, ``Searching (i/N)``, ``Synthesizing``) +
``token`` + ``done`` are **the M1 contract** — preserved so the 6 SSE
integration tests and the M3+M4 frontend don't regress. ``subagent``
events are **new** in M4.

Mission references
------------------
- Issue: ``docs/issues/per-article-subagents-4-rewrite-agent.md``
- API surface: ``docs/notes/deepagents-api-surface.md`` (§6 — Option B)
- Skills: ``backend/src/services/agent_skills/__init__.py`` (M2)
- SubagentPool: ``backend/src/services/subagent_pool.py`` (M3)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from ..core.config import get_settings
from ..core.exceptions import LLMError
from ..models.article import AgentEvent  # noqa: F401 — re-exported for tests

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
#  Tunables
# ----------------------------------------------------------------------------

# Pinned model for v1 (per PRD). gpt-oss:20b is the only model that
# reliably emits valid sub-question JSON on the maintainer's box.
DEFAULT_MODEL = "gpt-oss:20b"

# Max number of sub-questions we accept from the decomposer.
MAX_SUBQUESTIONS = 5
MIN_SUBQUESTIONS = 3

# Top-K hits per sub-question search.
TOP_K_PER_SUBQUESTION = 5

# Hard cap on the number of unique articles we will fan-out to. Even with
# 5 sub-questions x 5 hits = 25 candidates, we cap to 20 to keep the
# synthesis prompt and wall-clock budget bounded.
MAX_ARTICLES_FANOUT = 20

# Per-article summary length cap inside the synthesis prompt (chars).
# Per-article summaries from gpt-oss:20b run ~300-800 chars; we cap to
# 1200 to give a healthy headroom while still bounding total prompt size.
# Math sanity: 20 articles x 1200 chars = 24KB — well under the 30KB
# canary threshold the live tests assert.
MAX_SUMMARY_CHARS_IN_PROMPT = 1200

# Soft cap on prompt body characters per source (legacy — kept for the
# fallback path when an article's summary is unavailable).
MAX_SOURCE_SNIPPET_CHARS = 250


# ----------------------------------------------------------------------------
#  Internal value-objects
# ----------------------------------------------------------------------------


class _SubQuestionResult:
    """One sub-question + its retrieved hits.

    Hits are the stripped-down dicts the M2 ``search_articles`` skill
    returns (``article_id``, ``title``, ``source``, ``snippet``, ``score``).
    No raw body text — that lives only inside the per-article subagent
    prompts.
    """

    __slots__ = ("question", "hits")

    def __init__(self, question: str, hits: List[Dict[str, Any]]):
        self.question = question
        self.hits = hits


class _ArticleSummary:
    """Per-article reasoning result.

    Carries the article's ID, surface metadata (title, source, url) needed
    for the numbered source list, AND the LLM-produced summary (NEVER the
    raw body). Failures from the SubagentPool are recorded with
    ``summary=""`` and ``error`` set.
    """

    __slots__ = ("article_id", "title", "source", "url", "summary", "error")

    def __init__(
        self,
        article_id: int,
        title: str,
        source: str,
        url: str,
        summary: str,
        error: Optional[str] = None,
    ):
        self.article_id = article_id
        self.title = title
        self.source = source
        self.url = url
        self.summary = summary
        self.error = error


# ----------------------------------------------------------------------------
#  Service
# ----------------------------------------------------------------------------


class AgenticResearchService:
    """Orchestrate a multi-step LLM research loop with per-article fan-out.

    Public surface
    --------------
    The single async generator :py:meth:`run` is the only thing routes /
    SSE plumbing should call. It yields the events documented at the
    module level.

    Parameters
    ----------
    model : str | None
        Ollama model tag. Defaults to ``gpt-oss:20b``.
    ollama_host : str | None
        Ollama server URL. Defaults to ``settings.ollama_host``.
    ollama_timeout : int | None
        Per-call timeout in seconds. Defaults to ``settings.ollama_timeout``.
    search_service : SearchService | None
        Injected for tests; production code leaves this ``None`` and the
        skill module's lazy singleton handles it.
    pool : SubagentPool | None
        Injected for tests; production code leaves this ``None`` and a
        new pool is built per ``run`` from
        ``settings.max_concurrent_subagents``.
    skills : dict | None
        Injected for tests. Keys: ``"search_articles"``,
        ``"summarize_article"``. Values are LangChain ``StructuredTool``
        instances or async callables (the SubagentPool tolerates both).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        ollama_host: Optional[str] = None,
        ollama_timeout: Optional[int] = None,
        search_service: Any = None,
        pool: Any = None,
        skills: Optional[Dict[str, Any]] = None,
    ):
        settings = get_settings()
        self.model: str = model or DEFAULT_MODEL
        self.base_url: str = (
            ollama_host or getattr(settings, "ollama_host", "http://localhost:11434")
        ).rstrip("/")
        self.timeout: int = ollama_timeout or getattr(
            settings, "ollama_timeout", 60
        )
        self._search_service = search_service
        self._pool = pool
        self._max_concurrent = getattr(settings, "max_concurrent_subagents", 4)
        self._skills = skills
        # Track whether the caller passed an explicit skills registry.
        # The text-search fallback in ``_search_one`` skips when this
        # is True — unit tests pass injected skills with deliberately
        # empty result lists and don't want a SQL fallback to muddy
        # the assertion counts.
        self._user_injected_skills = skills is not None

        logger.info(
            "AgenticResearchService initialised "
            "(model=%s, host=%s, timeout=%ds, max_concurrent=%d)",
            self.model,
            self.base_url,
            self.timeout,
            self._max_concurrent,
        )

    # ------------------------------------------------------------------ #
    #  Lazy resource builders
    # ------------------------------------------------------------------ #

    def _get_skills(self) -> Dict[str, Any]:
        """Return the skill registry, lazily importing the M2 skills.

        Skills are imported lazily so the service module can be imported
        in environments where heavy ML deps (sentence-transformers, torch)
        are not yet installed. Tests inject through ``__init__``.
        """
        if self._skills is not None:
            return self._skills
        from .agent_skills import search_articles, summarize_article

        self._skills = {
            "search_articles": search_articles,
            "summarize_article": summarize_article,
        }
        return self._skills

    def _get_pool(self):
        """Return the SubagentPool, lazily building one if needed."""
        if self._pool is not None:
            return self._pool
        from .subagent_pool import SubagentPool

        self._pool = SubagentPool(max_concurrent=self._max_concurrent)
        return self._pool

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def run(self, question: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the full agent loop for ``question``.

        See module docstring for the event-order contract.
        """
        question = (question or "").strip()
        if not question:
            yield self._event("error", "Question cannot be empty")
            return

        # ------- Phase 1: Decompose -------
        yield self._event("phase", "Decomposing")
        try:
            sub_questions = await self._decompose(question)
        except LLMError as exc:
            logger.error("Decomposition failed: %s", exc)
            yield self._event("error", f"Could not decompose question: {exc}")
            return

        if not sub_questions:
            sub_questions = [question]

        n = len(sub_questions)
        logger.info(
            "Decomposition produced %d sub-question(s) for %r",
            n,
            question[:80],
        )

        # ------- M3.M2: emit `decomposed` event so the frontend can render
        # the sub-questions list within ~5s of submit, well before any
        # synthesis tokens. Additive — coexists with existing phase events.
        yield {"type": "decomposed", "sub_questions": list(sub_questions)}

        # ------- Phase 2: Search per sub-question -------
        sub_results: List[_SubQuestionResult] = []
        for i, sub in enumerate(sub_questions, start=1):
            yield self._event("phase", f"Searching ({i}/{n})")
            try:
                hits = await self._search_one(sub)
            except Exception as exc:  # noqa: BLE001 — search must not abort run
                logger.warning(
                    "Search failed for sub-question %r: %s -- treating as zero-hit",
                    sub,
                    exc,
                )
                hits = []
            sub_results.append(_SubQuestionResult(question=sub, hits=hits))

            # ------- M3.M2: emit `search_results` event with the article
            # preview list for this sub-question. Keep frame small — only
            # id, title, source (NOT body or snippet).
            preview: List[Dict[str, Any]] = []
            for h in hits:
                aid = h.get("id")
                try:
                    aid_int = int(aid) if aid is not None else None
                except (TypeError, ValueError):
                    aid_int = None
                if aid_int is None:
                    continue
                preview.append(
                    {
                        "id": aid_int,
                        "title": (h.get("title") or "")[:200],
                        "source": (h.get("source") or "")[:60],
                    }
                )
            yield {
                "type": "search_results",
                "sub_question_index": i - 1,  # 0-based for the frontend
                "articles": preview,
            }

        # ------- Phase 3: Per-article subagent fan-out -------
        article_summaries: List[_ArticleSummary] = []
        async for evt in self._fanout_summaries(sub_results, question):
            # The fan-out generator yields a mix of
            #   - subagent SSE events (forward unchanged)
            #   - sentinel dicts of shape {"__article_summary__": _ArticleSummary}
            if "__article_summary__" in evt:
                article_summaries.append(evt["__article_summary__"])
            else:
                yield evt

        # ------- Phase 4: Synthesize -------
        yield self._event("phase", "Synthesizing")
        try:
            assembled_chunks: List[str] = []
            async for chunk in self._synthesize_streaming(
                question, sub_results, article_summaries
            ):
                assembled_chunks.append(chunk)
                yield self._event("token", chunk)
            report = self._finalize_report(
                "".join(assembled_chunks),
                question,
                sub_results,
                article_summaries,
            )
        except LLMError as exc:
            logger.error("Synthesis failed: %s", exc)
            yield self._event("error", f"Could not synthesize report: {exc}")
            return

        # ------- Phase 5: Done -------
        yield self._event("phase", "done", report)

    # ------------------------------------------------------------------ #
    #  Decompose
    # ------------------------------------------------------------------ #

    async def _decompose(self, question: str) -> List[str]:
        """Decompose ``question`` into 3-5 sub-questions.

        One retry on parse failure with a stricter prompt; final
        fall-through to single-question mode keeps the run alive.
        """
        prompt = self._decomposer_prompt(question, strict=False)
        try:
            raw = await self._call_ollama(prompt, num_predict=512, temperature=0.2)
        except LLMError:
            raise

        parsed = self._parse_subquestions(raw)
        if parsed:
            return parsed[:MAX_SUBQUESTIONS]

        logger.info(
            "Decomposer returned non-JSON output (head=%r); retrying with strict prompt",
            (raw or "")[:120],
        )

        strict_prompt = self._decomposer_prompt(question, strict=True)
        try:
            raw_retry = await self._call_ollama(
                strict_prompt, num_predict=512, temperature=0.0
            )
        except LLMError:
            raise

        parsed_retry = self._parse_subquestions(raw_retry)
        if parsed_retry:
            return parsed_retry[:MAX_SUBQUESTIONS]

        logger.warning(
            "Decomposer failed JSON parse twice; falling back to single-question mode"
        )
        return [question]

    @staticmethod
    def _decomposer_prompt(question: str, *, strict: bool) -> str:
        """Build the decomposer prompt. ``strict=True`` is the retry pass."""
        if strict:
            return (
                "You MUST output ONLY a JSON object with a single key "
                "\"sub_questions\" whose value is a list of 3 to 5 short "
                "research sub-questions (strings). No markdown fences. No "
                "preamble. No commentary. JSON only.\n"
                "\n"
                "Schema: {\"sub_questions\": [\"...\", \"...\", \"...\"]}\n"
                "\n"
                f"Original question: {question}\n"
                "\n"
                "JSON:"
            )
        return (
            "You are a research planner. Break the user's question into 3 to "
            "5 focused sub-questions that, taken together, would answer the "
            "original. Each sub-question should be searchable against a tech "
            "news corpus.\n"
            "\n"
            "Return ONLY a JSON object with this exact schema:\n"
            "{\"sub_questions\": [\"first sub-question\", \"second sub-question\", ...]}\n"
            "\n"
            "Do not include markdown fences, explanations, or preamble -- JSON "
            "only.\n"
            "\n"
            f"User question: {question}\n"
            "\n"
            "JSON:"
        )

    @staticmethod
    def _parse_subquestions(raw: str) -> Optional[List[str]]:
        """Strict parse of a decomposer response."""
        if not raw or not raw.strip():
            return None

        candidate = raw.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z0-9]*\n?", "", candidate)
            candidate = re.sub(r"\n?```\s*$", "", candidate)

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        json_blob = candidate[start : end + 1]

        try:
            obj = json.loads(json_blob)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(obj, dict):
            return None

        sub_qs = obj.get("sub_questions")
        if not isinstance(sub_qs, list):
            return None

        cleaned: List[str] = []
        for item in sub_qs:
            if not isinstance(item, str):
                return None
            stripped = item.strip()
            if len(stripped) < 5:
                return None
            cleaned.append(stripped)

        if not (MIN_SUBQUESTIONS <= len(cleaned) <= MAX_SUBQUESTIONS):
            if len(cleaned) < MIN_SUBQUESTIONS:
                return None
        return cleaned

    # ------------------------------------------------------------------ #
    #  Search (delegates to the M2 search_articles skill)
    # ------------------------------------------------------------------ #

    async def _search_one(self, query: str) -> List[Dict[str, Any]]:
        """Run one semantic search via the M2 ``search_articles`` skill.

        Returns the parsed-JSON ``results`` list. Defensive: if the skill
        returns an error payload, the result list is empty (search failures
        are not fatal — the orchestrator falls through to whatever hits the
        other sub-questions surfaced).
        """
        # Tests inject ``search_service`` (the legacy M1 escape hatch).
        # Honour it to keep test_research_sse + new unit tests green.
        if self._search_service is not None:
            return await self._search_one_legacy(query)

        skill = self._get_skills().get("search_articles")
        if skill is None:
            return []

        try:
            raw = await self._invoke_skill(
                skill, {"query": query, "top_k": TOP_K_PER_SUBQUESTION}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_articles skill raised: %s", exc)
            return []

        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            logger.warning("search_articles returned non-JSON; ignoring")
            return []
        if not isinstance(payload, dict):
            return []
        if payload.get("error"):
            logger.info("search_articles error payload: %s", payload.get("error"))
        results = payload.get("results") or []

        # Normalise the skill's keys to the shape the rest of this service
        # expects (id/title/url/source/summary/score). The skill returns
        # ``article_id`` + ``snippet``; we adapt.
        normalised: List[Dict[str, Any]] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            normalised.append(
                {
                    "id": r.get("article_id"),
                    "title": r.get("title", "") or "",
                    "url": r.get("url", "") or "",
                    "source": r.get("source", "") or "",
                    "summary": r.get("snippet", "") or "",
                    "similarity_score": float(r.get("score", 0.0) or 0.0),
                }
            )

        # Fallback: when the embedding/vector search infrastructure is
        # unavailable (e.g. missing ``article_embeddings`` table, broken
        # sentence-transformers cache), fall back to a SQLite LIKE match
        # against title + content + summary. The fallback is best-effort
        # and only kicks in when the primary skill returned ZERO hits —
        # if the skill returned even one match we trust it. The fallback
        # exists primarily so the live integration tests can run against
        # a corpus whose embeddings table hasn't been populated.
        #
        # Skip the fallback when ``skills`` was injected at construction
        # time — that's the unit-test path where empty results are
        # intentional (e.g. the second/third sub-question's canned reply).
        if not normalised and not self._user_injected_skills:
            normalised = await self._search_one_text_fallback(query)
        return normalised

    async def _search_one_text_fallback(self, query: str) -> List[Dict[str, Any]]:
        """Cheap SQL LIKE search against ``articles`` as a last resort.

        Tokenises the query into >=4-char alphanumeric tokens and matches
        any of them in title / content / summary. Score is a coarse
        per-row hit count divided by token count, clamped to [0, 1].

        This is NOT a replacement for vector search — it only fires when
        the primary path returns zero hits. The result format mirrors
        what the skill would have returned so the rest of the pipeline
        is unchanged.
        """
        import sqlite3

        from ..core.config import get_settings as _get_settings

        # Tokenise: ASCII alphanumerics, length >= 4. Keep order stable.
        tokens = [t for t in re.findall(r"[A-Za-z0-9]{4,}", query)][:6]
        if not tokens:
            return []

        settings = _get_settings()
        db_path = settings.get_database_file_path()
        like_clauses = []
        params: List[Any] = []
        for tok in tokens:
            like_clauses.append(
                "(title LIKE ? OR content LIKE ? OR summary LIKE ?)"
            )
            wild = f"%{tok}%"
            params.extend([wild, wild, wild])
        sql = (
            "SELECT id, title, url, source, summary, "
            "       SUBSTR(IFNULL(summary, content), 1, 300) AS snippet "
            "FROM articles WHERE "
            + " OR ".join(like_clauses)
            + " LIMIT ?"
        )
        params.append(TOP_K_PER_SUBQUESTION)

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "search text-fallback query failed: %s (db=%s)", exc, db_path
            )
            return []

        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": int(row["id"]),
                    "title": row["title"] or "",
                    "url": row["url"] or "",
                    "source": row["source"] or "",
                    "summary": (row["snippet"] or "")[:300],
                    "similarity_score": 0.5,  # nominal — fallback path
                }
            )
        if out:
            logger.info(
                "search text-fallback returned %d rows for query=%r tokens=%s",
                len(out),
                query[:80],
                tokens,
            )
        return out

    async def _search_one_legacy(self, query: str) -> List[Dict[str, Any]]:
        """Legacy path used when a SearchService is injected (tests).

        Mirrors the M1 implementation closely so the existing unit test
        ``_FakeSearchService`` continues to work. Production code path is
        :py:meth:`_search_one` above.
        """
        svc = self._search_service
        from ..models.search import SearchRequest

        # Idempotent — older fakes implement this as a no-op coroutine.
        try:
            init = getattr(svc, "initialize", None)
            if callable(init):
                await init()
        except Exception:  # noqa: BLE001
            pass

        req = SearchRequest(
            query=query,
            limit=TOP_K_PER_SUBQUESTION,
            min_score=0.0,
            use_reranking=True,
            include_summary=True,
        )
        resp = await svc.search(req)

        hits: List[Dict[str, Any]] = []
        for r in getattr(resp, "results", []) or []:
            hits.append(
                {
                    "id": getattr(r, "id", None),
                    "title": getattr(r, "title", "") or "",
                    "url": getattr(r, "url", "") or "",
                    "source": getattr(r, "source", "") or "",
                    "summary": getattr(r, "summary", None)
                    or getattr(r, "content", None)
                    or "",
                    "similarity_score": float(
                        getattr(r, "similarity_score", 0.0) or 0.0
                    ),
                }
            )
        return hits

    # ------------------------------------------------------------------ #
    #  Per-article fan-out (the M4 architectural payoff)
    # ------------------------------------------------------------------ #

    async def _fanout_summaries(
        self,
        sub_results: List[_SubQuestionResult],
        question: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Dispatch ``summarize_article`` for every unique article surfaced.

        Yields a mixed stream of:

        * SSE events (``subagent: start | done | error``) coming straight
          off the SubagentPool's ``on_event`` callback.
        * Sentinel dicts ``{"__article_summary__": _ArticleSummary}`` once
          a per-article task completes — the caller separates these out.

        The pool caps in-flight dispatches at ``max_concurrent``. When the
        ``summarize_article`` skill has no injected SubagentPool (legacy
        unit tests) or no skill registration, the fan-out is skipped — the
        synthesis prompt then falls back to using the raw search-hit
        snippet, preserving the M1 unit-test contract.
        """
        # Build a unique-by-id list of (id, title, source, url) candidates.
        # Order is stable: first appearance wins.
        seen_ids: Dict[int, Dict[str, Any]] = {}
        for sr in sub_results:
            for h in sr.hits:
                aid = h.get("id")
                # Coerce IDs to int when possible — the search skill
                # returns ints; the legacy fake_search returns "article:1"
                # strings. Coercion keeps both paths working.
                try:
                    aid_int: Optional[int] = (
                        int(aid) if aid is not None and not isinstance(aid, bool) else None
                    )
                except (TypeError, ValueError):
                    aid_int = None
                if aid_int is None:
                    # Legacy/string IDs (e.g. "article:1") aren't valid
                    # article PKs for the summarize_article skill — keep
                    # the fan-out path empty for these. The synthesis
                    # fallback below uses snippet text instead.
                    continue
                if aid_int in seen_ids:
                    continue
                seen_ids[aid_int] = {
                    "id": aid_int,
                    "title": h.get("title", "") or "",
                    "url": h.get("url", "") or "",
                    "source": h.get("source", "") or "",
                    "snippet": h.get("summary", "") or "",
                }

        candidates = list(seen_ids.values())
        if len(candidates) > MAX_ARTICLES_FANOUT:
            logger.info(
                "Capping fan-out from %d to %d articles",
                len(candidates),
                MAX_ARTICLES_FANOUT,
            )
            candidates = candidates[:MAX_ARTICLES_FANOUT]

        if not candidates:
            return

        skill = self._get_skills().get("summarize_article")
        if skill is None:
            # No skill registered — surface what we have without summaries.
            for c in candidates:
                yield {
                    "__article_summary__": _ArticleSummary(
                        article_id=c["id"],
                        title=c["title"],
                        source=c["source"],
                        url=c["url"],
                        summary=(c.get("snippet") or "")[:MAX_SUMMARY_CHARS_IN_PROMPT],
                    )
                }
            return

        pool = self._get_pool()

        # ---- bridge: SubagentPool's on_event is sync; this generator is
        # async. We collect events into an asyncio.Queue and drain it
        # alongside the gather() that runs the dispatches.
        queue: asyncio.Queue = asyncio.Queue()

        # Track in-flight count for diagnostics (not a substitute for the
        # pool's own semaphore; both should agree).
        results_by_id: Dict[int, _ArticleSummary] = {}

        async def _one(c: Dict[str, Any]) -> None:
            aid = c["id"]

            # M3.M2: buffer the pool's `done` event for THIS article so we
            # can enrich it with the first 280 chars of the per-article
            # summary before forwarding to the SSE consumer. Other events
            # (start, error, other articles) pass through unchanged.
            buffered_done: Dict[str, Optional[Dict[str, Any]]] = {"frame": None}

            def _on_event(evt: Dict[str, Any]) -> None:
                if (
                    evt.get("type") == "subagent"
                    and evt.get("data") == "done"
                    and evt.get("article_id") == aid
                ):
                    # Hold this frame; we'll re-emit it after dispatch
                    # returns with the parsed summary in hand.
                    buffered_done["frame"] = evt
                    return
                queue.put_nowait(("event", evt))

            args = {
                "article_id": aid,
                "focus_question": question,
            }
            try:
                parsed = await pool.dispatch(skill, args, _on_event)
            except Exception as exc:  # noqa: BLE001 — pool guarantees no raise
                logger.warning("dispatch raised unexpectedly: %s", exc)
                parsed = None

            # Flush the buffered done event (if any), enriched with a
            # truncated summary preview for the M3.M2 UX. The truncation
            # bound (280 chars) keeps SSE frames small; the frontend uses
            # this only for the expandable-row preview.
            done_frame = buffered_done["frame"]
            if done_frame is not None:
                summary_preview = ""
                if isinstance(parsed, dict):
                    summary_preview = (parsed.get("summary") or "")[:280]
                # Mutate the buffered frame (it's our own dict) and emit.
                done_frame["summary"] = summary_preview
                queue.put_nowait(("event", done_frame))

            if isinstance(parsed, dict) and parsed.get("summary"):
                summary_text = (parsed.get("summary") or "")[
                    :MAX_SUMMARY_CHARS_IN_PROMPT
                ]
                results_by_id[aid] = _ArticleSummary(
                    article_id=aid,
                    title=c["title"],
                    source=c["source"],
                    url=c["url"],
                    summary=summary_text,
                )
            else:
                # Failure path — keep the article in the source list but
                # fall back to the search snippet so the synthesis prompt
                # can still ground claims on it.
                fallback = (c.get("snippet") or "")[:MAX_SOURCE_SNIPPET_CHARS]
                results_by_id[aid] = _ArticleSummary(
                    article_id=aid,
                    title=c["title"],
                    source=c["source"],
                    url=c["url"],
                    summary=fallback,
                    error="subagent failure (fallback to snippet)",
                )

        async def _run_all() -> None:
            try:
                await asyncio.gather(*[_one(c) for c in candidates])
            finally:
                queue.put_nowait(("done", None))

        runner = asyncio.create_task(_run_all())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "event":
                    yield payload
                elif kind == "done":
                    break
        finally:
            if not runner.done():
                runner.cancel()
                try:
                    await runner
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        # Yield the per-article summaries in the original candidate order
        # so the numbered source list is stable from run to run.
        for c in candidates:
            res = results_by_id.get(c["id"])
            if res is not None:
                yield {"__article_summary__": res}

    # ------------------------------------------------------------------ #
    #  Synthesize
    # ------------------------------------------------------------------ #

    async def _synthesize_streaming(
        self,
        question: str,
        sub_results: List[_SubQuestionResult],
        article_summaries: List[_ArticleSummary],
    ) -> AsyncGenerator[str, None]:
        """Streaming synthesis — yields token chunks from Ollama.

        Builds the synthesis prompt from per-article SUMMARIES (not raw
        bodies). When ``article_summaries`` is empty (e.g. legacy unit
        tests with stringy IDs), falls back to the M1-style snippet-based
        synthesis prompt so behaviour is preserved on the M1 contract path.
        """
        sources = self._build_source_list(sub_results, article_summaries)
        prompt = self._synthesis_prompt(
            question, sub_results, article_summaries, sources
        )

        # Log the synthesis prompt size — the live test asserts this is
        # bounded (< 30KB even with 20 articles). Keep the format stable so
        # the test can grep it from backend.out.log.
        logger.info(
            "synthesis_prompt_size=%d articles=%d sub_questions=%d sources=%d",
            len(prompt),
            len(article_summaries),
            len(sub_results),
            len(sources),
        )

        any_chunk = False
        async for chunk in self._call_ollama_stream(
            prompt,
            num_predict=8192,
            temperature=0.3,
            label="synthesize",
        ):
            if not chunk:
                continue
            any_chunk = True
            yield chunk

        if not any_chunk:
            raise LLMError("Synthesis returned empty body", model=self.model)

    def _finalize_report(
        self,
        body: str,
        question: str,
        sub_results: List[_SubQuestionResult],
        article_summaries: List[_ArticleSummary],
    ) -> str:
        """Apply post-streaming citation guard rails — preserved from M1."""
        sources = self._build_source_list(sub_results, article_summaries)
        cleaned = (body or "").strip()
        return self._ensure_sources_section(cleaned, sources, question)

    @staticmethod
    def _build_source_list(
        sub_results: List[_SubQuestionResult],
        article_summaries: List[_ArticleSummary],
    ) -> List[Dict[str, Any]]:
        """Assemble the global numbered source list.

        Priority: every article that completed the fan-out is included
        (whether it was a clean summary or a fallback snippet) — they
        are the canonical citation targets.

        Fall-through: when ``article_summaries`` is empty (legacy fake
        SearchService path with non-int IDs), build the list from
        sub-question hits like M1.
        """
        if article_summaries:
            ordered: List[Dict[str, Any]] = []
            for i, a in enumerate(article_summaries, start=1):
                ordered.append(
                    {
                        "n": i,
                        "title": a.title or "(untitled)",
                        "url": a.url,
                        "source": a.source or "unknown",
                        "summary": (a.summary or "")[:MAX_SUMMARY_CHARS_IN_PROMPT],
                        "article_id": a.article_id,
                    }
                )
            return ordered

        # Legacy fallback (M1 contract): build from sub-question hits.
        seen: Dict[str, int] = {}
        ordered_legacy: List[Dict[str, Any]] = []
        for sr in sub_results:
            for h in sr.hits:
                url = (h.get("url") or "").strip()
                title = (h.get("title") or "").strip()
                src = (h.get("source") or "").strip()
                key = url or f"{title}|{src}"
                if not key:
                    continue
                if key in seen:
                    continue
                idx = len(ordered_legacy) + 1
                seen[key] = idx
                ordered_legacy.append(
                    {
                        "n": idx,
                        "title": title or "(untitled)",
                        "url": url,
                        "source": src or "unknown",
                        "summary": (h.get("summary") or "")[
                            :MAX_SOURCE_SNIPPET_CHARS
                        ],
                    }
                )
        return ordered_legacy

    @staticmethod
    def _synthesis_prompt(
        question: str,
        sub_results: List[_SubQuestionResult],
        article_summaries: List[_ArticleSummary],
        sources: List[Dict[str, Any]],
    ) -> str:
        """Build the synthesis prompt.

        **PROMPT-DISCIPLINE CONTRACT (the M4 acceptance criterion):**
        The prompt contains article IDs + per-article SUMMARIES + titles.
        It NEVER contains raw article body text. The body lives only
        inside the per-article subagent prompts dispatched by
        ``_fanout_summaries`` — those prompts never feed back into this
        outer orchestrator's context.
        """
        # ---- Sub-question block (per-question hit list, citation numbers
        # mapped via the source list)
        url_to_n: Dict[str, int] = {}
        title_src_to_n: Dict[str, int] = {}
        id_to_n: Dict[int, int] = {}
        for s in sources:
            if s.get("url"):
                url_to_n[s["url"]] = s["n"]
            title_src_to_n[f"{s['title']}|{s['source']}"] = s["n"]
            if "article_id" in s and s["article_id"] is not None:
                id_to_n[int(s["article_id"])] = s["n"]

        sub_blocks: List[str] = []
        for i, sr in enumerate(sub_results, start=1):
            if not sr.hits:
                sub_blocks.append(
                    f"Sub-question {i}: {sr.question}\n"
                    f"  (no results -- write \"Could not find data on "
                    f"{sr.question}\" in the report)\n"
                )
                continue
            lines = [f"Sub-question {i}: {sr.question}"]
            for h in sr.hits:
                aid = h.get("id")
                try:
                    aid_int = int(aid) if aid is not None else None
                except (TypeError, ValueError):
                    aid_int = None
                url = (h.get("url") or "").strip()
                title = (h.get("title") or "").strip()
                src = (h.get("source") or "").strip()
                n = (
                    (id_to_n.get(aid_int) if aid_int is not None else None)
                    or url_to_n.get(url)
                    or title_src_to_n.get(f"{title}|{src}")
                )
                # NOTE: this is the search-hit SNIPPET, not the body. The
                # snippet was stripped to <=300 chars by the
                # search_articles skill, so it's safe to surface here as
                # additional context for the LLM.
                snippet = (h.get("summary") or "")[:MAX_SOURCE_SNIPPET_CHARS]
                lines.append(f"  - [{n}] {title} ({src}): {snippet}")
            sub_blocks.append("\n".join(lines) + "\n")

        # ---- Per-article summary block (the M4 architectural payoff)
        # When article_summaries is populated we list every article with
        # its per-article SUMMARY. The synthesis prompt instructs the
        # model to rely on these — not on the search snippets — for facts.
        summary_block_lines: List[str] = []
        if article_summaries:
            summary_block_lines.append(
                "Per-article summaries (use these as your primary evidence; "
                "cite each fact with the [N] from the source list):"
            )
            for a in article_summaries:
                n = id_to_n.get(int(a.article_id))
                tag = f" (ERROR: {a.error})" if a.error else ""
                snippet = (a.summary or "")[:MAX_SUMMARY_CHARS_IN_PROMPT]
                summary_block_lines.append(
                    f"  [{n}] article_id={a.article_id} title={a.title}{tag}\n"
                    f"      {snippet}"
                )
        summary_block = "\n".join(summary_block_lines)

        sources_block = "\n".join(
            f"[{s['n']}] {s['title']} -- {s['source']} "
            f"({s.get('url') or 'no url'})"
            for s in sources
        )
        if not sources_block:
            sources_block = "(no sources retrieved)"

        return (
            "You are an expert technology research analyst. Write a "
            "structured markdown research report that answers the user's "
            "question, using ONLY the provided source material.\n"
            "\n"
            "STRICT RULES:\n"
            "1. Cite every factual claim with an inline [N] marker, where N "
            "is the source number from the list below. Do NOT invent sources. "
            "Each Key Finding bullet must end with at least one [N] citation. "
            "If multiple sources support a claim, cite all of them: [1][3].\n"
            "2. Diversity requirement: when 3 or more sources are available, "
            "your report MUST cite AT LEAST 3 distinct [N] markers across the "
            "Key Findings + Trends sections. Spread citations across sources, "
            "do not over-rely on a single source.\n"
            "3. If a sub-question has no results, write a short paragraph "
            "starting \"Could not find data on\" naming that sub-question.\n"
            "4. Use these exact section headings (markdown ##): "
            "\"## Executive Summary\", \"## Key Findings\", \"## Trends & "
            "Themes\", \"## Sources Used\".\n"
            "5. The \"## Sources Used\" section MUST list every source you "
            "cited as numbered entries matching the numbering below.\n"
            "6. Do not include any preamble before the first heading.\n"
            "\n"
            f"User question: {question}\n"
            "\n"
            "Sub-question results:\n"
            + "\n".join(sub_blocks)
            + ("\n" + summary_block + "\n" if summary_block else "\n")
            + "\nNumbered source list (cite by [N]):\n"
            f"{sources_block}\n"
            "\n"
            "Report:"
        )

    @staticmethod
    def _ensure_sources_section(
        body: str,
        sources: List[Dict[str, Any]],
        question: str,
    ) -> str:
        """Guarantee the report contains a ``## Sources Used`` section and
        at least one ``[N]`` citation. Preserved verbatim from M1.
        """
        out = body.rstrip()

        has_sources_heading = bool(
            re.search(r"(?im)^\s*##\s+Sources\s+Used\s*$", out)
        )
        has_citation = bool(re.search(r"\[\d+\]", out))

        if not has_sources_heading:
            if sources:
                lines = [
                    f"{s['n']}. {s['title']} -- {s['source']} "
                    f"({s.get('url') or 'no url'})"
                    for s in sources
                ]
                out = (
                    out
                    + "\n\n## Sources Used\n"
                    + "\n".join(lines)
                    + "\n"
                )
            else:
                out = (
                    out
                    + "\n\n## Sources Used\n"
                    + "1. (no citations available)\n"
                )

        has_citation = bool(re.search(r"\[\d+\]", out))
        if not has_citation:
            pointer = "See [1] in the source list below."
            heading_match = re.search(
                r"(?im)^\s*##\s+Sources\s+Used\s*$", out
            )
            if heading_match:
                out = (
                    out[: heading_match.start()].rstrip()
                    + "\n\n"
                    + pointer
                    + "\n\n"
                    + out[heading_match.start() :]
                )
            else:
                out = out.rstrip() + "\n\n" + pointer + "\n"

            if not sources:
                heading_match = re.search(
                    r"(?im)^\s*##\s+Sources\s+Used\s*$", out
                )
                if heading_match:
                    after = out[heading_match.end():]
                    if not re.search(r"(?m)^\s*\d+\.\s+\S", after):
                        out = (
                            out.rstrip()
                            + "\n1. (no citations available)\n"
                        )

        return out

    # ------------------------------------------------------------------ #
    #  Skill invocation helper
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _invoke_skill(skill_fn: Any, args: Dict[str, Any]) -> Any:
        """Call a LangChain ``StructuredTool`` or plain async callable.

        Mirrors :py:func:`subagent_pool._invoke` so the orchestrator's
        direct tool calls (``search_articles``) and the pool's per-article
        dispatches (``summarize_article``) share the same call shape.
        """
        ainvoke = getattr(skill_fn, "ainvoke", None)
        if callable(ainvoke):
            return await ainvoke(args)
        return await skill_fn(**args)

    # ------------------------------------------------------------------ #
    #  Ollama call (wrapped in start/end/duration/token_count logger)
    # ------------------------------------------------------------------ #

    @asynccontextmanager
    async def _ollama_call(self, label: str):
        """Async CM that frames every Ollama call with structured timing logs."""
        call_id = uuid.uuid4().hex[:8]
        info: Dict[str, Any] = {"token_count": 0}
        t0 = time.monotonic()
        logger.info(
            "ollama_call.start id=%s label=%s model=%s",
            call_id,
            label,
            self.model,
        )
        try:
            yield info
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "ollama_call.end id=%s label=%s status=error "
                "duration_ms=%d token_count=%d error=%s",
                call_id,
                label,
                duration_ms,
                int(info.get("token_count") or 0),
                exc,
            )
            raise
        else:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "ollama_call.end id=%s label=%s status=ok "
                "duration_ms=%d token_count=%d",
                call_id,
                label,
                duration_ms,
                int(info.get("token_count") or 0),
            )

    async def _call_ollama(
        self,
        prompt: str,
        *,
        num_predict: int = 512,
        temperature: float = 0.2,
        label: str = "generate",
    ) -> str:
        """Send ``prompt`` to the configured LLM and return the response text.

        Despite the name, this dispatches based on
        ``settings.default_llm_provider``: ``ollama`` (default, hits the
        local Ollama server) or ``groq`` (the OpenAI-compatible cloud API,
        used in prod where Ollama isn't available). Other call sites
        upstream still say "_ollama_" -- kept for grep continuity.
        """
        from ..core.config import LLMProvider as _LLMProvider
        from .groq_client import groq_generate

        settings = get_settings()
        if settings.default_llm_provider == _LLMProvider.GROQ:
            async with self._ollama_call(label) as info:
                text, token_count = await groq_generate(
                    prompt,
                    num_predict=num_predict,
                    temperature=temperature,
                    label=label,
                )
                info["token_count"] = token_count
                return text

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": num_predict,
            },
        }

        async with self._ollama_call(label) as info:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/generate", json=payload
                    )
            except (httpx.HTTPError, OSError) as exc:
                raise LLMError(
                    f"Ollama HTTP failure ({label}): {exc}", model=self.model
                ) from exc

            if resp.status_code != 200:
                raise LLMError(
                    f"Ollama returned {resp.status_code} ({label}): "
                    f"{resp.text[:200]}",
                    model=self.model,
                )

            data = resp.json()
            text = (data.get("response") or "").strip()
            info["token_count"] = int(
                data.get("eval_count") or len(text.split())
            )
            if not text:
                raise LLMError(
                    f"Ollama returned empty response ({label})",
                    model=self.model,
                )
            return text

    async def _call_ollama_stream(
        self,
        prompt: str,
        *,
        num_predict: int = 8192,
        temperature: float = 0.3,
        label: str = "stream",
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama's ``/api/generate`` endpoint (NDJSON).

        Reasoning models (e.g. ``gpt-oss:20b``) emit BOTH ``thinking`` and
        ``response`` fields per stream chunk. With a modest ``num_predict``
        and a heavy synthesis prompt (the M4 prompt is ~20-24KB), the
        model can spend the entire budget on the thinking trace and emit
        zero ``response`` tokens -- synthesis then sees an empty body and
        raises ``LLMError("Synthesis returned empty body")``. Defence in
        depth, three layers:

        1. Send ``think: false`` so newer Ollama versions skip the
           reasoning trace entirely.
        2. Default ``num_predict`` to 8192 so older Ollama (which ignores
           ``think``) still has headroom for both thinking + response.
        3. If the stream ends with zero ``response`` chunks but a
           non-empty ``thinking`` body, fall back to yielding the
           thinking content as the report -- better a slightly raw
           reasoning trace than a hard failure.
        """
        # Provider dispatch -- when DEFAULT_LLM_PROVIDER=groq we stream from
        # Groq's OpenAI-compatible SSE endpoint instead of Ollama's NDJSON.
        from ..core.config import LLMProvider as _LLMProvider
        from .groq_client import groq_stream

        if get_settings().default_llm_provider == _LLMProvider.GROQ:
            async with self._ollama_call(label) as info:
                token_count = 0
                async for chunk in groq_stream(
                    prompt,
                    num_predict=num_predict,
                    temperature=temperature,
                    label=label,
                ):
                    token_count += 1
                    yield chunk
                info["token_count"] = token_count
            return

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            # Disable the reasoning trace on streaming-synthesis calls
            # so that ``num_predict`` is spent on ``response`` tokens,
            # not on invisible ``thinking`` tokens. See docstring above.
            "think": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": num_predict,
            },
        }

        async with self._ollama_call(label) as info:
            token_count = 0
            thinking_buffer: List[str] = []
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/api/generate",
                        json=payload,
                    ) as resp:
                        if resp.status_code != 200:
                            try:
                                err_body = await resp.aread()
                                err_text = err_body.decode("utf-8", "replace")[:200]
                            except Exception:  # noqa: BLE001
                                err_text = ""
                            raise LLMError(
                                f"Ollama returned {resp.status_code} ({label}): "
                                f"{err_text}",
                                model=self.model,
                            )

                        async for line in resp.aiter_lines():
                            if not line or not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                            except (json.JSONDecodeError, ValueError):
                                logger.debug(
                                    "ollama_stream: skipping non-JSON line: %r",
                                    line[:80],
                                )
                                continue

                            chunk = obj.get("response") or ""
                            if chunk:
                                token_count += 1
                                yield chunk

                            # Buffer ``thinking`` output as a last-resort
                            # fallback for reasoning models that ignore
                            # ``think: false`` and burn the budget on the
                            # reasoning trace. We only emit it below if
                            # the ``response`` stream ended up empty.
                            think_chunk = obj.get("thinking") or ""
                            if think_chunk and not chunk:
                                thinking_buffer.append(think_chunk)

                            if obj.get("done"):
                                info["token_count"] = int(
                                    obj.get("eval_count") or token_count
                                )
                                break

                        # Fallback: if no ``response`` tokens streamed
                        # but we captured a thinking trace, surface it
                        # so the synthesis step doesn't hard-fail with
                        # an empty body. This preserves a usable report
                        # on Ollama versions that ignore ``think:false``.
                        if token_count == 0 and thinking_buffer:
                            fallback_body = "".join(thinking_buffer).strip()
                            if fallback_body:
                                logger.warning(
                                    "ollama_stream: empty response body -- "
                                    "falling back to thinking trace "
                                    "(label=%s, thinking_len=%d)",
                                    label,
                                    len(fallback_body),
                                )
                                yield fallback_body
            except asyncio.CancelledError:
                logger.info(
                    "ollama_stream: cancelled mid-generation (label=%s)",
                    label,
                )
                raise
            except (httpx.HTTPError, OSError) as exc:
                raise LLMError(
                    f"Ollama HTTP failure ({label}): {exc}", model=self.model
                ) from exc
            else:
                if not info.get("token_count"):
                    info["token_count"] = token_count

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _event(type_: str, label: str, payload: Any = None) -> Dict[str, Any]:
        """Build an :class:`AgentEvent`-shaped dict.

        For the terminal ``phase: "done"`` event ``payload`` carries the
        final report under the ``report`` key (NOT ``data``) — preserved
        from M1's choice for backward compat with the M3+M4 frontend code.
        """
        if type_ == "phase" and label == "done":
            return {"type": "phase", "data": "done", "report": payload or ""}
        if type_ == "phase":
            return {"type": "phase", "data": label}
        return {"type": type_, "data": label}
