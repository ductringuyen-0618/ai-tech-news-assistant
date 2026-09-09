---
status: rejected
attempts: 0
branch: null
---
# Shareable Research Report Permalinks

## What you get
Every saved research report gets its own URL (`/research/:id`) that opens the
full cited report directly, plus a "Copy link" button on the report view. The
address bar follows what is on screen and the back button works. No new router
or backend work: the API endpoint already exists.

## Why start this now
Research reports are the strongest thing TechPulse produces, and right now they
cannot be bookmarked, sent to a colleague, or opened from a link. A report that
can be shared is a free acquisition channel: each link lands a new visitor on
finished, cited output with the rest of the app one click away. The backend half
is already done, so this is the cheapest engagement win on the backlog, and it
unblocks every future sharing feature.

## Problem / opportunity
The Research mode already produces cited, agentic markdown reports and
persists them via `POST /api/saved-research` (see
`backend/src/api/routes/saved_research.py`), and `GET
/api/saved-research/{id}` already returns the full record (question,
report_md, sources, created_at) -- but there is no URL that points at one
report. `SavedResearchList.tsx` opens a report's detail view purely as
in-memory component state after clicking a list row; the browser address
bar never changes. A finished report can't be bookmarked, sent in a Slack
message, or opened directly from a link -- the only way to see it again is
to already be a returning visitor who remembers to open the Saved tab and
click the right row.

This exact gap is called out in `docs/issues/2026-09-review-followups.md`
("Other deferred items") as "the strongest advocate-loop candidate in the
product (cited, agentic reports are inherently link-worthy)" -- the backend
half is already done, only the addressability is missing.

## Why this increases engagement
- **Sharing**: a report a user is proud of (or wants a colleague to see)
  becomes a URL instead of a screenshot. Every share is a zero-cost
  acquisition channel for a new visitor who lands directly on a piece of
  finished, cited AI output -- the product's strongest single artifact.
- **Return visits**: a bookmarked or linked report brings the same user, or
  a referred one, straight back into the app days later instead of relying
  on them remembering to reopen the tab.
- **Session length**: a visitor arriving via a shared link sees one full
  report immediately, then has the entire feed/digest one click away
  (existing nav chrome) instead of a dead end.

## Proposed solution
Add a client-side route `/research/:id`, following the exact pattern
`App.tsx` already uses for `/article/:id` (regex match on
`window.location.pathname`, `window.history.pushState` on navigation, no
new router dependency):

1. On matching `/research/:id`, fetch `GET
   /api/saved-research/:id` (already exists, via
   `API_ENDPOINTS.savedResearchById`) and render the same detail view
   `SavedResearchList.tsx` already has (reuse `MarkdownReport` +
   the existing header treatment), not a second implementation.
2. A "Copy link" affordance on the detail view (both the in-app
   post-click state and the direct-URL state) that copies
   `${window.location.origin}/research/{id}` to the clipboard and shows a
   toast confirmation (the app already uses `sonner` for toasts elsewhere,
   e.g. `SavedResearchList.tsx`).
3. Clicking a saved-research row from the list updates the URL via
   `pushState` to `/research/:id` (so the address bar always reflects what's
   on screen, and the back button closes the detail view back to the list --
   mirror the article-reader overlay's history handling in `App.tsx`).
4. Direct-load states: loading spinner, a real 404 "Report not found" state
   (not a blank screen or thrown error) when the backend 404s, and a link
   back to the main feed from the 404 state.
5. `<title>` and a meta description tag updated on mount to the report's
   question (best-effort link-preview improvement for an SPA without SSR;
   not building server-side rendering or an OG-image generator -- out of
   scope).

No backend changes are required -- `GET /api/saved-research/{id}` already
returns everything needed and already 404s correctly on a missing id.

## Effort estimate
**S/M.** The backend is already done. Frontend work is one new route match
in `App.tsx` (copy the `/article/:id` pattern), reusing the existing
`SavedResearchList` detail rendering instead of duplicating it, plus a
copy-link button and a 404 state. No new dependencies, no schema changes.

## Validation contract
- Functional assertions:
  - Navigating directly to `/research/{validId}` (fresh page load, no prior
    app state) renders that report's question as the title and its
    `report_md` via `MarkdownReport` (producing the same "Executive
    Summary" / "Sources Used" headings `saved-research.spec.ts` already
    asserts on).
  - Navigating directly to `/research/{nonexistentId}` renders a "not
    found" state with a link back to the feed, not a crash or blank page.
  - Clicking a row in the existing Saved Research list still opens the
    detail view (existing behavior in `saved-research.spec.ts` must keep
    passing unmodified) AND updates `window.location.pathname` to
    `/research/{id}`.
  - A "Copy link" control exists on the detail view and, when clicked,
    writes `{origin}/research/{id}` to the clipboard (assert via
    `navigator.clipboard.writeText` call args in the Playwright test,
    consistent with how the repo already tests clipboard-adjacent UI, or
    the visible copy of the URL text if clipboard isn't mockable in CI).
  - Browser back button from `/research/:id` (reached by clicking a list
    row) returns to the Saved Research list, matching the existing
    `saved-research-back-btn` behavior's end state.
- Behavioral assertions:
  - The detail view rendered at the direct `/research/:id` URL is visually
    and structurally the same component as the one reached by clicking a
    list row -- one implementation, not a fork.
  - The main app shell (Sidebar / top nav) still renders around the
    detail view when loaded directly via URL, so a visitor arriving via a
    shared link can navigate into the rest of the app in one click.
- Negative assertions (should NOT happen):
  - No new full-page reload / server round-trip on navigation between the
    list and a report -- this stays a client-side route change, consistent
    with `/article/:id`.
  - No duplicate/second markdown-report renderer introduced -- must reuse
    the existing `MarkdownReport` component.
  - Existing `saved-research.spec.ts` assertions (data-testids, empty
    state text, delete button) must not regress.
- Performance assertions:
  - Direct load of `/research/:id` shows a loading state within one
    render frame (no unstyled blank screen while the fetch is in flight)
    and completes using the single existing `GET
    /api/saved-research/{id}` call -- no additional network waterfall.
- Test commands the build will need to pass:
  - Backend: none required (no backend changes expected), but run `pytest
    tests/ -v -k saved_research` to confirm no accidental regression if
    any shared file is touched.
  - Frontend: `npm run typecheck`, `npm run lint`, `npm run build`.
  - E2E: extend `frontend/e2e/saved-research.spec.ts` (or add a
    sibling spec) covering direct-URL load, 404 state, and the copy-link
    control; existing spec's assertions must keep passing.

## Risks / open questions
- Clipboard API access inside Playwright's headless Chromium may need
  `context.grantPermissions(['clipboard-write'])` in the test setup -- the
  worker should check `frontend/e2e/_lib` for an existing helper before
  adding one.
- No SSR means social-platform link unfurls (Slack/Twitter previews) will
  show generic SPA meta, not per-report titles, unless the crawler executes
  JS. This is called out as accepted scope in "Proposed solution" above --
  do not scope-creep into building prerendering/OG-image generation for
  this proposal.
