# TechPulse — Atelier + Mission Control Redesign Plan

> Decision: drop the Broadsheet Terminal aesthetic.
> Ship Atelier as the default surface (first impression, casual reading).
> Ship Mission Control as a power-user mode (research, dense scanning).
> A single header toggle flips between them; the choice persists in localStorage.

Owner: Tri
Status: planning → implementation
Last updated: 2026-05-18

---

## 0. Why both, not one

A news-aggregator that hides its agents reads like any other RSS feed. A news-aggregator that only shows telemetry feels like ops software. The pair solves both:

| Surface          | Job                                                   | Density | Mood                    |
| ---------------- | ----------------------------------------------------- | ------- | ----------------------- |
| Atelier          | "What did my AI desk pull together overnight?"        | Low     | Calm, confident, modern |
| Mission Control  | "Show me everything, with provenance, in one screen." | High    | Working, alive, precise |

Both surfaces share the same data, the same routes (`/`, `/feed`, `/research`, `/knowledge`, `/digest`, `/saved`), and the same components underneath. Only the layout chrome + visual weight change.

---

## 1. Design tokens (`frontend/src/styles/globals.css`)

Retire the Broadsheet Terminal palette/typography. Replace with two token sets that share semantic names so component code does not change.

### 1.1 Palette — Atelier (default)

Warm off-white paper, near-black ink, single electric accent. Closer to Linear / Vercel / Arc than to a broadsheet.

```css
:root {
  /* surfaces */
  --background:       oklch(0.985 0.003 95);   /* warm paper */
  --background-tint:  oklch(0.965 0.004 95);   /* card surface */
  --background-deep:  oklch(0.93  0.005 95);   /* nav strip / footers */

  /* ink */
  --foreground:       oklch(0.16  0.01 260);   /* near-black w/ blue cast */
  --foreground-soft:  oklch(0.42  0.01 260);   /* secondary */
  --foreground-mute:  oklch(0.62  0.01 260);   /* tertiary / captions */

  /* structure */
  --rule:             oklch(0.88  0.005 260);  /* hairlines */
  --rule-strong:      oklch(0.78  0.005 260);

  /* accents */
  --accent-signal:    oklch(0.62  0.22 264);   /* electric indigo — agents live */
  --accent-signal-bg: oklch(0.94  0.04 264);
  --accent-warm:      oklch(0.70  0.16 56);    /* warm amber — confidence */
  --accent-soft:      oklch(0.78  0.10 178);   /* teal — info / muted state */
}
```

### 1.2 Palette — Atelier dark

```css
.dark {
  --background:       oklch(0.15  0.012 264);  /* deep cobalt */
  --background-tint:  oklch(0.20  0.014 264);
  --background-deep:  oklch(0.11  0.010 264);

  --foreground:       oklch(0.96  0.005 95);
  --foreground-soft:  oklch(0.74  0.008 95);
  --foreground-mute:  oklch(0.56  0.010 95);

  --rule:             oklch(0.28  0.012 264);
  --rule-strong:      oklch(0.38  0.012 264);

  --accent-signal:    oklch(0.78  0.18 230);   /* electric cyan */
  --accent-signal-bg: oklch(0.32  0.10 230);
  --accent-warm:      oklch(0.80  0.16 70);
  --accent-soft:      oklch(0.74  0.12 178);
}
```

### 1.3 Mission Control overrides

When `<html data-mode="mission">` is set, layer dense-mode tokens on top — colder background, brighter accent, tighter rhythm.

```css
[data-mode="mission"] {
  --background:       oklch(0.97 0.003 250);
  --background-tint:  oklch(0.94 0.004 250);
  --rule:             oklch(0.82 0.006 250);
  --accent-signal:    oklch(0.55 0.24 264);    /* deeper indigo */
  --accent-warm:      oklch(0.68 0.18 56);
}
[data-mode="mission"].dark,
.dark[data-mode="mission"] {
  --background:       oklch(0.09 0.010 264);   /* near-black ops */
  --background-tint:  oklch(0.14 0.012 264);
  --rule:             oklch(0.24 0.012 264);
  --accent-signal:    oklch(0.82 0.18 220);    /* sharper cyan */
  --accent-warm:      oklch(0.82 0.16 72);
}
```

### 1.4 Typography

Stop pretending we're a newspaper. Three faces, no italic display:

- **Display + UI**: `Geist` (with `Inter` fallback) — confident modern sans, optical sizing at hero scale.
- **Mono / data**: `IBM Plex Mono` — keep; reads well in tight rails.
- **Editorial moments** (citations, drop-caps inside the research report only): `Fraunces` — used sparingly, not for nav or hero.

