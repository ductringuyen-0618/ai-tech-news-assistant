"""
Settings Route
==============

User settings persistence: GET / PUT against a single-row settings table.
Powers the frontend's "Save preferences" button so user preferences (selected
categories, view mode, trending toggle) survive across browsers and devices.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings as get_app_settings
from ...models.api import BaseResponse
from ...models.settings import SettingsUpdate
from ...repositories.settings_repository import SettingsRepository
from ...services.settings_service import SettingsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["Settings"])


def get_settings_service() -> SettingsService:
    """Build a SettingsService bound to the configured SQLite DB."""
    app_settings = get_app_settings()
    return SettingsService(SettingsRepository(app_settings.get_database_file_path()))


@router.get("/", response_model=BaseResponse[Dict[str, Any]])
async def get_user_settings(
    service: SettingsService = Depends(get_settings_service),
) -> BaseResponse[Dict[str, Any]]:
    """
    Return the persisted user settings.

    On a fresh DB (no row yet) returns sensible defaults rather than 404 so
    the frontend can rely on a single shape for both first-run and subsequent
    visits.
    """
    try:
        data = service.get_settings()
        return BaseResponse[Dict[str, Any]](
            success=True,
            message="Settings loaded",
            data=data,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load settings: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {exc}")


@router.put("/", response_model=BaseResponse[Dict[str, Any]])
async def update_user_settings(
    payload: SettingsUpdate,
    service: SettingsService = Depends(get_settings_service),
) -> BaseResponse[Dict[str, Any]]:
    """Persist a partial settings update and return the saved shape."""
    try:
        data = service.update_settings(payload)
        return BaseResponse[Dict[str, Any]](
            success=True,
            message="Settings saved",
            data=data,
        )
    except ValueError as exc:
        # Validation failures are user-fixable -> 400.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save settings: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {exc}")
