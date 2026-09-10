# TechPulse COO -- State

Shipped: 2/3

## Log
- 2026-09-09: No proposals existed yet, so proposed two new engagement
  features (both docs-only, no app code): `001-research-report-permalinks.md`
  (shareable `/research/:id` URLs for saved research reports) and
  `002-personalized-feed-reactions.md` (client-side "more/less like this"
  reactions that lightly re-rank the feed). Both pull directly from
  reviewer-recommended, previously-deferred ideas in
  `docs/issues/2026-09-review-followups.md`. Awaiting human approval.
- 2026-09-09: Shipped `002-personalized-feed-reactions` (attempt 1,
  branch `coo/personalized-feed-reactions`). Three independent review
  rounds (scrutiny + professional-feel, each blind to prior reasoning)
  found and fixed a jump-scare reorder bug, three professional-feel
  must-fix items, a pagination-windowing edge case, and a one-frame
  remount flash. `npm run typecheck`/`lint`/`build` all clean throughout.
  See `docs/missions/coo/reports/personalized-feed-reactions.md` for the
  full trace. PR #5 opened, then merged to main (`b0fef6b`) after CI
  went green -- along the way, another session fixed a repo-wide
  prettier baseline and merged it in, which exposed an unrelated,
  pre-existing CI workflow bug (artifact-check looked for `dist/`, but
  this repo's Vite build outputs to `build/`); diagnosed it, proposed a
  one-line patch in a PR comment rather than editing the workflow
  unilaterally, and it landed the same way.
- 2026-09-10: Started building `003-add-a-trending-new-ai-agent-skills-technique-set`
  (a "Learning" tab for trending AI agent tooling content), previously
  approved. This is the first COO-built feature to touch `backend/`, which
  surfaced two pre-existing backend CI blockers unrelated to the feature
  itself: (1) `pip install -r requirements.txt` failing with
  `resolution-too-deep` from stale `httpx`/`fastapi`/pre-1.0 `langchain`
  floors -- PR #4 (open, from the repo owner) already diagnosed and fixed
  this exact conflict, so the same `requirements.txt` change was ported
  rather than waiting on it to merge; (2) `backend/test_ci.py`, the file
  CI's "Backend Quality & Tests" step runs, didn't exist at all, so that
  step always fell through to a fallback importing modules
  (`production_main`, etc.) that don't exist in this repo's current `src/`
  layout. Also found mid-build that CI installs `ruff` unpinned, so
  `ruff check .` silently drifted from a real (if debt-laden) ~1500-error
  baseline (already flagged in PR #4) to 1700+ against modernization-only
  rule categories (`UP`/`RUF`) this project never opted into, purely from
  newer ruff versions expanding their own defaults -- fixed by pinning
  `[tool.ruff.lint] select` in `pyproject.toml` rather than chasing an
  ever-growing backlog. These three are all shipped standalone in PR #7
  (`coo/fix-backend-ruff-lint-baseline`, still watching CI) since they
  block any backend-touching PR's CI, this one included.
  `003-add-a-trending-new-ai-agent-skills-technique-set` itself is PR #8
  (`coo/add-a-trending-new-ai-agent-skills-technique-set`), carrying the
  same three fixes plus the actual Learning tab. Both an independent
  scrutiny-validator pass and a product-quality reviewer pass (each blind
  to the other's/worker's reasoning) came back clean, with one disclosed
  scope reduction: no per-article entity-tag-to-knowledge-graph linking,
  since the standalone knowledge-graph view was already cut from the
  frontend before this was built and `/api/learning/` doesn't carry
  per-article entity data. Status stays `in_progress` in the proposal
  pending both PRs' CI going green.
- 2026-09-10: Both PRs' CI went green (`Build & Test`: success; both
  `mergeable_state: clean`; no `Claude Approvals` check configured on this
  repo). Shipped `003-add-a-trending-new-ai-agent-skills-technique-set`
  (attempt 1) -- see
  `docs/missions/coo/reports/add-a-trending-new-ai-agent-skills-technique-set.md`
  for the full trace, including the three incidental backend-CI fixes
  (PR #7) this build surfaced. PR #8:
  https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/8 and
  PR #7: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/7
  both left open (green, mergeable) for the repo owner to merge -- this
  routine never merges its own PRs.
- 2026-09-10: PR #8 merged by the repo owner. Since #8's branch already
  carried PR #7's ruff-lint-baseline fix plus the httpx/fastapi/langchain
  and test_ci.py fixes, `main` was now a strict superset of #7's branch
  (confirmed via `git diff origin/main origin/coo/fix-backend-ruff-lint-baseline`
  -- zero net-new content, only things `main` had that #7 didn't). Closed
  #7 as redundant with an explanatory comment rather than resolving the
  now-stale merge conflict.
