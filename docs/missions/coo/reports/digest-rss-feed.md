# Shipped: Daily Digest RSS Feed

Proposal: `docs/missions/coo/proposals/006-digest-rss-feed.md`
PR: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/13
CI run: https://github.com/ductringuyen-0618/ai-tech-news-assistant/actions/runs/36333901693

## What shipped

- New `GET /api/digest/rss` endpoint in `backend/src/api/routes/digest.py`:
  emits a standards-compliant RSS 2.0 feed of the same top stories
  `GET /api/digest/` already builds. Built with stdlib only
  (`xml.sax.saxutils.escape` for text-node escaping, `email.utils
  .format_datetime` for RFC 822 `<pubDate>`) -- no new dependency.
- Extracted `_fetch_top_story_rows()` so `/` and `/rss` share the exact same
  "top N most-recent, non-archived articles" query instead of duplicating
  the SQL, so the two endpoints can't drift on which articles are "today's
  top stories".
- New `digestRss: '/api/digest/rss'` constant in
  `frontend/src/config/api.ts`.
- Small RSS subscribe link added to `DigestView.tsx`'s masthead header
  (next to the existing title block), rendered only once the digest has
  actually loaded -- `DigestView` itself is only mounted once `App.tsx`'s
  `digest` state is truthy, so the link can't appear during the
  loading-skeleton state.
- New/extended test coverage in `backend/tests/unit/test_digest_route.py`
  (5 new tests under `TestDigestRssFeed`): valid RSS XML with one `<item>`
  per story and a guid stable across repeated requests, XML escaping of
  `&`/`<`/`>` in titles and descriptions, an empty-DB request returning 200
  with a valid empty `<channel>` (not a 500), no custom headers required
  (feed readers won't send `X-Client-Id`), and the existing `/api/digest/`
  JSON response shape staying unchanged.

## Commits

- `feat(digest): add RSS feed endpoint and subscribe link` (45d50aa)

## Validator findings

An independent scrutiny-validator pass (blind to the worker's reasoning,
given only the proposal and `git diff main...HEAD`) re-ran every
CI-equivalent command from scratch:

- Backend: `ruff check .` clean; `mypy . --ignore-missing-imports` --
  confirmed (via a diff against a fresh `main` worktree run through the
  identical invocation) that the pre-existing 285-error baseline is
  unchanged, no new errors introduced; `pytest test_ci.py -v` 4/4 passed;
  the new `tests/unit/test_digest_route.py` suite 8/8 passed.
- Frontend: `npm run lint` 0 errors (31 pre-existing warnings, unrelated
  files); `npx prettier --check` clean; `npx tsc --noEmit` clean;
  `npm run build` succeeded.
- Manually re-verified every Functional/Behavioral/Negative assertion in
  the proposal's Validation contract by reading the code (XML validity,
  escaping, RFC 822 `pubDate` correctness, stable guid, empty-DB handling,
  no new pip/npm dependency, unchanged `/api/digest/` JSON shape,
  `frontend/e2e/digest.spec.ts`'s existing assertions untouched by the
  diff).

No blocking issues found. One non-binding observation: the `<link>`
fallback for an article with no `url` points at the feed's own channel
link (backend root) rather than a per-article "detail-view URL", since the
frontend has no such per-article route to fall back to -- this was flagged
as an open question in the proposal's Risks section, not part of the
Validation contract, so it isn't a defect.

## Product reviewer notes

An independent product-quality pass (also blind to the worker's reasoning)
judged the RSS link purely on user-facing quality:

- Visual consistency: the link reuses the file's existing idioms exactly
  (`font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft`,
  `hover:text-foreground`, icon sized to match sibling icons) and the new
  `flex items-start justify-between` header wrapper mirrors patterns
  already used elsewhere in this file and in `LearningView.tsx`/
  `NewsCard.tsx`.
- Copy ("RSS" + `title="Subscribe via RSS"`) matches the file's terse,
  mono-caps voice.
- Loading/empty states verified correct via `App.tsx`'s gating of
  `DigestView` on `digest` being truthy; the `/rss` endpoint's empty-DB
  case returns a valid, non-broken feed.
- Responsive and accessibility basics checked against existing codebase
  conventions (icon `aria-hidden`, `shrink-0` link, no fixed-width
  overflow risk).
- Confirmed the feed carries real digest data via the shared query helper,
  not stubbed content.

Verdict: **PASS**, no must-fix issues. One optional, non-blocking
suggestion: add a fuller `aria-label` on the RSS link (e.g. "Subscribe to
daily digest via RSS") for screen readers beyond the current `title`
tooltip -- left as a natural follow-up, not applied in this pass to keep
the change minimal.

## Outcome

PR #13 CI went green in one run (`Build & Test`: success, `Deploy Preview`:
success, `Performance Monitoring`: skipped as expected for a non-main
push) and `mergeable_state: clean`. Left open for the repo owner to merge
-- this routine never merges its own PRs.
