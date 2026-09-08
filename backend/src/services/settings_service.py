"""
Settings Service
================

Business logic for user-settings persistence: applies defaults, validates
field values, and orchestrates repository calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..models.settings import (
    DEFAULT_CATEGORIES,
    DEFAULT_SHOW_TRENDING_ONLY,
    DEFAULT_VIEW_MODE,
    SettingsUpdate,
)
from ..repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


_VALID_VIEW_MODES = {"detailed", "compact"}


class SettingsService:
    """Service for reading and updating per-client settings rows."""

    def __init__(self, repo: SettingsRepository):
        self._repo = repo

    def get_settings(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Return the current settings for ``client_id``, falling back to
        sensible defaults when no row has been written yet. When
        ``client_id`` is ``None``, falls back to the legacy singleton row.
        Always returns a complete payload so the caller never has to deal
        with ``None`` fields.
        """
        row = self._repo.get(client_id=client_id)
        if row is None:
            return {
                "categories": list(DEFAULT_CATEGORIES),
                "view_mode": DEFAULT_VIEW_MODE,
                "show_trending_only": DEFAULT_SHOW_TRENDING_ONLY,
                "updated_at": None,
            }

        # Backfill any missing fields with their defaults so the response
        # shape is stable even if columns were left NULL by a partial write.
        return {
            "categories": (
                row["categories"] if row["categories"] is not None
                else list(DEFAULT_CATEGORIES)
            ),
            "view_mode": row["view_mode"] or DEFAULT_VIEW_MODE,
            "show_trending_only": bool(row["show_trending_only"]),
            "updated_at": row.get("updated_at"),
        }

    def update_settings(
        self, payload: SettingsUpdate, client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate and persist a partial settings update for ``client_id``
        (or the legacy singleton row when ``client_id`` is ``None``).
        """
        if payload.view_mode is not None and payload.view_mode not in _VALID_VIEW_MODES:
            raise ValueError(
                f"Invalid view_mode '{payload.view_mode}'. "
                f"Must be one of {sorted(_VALID_VIEW_MODES)}."
            )
        if payload.categories is not None:
            if not isinstance(payload.categories, list) or not all(
                isinstance(c, str) for c in payload.categories
            ):
                raise ValueError("'categories' must be a list of strings.")

        row = self._repo.upsert(
            client_id=client_id,
            categories=payload.categories,
            view_mode=payload.view_mode,
            show_trending_only=payload.show_trending_only,
        )
        # Repo guarantees a row exists after upsert, but make the response
        # shape match get_settings() for symmetry.
        return {
            "categories": (
                row["categories"] if row["categories"] is not None
                else list(DEFAULT_CATEGORIES)
            ),
            "view_mode": row["view_mode"] or DEFAULT_VIEW_MODE,
            "show_trending_only": bool(row["show_trending_only"]),
            "updated_at": row.get("updated_at"),
        }
