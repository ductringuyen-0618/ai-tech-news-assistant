---
status: proposed
attempts: 0
branch: null
---
# Daily Digest RSS Feed

## What you get
Visitors can subscribe to TechPulse the same way they subscribe to any blog
or newsletter: a small "RSS" link on the Digest tab hands them a standards-
compliant feed of today's top stories. Once someone adds it to Feedly,
Reeder, Apple News, or any feed reader, that reader pulls them back to
TechPulse's stories automatically every day -- no one has to remember to
open the site.

## Why start this now
The prior review round ranked "real email sending for the digest" as the
single highest-leverage retention feature in the product
(`docs/issues/2026-09-review-followups.md`, item 1), but it never shipped
because it needs a paid ESP API key (Resend/Postmark/SES) this routine
can't provision. RSS is the same mechanic -- subscribe once, get pulled
back automatically -- with none of that cost: no ESP, no scheduled send
job, no secret, no new dependency. It reuses the exact same digest data
`/api/digest/` already builds today. The same follow-up doc lists
"RSS/JSON export of the digest" directly under its "other deferred items"
section as a small, unassigned, shareable/indexable/scriptable win. Every
day this waits is a day the product misses the cheapest version of its
own top-recommended growth lever.

## Problem / opportunity
Nothing in TechPulse currently gives a visitor a reason to come back
*automatically* -- every return trip today requires the visitor to
remember to open the site themselves. `get_daily_digest()` in
`backend/src/api/routes/digest.py` already assembles exactly the payload
an RSS feed needs (top stories with title/source/summary/link), it just
isn't exposed in a format any feed reader, script, or aggregator can
consume.

## Proposed solution
- New `GET /api/digest/rss` endpoint in `backend/src/api/routes/digest.py`,
  reusing the same query/shape logic `get_daily_digest()` already uses
  (top N most-recent, non-archived articles) rather than duplicating the
  SQL. Emits a valid RSS 2.0 document: `<rss version="2.0"><channel>` with
  `<title>TechPulse Daily Digest</title>`, `<link>`, `<description>`, and
  one `<item>` per story -- `<title>`, `<link>` (the article's own `url`
  column), `<description>` (the same `summaryShort` text `/api/digest/`
  returns), `<pubDate>` (RFC 822 format, which feed readers require), and
  a stable `<guid>` (the article id). Build it with the stdlib
  (`xml.sax.saxutils.escape` for text nodes, or `xml.etree.ElementTree`) --
  no new dependency. Returned via FastAPI's `Response(content=...,
  media_type="application/rss+xml")`.
- New `digestRss: '/api/digest/rss'` constant in `frontend/src/config/api.ts`
  next to the other digest-adjacent endpoints.
- Small addition to `DigestView.tsx`'s masthead/header region: a `Rss`
  icon (already available via `lucide-react`, which the file already
  imports icons from) linking to `${API_BASE_URL}${API_ENDPOINTS.digestRss}`
  with `target="_blank" rel="noopener noreferrer"` -- the standard
  "click to subscribe" pattern, letting the browser or an installed feed
  reader take it from there. Rendered only once the digest has actually
  loaded (not during the loading-skeleton state), matching how the rest
  of the masthead already gates on load state.
- No backend schema change, no new pip/npm dependency, no secret, no
  scheduled job.

## Effort estimate
**S.** One new backend endpoint (~60-80 lines, reusing existing digest
query logic), one new frontend endpoint constant, one small link in an
existing component. No migration, no dependency changes, no auth.

## Validation contract
- Functional assertions:
  - `GET /api/digest/rss` returns HTTP 200 with a `Content-Type` starting
    `application/rss+xml`, and the body parses as well-formed XML
    (`xml.etree.ElementTree.fromstring` does not raise).
  - The parsed document has one `<item>` per story in `/api/digest/`'s
    `topStories` (same default `top=5`), and each item's `<title>` /
    `<description>` match that story's `title` / `summaryShort` exactly.
  - Article titles/summaries containing `&`, `<`, or `>` are properly
    XML-escaped -- the feed still parses even when source content has
    those characters.
  - Every `<item>` has a non-empty `<pubDate>` in RFC 822 form and a
    `<guid>` that is stable across repeated requests (same article -> same
    guid).
  - No articles in the DB -> `/api/digest/rss` still returns 200 with a
    valid `<channel>` and zero `<item>` elements, not a 500.
  - The RSS link in `DigestView.tsx` is present in the DOM only after the
    digest finishes loading, and its `href` resolves to the correct
    absolute backend URL (`API_BASE_URL` + the new constant).
- Behavioral assertions:
  - `curl -s <backend>/api/digest/rss` (no headers at all -- no
    `X-Client-Id`, no auth) succeeds, since feed reader software won't set
    custom headers.
  - The existing `/api/digest/` JSON endpoint's response shape is
    byte-for-byte unchanged.
- Negative assertions (should NOT happen):
  - No new pip or npm dependency is added (stdlib XML only; no `feedgen`
    or similar).
  - `frontend/e2e/digest.spec.ts`'s existing assertions ("Daily Tech
    Digest", "Top Stories Today", "Trending Now", `.border-l-4` on
    top-story `<li>`s, `[data-slot="badge"]` chips) keep passing unchanged.
  - The feed is not personalized and does not read or require
    `client_id`/`X-Client-Id` -- it stays a single shared feed, avoiding
    per-visitor caching complexity this S-sized version doesn't need.
- Test commands the build will need to pass (from `.github/workflows/ci.yml`):
  - Backend (touches `backend/`): `ruff check .`, `mypy . --ignore-missing-imports`,
    `python -m pytest test_ci.py -v --tb=short`, plus new/extended coverage
    in `backend/tests/unit/test_digest_route.py` (which already covers this
    route file) for the new endpoint.
  - Frontend (touches `frontend/`): `npm run lint`,
    `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`,
    `npx tsc --noEmit`, `npm run build`.

## Risks / open questions
- RFC 822 `<pubDate>` formatting from the stored `created_at` timestamp is
  a natural bug magnet (timezone handling) -- reuse `_parse_dt()`, which
  `digest.py` already has, rather than re-deriving it.
- Confirm the `articles.url` column (see `backend/src/database/models.py`)
  is reliably populated for ingested rows before relying on it for
  `<link>`; fall back to the digest item's own detail-view URL if a row's
  `url` is ever empty, so no `<item>` ships with a dead link.
- Not adding a JSON Feed (`feed.json`) variant in this pass, even though
  the follow-up doc mentions "RSS/JSON export" together -- RSS alone
  covers the actual reader ecosystem (Feedly, Reeder, Apple News, etc.);
  a JSON Feed variant is a natural, separate follow-up if anything
  specifically needs machine-readable JSON later.
