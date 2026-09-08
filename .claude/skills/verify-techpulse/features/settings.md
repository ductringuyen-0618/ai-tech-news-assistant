# Settings and preferences

A reader tells the desk which topics they care about and how they want it to look. Category preferences filter the feed and persist on the server. Theme and density are per-browser choices that take effect immediately and survive a reload.

## Sub-features

- `settings-categories` ticks topic categories and saves them.
- `settings-persist` keeps saved categories across a reload and a fresh browser session.
- `settings-feed-effect` narrows the news feed to the saved categories.
- `settings-theme` switches dark and light.
- `settings-density` switches compact and comfortable.

## How to get to it (user POV)

- Sidebar tab `Settings`, which pushes `/settings`. The path `/preferences` is an alias for the same view.
- Direct URL `http://localhost:3000/settings`.
- The theme control also sits at the bottom of the sidebar as `getByTestId("theme-toggle")`, reachable from every view.

## Driving it with the harness

Preconditions: backend up, frontend on 3000, doctor exit 0. Categories round-trip through the server, so capture the starting value and restore it in cleanup.

- `settings-categories`. Capture the current server state first.
  ```powershell
  $b = "http://127.0.0.1:8000"
  $before = Invoke-RestMethod "$b/api/settings/"
  $before | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 "$EVIDENCE/settings-before.json"
  ```
  In the UI, find the label containing `Hardware`, click its `button[role="checkbox"]`, then click `getByRole("button", { name: /Save Preferences/i })`.
  Observable result: `aria-checked` on that checkbox becomes `true` and the toast `Preferences saved successfully` appears. Prove the write through the server: `Invoke-RestMethod "$b/api/settings/"` now lists the category.

- `settings-persist`. Reload the page, then reopen Settings.
  Observable result: the checkbox is still ticked. Repeat in a fresh browser context to prove the value came from the server rather than local storage.

- `settings-feed-effect`. Open the `News Feed` tab.
  Observable result: `getByTestId("news-feed-active-filters")` lists the saved categories and the card list holds only matching articles. An empty list here is a legitimate outcome when no ingested article carries that category. Confirm with `GET /api/news/?category=Hardware` before calling it a bug.

- `settings-theme`. Click `getByTestId("settings-theme-light")`, or `getByTestId("theme-toggle")` from the sidebar.
  Observable result: the `html` element loses the `dark` class and `localStorage.techpulse-theme` reads `light`. Capture a screenshot in each theme.

- `settings-density`. Click `getByTestId("settings-density-compact")`.
  Observable result: the density radio reflects the choice and it survives a reload. This one is local storage only and never reaches the server.

Scripted equivalent:

```powershell
Push-Location frontend
$env:PLAYWRIGHT_SLOW_MO = "0"
npx playwright test e2e/settings.spec.ts
```

Cleanup for this feature:

```powershell
Invoke-RestMethod -Method Put -Uri "$b/api/settings/" -ContentType "application/json" `
  -Body (Get-Content "$EVIDENCE/settings-before.json" -Raw)
```

## Gotchas

- `PUT /api/settings/` is instance-wide, not per user. A drive that leaves categories changed alters what every other viewer of that backend sees, and it silently empties their feed. Always restore.
- The `Save Preferences` button renders only when at least one category is ticked. Untick everything and the control disappears rather than saving an empty set.
- When the backend is unreachable the settings view falls back to `localStorage.techpulse_categories` and logs a console warning instead of failing visibly. A reload can therefore look like it persisted when nothing reached the server. Read the server value.
- Theme and density bootstrap from local storage before React mounts, so a fresh browser profile starts dark and Atelier regardless of what the server holds.
- Density is browser-local. Do not assert it through any HTTP call.
