# Research a topic

A reader asks the desk a question in plain language and watches it work. The answer streams back over SSE as a sequence of named phases, then a report with numbered citations that jump to their sources. The run can be cancelled mid-flight, and a failed run offers a retry.

## Sub-features

- `research-submit` sends a question and starts a run.
- `research-phases` advances the phase chips as the agent works.
- `research-report` renders the streamed report body, including markdown tables.
- `research-citations` links inline markers to numbered source anchors.
- `research-cancel` stops a run in flight.
- `research-error` surfaces a failure with a retry control.
- `research-followups` offers follow-up question chips after a report lands.
- `research-single-flight` rejects a second concurrent run.

## How to get to it (user POV)

- Sidebar tab `Research`, which pushes `/research`.
- Direct URL `http://localhost:3000/research`.
- The Atelier hero CTA `Research a topic` on `/`.
- A suggested-query chip on the empty research panel, which submits on click.

## Driving it with the harness

Preconditions: backend up, frontend on 3000. A real run needs the doctor's `summarization` check green, meaning Ollama answers at `OLLAMA_HOST` with the configured model pulled, or `DEFAULT_LLM_PROVIDER=groq` with a valid key. Without that gate, drive the mocked paths only and report the live ones as skipped.

- `research-submit`. Fill `getByPlaceholder(/ask the desk/i)` and click `getByRole("button", { name: /^Research$/i })`.
  Observable result: the submit control disables, `getByTestId("research-cancel-btn")` appears, and the first `getByTestId("research-phase-chip")` renders.

- `research-phases`. Watch the chips' `data-state` attribute.
  Observable result: state advances through the run and reaches `ready`. Capture the chip states at two points in time, not just the final one, so the evidence shows movement.

- `research-report`.
  Observable result: `getByTestId("research-report-body")` grows past a few hundred characters and `getByTestId("research-report-card")` renders. Assert length and structure, never specific wording; the model output differs every run.

- `research-citations`. Click an `a.citation[href^="#source-"]` marker.
  Observable result: the matching `#source-N` anchor scrolls into view.

- `research-cancel`. Start a run, then click `getByTestId("research-cancel-btn")` before it completes.
  Observable result: the phase chips stop advancing and the submit control re-enables.

- `research-error`. Route `/api/research` to a failure with the browser or a Playwright route mock, then submit.
  Observable result: `getByTestId("research-error-panel")` shows the error text and `getByTestId("research-retry-btn")` is clickable.

- `research-followups`.
  Observable result: `getByTestId("research-follow-ups")` renders `getByTestId("research-follow-up-chip")` entries. Clicking one submits it as the next question.

- `research-single-flight`. While one run is streaming, `POST /api/research` again over HTTP.
  Observable result: HTTP 429. The gate is per process, so restarting the backend clears it.

Scripted equivalent, mocked and safe to run without an LLM:

```powershell
Push-Location frontend
$env:PLAYWRIGHT_SLOW_MO = "0"
npx playwright test e2e/research.spec.ts --grep-invert "real Ollama"
```

## Gotchas

- `research.spec.ts` test 5 is a real Ollama run with a 150 second budget and it sits inside the default suite. A bare `npx playwright test` will hang there on a machine with no Ollama. Exclude it or start Ollama.
- `research.live.spec.ts` documents `--config playwright.live.config.ts`, and that config file does not exist. The main config also excludes `**/*.live.spec.ts` via `testIgnore`, which `--grep @live` does not lift. There is currently no working invocation for that file. Do not report it as run.
- Only one research run exists per backend process. A second concurrent drive gets 429, which looks like a failure but is the designed gate.
- `RESEARCH_ENABLED` is read straight from the environment. When it is falsy the route returns 503 before any of the above applies.
- A live run spends real money when `DEFAULT_LLM_PROVIDER=groq`. Prefer the mocked paths unless the change under test is the agent itself.
- `research-copy-btn`, `research-download-btn`, the citation hover card and the recent-dispatches panel exist in the component and are covered by no spec. Drive them by testid if a change touches them.
