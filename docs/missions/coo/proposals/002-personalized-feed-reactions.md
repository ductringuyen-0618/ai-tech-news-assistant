---
status: shipped
attempts: 1
branch: coo/personalized-feed-reactions
---
# Personalized Feed Ranking via Lightweight Reactions

## Attempt 1 notes
Worker implemented the full feature (frontend/src/lib/interestWeights.ts,
NewsCard.tsx reaction controls, UnifiedFeedView.tsx bounded reorder +
personalization status/reset row, e2e coverage in news-feed.spec.ts).
`npm run typecheck`, `npm run lint` (0 errors, no new warnings vs.
baseline), and `npm run build` all passed on the first pass.

Independent scrutiny validator (subagent, saw only the proposal + diff)
found a real bug by tracing the code: `UnifiedFeedView`'s weights re-read
was keyed off the `articles` array reference, but that reference changes
on ordinary re-renders (App.tsx's `visibleFeedArticles` filter is
unmemoized) and grows via append during infinite-scroll pagination -- not
only on a genuine new feed load. That could silently re-read localStorage
mid-scroll and reshuffle windows already rendered on screen, violating
the "not a live jump-scare" behavioral assertion. Fixed by keying the
re-read off the feed's leading article id instead (stable across
appends, only moves on a real reload); added a regression test that
reacts then triggers pagination and asserts the already-rendered prefix
is untouched.

Independent professional-feel reviewer (subagent, same isolation) scored
the first pass FAIL on 3 must-fix items: (1) the reaction toast still
claimed an effect after a weight was already at its -3..3 clamp -- fixed
by having `nudgeInterestWeight` report whether it actually changed
anything, and showing an honest "already at the limit" toast otherwise;
(2) the "Personalized for you" status row hand-rolled its eyebrow styling
instead of reusing the app's shared `.uppercase-eyebrow` class used by
every other metadata row (including this same card's own source
eyebrow) -- fixed by reusing it; (3) reactions had no persisted visible
marker unlike Save/Read -- fixed by adding an `aria-pressed`,
signal-colored state on the reaction buttons derived from the article's
aggregate interest score, which survives a reload.

All three fixes are committed on this branch along with e2e coverage for
the clamp-honesty toast and the persisted pressed indicator.

