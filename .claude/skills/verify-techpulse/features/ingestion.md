# Ingest and summarize

A reader expects the desk to have read the news overnight. Ingestion pulls articles from five RSS sources into the database, optionally summarizes them through the configured LLM, and makes them available to every other feature. Nothing else in the app has content until this runs.

## Sub-features

- `ingest-pull` fetches the configured RSS feeds and saves new articles.
- `ingest-read-back` proves the saved articles are visible through the read path a user actually hits.
- `ingest-summarize` fills AI summaries for articles that lack them.
- `ingest-freshness` reports how stale the last run is.
- `ingest-dry-run` counts the work set without writing articles.

## How to get to it (user POV)

- No UI control triggers ingestion. A user experiences it only as content appearing in the feed, digest and knowledge graph.
- Operators trigger it with `POST /api/ingest/`, or with `POST /api/admin/ingest` when `ADMIN_TOKEN` is set.
- A scheduled run fires daily at 05:00 UTC unless `ENVIRONMENT=testing` or `RETENTION_ENABLED=false`.

## Driving it with the harness

Preconditions: backend up per `../SKILL.md`, doctor exit 0 without `--require-articles`, `SQLITE_DATABASE_PATH` and `DATABASE_URL` naming the same file.

- `ingest-pull`. Record the starting count, then run the pull in the foreground with summarization off so the drive does not depend on an LLM gate.
  ```powershell
  $b = "http://127.0.0.1:8000"
  (Invoke-RestMethod "$b/api/news/stats").data.total_articles
  Invoke-RestMethod -Method Post -Uri "$b/api/ingest/" -ContentType "application/json" `
    -Body '{"background": false, "auto_summarize": false}' -TimeoutSec 600
  ```
  Observable result: the response `message` reads `Ingestion completed: N articles saved` with `background: false`.

- `ingest-read-back`. This is the assertion that matters. The write path's own message is not proof.
  ```powershell
  (Invoke-RestMethod "$b/api/ingest/stats").total_articles
  (Invoke-RestMethod "$b/api/news/stats").data.total_articles
  ```
  Observable result: both numbers are equal and greater than the starting count. A pair like `80` and `0` means the two stores diverged and every downstream feature is unverifiable.

- `ingest-summarize`. Requires the summarization gate green in the doctor.
  ```powershell
  Invoke-RestMethod -Method Post -Uri "$b/api/ingest/summarize-pending" -TimeoutSec 900
  (Invoke-RestMethod "$b/api/news/stats").data.articles_with_summaries
  ```
  Observable result: `articles_with_summaries` rises. Confirm in the UI that a feed card shows summary text rather than the truncated article body.

- `ingest-freshness`.
  ```powershell
  Invoke-RestMethod "$b/health/ingestion"
  ```
  Observable result: `status` is `green`, `yellow`, `red` or `unknown`, with `age_hours` since the last recorded run.

- `ingest-dry-run`. Needs `ADMIN_TOKEN` set on the instance.
  ```powershell
  Invoke-RestMethod -Method Post -Uri "$b/api/admin/ingest?dry_run=true" -Headers @{ "X-Admin-Token" = $env:ADMIN_TOKEN }
  ```
  Observable result: per-phase counts with zero articles written. Confirm by re-reading `/api/news/stats` and seeing no change.

## Gotchas

- The split store is the first thing to rule out. Ingestion writes through SQLAlchemy (`sqlite:///./data/ai_news.db` by default) while the news routes read `SQLITE_DATABASE_PATH` (`./data/articles.db` by default). Set both to one file at launch.
- `background` defaults to `true` and `auto_summarize` defaults to `true`. The defaults return immediately and then spend LLM budget in the background, which makes the run neither observable nor cheap. Pass both explicitly.
- Ingestion reaches five live RSS feeds. Article counts and titles differ between runs, so never assert an exact number or a specific headline.
- A dry run still inserts an `ingestion_runs` row, so it changes what `/health/ingestion` reports afterward. Capture freshness before the dry run if that value matters.
- `POST /api/admin/ingest` returns 503 when `ADMIN_TOKEN` is unset and 401 when the token is wrong. The 503 means the gate is unconfigured, not that the route is broken.
- Ingested articles carry source categories that may not overlap the categories saved in the browser's preferences. The feed can read empty right after a successful ingest for that reason alone. See [news-feed.md](./news-feed.md).
