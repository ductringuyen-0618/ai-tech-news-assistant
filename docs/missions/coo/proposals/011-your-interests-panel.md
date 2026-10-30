---
status: proposed
attempts: 0
branch: null
---
# Your Interests Panel

## What you get
The Settings tab gets a new "Your Interests" section that plainly shows what the feed's "more/less like this" reactions have learned: a short list of sources and topics ranked by how much a reader has nudged them up or down, plus a one-click "Reset my interests" action. Nothing changes about how the feed itself ranks stories — this just makes a system that already quietly reorders the feed visible and controllable for the first time.

## Why start this now
The feed-reactions feature shipped over a month ago and has been silently reweighting everyone's feed since, but the reader has had zero way to see it working, check it's accurate, or undo it — a personalization system nobody can see is a personalization system nobody trusts enough to keep using. Showing people the effect of their own clicks is one of the best-evidenced ways to get them to make more of those clicks, which is exactly the engagement loop the original feature was built to create but never closed. It costs nothing to build: the weights are already recorded in `localStorage` by proposal 002's `interestWeights.ts`, a `clearInterestWeights()` reset function already exists and is unused, and the natural home for this (Settings, right next to the existing Topic Preferences section) is already built and open to extension.

## Problem / opportunity
`frontend/src/lib/interestWeights.ts` stores a flat map of `source:<name>`/`category:<name>` → a clamped integer, updated every time a reader clicks "more like this" / "less like this" on a `NewsCard` (see `NewsCard.tsx`) and consumed by `UnifiedFeedView.tsx` to silently re-rank the feed. The map is never read back anywhere for display — `clearInterestWeights()` is exported from the module but has no caller in the codebase. A reader who reacts to ten articles has no way to find out what that did, and no way to start over if a bad click (e.g. a mis-tap) permanently biases their feed within the existing clamp.

## Proposed solution
In `frontend/src/components/Settings.tsx`, add a new section between "Appearance" and "TOPICS" (same `<SectionEyebrow>` / `<section className="space-y-4">` pattern already used by the other two sections):
- Read `readInterestWeights()` on mount, split keys into "sources" and "categories" (the key already carries the `source:`/`category:` prefix), sort each group by weight descending, and render the top few of each as a small list — e.g. "More of: OpenAI, AI Agents" / "Less of: Crypto" — using the same mono-eyebrow/ticker visual language as the rest of the page. When the map is empty, show one quiet sentence ("React to articles in your feed and your interests will show up here.") instead of an empty box.
- Add a "Reset my interests" `TickerOption`-style button that calls the existing `clearInterestWeights()` and re-renders the (now empty) list, with a `sonner` toast confirming the reset (the same toast pattern `SavedArticlesList.tsx` already uses).
- No backend change, no new endpoint, no new dependency — everything needed (`readInterestWeights`, `clearInterestWeights`) already exists and is exported from `interestWeights.ts`.

## Effort estimate
S — one new section in one existing component, built entirely on functions that already exist and are already exported but unused. No backend, no new state management, no new dependency. Comfortably a half-day including the e2e check.

## Validation contract
- Functional assertions: opening Settings with at least one prior feed reaction shows a "Your Interests" section listing the sources/categories nudged up ("More of: ...") and down ("Less of: ..."), derived from `readInterestWeights()`; with no prior reactions, the section shows the empty-state sentence instead of an empty list; clicking "Reset my interests" calls `clearInterestWeights()` and the section immediately reflects the empty state.
- Behavioral assertions: the panel reads existing `localStorage` data only — no new `apiFetch`/network call is introduced; the reset action is a single explicit button (never automatic/silent); visual treatment (mono eyebrow, ticker-style buttons, spacing) matches the existing "Appearance" and "TOPICS" sections on the same page.
- Negative assertions (should NOT happen): must NOT change how `UnifiedFeedView.tsx` ranks or filters the feed — this is a read/reset surface only; must NOT introduce a new localStorage key (reuses `techpulse-interest-weights` via the existing module's own functions); must NOT remove or alter the existing Topic Preferences / Appearance sections' markup, test ids, or save behavior.
- Test commands the build will need to pass (frontend-only change, from `frontend/`): `npm run lint`, `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`, `npx tsc --noEmit`, `npm run build`.

## Risks / open questions
- Display names: raw category/source strings in the weight keys may be lowercase/slug-like (e.g. `ai-agents`) rather than display-ready ("AI Agents") — worker should check what `TopicFilter`/`NewsCard` already use for human-readable labels and reuse that mapping rather than printing raw keys.
- How many items to show per list (all vs. top 3-5) is a judgment call for readability; a long tail of near-zero weights shouldn't crowd out the signal, so a small cap with "+N more" is reasonable if the list is long, but isn't required by the validation contract above.
