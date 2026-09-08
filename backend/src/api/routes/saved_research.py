"""
Saved Research Routes
=====================

CRUD endpoints for persisted research reports (M3.M5).

Wire-level contract
-------------------
- ``POST /api/saved-research`` body ``{question, report_md, sources}``
  -> 201 with the full :class:`SavedResearchRead` record.
- ``GET /api/saved-research`` -> list of
  :class:`SavedResearchListItem` rows ordered by ``created_at`` DESC,
  capped at 100.
- ``GET /api/saved-research/{id}`` -> full record or 404.
- ``DELETE /api/saved-research/{id}`` -> 204 on success, 404 if missing.

Cap policy
----------
The table is capped at 100 rows. When ``POST`` is called and the table
is already at the cap, the OLDEST row (smallest ``created_at``, then
smallest ``id`` for tie-breaking) is deleted BEFORE the new row is
inserted. This keeps long-running installations from growing the table
unboundedly.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...core.config import get_settings as get_app_settings
from ...models.saved_research import (
    SavedResearchCreate,
    SavedResearchListItem,
    SavedResearchRead,
)
from ...repositories.saved_research_repository import (
    MAX_SAVED_ROWS,
    SavedResearchRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/saved-research", tags=["SavedResearch"])


def get_saved_research_repository() -> SavedResearchRepository:
    """Build a :class:`SavedResearchRepository` bound to the configured DB.

    Mirrors the dependency-injection pattern in ``settings.py`` so route
    handlers stay testable via ``app.dependency_overrides``.
    """
    settings = get_app_settings()
    return SavedResearchRepository(settings.get_database_file_path())


# ---------------------------------------------------------------------- #
#  POST
# ---------------------------------------------------------------------- #


@router.post(
    "",
    response_model=SavedResearchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_saved_research(
    payload: SavedResearchCreate,
    repo: SavedResearchRepository = Depends(get_saved_research_repository),
) -> SavedResearchRead:
    """Persist a completed research report.

    When the table is already at the ``MAX_SAVED_ROWS`` cap (100), the
    OLDEST row is deleted before the new row is inserted. The eviction
    keeps the API non-blocking — the client never sees a 4xx for "table
    full".
    """
    try:
        # LRU-by-created_at eviction: drop the oldest row first if we'd
        # otherwise grow past the cap.
        if repo.count() >= MAX_SAVED_ROWS:
            repo.delete_oldest()

        new_id = repo.create(
            question=payload.question,
            report_md=payload.report_md,
            sources=payload.sources or [],
        )
        record = repo.get_by_id(new_id)
        if record is None:
            # Should be unreachable — we just inserted the row.
            raise HTTPException(
                status_code=500,
                detail="Failed to re-read just-inserted saved-research row",
            )
        return SavedResearchRead(**record)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create saved-research: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to save research: {exc}"
        )


# ---------------------------------------------------------------------- #
#  GET (list)
# ---------------------------------------------------------------------- #


@router.get("", response_model=list[SavedResearchListItem])
async def list_saved_research(
    repo: SavedResearchRepository = Depends(get_saved_research_repository),
) -> list[SavedResearchListItem]:
    """List saved research rows, newest first, capped at 100."""
    try:
        rows = repo.list_all(limit=MAX_SAVED_ROWS)
        return [
            SavedResearchListItem(id=rid, question=q, created_at=ts)
            for (rid, q, ts) in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to list saved-research: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list saved research: {exc}"
        )


# ---------------------------------------------------------------------- #
#  GET (by id)
# ---------------------------------------------------------------------- #


@router.get("/{row_id}", response_model=SavedResearchRead)
async def get_saved_research(
    row_id: int,
    repo: SavedResearchRepository = Depends(get_saved_research_repository),
) -> SavedResearchRead:
    """Return the full saved-research record for ``row_id``."""
    try:
        record = repo.get_by_id(row_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Saved research with id {row_id} not found",
            )
        return SavedResearchRead(**record)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch saved-research %d: %s", row_id, exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch saved research: {exc}"
        )


# ---------------------------------------------------------------------- #
#  DELETE
# ---------------------------------------------------------------------- #


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_research(
    row_id: int,
    repo: SavedResearchRepository = Depends(get_saved_research_repository),
) -> Response:
    """Delete a saved-research row by id. 204 on success, 404 if missing."""
    try:
        deleted = repo.delete_by_id(row_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Saved research with id {row_id} not found",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to delete saved-research %d: %s", row_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to delete saved research: {exc}"
        )
