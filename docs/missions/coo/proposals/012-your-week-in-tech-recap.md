---
status: proposed
attempts: 0
branch: null
---
# Your Week in Tech Recap

## What you get
When someone comes back to TechPulse after a few days away, they see a short "Your Week in Tech" card at the top of the feed: how many stories they read, how many they saved, and the topic they leaned into most — built entirely from signals the app already quietly collects. The same recap lives permanently in Settings so it is never a one-shot surprise. Dismiss it once and it stays away until the next calendar week.

## Why start this now
Readers currently get zero feedback that their activity on the site adds up to anything — every visit looks like the first one. A personal "here's your week" moment is the cheapest, most proven re-engagement pattern in consumer news/reading apps (Duolingo, Spotify Wrapped, Pocket's reading stats all lean on it), and this one costs nothing to build: the read-tracking, save-tracking, and interest-weight data it summarizes already exist in localStorage from shipped features (card/article read-state, Saved Articles, and the Your Interests panel from proposal 011) — they're just never shown back to the person who generated them. The longer that data sits unused, the more a free, good idea stays on the table.

## Problem / opportunity
TechPulse tracks read state (`techpulse-read-articles`), saved articles, and interest weights per visitor, but none of it is ever reflected back as a sense of progress or identity ("you're the kind of reader who..."). There's also an existing `techpulse-last-seen-timestamp` used for the "N new stories since your last visit" badge, but nothing yet keyed off how long someone has been away for a personalized welcome-back moment. Competitors in the same race-for-attention space (newsletters with streaks, Wrapped-style recaps) use exactly this kind of lightweight stat surface to pull people back.

## Proposed solution
- `frontend/src/lib/readHistory.ts` (new): centralizes the read-tracking logic currently duplicated in `NewsCard.tsx` and `ArticleReader.tsx` (`READ_ARTICLES_KEY`/`markRead`/`readReadSet`). Keeps the existing plain-ID-array format readable (treated as undated legacy reads, still counted as "read" for the grey-out state) but future writes store `{ id, readAt, source, category }`, capped at the most recent ~200 entries so localStorage never grows unbounded. Exposes `markRead(...)` (superset of today's signature) and `getReadsSince(sinceMs)`.
- `NewsCard.tsx` and `ArticleReader.tsx`: switch their local read-tracking helpers to import from `readHistory.ts` instead of each keeping its own copy (removes the existing duplication as a side effect, doesn't change their current behavior).
- `frontend/src/components/WeeklyRecap.tsx` (new): computes the last-7-days stats (read count via `getReadsSince`, saved count via the existing saved-articles helper, top category/source via `readInterestWeights()` from proposal 011's `interestWeights.ts`) and renders a small dismissible card. Shown once per calendar week (tracked via a new `techpulse-recap-last-shown` key, same pattern as `techpulse-last-seen-timestamp`), only when there is at least one read or saved article to report — never shown to a first-time or inactive visitor with nothing to recap.
- `App.tsx` or `UnifiedFeedView.tsx`: mount `WeeklyRecap` above the feed, gated the same way the existing "N new stories" badge is gated (not shown while searching/filtering).
- `Settings.tsx`: add a permanent "Your Week" section (same visual slot pattern as the existing "Your Interests" section from proposal 011) showing the same stats with no dismiss/expiry, so the recap is never only a fly-by banner.

## Effort estimate
M — four touched files plus one new lib and one new component, but every number it displays already exists in localStorage from shipped features; the only new mechanics are the capped/timestamped read-history format and the once-per-week display gate. No backend change, no new dependency, no new network call, no secret.

## Validation contract
- Functional assertions: reading an article still marks it read exactly as today; saved-article count and top-interest category match what Settings' existing "Your Interests" section already derives from the same localStorage keys; the recap's read/saved counts only include activity from the last 7 days.
- Behavioral assertions: the recap banner appears on the feed only once per calendar week and only when there is at least one countable read or save; dismissing it hides it until the next calendar week; the permanent Settings "Your Week" section always reflects current data with no dismiss state; legacy (undated) entries in `techpulse-read-articles` still render the read/grey-out state on cards exactly as before this change.
- Negative assertions (should NOT happen): no new backend endpoint, network call, or dependency; no change to feed ranking/ordering logic (`reorderByInterest` stays untouched); the recap must never appear for a visitor with zero reads and zero saves in the window; `techpulse-read-articles` must never grow unbounded (capped list enforced on every write).
- Test commands the build will need to pass (from `frontend/`): `npm run lint`, `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`, `npx tsc --noEmit`, `npm run build`.

## Risks / open questions
- Legacy read entries (plain ID strings, no timestamp) can't retroactively count toward "read this week" — the first recap after this ships may undercount for returning visitors until fresh dated reads accumulate. Worth stating plainly in the card copy rather than hiding the gap (e.g. omit the read-count line entirely if all of a visitor's reads are legacy/undated).
- Needs a product-feel pass on copy and visual weight so the banner reads as a pleasant nudge, not a guilt-trip or a notification-badge-style annoyance.
- Namespacing collision risk is low but real: this is the second feature (after proposal 011) to read `interestWeights.ts`'s data for display rather than ranking — worth double-checking both surfaces stay visually consistent with each other.
