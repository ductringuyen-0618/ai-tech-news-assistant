---
status: expired
attempts: 0
branch: null
---
# Article Coverage Chip

## What you get
Opening any article now shows at a glance whether this is a story the whole industry is reporting or just one outlet's take — a small "Covered by N sources" chip sits right above the existing "Related coverage" list in the article reader. Stories with wide coverage visibly stand out, which is exactly the kind of context-at-a-glance signal that makes people click one more related article instead of closing the tab. Single-source stories simply show no chip, so nothing new is claimed about them.

## Why start this now
A review round in September flagged this as the top "missing vs. Techmeme" gap and explicitly recommended a cheap distinct-source count as the fallback to full story clustering — nothing has shipped against that finding since. The exact counting mechanic (dedupe articles by `source` from data the knowledge-graph endpoints already return) is already live and proven in production in `TrendingRail.tsx`'s per-entity "· Nsrc" chip, so this isn't speculative: it's reusing a pattern that already works, just applied to the one place users spend the most time — the article reader — instead of only the trending ticker. It costs nothing to build (zero new endpoints, zero new network calls, derived entirely from the `related-articles` response `ArticleReader.tsx` already fetches) and every day without it is a day the reader shows a bare, context-free list where a one-line trust signal could be nudging people deeper into the related-coverage list they already have in front of them.

## Problem / opportunity
`ArticleReader.tsx` (lines 152-175, 425-453) already fetches `GET /api/knowledge-graph/related-articles/{id}?limit=6` and renders the results as a bare "Related coverage — {entity}" list of titles/sources. It never tells the reader how many *distinct* outlets are behind that list, so a story confirmed by five publications looks identical to one confirmed by a single uncorroborated source. `TrendingRail.tsx` already solves this exact problem at the entity level (dedupes `articles.map(a => a.source)` into a `Set` and renders `"· Nsrc"` with a `title` tooltip), but nothing surfaces it per-article where users are actually reading.

## Proposed solution
In `frontend/src/components/ArticleReader.tsx`, where `related` state is already set from the existing fetch (line 166), derive `new Set([article.source, ...related.map(r => r.source)]).size` and render it as a small chip/badge next to the "Related coverage" header (around line 430-432) — e.g. "Covered by 4 sources" — following `TrendingRail.tsx`'s existing visual pattern (signal-color count, visible text rather than hover-only tooltip, since mobile has no hover) and the app's existing design tokens. Only render when the computed count is 2 or more; a lone source isn't a coverage signal and should show nothing, matching the current `related.length > 0` guard's "stay silent rather than claim something false" behavior. No backend change, no new fetch, no new dependency.

## Effort estimate
S — one component, no backend changes, no new endpoint or network call, reuses an already-shipped counting pattern verbatim from `TrendingRail.tsx`. Should fit in well under a day of implementation plus validation.

## Validation contract
- Functional assertions: when the existing related-articles fetch returns 2+ distinct sources (counting the current article's own source plus every related article's source), a "Covered by N sources" chip renders directly above/alongside the "Related coverage" header; when the distinct-source count is 0 or 1, no chip renders (identical to today).
- Behavioral assertions: the chip's count is computed client-side from data already in the `related`/`article` state — no additional `apiFetch` call is introduced; the chip uses visible text (not an icon/tooltip-only treatment) so it is legible on touch devices with no hover; styling reuses existing design tokens (`--accent-signal`/`--foreground-mute` etc. per `TrendingRail.tsx`'s own treatment) rather than introducing new colors.
- Negative assertions (should NOT happen): must NOT add a new backend endpoint, database query, or network request; must NOT render a chip claiming coverage when the count is <= 1; must NOT alter the existing "Related coverage" list's rendering, ordering, or click-through behavior (`setCurrentId` on click) below it.
- Test commands the build will need to pass (frontend-only change, from `frontend/`): `npm run lint`, `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`, `npx tsc --noEmit`, `npm run build`.

## Risks / open questions
- Naming/copy: "Covered by N sources" vs. matching `TrendingRail`'s terser "· Nsrc" — worker should pick whichever reads clearly as prose next to a section header rather than inline in a ticker, and should keep the two consistent in tone even though their layouts differ.
- The distinct-source count technically only reflects the up-to-6 related articles the existing endpoint caps at (`limit=6`), so very widely covered stories undercount rather than overcount — acceptable given the existing cap already governs the list shown directly below the chip, so the number always matches what the user can click through to.
