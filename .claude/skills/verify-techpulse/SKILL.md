---
name: verify-techpulse
description: Launch and drive the TechPulse AI news assistant (FastAPI backend plus React web UI) to prove user-facing behavior with captured evidence. Use when a change needs proof it works in the running app, before declaring a feature done, when a bug needs reproducing on the real surface, or when asked to verify, drive, or demo TechPulse locally.
---

# Verify TechPulse

This skill starts the app, decides whether the instance is worth driving, drives one user path, and leaves evidence behind. Read [`features/README.md`](features/README.md) before driving anything. It is the maintained map of what a user can do and what proves each thing works.

Two surfaces. The web UI at `http://localhost:3000` is what a user touches. The FastAPI backend at `http://127.0.0.1:8000` is what the UI reads. Verify the UI when the change is user-visible. Verify HTTP directly when the change is a contract, a store, or a pipeline.

## Launch

Set the run identity first. Every artifact goes under it.

```powershell
$RUN_ID = Get-Date -Format "yyyyMMdd-HHmmss"
$EVIDENCE = "C:/temp/atn-verify/$RUN_ID"
New-Item -ItemType Directory -Force -Path $EVIDENCE | Out-Null
```

**Python environment.** The committed `backend/venv` in the main checkout is dead. Its `pyvenv.cfg` points at `C:\Users\Tri\...`, a profile that no longer exists, so every command through it fails with "did not find executable". Build a throwaway one at a short path instead. Long paths under the agent scratchpad break the numpy install.

```powershell
python -m venv C:\temp\atn-verify-venv
C:\temp\atn-verify-venv\Scripts\python.exe -m pip install --quiet `
  "fastapi==0.104.1" "uvicorn[standard]==0.24.0" "pydantic-settings==2.5.2" `
  python-dotenv python-multipart "httpx==0.27.2" requests numpy feedparser `
  beautifulsoup4 "sqlalchemy==2.0.36" APScheduler structlog
```

That set boots the API and serves news, ingestion, digest, settings, saved research and knowledge graph. `backend/requirements.txt` additionally pulls torch, sentence-transformers, chromadb and langchain, several gigabytes. Install those only when the change under test is embeddings, semantic search or RAG.

**Backend.** Run from `backend/`. Settings load `.env` relative to cwd and every database path default is relative, so a launch from anywhere else silently reads different files.

```powershell
Push-Location backend
$env:ENVIRONMENT = "testing"
$env:SQLITE_DATABASE_PATH = "./data/verify.db"
$env:DATABASE_URL = "sqlite:///./data/verify.db"
C:\temp\atn-verify-venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

All three variables are load-bearing.

`ENVIRONMENT=testing` suppresses the retention cron. Without it the app schedules a live delete against your database 15 seconds after boot.

`SQLITE_DATABASE_PATH` and `DATABASE_URL` must name the same file. The app resolves its database three different ways. The news, search, settings, digest and knowledge-graph routes read `SQLITE_DATABASE_PATH` (default `./data/articles.db`). The ingestion routes write through a SQLAlchemy engine whose default is `sqlite:///./data/ai_news.db`. Under stock defaults ingestion fills one file and the feed reads the other, so the UI shows an empty feed no matter how much you ingest. The doctor checks this on every run.

**Frontend.** Serves on port 3000, fixed by `server.port` in `frontend/vite.config.ts`.

```powershell
Push-Location frontend
npm install
npm run dev
```

Ready when the Vite banner prints `Local: http://localhost:3000/`. The UI calls `http://localhost:8000` unless `VITE_API_BASE_URL` says otherwise, so a backend on any other port leaves every panel empty with `ERR_CONNECTION_REFUSED` in the console.

`.claude/launch.json` targets port 3000, matching `server.port`, and `vite.config.ts` sets `strictPort: true`, so a busy 3000 fails loudly instead of silently falling back to 3001. Check the banner, do not assume.

