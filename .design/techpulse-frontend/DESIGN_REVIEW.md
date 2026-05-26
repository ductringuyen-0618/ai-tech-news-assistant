# TechPulse — Design Review (post-redesign)

> Replaces the previous Broadsheet Terminal-anchored review.
> Anchored to `REDESIGN_PLAN.md` (Atelier + Mission Control).
> Target viewport: desktop ≥ 1280 px. Mobile is out of scope per project direction.

Owner: Tri
Reviewer: Claude (design-review pass after Phases A–E)
Date: 2026-05-18
Build under review: redesign branch, post-Phase E

---

## 0. How to read this

Each finding is graded:

- **Must** — ship-blocker. Layout, accessibility, or contract regression.
- **Should** — quality bar. Fix before next public sweep.
- **Could** — polish. Nice-to-have, not required.

Each finding references the file:line where the change should land. Screenshots referenced live under `.design/techpulse-frontend/screenshots/`. The capture command at the bottom regenerates them.

---

## 1. What the redesign was supposed to fix

The previous DESIGN_REVIEW identified 17 findings, most of which were anchored to the Broadsheet Terminal aesthetic. The Atelier + Mission Control redesign is a wholesale visual reset, so those findings are reframed below as **status** rather than open items:

| Old finding (Broadsheet)                                          | Status after redesign                                                                               |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Fraunces italic in masthead read as "newspaper", not "AI"         | **Closed** — masthead now sets in Geist via `font-display` utility update (Phase A).                |
| Bracket-frame chrome (`[ saved ]`, `[+ save ]`) felt skeuomorphic | **Closed** — replaced with clean rounded-pill buttons (`Save` / `Saved`) in Phase D.                |
| Card edges had heavy `border-t-2 border-foreground` slabs         | **Closed** — `LeadStoryCard` lost the top slab and the footer thick rule (Phase D).                 |
| `NewsCard` top hairline made the grid feel like a list, not cards | **Closed** — cards now sit on `bg-[var(--background-tint)]` with hover-only `--rule` border.        |
| `editorial-drop` Fraunces drop-cap inside news cards was loud     | **Closed** — drop-cap removed from cards. It survives in `MarkdownReport` only, where it earns it.  |
| First-load home was a 96 px Fraunces wordmark cover               | **Closed** — replaced with the Atelier conversational hero (Phase C).                               |
| No surfaced "agents at work" signal anywhere in the UI            | **Closed** — Mission Control's `AgentTelemetry` rail shows live count + ticks (Phase E).            |
| Color signal was oxblood ink — read as warning, not "live"        | **Closed** — accent is now electric indigo (light) / electric cyan (dark), reads as energetic AI.   |
| No way to switch between casual reading and dense scanning        | **Closed** — `ModeToggle` in the masthead persists the choice (Phase B).                            |

Items that were NOT design-anchored survive the redesign and are tracked below.

---

## 2. New findings — Atelier home

### 2.1 Must — none observed.

### 2.2 Should

**[S-1] — Resolved.** The integer + `stories overnight` phrase is now a button (`data-testid="atelier-hero-count"`) that calls `onBrowseFeed()`. Greeting also memoized at mount (also closes [C-1]). Fixed in `frontend/src/components/atelier/AtelierHero.tsx`.

**[S-2] — Resolved.** Code comment added at the grid-config site noting the 1-col fallback under `md` is intentional under the desktop-only project direction. A future mobile pass should rebuild against real mobile mockups rather than re-using these tokens.

### 2.3 Could

**[C-1] — Resolved alongside S-1.** Greeting is now memoized at mount.

**[C-2] — Resolved.** `App.tsx`'s `onBrowseFeed` now accepts `(topic?: string)`. `WelcomeScreen.handleOpenFeed` threads the digest topic through, and the host seeds `selectedCategories` with `[topic]` before switching to the feed tab. Digest card → topic-filtered feed now works in one click.

---

## 3. New findings — Atelier feed

### 3.1 Must

**[M-1] — Resolved.** `LeadStoryCard`'s image wrapper now uses `rounded-lg` so the inner radius matches the outer card. Fixed in `frontend/src/components/LeadStoryCard.tsx:133`.

### 3.2 Should

**[S-3] — Resolved.** Compact rows now sit on `bg-[var(--background-tint)]/60` with rounded hover, matching the Detailed-view card idiom. Hairline dividers retired. Fixed in `frontend/src/App.tsx:876-913`.

**[S-4] — Resolved.** `globals.css` adds an `[data-slot="card"] .text-gray-500 { color: var(--foreground-soft); }` override so the source span reads at the correct contrast on warm paper. The class survives in the DOM so `e2e/news-feed.spec.ts`'s `[data-slot="card"] .text-gray-500` locator still resolves.

### 3.3 Could

**[C-3] — Resolved.** Cards now show the lead chip in full followed by `· +N` for the remainder, with the overflow count exposed via `aria-label`. Applied to both `LeadStoryCard` and `NewsCard` footers.

