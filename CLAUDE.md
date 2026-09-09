# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TechPulse — an AI-powered tech news aggregator. Python/FastAPI backend (RAG, summarization, agentic research, knowledge graph) + React/TypeScript (Vite) frontend. Backend deploys to Fly.io (`techpulse-ai-backend`), frontend to Vercel. Root `README.md` and `frontend/README.md` are stale (describe an earlier skeleton) — trust the code and this file over them.

## Commands

### Backend (run from `backend/`, using `backend/venv/Scripts/python.exe` on Windows)
- Run server: `uvicorn src.main:app --host 127.0.0.1 --port 8000` (real entrypoint is `backend/src/main.py` — ignore `simple_main.py`/`api_demo.py`/`demo_app.py`, which are legacy/experimental)
- Run all tests: `pytest tests/ -v`
- Run a single test: `pytest tests/path/to/test_file.py::test_name -v`
- Run by marker (registered in `pytest.ini`, `--strict-markers` enforced): `pytest -m unit`, `-m integration`, `-m e2e`, `-m smoke`, `-m live`, etc. — `requires_ollama`/`requires_db`/`requires_network`/`skip_ci`/`slow` also exist; unmarked/uncategorized tests are excluded from none of these by default so just use `-m` to narrow.
- Lint/type-check: `ruff check .`, `mypy . --ignore-missing-imports`, formatting via `black`
- Import smoke check: `python -c "from src.main import app"`

### Frontend (run from `frontend/`)
- Dev server: `npm run dev`
- Build: `npm run build` (outputs to `build/`)
- Typecheck: `npm run typecheck`
- Lint: `npm run lint`
- Format check: `npm run format:check`
- Full check (typecheck + lint + format + build): `npm run verify`
- E2E tests (Playwright, specs in `frontend/e2e/*.spec.ts`): `npm run test:e2e:ui` (headed: `test:e2e:ui:headed`)
- There is no unit-test script (no Jest/Vitest) — only Playwright e2e.

### Full-stack verification
- `verify.ps1` (repo root, Windows PowerShell): builds the frontend, smoke-imports the backend, boots both servers as background jobs, curls `/health` and `/api/news/?page_size=3`, then runs `npx playwright test --reporter=line --grep-invert "visual.baseline|@exhaustive"` (visual-baseline and exhaustive-sweep specs are intentionally excluded — see the `verify-feature` skill for those), and tears down the background jobs/ports afterward.

## Architecture

### Backend (`backend/src/`)
- `api/routes/` — one router module per resource: `news`, `search`, `digest`, `knowledge_graph`, `subscribers`, `settings`, `admin`, `health`, `saved_research`.
- `core/` — `config.py` (Settings, env config), `exceptions.py`, `logging.py`, `middleware.py`, `retry.py`.
- `database/` — `base.py`, `init_db.py`, `models.py` (SQLAlchemy). SQLite by default; Alembic migrations live in `backend/alembic/` (`env.py` imports `src.database.models.Base`).
- `repositories/` — repository pattern per entity (`article_repository.py`, `embedding_repository.py`, etc.) plus a factory.
- `services/` — `news`, `search`, `rag`, `entity_extraction_service.py`, `summarization_orchestrator.py`, `retention_service.py`, `agentic_research_service.py`, `agent_skills/`.

**Database path resolution is unified — always use it.** `core/config.py`'s `Settings` class is the single source of truth for "where is the database": `get_database_path()` returns `DATABASE_URL` if set, else `sqlite_database_path` (default `./data/articles.db`); `get_database_file_path()` strips any `sqlite:///`/`sqlite://` scheme to a plain filesystem path for raw `sqlite3.connect()` use; `get_database_sqlalchemy_url()` returns the SQLAlchemy-URL form. Every repository/service must call one of these rather than reading `database_url`/`sqlite_database_path` directly or hardcoding a path — a prior bug (subscribers route resolving its own path) caused the write path and read path to silently point at two different SQLite files.

**AI/LLM**: multi-provider — `langchain-groq` (cloud), `langchain-ollama` (local), `deepagents` (LangGraph-based agent harness used for per-article/agentic research in `agentic_research_service.py`), `sentence-transformers` + `chromadb`/`langchain-chroma` for embeddings/vector search (RAG).

**Knowledge graph / digest**: `api/routes/knowledge_graph.py`, `services/entity_extraction_service.py`, `services/agent_skills/query_knowledge_graph.py`, `api/routes/digest.py` — mirrored on the frontend by `KnowledgeGraph.tsx` / `DigestView.tsx`.

### Frontend (`frontend/src/`)
- No router — single-page app, tab-based navigation lives inside `App.tsx`.
- `components/` — feature components plus `ui/` (shadcn/radix primitives), `figma/`, `atelier/`, `mission/` subdirs.
- `config/api.ts` — resolves `API_BASE_URL` from `VITE_API_BASE_URL`, falling back to the Fly.io backend when hosted on `vercel.app`, else `http://localhost:8000`. Endpoint constants deliberately use canonical trailing-slash paths (e.g. `/api/news/`) because FastAPI's `redirect_slashes=True` 307-redirects don't carry CORS headers — omitting the trailing slash breaks CORS in the browser.
- `supabase/` is legacy/unused — do not extend it.

### Cross-cutting conventions (from `.github/copilot.yaml` / `copilot-instructions.md`)
- Python only on the backend (no Node/Go services); TypeScript/React only on the frontend.
- Keep `backend/` root limited to `main.py`/`conftest.py`/config files — put one-off/debug scripts in `backend/scripts/`.
- Always go through the LLM provider abstraction for model calls; design for graceful fallback between providers; cache embeddings/LLM responses; mock external AI services in tests.
- Don't create new top-level documentation/markdown files (progress notes, changelogs, deployment guides, etc.) unless explicitly asked.
- Conventional commits (`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`); branch prefixes `feature/`, `bugfix/`, `hotfix/`, `refactor/`, `docs/`.

### Frontend formatting (`.prettierrc`)
`singleQuote: true`, `printWidth: 80`, `tabWidth: 2`, `arrowParens: "avoid"` (non-default), `trailingComma: "es5"`, `endOfLine: "lf"`.