**Teardown** is in [Cleanup](#cleanup).

## Doctor

One read-only command decides whether the instance is worth driving. Stdlib only, so system Python runs it without the venv.

```powershell
python .claude/skills/verify-techpulse/scripts/doctor.py --require-articles
```

Exit 0 means drive. Exit 1 means stop and fix the named check first. Drop `--require-articles` when verifying an empty-state path.

`ok` on `article_store_agreement` is the check that matters most. It compares what the write path holds against what the read path serves and fails loudly when they diverge.

`WARN` is a scope limit, not a failure. `embeddings` warns when sentence-transformers is absent, which leaves semantic search and the knowledge graph empty. `summarization` warns when neither Ollama nor Groq answers, which leaves summaries, digest text and research empty. Report a feature that needs a warned gate as skipped with the unmet precondition. Never report it as verified.

Do not use `GET /health` for a verdict. It reports `embeddings` and `summarization` as `"available"` unconditionally while `GET /health/detailed` reports both unhealthy on the same instance. The doctor reads the detailed route for this reason.

## Drive

Pick the surface the change is visible on.

**UI.** Drive with the browser tools against `http://localhost:3000`, or run the existing Playwright suite from `frontend/`.

```powershell
Push-Location frontend
$env:PLAYWRIGHT_SLOW_MO = "0"
npx playwright test e2e/news-feed.spec.ts
```

First run needs `npx playwright install chromium`. Prefer ARIA roles and accessible names, then `data-testid`. The six top-level views are `getByRole("tab", { name: /News Feed|Research|Knowledge|Digest|Settings/i })` plus `{ name: "Saved", exact: true }`, because a loose `/Saved/i` also matches the "Unsaved changes" badge. Per-feature handles live in [`features/`](features/README.md).

Three cautions on the bundled suite. A bare `npx playwright test` also runs five specs that hit production at `https://techpulse-ai-phi.vercel.app`, and `research.spec.ts` test 5 makes a real Ollama call with a 150s budget. Name the spec you want. The config runs headed with a 600ms slowMo and video on every test; `PLAYWRIGHT_SLOW_MO=0` is the agent setting. Visual baselines exist only as `*-chromium-win32.png` at 1440x900 and five of the six depend on live database content, so they drift as articles ingest.

**HTTP.** The existing black-box battery covers the contract layer. Reuse it rather than writing new curl chains.

```powershell
python .claude/skills/test-app-e2e/scripts/run_e2e.py --json --out "$EVIDENCE/e2e.json" --skip-frontend
```

It proves route shapes and a settings round-trip. It does not prove `/api/news/front-page`, admin auth, saved research, digest sub-routes, any embeddings route, or research past the first stream event. Drive those directly and add what you prove to the feature map.

## Evidence

Everything lands under `C:/temp/atn-verify/$RUN_ID/`, outside the repo, so a run never dirties the worktree.

```powershell
python .claude/skills/verify-techpulse/scripts/doctor.py --json | Out-File -Encoding utf8 "$EVIDENCE/doctor.json"
Invoke-RestMethod "http://127.0.0.1:8000/api/news/?page_size=5" | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 "$EVIDENCE/news-page1.json"
```

Playwright writes its own artifacts to `C:/temp/playwright-tech-news/`, already outside the repo. The `e2e/README.md` claim that they land in `frontend/test-results/` is stale.

Proof standards.

- Exercise the real user path. Reading the feed means the feed, not the repository behind it.
- Capture the action and the resulting state, not just the final screen.
- Prove a write by reading it back through the user-facing read path. The write endpoint's own success message proves nothing here: `POST /api/ingest/` reports "80 articles saved" on an instance whose feed serves zero.
- Verify side effects alongside what is visible. Ingestion writes an `ingestion_runs` row that changes what `/health/ingestion` reports afterward.
- Mock only where a production boundary already isolates the external system. The research specs mock the SSE stream; the feed specs do not mock the database.
- `dry_run=true` on `POST /api/admin/ingest` skips the RSS fetch and writes no articles, but it still inserts an `ingestion_runs` row and so flips the public ingestion-health probe. Observe what a dry run touched; do not trust the name.

## Cleanup

Kill what you started, by task or process id. Never by process name: `python.exe` and `node.exe` on this machine belong to other work.

```powershell
Pop-Location
Stop-Process -Id <uvicorn-pid> -ErrorAction SilentlyContinue
Stop-Process -Id <vite-pid> -ErrorAction SilentlyContinue
Remove-Item backend/data/verify.db -Force -ErrorAction SilentlyContinue
```

`C:/temp/atn-verify/` and `C:/temp/playwright-tech-news/` survive teardown. They hold the proof. `C:\temp\atn-verify-venv` is reusable across runs; delete it only to force a clean rebuild.

Restore any server-side state a drive mutated. `PUT /api/settings/` is shared by every viewer of the instance.

## Danger list

Never call these during verification unless the change under test is the endpoint itself.

- `POST /api/admin/wipe?confirm=WIPE` deletes every article, category and embedding row. No auth beyond the literal string.
- `POST /api/admin/retention/run` without `dry_run=true` deletes articles older than `RETENTION_DAYS`. No auth.
- `DELETE /api/saved-research/{id}` and `DELETE /api/embeddings/articles/{id}` are irreversible on the instance's database.
- Any summarization, digest, RAG or research call spends real money when `DEFAULT_LLM_PROVIDER=groq`.

Two backends can share one SQLite file and each starts its own scheduler. Give every concurrent instance a distinct `--port` and a distinct `SQLITE_DATABASE_PATH` plus `DATABASE_URL` pair, or run only one.

## Helpers

- [`scripts/doctor.py`](scripts/doctor.py). The readiness verdict. Flags `--backend`, `--frontend`, `--require-articles`, `--json`. Invocation is under [Doctor](#doctor).
- [`.claude/skills/test-app-e2e/scripts/run_e2e.py`](../test-app-e2e/scripts/run_e2e.py). The pre-existing HTTP battery, reused rather than replaced.

## Maintenance

Run `/maintain-verification-skill` when the feature map drifts from the app.
