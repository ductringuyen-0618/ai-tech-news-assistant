---
status: expired
attempts: 0
branch: null
---
# Daily Reading Streak

## What you get
A small "3-day streak" style badge appears in the sidebar once someone has
opened TechPulse on two or more consecutive calendar days, the same habit
mechanic Duolingo and Wordle use to pull people back tomorrow. It counts up
quietly in the background from the moment this ships -- no onboarding, no
signup, nothing for a first-time visitor to notice or be confused by.

## Why start this now
TechPulse currently gives a visitor zero reason to come back the *next* day
specifically -- only "there might be new articles," which is true of any
news site and doesn't create a habit loop. Streak mechanics are one of the
best-evidenced return-visit levers in consumer product design precisely
because they cost the visitor nothing to start and convert "I could check
back" into "I don't want to lose my streak." It is also the cheapest
engagement feature left on the backlog: purely client-side, no backend
change, no new dependency, no secret, built entirely on the anonymous
`client_id`/localStorage pattern (`frontend/src/lib/clientId.ts`) this app
already uses for settings and interest weighting. Every day this waits is a
day of visits that create no compounding reason to return.

## Problem / opportunity
Nothing in the product currently tracks or rewards repeat visits. The two
personalization primitives that exist -- `getClientId()` (a stable anon
UUID in localStorage, sent as `X-Client-Id`) and `interestWeights.ts`
(client-side engagement weighting from saves/reactions) -- both describe
*what* a visitor likes, not *when* or *how often* they come back. Retention
mechanics research (and this repo's own prior COO proposal `002`, which
shipped lightweight feed reactions) point the same direction: the cheapest
engagement wins left are behavioral, client-side, and additive to what's
already there. A streak is the natural next primitive in that family.

## Proposed solution
- New `frontend/src/lib/visitStreak.ts`: a small pure-function module,
  mirroring the style of `clientId.ts` (try/catch around every localStorage
  read/write, silent graceful degradation in privacy mode). Stores
  `{ lastVisitDate: 'YYYY-MM-DD', currentStreak: number, longestStreak:
  number }` under a single localStorage key, keyed off the *browser's local*
  calendar date (not UTC) so the day boundary matches what the visitor
  actually experiences. On call: same day as `lastVisitDate` -> no-op,
  return current state; exactly one day later -> increment `currentStreak`,
  update `longestStreak` if beaten; more than one day later (or no prior
  record) -> reset `currentStreak` to 1. Called once per app mount from
  `App.tsx`, the same place `getClientId()` is already established.
- A small streak badge in `Sidebar.tsx`, next to the wordmark or in the
  footer area near the theme toggle, using the existing typographic /
  mono-eyebrow styling already established there (`font-mono-tx`,
  `uppercase-eyebrow`, the `--accent-signal` color token) -- not a new
  visual language, not a gamified badge/confetti aesthetic that would clash
  with the "Broadsheet Terminal" design system. Something like a small flame
  glyph + `3-day streak` in the existing mono type. Rendered only once
  `currentStreak >= 2` -- a first-time visitor sees nothing, so the feature
  never reads as broken or empty.
- A one-time celebratory `sonner` toast (the toast library already used in
  `SavedArticlesList.tsx` / `SavedResearchList.tsx`) the moment a visitor
  first crosses 3, 7, or 30 days, each shown at most once (tracked in the
  same localStorage record so a reload doesn't re-fire it).
- No backend changes, no new npm dependency, no new route.

## Effort estimate
**S.** One new frontend utility module (~60-80 lines, pure functions,
easily unit-testable via Playwright date mocking), one small addition to
`Sidebar.tsx`, one `useEffect` call site in `App.tsx`. No backend, no schema,
no dependency changes.

## Validation contract
- Functional assertions:
  - First-ever visit (no localStorage record): no badge renders, and a
    record is created with `currentStreak: 1`.
  - A second visit on the immediately following local calendar day sets
    `currentStreak: 2` and the badge now renders "2-day streak" (or
    equivalent copy).
  - A second visit on the *same* local calendar day as the last recorded
    visit does not increment `currentStreak` (reloading the page 5 times in
    one day must not inflate the count).
  - A visit after a gap of 2+ local calendar days resets `currentStreak` to
    1 and the badge disappears again (streak >= 2 required to show).
  - `longestStreak` never decreases once set, even after a reset.
  - The first time `currentStreak` reaches 3, 7, and 30, a toast fires
    exactly once each (verified by reloading after the milestone and
    confirming no repeat toast).
- Behavioral assertions:
  - The badge uses the existing sidebar typographic system (mono type,
    existing color tokens) -- no new color, no new font, no confetti/emoji
    styling inconsistent with the rest of the shell.
  - Works identically on the desktop `<aside>` sidebar and the mobile
    `Sheet` drawer (both render `renderSidebarBody()`).
- Negative assertions (should NOT happen):
  - No network request is added anywhere in this feature -- it is 100%
    client-side.
  - No badge, toast, or console error when `localStorage` is unavailable
    (privacy/incognito mode) -- must degrade the same way `clientId.ts`
    does (silent catch, feature simply doesn't show).
  - Does not touch `client_id`/`X-Client-Id` or send streak data to the
    backend in any form.
  - Does not regress any existing Sidebar Playwright assertions
    (`data-slot="sidebar"`, tablist roles, `data-testid="theme-toggle"`,
    `data-testid="sidebar-mobile-trigger"`).
- Test commands the build will need to pass (from `.github/workflows/ci.yml`,
  frontend job, since this touches only `frontend/`):
  - `npm run lint`
  - `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`
  - `npx tsc --noEmit`
  - `npm run build`
  - New/extended Playwright coverage (e.g.
    `frontend/e2e/reading-streak.spec.ts`) driving the day-rollover logic
    via `page.addInitScript` / `page.clock` (Playwright's clock API) rather
    than real multi-day waits, plus confirming no regression in
    `frontend/e2e/news-feed.spec.ts`'s existing sidebar assertions.

## Risks / open questions
- Local-date vs. UTC-date: must key off `new Date()` local calendar day, not
  `toISOString()` (which is UTC and would flip the "day" at the wrong wall-
  clock moment for most visitors). Worth a code comment at the one place
  this matters, since it's a natural bug magnet.
- Clock/testability: Playwright's `page.clock` API (or `page.addInitScript`
  overriding `Date`) is the cleanest way to simulate day rollovers in CI
  without real waits -- the worker should confirm the repo's Playwright
  version supports it before relying on it, falling back to directly
  seeding the localStorage record with a controlled `lastVisitDate` if not.
- Multi-device: because this is pure localStorage, a streak does not follow
  a visitor across devices/browsers. That's an accepted, disclosed
  limitation for this S-sized version, not a defect -- a server-backed
  streak keyed on `client_id` would be a natural, separate follow-up once
  (if ever) real accounts exist.