```css
body {
  font-family: 'Geist', 'Inter', system-ui, -apple-system, sans-serif;
  font-feature-settings: "ss01", "cv11";
  font-size: 15px;
  line-height: 1.55;
}

.display { font-family: 'Geist', 'Inter', sans-serif; letter-spacing: -0.025em; }
.mono, code, [data-mono] { font-family: 'IBM Plex Mono', ui-monospace, monospace; }
.editorial { font-family: 'Fraunces', 'Times New Roman', serif; }
```

Type scale:

| Token     | Atelier | Mission |
| --------- | ------- | ------- |
| hero      | 44 px   | 24 px   |
| display   | 28 px   | 18 px   |
| body      | 15 px   | 13 px   |
| caption   | 12 px   | 11 px   |
| mono data | 12 px   | 11 px   |

### 1.5 Motion

- Hover/focus: 120 ms ease-out
- Mode flip: 240 ms layout cross-fade
- Agent telemetry pulse: 2 s ease-in-out (respect `prefers-reduced-motion`)
- Streaming token reveal: keep existing 16 ms tick (no change)

---

## 2. Mode infrastructure

### 2.1 New context: `frontend/src/components/ModeProvider.tsx`

Wrap `AppShell` similar to `ThemeProvider`. Exposes `mode: 'atelier' | 'mission'` and `setMode`. Persists to `localStorage.techpulse_mode`. Mirrors the value onto `<html data-mode="...">` so CSS variables can switch without re-rendering React.

Default value: `atelier`.

Inline bootstrap in `index.html` (same pattern as the existing dark-mode bootstrap) so first paint already has the right palette:

```html
<script>
  try {
    var m = localStorage.getItem('techpulse_mode') || 'atelier';
    document.documentElement.setAttribute('data-mode', m);
  } catch (e) { document.documentElement.setAttribute('data-mode', 'atelier'); }
</script>
```

### 2.2 Mode toggle in the masthead

New component `frontend/src/components/ModeToggle.tsx`. Rendered top-right of the existing `<header>` inside `App.tsx`. Two-pill segmented control:

```
[ Atelier  ·  Mission ]
```

Active pill carries `bg-foreground text-background`. Title attribute explains the difference on hover.

---

## 3. Atelier surface

### 3.1 New components

| Path                                              | Purpose                                                                     |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| `frontend/src/components/atelier/AtelierShell.tsx`| Wraps page content with the atelier max-width container + softer header.    |
| `frontend/src/components/atelier/AtelierHero.tsx` | "I read N stories overnight…" hero + two CTA pills.                         |
| `frontend/src/components/atelier/AgentDigestCard.tsx` | 2×2 grid card showing a category's AI take + 3 headline links.          |
| `frontend/src/components/atelier/MorningBriefRail.tsx`| Right-rail "What changed since you last looked" — concise diff feed.    |

### 3.2 Home (`/`) rewrite

Replace the current `WelcomeScreen` with `AtelierHero` + 4 `AgentDigestCard`s + (optional) `MorningBriefRail`. The four cards map to top topic clusters from `/api/digest/topics` so the home page is always live data, not static copy.

