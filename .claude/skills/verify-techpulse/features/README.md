# TechPulse verification map

This directory is the maintained source for verifying the user-facing behavior of TechPulse AI. Read this index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Start the backend yourself on `http://127.0.0.1:8000` with `ENVIRONMENT=testing`, per the Launch section of `../SKILL.md`. Never drive an instance you did not start.
- Start the frontend on `http://localhost:3000`. That port is fixed by `frontend/vite.config.ts` and is the only port the Playwright suite and `frontend/src/config/api.ts` agree on.
- Run `python .claude/skills/verify-techpulse/scripts/doctor.py` and require exit 0 before driving anything.
- Treat `WARN` on embeddings or summarization as a scope limit, not a failure. Those two gates decide which features are verifiable at all; each feature file names which gate it needs.
- Set `RUN_ID` once per run and write every artifact under `C:/temp/atn-verify/$RUN_ID/`.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Prefer ARIA roles and accessible names, then `data-testid`. Never drive by coordinates or tab order.
- Treat every command as literal. Keep quoted names, flags and query strings unchanged.
- Drive HTTP with `python .claude/skills/test-app-e2e/scripts/run_e2e.py` or direct requests. Drive the UI with the browser tools or `npx playwright test` from `frontend/`.
- Restore any server-side state a recipe mutates. `PUT /api/settings/` is shared across every viewer of that instance.
- Cleanup removes instances and scratch state. It never removes artifacts under `C:/temp/atn-verify/`.

## Proof and skip reporting

- Capture the user action and the resulting state, not only the final screen.
- Prove a write by reading it back through the user-facing read path, not through the endpoint that performed the write. The two article stores disagree on this app, so a write path's own success message proves nothing.
- UI proof includes the accessibility tree and a screenshot with the masthead visible.
- HTTP proof includes method, URL, status and body.
- Record the feature ID and the entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition. Never report an entry point skipped for a missing gate as verified through a different path.

## Feature entry contract

Each feature file opens with an H1 and one paragraph of user-visible behavior, then exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line each.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with the harness` starts with `Preconditions:` and pairs each user action with an exact command and an observable result.
4. `Gotchas` lists traps that waste or invalidate a run.

## Features

- [Read the news feed](./news-feed.md) covers ingestion landing in the feed, search, trending and category filters, and the two display modes.
- [Ingest and summarize](./ingestion.md) covers the RSS pull, the summarization pass, and the store-agreement check that decides whether anything a user reads is real.
- [Research a topic](./research.md) covers the streamed agentic research report, its phases, citations, cancel and retry.
- [Saved research](./saved-research.md) covers saving a report, listing it, opening it and deleting it.
- [Settings and preferences](./settings.md) covers category preferences, theme and density, and what survives a reload.
