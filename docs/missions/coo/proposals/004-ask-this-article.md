---
status: proposed
attempts: 0
branch: null
---
# Ask This Article

## What you get
A "Ask about this article" box right inside the article reader. A visitor
types a question about the story they're already reading -- "what does this
mean for X", "who else is affected", "explain the jargon in paragraph 2" --
and gets a grounded answer in a few seconds, without leaving the article or
navigating to the separate Research tab.

## Why start this now
Every article dead-ends today: a reader finishes the AI summary and the
excerpt, then either leaves or clicks out to the publisher. A quick,
in-context question box turns that dead end into another few minutes in the
app and a reason to come back to other articles the same way. This was
flagged directly against a named competitor (Particle) as a gap in the
2026-09 review round, the underlying LLM call-and-fallback plumbing already
exists (`SummarizationService`), and it needs no new provider, secret, or
paid API to ship -- it's the cheapest "the product talks back" moment left
on the backlog.

## Problem / opportunity
`ArticleReader.tsx` already gives a reader an AI summary, a short excerpt,
"Related coverage" (via
`GET /knowledge-graph/related-articles/{article_id}`), and a link out to the
publisher -- but nothing lets a reader interact with the content itself. The
only conversational surface in the app is the full "Ask AI" / Research tab
(`ResearchMode.tsx`, backed by `POST /api/research`), which is a separate
destination, runs the full multi-subagent `AgenticResearchService`, and is
gated to exactly one run in flight process-wide
(`backend/src/api/routes/research.py`'s `_try_acquire_in_flight`) -- it is
built for open-ended deep research, not a fast one-off question about the
article on screen, and reusing it here would let one visitor's article
question block every other visitor's real research run.

review-09 (competitive) named per-article inline Q&A ("ask about this
story") as a gap versus Particle; it's tracked as deferred item #4 in
`docs/issues/2026-09-review-followups.md`, explicitly called out as
"distinct from ... citation-rendering work, not a new per-article entry
point into Research" -- i.e. its own, smaller thing.

## Proposed solution
Backend (FastAPI), reusing the existing LLM-provider abstraction rather than
building new plumbing:
- Add `POST /api/news/{id}/ask` (`backend/src/api/routes/news.py`) with body
  `{"question": str}`. Loads the article via the existing article repository,
  builds a prompt from its title + AI summary + excerpt + source, and answers
  using `SummarizationService`'s existing `_call_llm` (same Groq-first,
  Ollama-fallback path `summarize_content` already uses) -- no new provider
  code, no SSE, no agent dispatch, one plain request/response call.
- Explicitly answers only from the article's own content; if the question
  can't be answered from it, the response says so plainly (e.g. "That's not
  covered in this article") instead of guessing or silently pulling in
  outside knowledge -- keeps it honest about what it does and doesn't know,
  and keeps it distinct from the full Research agent.
- Short, in-memory response cache keyed on `(article_id, normalized
  question)` for the process lifetime, matching the "cache LLM responses"
  convention in CLAUDE.md and cheaply handling the "two visitors ask the same
  obvious question" case.
- Independent of the Research route's in-flight lock -- a burst of article
  questions must never 429 or block the Research tab, and vice versa.

Frontend (Vite/React):
- A collapsed "Ask about this article" affordance in `ArticleReader.tsx`
  (below the summary, above "Related coverage"), expanding to a single text
  input + submit button + answer area on click -- no new tab, no route
  change.
- Loading state while the request is in flight, a plain error state on
  failure (reuse the existing toast pattern), and the answer rendered as
  plain text (no markdown/citation rendering needed -- this is intentionally
  simpler than the Research report view).
- Each article keeps its own small, session-only Q&A history (question +
  answer pairs) in component state so a reader can ask a follow-up without
  losing the first answer; no persistence required for v1.

## Effort estimate
**S/M.** One new backend endpoint reusing an existing service's existing LLM
call path (no new dependency, no new provider integration), one new
collapsed section in an existing component. No schema/migration, no new
Playwright fixture infrastructure beyond what `ArticleReader`'s existing
specs already set up.

## Validation contract
- Functional assertions:
  - `POST /api/news/{id}/ask` with a valid article id and a question returns
    200 with `{"answer": str}`; with an unknown id returns 404, not a 500.
  - `ArticleReader.tsx` renders an "Ask about this article" control
    (`data-testid="article-ask-toggle"`) that expands to an input
    (`data-testid="article-ask-input"`) and shows the returned answer
    (`data-testid="article-ask-answer"`) after submit.
  - Asking a second question on the same article appends to, rather than
    replaces, the visible Q&A history in that session.
- Behavioral assertions:
  - The endpoint answers only from the article's own stored content
    (title/summary/excerpt) -- verified in a backend test via a mocked LLM
    call asserting the prompt sent to `_call_llm` includes the article's
    text and does not fetch or reference any other article.
  - A burst of concurrent `/api/news/{id}/ask` calls never touches or blocks
    `/api/research`'s in-flight lock (verified by a backend test exercising
    both routes concurrently and asserting neither 429s the other).
- Negative assertions (should NOT happen):
  - No SSE connection, no multi-subagent dispatch, and no dependency on
    `AgenticResearchService` for this endpoint.
  - No new LLM provider, API key, or paid service is introduced -- only the
    existing Groq/Ollama path via `SummarizationService`.
  - Existing `ArticleReader`-related e2e/unit coverage (related coverage,
    read-marking, summary rendering) must not regress.
- Test commands the build will need to pass (exact CI commands, from
  `.github/workflows/ci.yml`):
  - Backend: `ruff check .`, `mypy . --ignore-missing-imports`,
    `python -m pytest test_ci.py -v --tb=short` (run from `backend/`), plus
    `pytest tests/ -v -k "news or ask"` for the new endpoint's own tests.
  - Frontend (run from `frontend/`): `npm run lint`,
    `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`,
    `npx tsc --noEmit`, `npm run build`.

## Risks / open questions
- Answer quality depends entirely on the article's stored summary/excerpt
  being substantive; a very thin excerpt may only support shallow answers --
  acceptable for v1, and the "not covered in this article" fallback keeps
  that honest rather than papering over it with a hallucinated answer.
- Rate/abuse: since this is a new unauthenticated LLM-backed endpoint,
  the worker should apply the same lightweight per-`client_id` guard pattern
  already used elsewhere (see the settings/identity work referenced in
  `docs/issues/2026-09-review-followups.md` item 4) if one already exists to
  reuse; if not, a minimal per-IP/per-client rate limit is in scope, but
  building a new generic rate-limiting framework is not.
- Out of scope for this proposal: markdown/citation rendering of answers,
  cross-article Q&A, and persisting Q&A history across sessions.
