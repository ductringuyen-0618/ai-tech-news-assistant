"""
Settings API Models
==================

Pydantic models for the user-settings API. The app currently has a single
user, so settings is a single-row table — these models describe the JSON
shape the frontend uses when reading/writing those settings.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# Sensible defaults that mirror the frontend's hard-coded initial state in
# App.tsx. A fresh DB (no settings row yet) returns these from GET so the
# frontend always gets HTTP 200 with a usable payload.
#
# Empty on purpose: an unfiltered feed. ["AI", "Machine Learning"] used to
# be the default here, but those strings don't match any value in the
# real category taxonomy (which uses "AI/ML", "AI Agents", etc.) -- every
# first-time visitor (no settings row yet) silently got a feed filtered
# down to zero articles. See App.tsx's matching fix/comment for the
# frontend-side half of this same bug.
DEFAULT_CATEGORIES: List[str] = []
DEFAULT_VIEW_MODE: str = "detailed"
DEFAULT_SHOW_TRENDING_ONLY: bool = False


class SettingsResponse(BaseModel):
    """Shape returned by GET /api/settings (inside BaseResponse.data)."""

    categories: List[str] = Field(
        default_factory=lambda: list(DEFAULT_CATEGORIES),
        description="User-selected topic categories",
    )
    view_mode: str = Field(
        default=DEFAULT_VIEW_MODE,
        description="UI view mode: 'detailed' or 'compact'",
    )
    show_trending_only: bool = Field(
        default=DEFAULT_SHOW_TRENDING_ONLY,
        description="Whether the feed is filtered to trending articles only",
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last-updated timestamp (None if defaults)"
    )


class SettingsUpdate(BaseModel):
    """Shape accepted by PUT /api/settings (partial updates allowed)."""

    categories: Optional[List[str]] = Field(
        default=None, description="User-selected topic categories"
    )
    view_mode: Optional[str] = Field(
        default=None, description="UI view mode: 'detailed' or 'compact'"
    )
    show_trending_only: Optional[bool] = Field(
        default=None, description="Whether to filter to trending articles only"
    )
