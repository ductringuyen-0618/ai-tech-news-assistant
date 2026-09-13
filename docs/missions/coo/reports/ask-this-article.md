# Ask This Article — shipped

Proposal: `docs/missions/coo/proposals/004-ask-this-article.md`
PR: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/10
CI run: https://github.com/ductringuyen-0618/ai-tech-news-assistant/actions/runs/34769527409

## What shipped

A per-article "Ask about this article" Q&A box inside `ArticleReader.tsx`.

- **Backend**: `POST /api/news/{article_id}/ask` (`backend/src/api/routes/news.py`)
  — body `{"question": str}`, response `{"answer": str}`. Looks up the article,
  builds a prompt from its own title/summary/source, and answers via
  `SummarizationService._call_llm` (same Groq-first/Ollama-fallback path
  `summarize_content` already uses — no new provider, no SSE, no agent
  dispatch). Answers strictly from the article's own content; the prompt
  instructs the model to say plainly when something isn't covered rather
  than guess. In-memory response cache keyed on `(article_id,
  normalized_question)`, and a self-contained per-client rate limit (10
  req/60s, keyed on `X-Client-Id`, falling back to client host) that raises
  the existing `RateLimitError` -> 429. Fully independent of
  `/api/research`'s in-flight lock (no import from `research.py`).
- **Frontend**: collapsed "Ask about this article" section in
  `ArticleReader.tsx` between the AI summary and "Related coverage", with a
  toggle (`article-ask-toggle`), input (`article-ask-input`), and rendered
  answer (`article-ask-answer`). Loading state disables the form (no
  double-submit), inline scoped error on failure, and a session-only Q&A
  history that appends per question rather than replacing.
- **Tests**: `backend/tests/integration/test_ask_article.py` — 200 success
  (prompt scoped to only this article), 404 for unknown id, cache-hit
  behavior, rate-limit behavior, and a real-thread concurrency test proving
  `/api/news/{id}/ask` and `/api/research` never block or 429 each other.

## Commits

- `fae1240` feat(backend): add POST /api/news/{id}/ask endpoint
- `bf8d2dd` feat(frontend): add ask-about-this-article box to ArticleReader

## Validator findings (scrutiny pass)

**PASS.** All CI-equivalent commands run clean: `ruff check .`, `mypy .
--ignore-missing-imports` (no new build-blocking errors — mypy doesn't gate
this repo's CI), `pytest test_ci.py -v --tb=short`, `pytest tests/ -v -k
"news or ask"` (4 unrelated pre-existing failures confirmed identical on
`main` via a clean worktree diff), `pytest
tests/integration/test_ask_article.py -v` (5/5), `npm run lint`, `npx
prettier --check`, `npx tsc --noEmit`, `npm run build`. Every
functional/behavioral/negative assertion in the proposal's Validation
contract verified directly against the diff: no `research.py` import, no
new dependency in `requirements.txt`/`package.json`, correct 404 vs 500 on
unknown article id, real-thread (not sequential) concurrency proof, exact
frontend test ids, Q&A history appends rather than replaces.

No must-fix defects. Nice-to-haves for a future pass: reorder the cache
lookup ahead of `get_by_id`'s view-count side effect so cache hits don't
still write to the DB; the in-memory cache/rate-limit dicts are unbounded
for the process lifetime (accepted for v1 per the proposal's own scoping);
an all-whitespace question can slip past `Field(min_length=1)`.

## Product reviewer notes

**PASS**, verified with a full live run (real backend + real Vite dev
server + real Chromium via Playwright, only the LLM call patched)
exercising expand -> ask -> loading -> answer -> follow-up -> simulated
network failure -> keyboard-only navigation -> mobile viewport. Loading/
disabled states, the hand-rolled dialog's focus trap correctly capturing
the new input/toggle, and the append-only Q&A history were all verified
live rather than assumed from source reading alone.

Should-fix items filed for a later pass (none blocked this PR): the error
message is identical for every failure mode (404/429/422/network) instead
of differentiated; the ask form's `sm:flex-row` class has no effect because
this repo's Tailwind CSS is a static pre-generated bundle with zero `sm:`
rules anywhere in it — a pre-existing, repo-wide condition this PR
inherited rather than introduced (also affects several pre-existing
classes elsewhere in `ArticleReader.tsx`); the toggle's label uses a
slightly different class idiom than its sibling section headers; a
redundant background class on the Q&A history card; missing
`aria-controls`/`aria-live` for screen readers and no client-side
`maxLength` mirroring the backend's 1000-char cap.

## Outcome

PR #10 opened, CI ("🏗️ Build & Test", "🚀 Deploy Preview") green,
`mergeable_state: clean`, no Claude Approvals check configured on this
repo. Left open for the repo owner to merge — this routine never merges
its own PRs.
