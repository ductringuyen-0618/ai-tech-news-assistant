#!/usr/bin/env python
"""
Seed Saved Research Script (design-review #4).

Inserts the demo "saved dispatches" defined in
``src.repositories.seed_data.saved_research_seeds`` into the
``saved_research`` table.

Usage
-----

Local::

    cd backend
    python -m scripts.seed_saved_research

The script is idempotent — it calls
:meth:`SavedResearchRepository.seed_if_empty`, which short-circuits when
the table already has any rows. Re-running it is safe.

Production parity
-----------------

The same seed path is wired into the FastAPI lifespan startup in
:mod:`src.main`, so a fresh deploy populates the table automatically.
This script is provided for local development and for manually re-
seeding after a database wipe.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Make the project importable when running this file directly
    # (mirrors the convention used by the other ``scripts/`` entry points).
    backend_dir = Path(__file__).parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from src.core.config import get_settings
    from src.repositories.saved_research_repository import (
        SavedResearchRepository,
    )

    settings = get_settings()
    db_path = (
        settings.database_url
        or getattr(settings, "sqlite_database_path", None)
        or "./news.db"
    )
    repo = SavedResearchRepository(db_path)

    existing = repo.count()
    inserted = repo.seed_if_empty()
    final = repo.count()

    print(f"Saved research seed run:")
    print(f"  db_path     = {db_path}")
    print(f"  existing    = {existing}")
    print(f"  inserted    = {inserted}")
    print(f"  total now   = {final}")
    if existing > 0:
        print("  note: table was non-empty; seed was a no-op.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
