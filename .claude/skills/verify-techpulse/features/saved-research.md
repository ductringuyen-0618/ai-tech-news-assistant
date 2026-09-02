# Saved research

A reader who liked a research report saves it, then finds it later under Saved. The list holds the question and the report, opens one on click, backs out to the list, and deletes on demand. Saved reports live on the server, not in the browser, so they survive a different machine.

## Sub-features

- `saved-create` saves the current research report.
- `saved-list` lists saved reports newest first.
- `saved-open` opens one report in full.
- `saved-back` returns from a report to the list.
- `saved-delete` removes one report permanently.
- `saved-empty` shows the empty state when nothing is saved.

## How to get to it (user POV)

- Sidebar tab `Saved`, which pushes `/saved`.
- Direct URL `http://localhost:3000/saved`.
- The save control on a completed research report, `getByTestId("research-save-btn")`.

## Driving it with the harness

Preconditions: backend up, frontend on 3000, doctor exit 0. Saving needs a report on screen, which needs either a live research run or a mocked stream. The mocked path is the cheap one and proves the same persistence.

- `saved-create`. With a report rendered on `/research`, click `getByTestId("research-save-btn")`.
  Observable result: the button reflects the saved state. Prove the write through the read path, not the button:
  ```powershell
  (Invoke-RestMethod "http://127.0.0.1:8000/api/saved-research").Count
  ```
  The count rises by one and the newest entry carries the question you asked.

- `saved-list`. Open the `Saved` tab with `getByRole("tab", { name: "Saved", exact: true })`.
  Observable result: `getByTestId("saved-research-list")` renders one `getByTestId("saved-research-item")` per saved report, newest first.

- `saved-open`. Click an item.
  Observable result: `getByTestId("saved-research-detail")` renders the full report body for that question.

- `saved-back`. Click `getByTestId("saved-research-back-btn")`.
  Observable result: the detail unmounts and the list returns with the same items.

- `saved-delete`. Click `getByTestId("saved-research-delete-btn")`, whose accessible name is `Delete saved research: <question>`.
  Observable result: the item leaves the list, and `GET /api/saved-research` returns one fewer row. This is irreversible on that instance.

- `saved-empty`. On an instance with nothing saved, open the Saved tab.
  Observable result: `getByTestId("saved-research-empty")` renders with the text `No saved research yet`.

Scripted equivalent, fully mocked:

```powershell
Push-Location frontend
$env:PLAYWRIGHT_SLOW_MO = "0"
npx playwright test e2e/saved-research.spec.ts
```

## Gotchas

- Every bundled saved-research test mocks the backend. None of them proves the row reaches the database. Verify persistence over HTTP as shown above, or the coverage is an illusion.
- The backend seeds saved-research rows on first boot against an empty table, so a fresh instance is not empty. Read `GET /api/saved-research` before driving `saved-empty` rather than assuming a new database is blank.
- The store evicts the oldest row once it holds 100. A long-lived instance silently loses the earliest saves.
- `DELETE /api/saved-research/{id}` has no undo. Delete only rows this run created.
- Saved rows live in the same SQLite file as everything else, so they follow whatever `SQLITE_DATABASE_PATH` the instance launched with. Two instances on different files see different saved lists.
