---
name: verify-feature
description: Use when a new feature, UI change, or user-facing behavior was just implemented in the AI Tech News Assistant and needs verifying before calling it done, or when asked to comprehensively test the app, exercise every button/tab/control on the site, or confirm nothing broke — rather than spot-checking one happy path.
---

# Verify a feature (full loop + exhaustive UI sweep)

Two gates, in order. Skipping straight to the second without the first
wastes time chasing a UI bug that's actually a backend regression the fast
loop would have caught in seconds.

1. **Baseline gate** — the project's full verification loop (backend +
   frontend + app-level e2e). Fast-ish, deterministic, catches build/type/
   lint/test regressions.
2. **UI sweep** — click every interactive element on every tab, not just
   the ones the feature touched. Slower, coarser, catches "I added a
   button whose handler throws" and "this new modal traps focus" class
   bugs that a scenario spec testing only the new flow would miss.

## Relationship to test-app-e2e

`.claude/skills/test-app-e2e` already exists in this repo. It is a
black-box HTTP smoke test of the backend/pipeline contract (with optional
"does the frontend's HTML load") that dispatches a fixer agent per
failure. Its own SKILL.md says explicitly: "For pure UI/visual checks —
the runner only confirms HTML loads, not layout" is a case where it does
NOT apply. It never clicks anything.

This skill is the complement, not a replacement: use `test-app-e2e` for
backend/API contract regressions with auto-fix, use this skill for "does
every control on the page I just touched (and its neighbors) actually
work." For a large feature touching both layers, run both — `test-app-e2e`
first (auto-fixes backend issues), then this skill's UI sweep against the
now-working backend.

## Step 1 — Baseline gate: run the full verification loop

Backend (`cd backend`, using the project's own venv — a bare `python` on
PATH does NOT have this repo's deps installed):

```
venv\Scripts\python.exe -m pytest tests -q -m "not slow and not integration"
venv\Scripts\python.exe -m black --check src tests
venv\Scripts\python.exe -m isort --check src tests
venv\Scripts\python.exe -m mypy . --ignore-missing-imports   # non-blocking, report only
```

Frontend (`cd frontend`):

```
npm run verify    # chains: typecheck -> lint -> format:check -> build
```

Full app, boot-and-e2e (`repo root`, PowerShell):

```
powershell -ExecutionPolicy Bypass -File .\verify.ps1
```

`verify.ps1` builds the frontend, smoke-imports the backend, boots both
on :8000 / :3000, curls `/api/health` and `/api/news/`, then runs the
Playwright functional suite (everything except `visual.baseline` and
`@exhaustive`, see Step 2) and cleans up after itself. If port 3000 is
already taken by something outside this repo, pass
`-FrontendPort <free-port>` — it threads through the boot, the health
check, and `playwright.config.ts`'s `PLAYWRIGHT_BASE_URL` override, and
scopes the cleanup step's process kill to that port so it can't kill an
unrelated process. Never kill a process on a contested port without
confirming it isn't someone else's — pick a different port instead.

**Gate rule:** compare against the state before your change. Pre-existing
failures your change didn't touch are not a blocker (this repo has some —
check whether the failure is new by re-running against `git stash` if
unsure). Any *new* failure introduced by your change is a blocker — fix
it before moving to Step 2.

## Step 2 — Exhaustive UI sweep

**Vehicle: Playwright.** It's already this project's e2e harness
(`frontend/e2e/*.spec.ts`, chromium via `npx playwright install
chromium`, `playwright.config.ts` wired to the dev server). Don't reach
for a different tool.

**Existing specs do NOT already cover this.** `frontend/e2e/*.spec.ts`
(news-feed, digest, research, saved-research, settings, sidebar,
mode-toggle, m3-demo, design-review-capture, ...) are scenario specs —
each exercises one named flow end-to-end. None of them enumerate "every
clickable thing on this page" — a new button can ship with zero coverage
and every existing spec stays green.

`frontend/e2e/exhaustive-click-sweep.spec.ts` fills that gap: it
discovers every tab from the live `role="tablist"` (not a hardcoded
list, so a newly added tab is covered automatically), and within each tab
clicks every visible `button`, `a[href]`, `[role=button/tab/switch/
checkbox/menuitem]`, `input`, `select`, and `textarea`, watching for
uncaught page errors and `console.error`. It's tagged `@exhaustive` and
excluded from `verify.ps1`'s default run (too slow for the fast loop) —
run it explicitly:

```
cd frontend
npx playwright test exhaustive-click-sweep --grep "@exhaustive"
```

Requires the backend (`:8000`) and frontend (`:3000`) already running —
boot them the same way `verify.ps1` does, or run `verify.ps1` first and
keep the servers up by commenting out its Cleanup section temporarily
(don't leave that commented out — revert after).

**When you added a new page/tab/major control**, extend
`exhaustive-click-sweep.spec.ts` rather than writing a one-off script:
tabs are discovered live so a new tab needs no changes; a destructive new
action (delete/remove/clear/sign-out-shaped) needs a `DENYLIST` entry so
the sweep skips it instead of firing it for real — read the file's own
header comment before editing, it documents the denylist and the known
stale-element limitation (an early click that mutates the DOM can make a
later element in the same tab go stale and throw on click — that's
reported as a failure but isn't automatically a real bug; triage by hand,
e.g. re-run scoped to just that tab).

**Read every reported failure before dismissing it.** A failure means
either: a real bug (fix it, or hand off same as any other test failure),
or a false positive from DOM mutation (note it, consider narrowing the
sweep or adding a short wait). Don't blanket-suppress console.error to
make the sweep pass — that hides the exact class of bug this exists to
catch.

## Step 3 — Report

State plainly, for both gates: what ran, what passed, what's new-broken
vs. pre-existing, and — for the UI sweep — which controls were clicked
(the spec logs a JSON report per tab: `ok` list and `failed` list) and
which need human triage because they're ambiguous rather than clearly
broken.
