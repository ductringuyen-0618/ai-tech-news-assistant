# Trending AI Agent Skills — a Learning tab — shipped

Proposal: [`docs/missions/coo/proposals/003-add-a-trending-new-ai-agent-skills-technique-set.md`](../proposals/003-add-a-trending-new-ai-agent-skills-technique-set.md)
Branch: `coo/add-a-trending-new-ai-agent-skills-technique-set`
PR: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/8

## What shipped

**Backend**
- `backend/src/core/config.py` — `learning_rss_sources`: a small curated
  feed list (GitHub Blog's AI & ML category, two `hnrss.org`
  keyword-search feeds for "AI agent" and "Claude Code"), kept in config
  rather than hardcoded so it's tunable without a redeploy.
- `backend/src/services/learning_filter.py` (new) — pure, dependency-free
  `is_learning_content(title, content)` keyword filter distinguishing
  agent-tooling content from general AI/tech news.
- `backend/src/services/learning_ingestion.py` (new) — fetches the
  curated sources through the existing `IngestionService` (same
  dedupe-by-URL and raw-SQL `categories`-column sync every other feed
  already uses), tags matches with a reserved `"Agent Skills"` category,
  then demotes any row that fails the keyword filter (strips the tag
  rather than deleting the row) so a broad source can't flood the tab
  with off-topic items. Deliberately does NOT duplicate
  summarize/embed/entity-extract — those already-scheduled daily-ingestion
  phases process any row missing them regardless of category, so new
  Learning rows are picked up for free.
- `backend/src/api/routes/learning.py` (new) — `GET /api/learning/`,
  same offset-pagination shape as `/api/news/`, filtered to the reserved
  category via `ArticleRepository.list_articles(categories=...)`.
- `backend/src/api/routes/admin.py` — `POST /api/admin/ingest-learning`
  on-demand trigger, mirroring `/admin/ingest`'s auth/response shape.

**Frontend**
- `frontend/src/components/LearningView.tsx` (new) — the tab itself:
  loading (skeleton cards) / empty / error states, cards mirroring
  `NewsCard`'s visual language (mono source eyebrow, Fraunces-style
  title, category chip, "read at &lt;host&gt; →" CTA), without the
  save/read/reaction mechanics (out of scope for v1 per the proposal).
- `frontend/src/App.tsx` / `Sidebar.tsx` — new `Learning` tab between
  Research and Digest; `config/api.ts` — `learning: '/api/learning/'`.
- `frontend/e2e/learning.spec.ts` (new) — mocked-`/api/learning/`
  Playwright spec: populated state, a differentiating-tag-beyond-the-feed
  -category case, empty state, error state. **Run live** against a
  real dev server + the pre-installed headless Chromium (this
  environment supports it, unlike the prior 002 report) — 4/4 pass.

## Deliberate scope reduction vs. the proposal

The proposal's "Proposed solution" promised entity tags that "link into
the existing knowledge graph" and "clicking a tag jumps into the
existing knowledge graph view filtered to that entity." Checked against
the actual current frontend rather than assumed: the standalone
knowledge-graph tab was already cut before this was built (see
`App.tsx`'s `VALID_TABS` comment — entity filtering today lives in
`SearchBar`'s dropdown against the main feed, not a separate graph
view), and `/api/learning/`'s article payload doesn't carry per-article
entity data at all. Building this as originally described would have
required a new API surface beyond this proposal's stated scope, so v1
ships with informational-only category chips instead — disclosed in
code comments and in the PR description, not silently dropped.

## Independent review (each blind to the other's reasoning, and to this report)

**Scrutiny validator** — saw only the proposal and `git diff main...HEAD`.
Ran every CI command directly: `ruff check .`, `mypy . --ignore-missing-imports`
(one pre-existing-pattern false positive, matches an identical case
already on `main` in `news.py`), `pytest test_ci.py -v` (4/4),
`pytest tests/` (359 passed / 18 failed / 3 skipped — diffed against the
same command on `main` and confirmed the 18 failures are identical,
pre-existing, and untouched by this diff), `npm run lint`, `prettier
--check`, `tsc --noEmit`, `npm run build` — all pass. Specifically
audited the raw-SQL keyword-filter demotion query for injection risk
(safe: bound parameter, not string-concatenated) and grepped every
symbol removed by the bundled ruff-cleanup commits to confirm nothing
load-bearing was deleted. One latent (not current) fragility flagged:
the demotion pass sets `categories = NULL` wholesale, which would
clobber other tags if an article ever gains multiple categories in the
future — no code path does that today.

**Product reviewer** — ran the real backend + frontend, plus a
throwaway mocked-API Playwright spec (deleted after use) to capture
screenshots of every state. **Pass.** Visual consistency, copy quality,
and all three loading/empty/error states confirmed genuinely
product-grade via actual screenshots, not code-reading. Found two real
nits, both fixed in the last commit on the branch before opening the
PR: a redundant "Agent Skills" chip repeated on every card of a feed
that's already entirely that category (now filtered out client-side,
only differentiating tags render), and a literal `--` in the empty-state
copy instead of an actual em dash. Independently confirmed the
KG-linking gap above is a legitimate, disclosed constraint rather than
an oversight.

## Incidental: three pre-existing backend CI blockers found and fixed

This is the first COO-built feature to touch `backend/`. Doing so
surfaced three problems entirely unrelated to the feature itself, each
blocking this PR's (and every future backend PR's) CI:

1. `pip install -r requirements.txt` failing with `resolution-too-deep`
   from stale `httpx`/`fastapi`/pre-1.0 `langchain` version floors. PR #4
   (open, from the repo owner) had already diagnosed and fixed this exact
   conflict, so the same `requirements.txt` change was ported rather than
   waiting for it to merge.
2. `backend/test_ci.py` — the file CI's "Backend Quality & Tests" step
   runs (`pytest test_ci.py`) — didn't exist at all, so that step always
   fell through to a fallback importing modules (`production_main`, etc.)
   that don't exist in this repo's current `src/` layout, and always
   failed too. Added a small, dependency-light smoke suite.
3. CI installs `ruff` unpinned (`pip install ruff`); ruff's own default
   rule selection has grown across releases (pyupgrade/`UP` and
   ruff-specific/`RUF` rules are on by default on current ruff versions),
   so the identical backend/ tree went from "0 errors" (pinned older
   ruff) to 1723–1747 errors (unpinned latest, confirmed directly in this
   session) purely from modernization-suggestion rule categories this
   project never opted into — not real bugs. Root-caused rather than
   chased: pinned `[tool.ruff.lint] select = ["E4","E7","E9","F"]` in
   `pyproject.toml`, restoring the ~56-error baseline (already fixed
   mechanically) that CI actually enforced when it was last passing.

Shipped standalone as PR #7 (`coo/fix-backend-ruff-lint-baseline`) since
these block every backend PR, this one included — CI green, mergeable,
not yet merged (never merges its own PRs, per the routine's rules).
Ported into this feature branch too so its own CI could go green without
waiting on #7 to land first.

## CI result

Both PRs' "Build & Test" job: **success**. Both `mergeable_state: clean`.
No `Claude Approvals` check configured on this repo. Neither PR merged
by this routine (never merges its own work) — left for the repo owner.

- PR #7: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/7
  (CI run: https://github.com/ductringuyen-0618/ai-tech-news-assistant/actions/runs/34504425658)
- PR #8: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/8
  (CI run: https://github.com/ductringuyen-0618/ai-tech-news-assistant/actions/runs/34504484924)
