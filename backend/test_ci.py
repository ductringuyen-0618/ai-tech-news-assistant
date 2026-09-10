"""CI smoke tests.

Referenced directly by ``.github/workflows``'s "Backend Quality & Tests"
step (``python -m pytest test_ci.py -v``). This file did not previously
exist, which meant CI's own `pytest test_ci.py` invocation errored with
"file not found" on every backend-touching PR and fell through to a
fallback block that imports `production_main`/`llm.providers`/
`utils.config` -- modules that don't exist in this codebase's current
`src/` layout (see CLAUDE.md: the real entrypoint is `src/main.py`).
That fallback always failed too, so the whole step was red regardless
of what a PR actually changed.

Deliberately narrow and dependency-light: these tests only need what
CI's own env already sets up (`OLLAMA_HOST`, `USE_MOCK_DATA`,
`ANTHROPIC_API_KEY` -- see the workflow) and the app's existing graceful
handling of missing optional AI/ML packages (`_safe_include_router`
catches and logs import failures per-router rather than crashing the
whole app). No network access, no real database writes.
"""

from fastapi.testclient import TestClient


def test_app_imports():
    """`from src.main import app` must succeed -- this is the same
    check CLAUDE.md documents as the manual import smoke check."""
    from src.main import app

    assert app is not None


def test_health_endpoint_returns_ok():
    """`/health` must respond without needing a live database or any
    external AI provider."""
    from src.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_settings_load():
    """Configuration loads without requiring real secrets -- CI sets
    `ANTHROPIC_API_KEY=mock-key-for-ci`, not a real credential."""
    from src.core.config import get_settings

    settings = get_settings()
    assert settings.app_name


def test_news_router_registered():
    """The main news-feed endpoint is mounted -- a quick regression
    guard for `_safe_include_router` silently swallowing an import
    error."""
    from src.main import app

    # FastAPI's route tree only exposes the mounted sub-router's own
    # entries once resolved; walking `app.openapi()` is the reliable way
    # to see the final flattened path list including prefixes.
    openapi_paths = set(app.openapi()["paths"].keys())
    assert "/api/news/" in openapi_paths