---

## 4. New findings — Mission Control feed

### 4.1 Must

**[M-2] — Resolved.** Title column now uses `minmax(260px, 1fr)`, so on 1280–1440 px viewports the title stays readable before truncation. Fixed in `frontend/src/components/mission/DenseArticleRow.tsx:71`.

### 4.2 Should

**[S-5] — Resolved.** The "Recent ticks" block now only mounts after the first event arrives, so a cold tab no longer shows "no events yet". The aria-live container survives outside the conditional, so screen readers still announce the first tick the moment it lands.

**[S-6]** `inferSubagent()` is a string-match heuristic; on rare sources it always falls back to `feed-ingest`. Once the backend ships the `surfaced_by` column (REDESIGN_PLAN §5.3), delete the heuristic.

- File: `frontend/src/components/mission/DenseArticleRow.tsx:23-31`

### 4.3 Could

**[C-4] — Resolved.** `DenseArticleRow` confidence is now `--foreground-soft` by default; amber is reserved as an actual warning, escalated only when the confidence reading drops below 60%. The indigo subagent label is now the loudest color in the row, which is the intended hierarchy.

---

## 5. New findings — Research

### 5.1 Should

**[S-7] — Resolved.** Bumped `.editorial-drop { line-height: 1.7 }` both in the global Tailwind layer and inside `.research-report` scope, so the Fraunces drop-cap descender no longer crowds the Geist body line.

**[S-8] — Resolved.** All bracket-framed `[ … ]` affordances in ResearchMode are scrubbed: Retry / Cancel / Save / Copy / Download / Research-submit / follow-up chips now use clean labels with mono uppercase-eyebrow type and rounded borders, matching the Atelier pill idiom. Keyboard hints (⌃S, ⌃C, ⌃D, ⌃X, ⏎) are preserved but rendered in a muted secondary color rather than as terminal brackets.

---

## 6. What works (post-redesign)

- The masthead toggle is discoverable but unobtrusive. Mode flips are instant because `data-mode` lives on `<html>` and CSS variables cascade.
- The Atelier hero's data-driven story count makes the AI's work concrete. "I read 163 stories overnight" reads as a colleague rather than a tool.
- Mission Control's telemetry rail feels alive when a research dispatch is running. The pulsing dot + count banner is the cheapest possible "agents at work" cue.
- The token swap (Phase A) gave us 70 % of the visual goal for free — every component that used `font-display` automatically modernized.
- `WelcomeScreen` keeping its name + prop contract meant zero `App.tsx` plumbing churn and zero Playwright spec rewrites.

---

## 7. How to regenerate screenshots + re-run E2E

From `frontend/`, on Windows because the dev server + Playwright `headless: false` are pinned to local:

```powershell
# 1. Atelier-mode capture, all routes, desktop-1280 only
npx playwright test e2e/design-review-capture.spec.ts --grep "desktop-1280"

# 2. Mission-mode capture, all routes, desktop-1280 only
npx playwright test e2e/design-review-capture-mission.spec.ts --grep "desktop-1280"

# 3. Both modes back-to-back (desktop only) — full design-review set
npx playwright test e2e/design-review-capture.spec.ts e2e/design-review-capture-mission.spec.ts --grep "desktop-1280"

# 4. New redesign specs
npx playwright test e2e/mode-toggle.spec.ts e2e/atelier-home.spec.ts e2e/mission-feed.spec.ts

# 5. Contract regression — existing 35+ specs
npx playwright test e2e/news-feed.spec.ts e2e/research.spec.ts e2e/digest.spec.ts e2e/knowledge-graph.spec.ts e2e/saved-research.spec.ts e2e/settings.spec.ts

# 6. Production smoke (against the live deploy)
npx playwright test e2e/prod-smoke.spec.ts e2e/prod-research.spec.ts
```

Atelier shots land at `.design/techpulse-frontend/screenshots/review-{slug}-{bp}.png`; Mission shots at `review-mission-{slug}-{bp}.png` so the two sets sit side by side without overwriting each other. Mission mode is forced via `localStorage.techpulse_mode = "mission"` in an `addInitScript`, so the first paint is already in Mission Control — no toggle click, no flash of Atelier.

---

## 8. Open items rolled forward from REDESIGN_PLAN

- `articles.surfaced_by` backend column + migration (REDESIGN_PLAN §5.3) — unblocks deleting `inferSubagent()`.
- `QuickFacets` vertical filter column for Mission Control — deferred from Phase E.
- ~~Category deep-link wiring for `AgentDigestCard` clicks~~ — **shipped** as C-2 (`App.tsx` + `WelcomeScreen.tsx`).
- ~~A `--mode=mission` capture spec to round out the screenshot set.~~ — **shipped** as `e2e/design-review-capture-mission.spec.ts`.
