# Read the news feed

The feed is the front door. A reader opens it to see what the desk pulled overnight, scans a lead story and a run of cards, then narrows by search, a trending chip or a category. Two display modes exist: Atelier, the calm editorial layout, and Mission, a dense telemetry layout over the same articles.

## Sub-features

- `feed-render` shows a lead story and article cards from real ingested sources.
- `feed-search` narrows the list by free text.
- `feed-trending` narrows by a trending chip, which writes an active-filter pill.
- `feed-categories` narrows by the categories saved in Settings.
- `feed-reset` clears every active filter and restores the full list.
- `feed-mode` swaps between Atelier cards and Mission dense rows.

## How to get to it (user POV)

- Sidebar tab `News Feed`, which pushes `/feed`.
- Direct URL `http://localhost:3000/feed`.
- The Atelier hero CTA `Read today's brief` on `/`.
- A digest card on the home grid, which lands on the feed pre-filtered by that topic.

## Driving it with the harness

Preconditions: backend up, frontend on 3000, `doctor.py --require-articles` exit 0. The feed reads live RSS content, so assert shape and non-emptiness, never specific headlines.

- `feed-render`. Navigate to `http://localhost:3000/feed`, wait for `.animate-spin` to clear, then read the page.
  Observable result: the masthead pill reads `[ N today ]` with N greater than zero, and the accessibility tree lists article cards, each carrying a source name, a relative date and a title. `getByTestId("news-feed-list")` is present.
  Cross-check the same numbers through HTTP: `(Invoke-RestMethod "$b/api/news/?page_size=5").data` returns five items whose titles match what the page shows.

- `feed-search`. Fill `getByPlaceholder(/search tech news/i)` with a word taken from a title the page already shows, not an invented one.
  Observable result: the card count drops and every remaining title or summary contains the term.

- `feed-trending`. Click a `getByTestId("news-feed-trending-chip")` inside `getByTestId("news-feed-trending-rail")`.
  Observable result: `getByTestId("news-feed-active-filters")` gains a pill naming the chip's `data-category`, and the list narrows.

- `feed-categories`. Tick a category in Settings, save, return to the feed. Recipe in [settings.md](./settings.md).
  Observable result: the active-filter row lists the saved categories and the list holds only articles carrying one of them.

- `feed-reset`. Click `getByRole("button", { name: /^Reset Filters$/i })` from the empty state, or `/^Clear Filters$/i` from the filter row.
  Observable result: the active-filter row empties and the full card list returns. This is the single fastest way to tell a filtered feed from a broken one.

- `feed-mode`. Click `getByTestId("mode-toggle-mission")` in the masthead.
  Observable result: `html[data-mode]` becomes `mission`, `getByTestId("mission-shell")` and `getByTestId("agent-telemetry")` mount, and articles render as `getByTestId("dense-article-row")`. Clicking `mode-toggle-atelier` restores `news-feed-list`.

Scripted equivalent for the render and filter paths:

```powershell
Push-Location frontend
$env:PLAYWRIGHT_SLOW_MO = "0"
npx playwright test e2e/news-feed.spec.ts e2e/mission-feed.spec.ts
```

## Gotchas

- `getByTestId("news-feed-list")` is on the empty state too. Its presence proves the panel mounted, not that any article rendered. Count cards.
- An empty feed on a populated backend is usually saved category preferences, not a bug. Those persist in `localStorage.techpulse_categories` and survive a reload and a restart. Clear the filters before concluding anything, and check the `[ N today ]` pill: a non-zero N with an empty list is a filter, a zero N is a data problem.
- The card testids `news-card`, `news-card-lead`, `news-card-save-btn` and `news-card-read-more` exist in the components but no bundled spec uses them. They are safe handles and better than the `[data-slot="card"]` selectors the older specs rely on.
- The UI calls `http://localhost:8000` unless `VITE_API_BASE_URL` is set. A backend on another port leaves the feed empty with `ERR_CONNECTION_REFUSED` in the console and a "Failed to fetch articles" toast.
- Every backend-down path calls `console.error`, so the suite's `assertConsoleClean` rubric fails for that reason alone. Read the console before blaming the assertion.
- `/api/news/front-page` composes what the feed shows and is covered by no existing test. Calling it with `recompute=true` writes a snapshot row.
