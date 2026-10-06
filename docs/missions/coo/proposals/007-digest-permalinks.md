---
status: expired
attempts: 0
branch: null
---
# Shareable Digest Editions

## What you get
Every day's digest gets its own shareable link, like `/digest/2026-09-29`. Anyone who opens that link sees exactly that day's top stories, not whatever happens to be newest right now — so a link posted on social media or sent to a friend still shows the right edition a week later. A "Copy link to this edition" button sits right on the Digest tab.

## Why start this now
The digest is the one piece of content in the app shaped like something people already share daily (a Techmeme-style morning roundup), but today it has no stable URL — it's always "whatever is newest," so nothing about it is linkable or archivable. This was explicitly flagged as a small, high-value gap in the last review round (deferred item: "Per-digest permalinks... make each day's edition shareable/indexable"). It's a natural next step after last week's RSS feed shipped the "subscribe" side of digest distribution; this ships the "share a specific edition" side, at similarly low cost.

## Problem / opportunity
`GET /api/digest/` always returns "the N most recent articles right now" with no way to ask for a specific day, and the frontend's Digest tab has no URL of its own beyond `/digest`. That means: no way to link back to "Tuesday's digest," no way for a visitor to bookmark a specific day, and no crawlable/indexable per-day URL. Every other tab in the app (feed, research, article reader) already has a real path; digest editions are the one piece of dated content without one.

## Proposed solution
- **Backend** (`backend/src/api/routes/digest.py`): add an optional `date` query param (`YYYY-MM-DD`) to `GET /api/digest/`. When present, filter top stories to that calendar day (`COALESCE(published_at, created_at)` within `[date 00:00:00, date+1 00:00:00)` UTC, mirroring the date-window pattern `_parse_dt`/the `curated`/`topics` endpoints already use) instead of "most recent N" — same response shape, `date` field in the response reflects the requested day. Omitting the param preserves today's exact existing behavior (no breaking change). Add `date` to the response's echoed `date` field either way, so the frontend always knows which day it's looking at.
- **Frontend** (`frontend/src/config/api.ts`, `App.tsx`, `DigestView.tsx`): extend the existing path-based tab routing (the same `readPathTab`/`pushState` pattern already used for `/article/:id`) to recognize `/digest/:date`. On load, if a date segment is present, fetch `/api/digest/?date=<date>` instead of the bare endpoint. Add a small "Copy link to this edition" action in `DigestView.tsx`'s masthead (next to the RSS link added in the last release) that copies `<origin>/digest/<today's date>` and pushes that path into history so the visible URL matches what's on the clipboard.
- User sees: opening `/digest/2026-09-25` shows that day's top stories instead of today's; a new "Copy link" button next to the existing RSS subscribe link.

## Effort estimate
S — one new query param on an existing, already-understood endpoint (reusing the date-window pattern from `/curated`/`/topics`), plus a routing extension that mirrors the app's existing `/article/:id` pattern almost exactly. No new dependency, no new table, no migration.

## Validation contract
- Functional assertions:
  - `GET /api/digest/?date=2026-09-25` returns only articles whose `COALESCE(published_at, created_at)` falls within that UTC calendar day.
  - `GET /api/digest/` (no `date`) is byte-for-byte unchanged in behavior from before this change.
  - An invalid `date` value returns a 400/422, not a 500.
  - A date with zero articles returns 200 with an empty `topStories` list, not an error.
- Behavioral assertions:
  - Visiting `/digest/2026-09-25` in the browser renders that day's stories; visiting `/digest` (no date) still renders "today"/most-recent as before.
  - Browser back/forward between `/digest` and `/digest/2026-09-25` works via the existing popstate listener.
  - "Copy link to this edition" copies a full URL and shows a toast/confirmation, matching the existing copy-link UX conventions already used elsewhere in the app.
- Negative assertions (should NOT happen):
  - No new dependency added to `requirements.txt`/`package.json`.
  - No change to `/api/digest/daily-summary`, `/api/digest/curated`, `/api/digest/topics`, or `/api/digest/rss` response shapes.
  - The date filter must not be vulnerable to SQL injection (parameterized query only, same as the rest of the file).
- Test commands the build will need to pass:
  - Backend, from `backend/`: `ruff check .`, `mypy . --ignore-missing-imports`, `python -m pytest test_ci.py -v`
  - Frontend, from `frontend/`: `npm run lint`, `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`, `npx tsc --noEmit`, `npm run build`

## Risks / open questions
- Timezone: the app has no user-timezone concept anywhere yet, so "calendar day" here means UTC day, same convention `daily-summary`'s cache key already uses — worth flagging in the PR but not worth solving generally in this scope.
- Very old dates (before the corpus existed) will legitimately render an empty digest; the empty-state should look intentional, not broken (reuse whatever empty-state pattern the feed/search views already have rather than inventing a new one).