```
┌─────────────────────────────────────────────────────────────┐
│  TechPulse                       [Atelier · Mission] [☾]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   I read 163 stories overnight.                             │
│   Here's what your desk thinks matters today.               │
│                                                             │
│   [ Read the brief → ]   [ Research a topic ]               │
│                                                             │
│   ─────────────────────────────────────                     │
│                                                             │
│   ┌─────────────┐  ┌─────────────┐                          │
│   │ Foundation  │  │ Infra & GPU │                          │
│   │ models      │  │             │                          │
│   │ • headline  │  │ • headline  │                          │
│   │ • headline  │  │ • headline  │                          │
│   └─────────────┘  └─────────────┘                          │
│   ┌─────────────┐  ┌─────────────┐                          │
│   │ Policy & EU │  │ Apps & dev  │                          │
│   └─────────────┘  └─────────────┘                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Feed (`/feed`) in Atelier mode

The current Lead + Deck + tail grid stays, but:

- `LeadStoryCard`: drop the broadsheet drop-cap. Hero image rounded 8 px, headline in Geist 28 px, byline as mono micro-row beneath.
- `NewsCard`: lose the bracket frames and tick rules. Card surface = `--background-tint`, 1 px `--rule` only on hover.
- Masthead: simplify Row 2. No serif italic, no `Vol III · No. xx`. Just "Today, Mon May 18" left, stat chips right.

### 3.4 Research (`/research`) in Atelier mode

Soften the existing `ResearchMode` chrome. Keep the streamed report, the timeline, the sub-questions. Replace the terminal-style green/cyan with `--accent-signal` and `--accent-warm`. The MarkdownReport itself can lean editorial (Fraunces drop-cap, larger leading) — this is the one place serif still earns its keep.

---

## 4. Mission Control surface

### 4.1 New components

| Path                                                       | Purpose                                                                    |
| ---------------------------------------------------------- | -------------------------------------------------------------------------- |
| `frontend/src/components/mission/MissionShell.tsx`         | 3-col layout: existing Sidebar + center feed + right `AgentTelemetry`.     |
| `frontend/src/components/mission/AgentTelemetry.tsx`       | Live "N agents working" panel, list of recently fired subagents, SSE pulse.|
| `frontend/src/components/mission/DenseArticleRow.tsx`      | Timestamped one-line row: time · source · title · confidence% · subagent.  |
| `frontend/src/components/mission/QuickFacets.tsx`          | Stacked vertical facet column to filter feed in place (no modals).         |

### 4.2 Mission feed layout

```
┌────────────┬─────────────────────────────────────────┬──────────────────┐
│            │ 07:14  Reuters       OpenAI ships…  92% │  3 agents live   │
│  Sidebar   │ 06:58  TechCrunch    Anthropic raise 87%│  ─────────────── │
│  (140 px)  │ 06:42  Bloomberg     EU AI Act…      94%│  ▮ ingest-rss    │
│            │ 06:31  The Verge     Apple silicon…  78%│  ▮ entity-link   │
│            │ ...                                     │  ▮ digest-build  │
│            │                                         │  ─────────────── │
│            │                                         │  Last cycle      │
│            │                                         │  163 stories →   │
│            │                                         │  47 surfaced     │
└────────────┴─────────────────────────────────────────┴──────────────────┘
```

### 4.3 Telemetry data wiring

`AgentTelemetry` listens for the existing `techpulse:research-stream` CustomEvent plus a new `techpulse:agent-event` CustomEvent. The event surface is local for now; we can later wire it to a `/api/agents/events` SSE endpoint without changing the component.

Confidence % per row: backend already stores per-article scores when ranked. For rows without a score, render `—` (em-dash), do not invent.

Which subagent surfaced an article: derived from the existing `articles.source_id` + a small static map (`feed_ingest`, `entity_link`, `topic_cluster`, `editor_pick`). Stored on `articles.surfaced_by` (new column, migration via existing `_ensure_tables_exist`).

---

## 5. Files that change

### 5.1 Modify

- `frontend/src/styles/globals.css` — full token rewrite (§1).
- `frontend/index.html` — add mode bootstrap script (§2.1). Swap font import to Geist + IBM Plex Mono. Keep Fraunces but lazy-load for `/research`.
- `frontend/src/App.tsx` — wrap in `ModeProvider`. Read `mode` from context, switch shell. Masthead simplification.
- `frontend/src/components/Sidebar.tsx` — denser variant when `data-mode=mission`. Active item gets a 2 px left bar instead of full pill.
- `frontend/src/components/LeadStoryCard.tsx` — drop bracket frames + serif italic; Geist headlines; rounded image.
- `frontend/src/components/NewsCard.tsx` — simpler card, no tick-rule decoration.
- `frontend/src/components/WelcomeScreen.tsx` — becomes a thin wrapper that renders `AtelierHero` (kept for back-compat with e2e selectors).
- `frontend/src/components/DigestView.tsx` — re-tune typography to Geist; keep the editorial moments in the daily-summary panel.
- `frontend/src/components/ResearchMode.tsx` — re-skin the timeline + streaming surface to new tokens.
- `frontend/src/components/MarkdownReport.tsx` — keep Fraunces for prose, but tighten line-height + drop the all-caps eyebrows.

### 5.2 Create

- `frontend/src/components/ModeProvider.tsx`
- `frontend/src/components/ModeToggle.tsx`
- `frontend/src/components/atelier/AtelierShell.tsx`
- `frontend/src/components/atelier/AtelierHero.tsx`
- `frontend/src/components/atelier/AgentDigestCard.tsx`
- `frontend/src/components/atelier/MorningBriefRail.tsx`
- `frontend/src/components/mission/MissionShell.tsx`
- `frontend/src/components/mission/AgentTelemetry.tsx`
- `frontend/src/components/mission/DenseArticleRow.tsx`
- `frontend/src/components/mission/QuickFacets.tsx`

### 5.3 Backend (small)

- `backend/src/repositories/article_repository.py` — add `surfaced_by` column via existing `_ensure_tables_exist` ALTER. Default value `feed_ingest`.
- `backend/src/api/news.py` — pass `surfaced_by` through in the article response.

No backend changes required for telemetry pulse; CustomEvent stays in the browser.

---

## 6. E2E compatibility

The 35+ Playwright specs key off **roles and `data-testid`**, not visual styling. Specifically preserved:

- `<h1 aria-label="TechPulse AI">` — kept in both modes.
- `[data-testid="news-feed-list"]`, `[data-testid="news-card"]`, `[data-testid="news-feed-active-filters"]` — kept.
- `role="tab"` / `role="tablist"` / `role="tabpanel"` on Radix Tabs — kept.
- `WelcomeScreen` exports remain; it now renders `AtelierHero`.
- `<a href="#main-content">` skip link — kept.

New required tests:

- `e2e/mode-toggle.spec.ts` — flip Atelier ↔ Mission, assert `<html data-mode>` updates, assert layout changes (telemetry rail appears in Mission).
- `e2e/atelier-home.spec.ts` — `/` renders hero text + 4 digest cards.
- `e2e/mission-feed.spec.ts` — `/feed` in Mission mode renders `DenseArticleRow` + `AgentTelemetry`.

---

## 7. Phased rollout

Each phase is independently shippable. Tests pass at the end of every phase.

### Phase A — Tokens (1 commit)

Files: `globals.css`, `index.html`.

Acceptance: visual change only — typography is Geist, palette is Atelier-light. No layout changes. All existing tests still green.

### Phase B — Mode plumbing (1 commit)

Files: `ModeProvider.tsx`, `ModeToggle.tsx`, `App.tsx` (header).

Acceptance: toggle is visible; flipping it sets `<html data-mode>` and persists to localStorage. No layout changes yet — Mission Control still renders Atelier layout.

### Phase C — Atelier home (1 commit)

Files: `AtelierHero.tsx`, `AgentDigestCard.tsx`, `AtelierShell.tsx`, `WelcomeScreen.tsx` (wrap).

Acceptance: `/` renders the new hero + 4 cards driven by `/api/digest/topics`. Cards link into `/feed?category=…` or `/research?q=…`.

### Phase D — Atelier feed + research polish (1 commit)

Files: `LeadStoryCard.tsx`, `NewsCard.tsx`, `ResearchMode.tsx`, `MarkdownReport.tsx`.

Acceptance: `/feed` and `/research` look like Atelier even when mode=mission (Mission's layout comes in Phase E).

### Phase E — Mission Control (1 commit)

Files: `MissionShell.tsx`, `AgentTelemetry.tsx`, `DenseArticleRow.tsx`, `QuickFacets.tsx`, `App.tsx` (conditional shell), `article_repository.py`, `news.py`.

Acceptance: with mode=mission, `/feed` renders the 3-col dense layout. Telemetry rail pulses on SSE events. Confidence + subagent shown per row.

### Phase F — Verification (1 commit)

- Re-run `design-review-capture.spec.ts` at desktop-1280, both modes.
- Re-run `prod-smoke.spec.ts` and `prod-research.spec.ts`.
- Update `DESIGN_REVIEW.md` with the new screenshots.

---

## 8. Open questions to resolve before Phase E

1. **Confidence score**: do we expose the existing `credibility_score` (currently hardcoded 85), or compute a new per-article confidence from entity overlap + source weight? Phase E ships with the existing field; we can iterate.
2. **`surfaced_by` taxonomy**: starting set is `feed_ingest`, `entity_link`, `topic_cluster`, `editor_pick`. Open to a 5th if research dispatches surface articles too.
3. **Mode default per device**: should we default to Mission on very wide viewports (≥1600 px)? Recommendation: no — let the user choose, then remember.

---

## 9. Out of scope

- Mobile layout. Per the project direction, we are ignoring mobile traffic until further notice. The redesign targets desktop ≥ 1280 px only.
- A 3rd mode ("Kiosk" bento). We rejected it during direction selection; can revisit later.
- New backend endpoints for agent events. Use the existing CustomEvent surface for now.

---

## 10. Risks

- **Geist font load** is a new request. Mitigation: `preconnect` + `font-display: swap`. Fallback to Inter (already on most systems).
- **Two layouts double the surface area for visual bugs.** Mitigation: shared component library underneath both shells; only the chrome diverges.
- **Mode toggle could feel gimmicky if it doesn't change enough.** Mitigation: Mission must show data Atelier hides (confidence, subagent, telemetry). If it ever feels like "same page, smaller text," we cut it.
