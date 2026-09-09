# Personalized Feed Ranking via Lightweight Reactions — shipped

Proposal: [`docs/missions/coo/proposals/002-personalized-feed-reactions.md`](../proposals/002-personalized-feed-reactions.md)
Branch: `coo/personalized-feed-reactions`

## What shipped

- `frontend/src/lib/interestWeights.ts` (new) — a small localStorage-backed
  module for a per-`source:`/`category:` interest-weight map, clamped to
  `-3..3`. `nudgeInterestWeight` reports whether a nudge actually changed
  anything (needed so the UI never claims an effect it didn't have).
  `reorderByInterest` does the bounded, windowed reorder: recency stays
  primary, articles only ever move within a fixed-size (default 6) window
  of adjacent, already-recency-sorted articles.
- `frontend/src/components/NewsCard.tsx` — "More like this" / "Less like
  this" reaction buttons in the card footer (`data-testid="reaction-more"`
  / `"reaction-less"`), matching the existing share-button footer rhythm.
  Reacting nudges the weight, shows a toast, and the button carries a
  persisted `aria-pressed` state derived from the article's aggregate
  interest score (survives reload, same idea as the existing Save/Read
  markers).
- `frontend/src/components/UnifiedFeedView.tsx` — applies the bounded
  reorder to the already-fetched article list and renders a "Personalized
  for you" status row (reusing the app's shared `.uppercase-eyebrow`
  primitive) with a reset control, shown only once a visitor has actually
  reacted. The reorder snapshot (weights + how much of the list it covers)
  updates only on a genuine reload, never on a bare re-render or an
  infinite-scroll append, so reacting to a card and scrolling never
  reshuffles content already on screen.
- `frontend/e2e/news-feed.spec.ts` — new coverage against a mocked
  `/api/news/` response (needed for deterministic ordering assertions,
  which live backend data can't guarantee): reaction controls render,
  reacting persists a weight and toasts, a fresh visitor is byte-identical
  to chronological order, reacting doesn't reorder anything live, a
  pre-seeded weight reorders within its window on load, reset restores
  chronological order instantly, negative reactions never remove an
  article, a clamped weight stops claiming an effect, a reacted card shows
  a persisted pressed indicator, and two pagination regression tests (one
  for the leading-id boundary, one for the windowing-across-appends edge
  case).

No backend or schema changes. No new network calls — verified by grep and
by reading the reaction handler directly.

## Why it shipped as attempt 1 despite three rounds of fixes

Everything below happened inside a single `attempts: 1` cycle — real bugs
were found, fixed, and re-verified in the same pass rather than being
deferred to a next fire. Each independent review pass saw only the
proposal and the current diff, not this report or each other's reasoning.

1. **Worker pass** — full implementation. `npm run typecheck` / `lint` /
   `build` all passed on the first try.
2. **Scrutiny validator (round 1)** — found a real bug: the reorder's
   weights re-read was keyed off the `articles` array reference, which
   changes on ordinary re-renders and infinite-scroll appends, not just
   real reloads — could silently reshuffle on-screen content mid-scroll.
   **Professional-feel reviewer (round 1)** — FAIL, 3 must-fix items: a
   toast that claimed an effect after hitting the weight clamp, hand-
   rolled eyebrow styling instead of the app's shared primitive, and no
   persisted visual marker for a reacted card (unlike Save/Read). All
   four issues fixed; e2e coverage extended for each.
3. **Scrutiny validator (round 2)** — the round-1 fix was correct as far
   as it went, but hand-tracing a pagination-with-non-empty-weights
   scenario surfaced a subtler edge case in the reorder's windowing math
   itself (see the proposal's "Attempt 1 notes" for the full trace).
   Fixed by freezing the personalized region to a snapshot boundary;
   added a regression test that actually exercises the buggy path (the
   round-1 test didn't, since reacting alone never reaches render state).
   **Professional-feel reviewer (round 2)** — PASS; all three round-1
   fixes independently confirmed genuine, only nice-to-haves remained.
4. **Scrutiny validator (round 3)**, scoped narrowly to the round-2 fix —
   confirmed it correct and complete, but found one more small issue (a
   hardcoded vs. lazy-initialized default that could flash unpersonalized
   order for one frame on certain remounts). Fixed.

Severity converged with each round (a real functional bug → an edge-case
bug → a one-frame visual flash), which is why this shipped rather than
continuing to iterate indefinitely.

## Validator findings

- `npm run typecheck` — PASS (0 errors), every round.
- `npm run lint` — PASS (0 errors; 29 warnings, all pre-existing, none in
  the files this diff touches), every round.
- `npm run build` — PASS, every round.
- `npm run format:check` — fails, but on ~85 pre-existing files unrelated
  to this change (confirmed by checking `main` before this diff touched
  anything); pre-existing repo debt, not introduced or fixed here. The one
  brand-new file (`interestWeights.ts`) was formatted to the repo's
  prettier config anyway.
- Playwright e2e was not run live in this environment: `playwright.config.ts`
  is Windows-oriented (`headless: false`, hardcoded `C:/temp/...` artifact
  paths) and needs a live backend+frontend dev stack with a populated DB
  that this container doesn't have. The new/changed test cases were instead
  verified by hand-tracing the implementation against each test's mocked
  fixture data, independently, across all three review rounds.

## Professional-feel notes

Round 2's independent review verdict: **PASS**. All three round-1
must-fix items confirmed genuinely resolved by reading the actual code,
not just the claims:
- Toast honesty — `nudgeInterestWeight`'s `changed` flag is real and
  `NewsCard` branches on it correctly (traced click-by-click through the
  clamp).
- Eyebrow consistency — the personalization status row and the card's own
  source eyebrow both apply the same `.uppercase-eyebrow` class.
- Pressed-state marker — derived from persisted weights on every mount,
  not just local component state; survives reload.

Remaining nice-to-haves noted but not required to ship: the pressed
background reuses the generic hover tint rather than the app's dedicated
active-toggle wash token used elsewhere (e.g. `Settings.tsx`'s theme
toggle), the reset link's hover color doesn't match other reset/clear
links' signal-color hover treatment, and the pressed indicator reflects
aggregate source/category sentiment rather than "you clicked this exact
card" (by design, per the proposal, but not called out to the user via
copy).

## What's next

Branch `coo/personalized-feed-reactions` is pushed. PR opened via GitHub
MCP: https://github.com/ductringuyen-0618/ai-tech-news-assistant/pull/5

Recommend running `npm run test:e2e:ui` locally before merge, since the
new/changed Playwright cases could only be hand-traced (not executed
live) in this environment.