A second independent scrutiny pass on the fixed diff confirmed all four
attempt-1 fixes hold, but by hand-tracing `reorderByInterest` against a
pagination scenario with non-empty weights (the first regression test
happened to only exercise empty weights, since an in-session reaction
never flows into render state without a reload -- correct by design, but
it meant that test didn't reach the buggy path), it found a real edge
case: `reorderByInterest` re-chunks its fixed-size windows from scratch
over the *entire* live `articles` array on every render. If an infinite-
scroll append landed inside what would otherwise be a partial trailing
window, the newly-fetched articles could get folded into a window that's
already rendered on screen and sort above an already-visible card --
this only failed to trigger before because the default page size (24)
happened to be a multiple of the window size (6), not because it was
actually guarded. Fixed by freezing a `personalizedThrough` boundary
alongside `weights` (same leading-article-id trigger); only that frozen
prefix ever gets re-windowed, anything appended beyond it is appended
verbatim until the next real reload. Added a regression test that
pre-seeds a weight so it's genuinely present in render state before
pagination fires (the actual buggy path) and asserts the prefix stays
untouched and new articles land strictly after it, never interleaved.

A third independent pass confirmed that fix is correct and complete, and
found one more small issue: `personalizedThrough` was hardcoded to `0`
on mount instead of lazily initialized like `weights` is, which could
flash the whole already-loaded list to unpersonalized order for one
frame on a remount with `articles` already populated (e.g. a feed tab
that unmounts on switch-away and doesn't refetch on return). Fixed by
lazy-initializing it from `articles.length`, matching the `weights`
pattern.

`npm run typecheck` / `npm run lint` (0 errors throughout, no new
warnings vs. the pre-existing baseline) / `npm run build` all passed
after every fix. `npm run format:check` was checked once and found to
already fail on ~85 pre-existing files unrelated to this change
(including files this diff never touches) -- pre-existing repo-wide
debt, not something this feature introduced or is in scope to fix; the
one file this diff added from scratch (`interestWeights.ts`) was
formatted to match the repo's prettier config regardless.
`playwright test` itself was not run live -- `playwright.config.ts` is
Windows-oriented (hardcoded `headless: false`, `C:/temp/...` artifact
paths) and requires a live backend+frontend dev stack with a populated
DB that isn't available in this container; the new/changed e2e cases
were instead verified by hand-tracing the implementation against each
test's mocked fixture data, three times over, by three independent
review passes.

## What you get
"More like this" and "Less like this" buttons on each news card. Reacting
nudges a per-source and per-category weight, stored in the browser, and the feed
visibly re-ranks so the front page reflects what the visitor cares about. Weights
survive between visits. Fully client-side; no backend or schema changes.

## Why start this now
The feed is the same reverse-chronological list for everyone, so a visitor who
saved five machine-learning articles sees exactly what a first-timer sees. There
is no way to say "more of this". A feed that adapts gives a reason to keep
scrolling today and a more relevant front page tomorrow, which is the core
return-visit loop competitors like Feedly already run. The signals it needs
(read state, saved articles) are already tracked, so it is a medium-sized
frontend change with no infrastructure risk.

## Problem / opportunity
The feed (`UnifiedFeedView.tsx`) is strict reverse-chronological for every
visitor. The app already tracks two client-side interest signals per
browser -- read state (`NewsCard.tsx`'s `markRead`/`isRead`, key
`techpulse-read-*`) and saved articles (`SavedArticlesList.tsx`, key
`techpulse-saved-articles`) -- but neither feeds back into what the feed
shows next. A visitor who saves five machine-learning articles in a row
sees the exact same chronological list as a first-time visitor. There is
also no way for a user to say "show me more/less of this" -- the only
interest signal is the passive, invisible act of saving or reading.

`docs/issues/2026-09-review-followups.md` names both of these as deferred
engagement work: "Interest-weighted re-ranking from Save/read/topic-click
behavior" (review-01 #4, review-09 #5, vs. Feedly Leo) and "Lightweight
reaction mechanic (thumbs up/down or 'more/less like this')" (review-05
#3), explicitly noting they're "worth bundling ... rather than doing
standalone" -- a bare reaction button with no visible effect on the feed
would fail the professional-feel bar (a control that visibly does nothing
reads as a prototype, not a shipped product), so this proposal bundles
them as the backlog recommends.

## Why this increases engagement
- **Session length**: a feed that visibly adapts to what a visitor just
  reacted to gives an immediate, tangible reason to keep scrolling instead
  of hitting a wall of undifferentiated chronological cards.
- **Return visits**: interest weights persist across sessions (localStorage
  survives a closed tab), so a visitor who trained the feed yesterday gets
  a noticeably more relevant front page today -- the core Feedly-Leo-style
  retention loop the backlog calls out.
- **Personalization as differentiator**: it's the cheapest available step
  toward "this product learns about me," which the existing product
  (search, digest, research) doesn't yet offer anywhere.

## Proposed solution
Entirely client-side for v1 -- no backend, schema, or API changes. All
raw signal data this needs (read state, saved ids) already lives in
`localStorage`, matching the existing pattern.

1. Add a small reaction control to `NewsCard.tsx` -- two icon buttons,
   "More like this" / "Less like this" (lucide-react icons already used
   elsewhere in the file), visible on hover/focus like the existing
   save affordance. Clicking one nudges a per-`(source, category)` integer
   weight up or down and shows a brief inline confirmation (reuse the
   `sonner` toast pattern already used in `SavedResearchList.tsx`).
2. Persist weights to a new localStorage key, e.g.
   `techpulse-interest-weights`, as `{ [sourceOrCategory: string]: number
   }`, clamped to a small range (e.g. -3..+3) so one click can't
   permanently bury a whole source.
3. In `UnifiedFeedView.tsx`, compute a blended sort key for the already-
   fetched article list: recency remains the primary key; the interest
   weight (summed across the article's source + each of its categories)
   is a secondary, bounded nudge -- e.g. reorder only within a sliding
   window of adjacent recency-ranked articles, never a full re-sort that
   could bury breaking news under old "liked" content. Read articles keep
   their existing opacity-dimming treatment (`NewsCard.tsx`); being read
   does not additionally penalize ranking in v1 -- keep the model to one
   signal (explicit reactions) plus recency, not three interacting
   heuristics, to keep behavior predictable and explainable.
4. A small, honest "Personalized for you" affordance (e.g. a toggle or a
   subtitle) so a user can tell the feed is adapting and can reset their
   weights -- avoids the product silently doing something invisible to the
   user, which the professional-feel pass should treat as a hard
   requirement, not a nice-to-have.

## Effort estimate
**M.** No backend/schema work. Frontend touches two existing files
(`NewsCard.tsx`, `UnifiedFeedView.tsx`) plus one new small localStorage
utility module (mirroring the existing `clientId.ts` / saved-articles
key pattern). Main complexity is getting the bounded-reorder algorithm
right so it visibly personalizes without ever looking broken (e.g. a
day-old article jumping above breaking news).

## Validation contract
- Functional assertions:
  - Each `NewsCard` renders "more like this" / "less like this" controls
    (distinct `data-testid`s, e.g. `data-testid="reaction-more"` /
    `data-testid="reaction-less"`).
  - Clicking a reaction control persists an updated weight to the
    `techpulse-interest-weights` localStorage key and shows a toast
    confirmation.
  - A reset/clear-personalization control exists and, when used, clears
    the weights key and returns the feed to pure chronological order.
- Behavioral assertions:
  - Given a fixed set of articles and a pre-seeded
    `techpulse-interest-weights` value favoring one source, that source's
    articles appear measurably earlier in the rendered feed than in the
    zero-weight (fresh visitor) baseline order, without violating the
    "recency stays primary within the reorder window" rule above.
  - Reacting to one card does not cause other, unrelated cards to jump
    or flicker on screen immediately (the re-rank applies on next
    feed load/refresh, not as a live jump-scare mid-scroll) -- this is a
    professional-feel requirement as much as a functional one.
  - The existing read-state dimming behavior (`isRead` /
    `opacity-60`) is unchanged by this feature.
- Negative assertions (should NOT happen):
  - No article is ever hidden or removed from the feed because of a
    negative reaction -- only reordered, and only within the bounded
    window described above.
  - No backend request is added for this feature in v1 -- it must not
    call any new or existing API endpoint to read/write reactions.
  - A brand-new visitor (empty localStorage) sees byte-identical ordering
    to the current chronological feed -- this feature must be a no-op
    until a user has reacted at least once.
- Performance assertions:
  - Re-ranking is a pure client-side sort over the already-fetched
    in-memory article array (existing `UnifiedFeedView` state) -- O(n log
    n) on typical feed page sizes, no additional network round-trip, no
    added render-blocking work (measure via existing Lighthouse/manual
    check that feed first-paint timing is not regressed).
- Test commands the build will need to pass:
  - Frontend: `npm run typecheck`, `npm run lint`, `npm run build`.
  - E2E: extend `frontend/e2e/news-feed.spec.ts` with cases for reaction
    controls, localStorage persistence, bounded reordering with seeded
    weights, and the empty-localStorage no-op case; existing feed spec
    assertions must not regress.
  - Backend: none required (no backend files should change) -- run
    `pytest tests/ -v` only if the worker touches any shared backend
    file, to confirm no accidental regression.

## Risks / open questions
- Getting the "bounded window" reorder algorithm to feel right (not too
  subtle to notice, not so aggressive it looks random) is the main design
  risk -- the worker should bias toward a small, clearly-testable window
  (e.g. reorder within each visible page/batch of N cards, not across the
  whole feed) rather than a global re-sort.
- If category data is sparse/missing on many articles (categories come
  from a JSON column that can be empty, per `digest.py`'s
  `_decode_categories`), weighting may need to fall back to `source`
  alone for those articles -- acceptable, but the worker should verify
  real data before assuming categories are populated.
- v1 intentionally has no server-side persistence, so weights don't
  follow a user across browsers/devices. That's an accepted limitation,
  not a defect -- do not scope-creep into building account-linked
  preference sync for this proposal.
