"""
Subscribers Route
==================

Digest email-capture: ``POST /api/subscribers`` stores an email address so a
future daily-digest send has someone to send to, and
``GET /api/subscribers/count`` exposes a cheap trust-signal count for the
frontend. This backs the "SUBSCRIBE AT /DIGEST" footer promise, which
previously pointed at nothing.

Capture-only: no email is actually sent. Wiring a real send (cron job +
ESP like Resend/Postmark/SES) is a follow-up that needs a third-party API
key this pass doesn't have access to.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings as get_app_settings
from ...models.api import BaseResponse
from ...models.subscriber import (
    SubscriberCountResponse,
    SubscriberCreate,
    SubscriberResponse,
)
from ...repositories.subscriber_repository import SubscriberRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscribers", tags=["Subscribers"])


def get_subscriber_repository() -> SubscriberRepository:
    """Build a SubscriberRepository bound to the configured SQLite DB."""
    app_settings = get_app_settings()
    return SubscriberRepository(app_settings.get_database_file_path())


@router.post("/", response_model=BaseResponse[SubscriberResponse])
async def create_subscriber(
    payload: SubscriberCreate,
    repository: SubscriberRepository = Depends(get_subscriber_repository),
) -> BaseResponse[SubscriberResponse]:
    """Subscribe an email to the digest. Idempotent — resubscribing (or
    subscribing an already-active email) returns success rather than 409."""
    try:
        data = repository.subscribe(payload.email)
        return BaseResponse[SubscriberResponse](
            success=True,
            message="Subscribed",
            data=SubscriberResponse(**data),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create subscriber: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to subscribe: {exc}")


@router.get("/count", response_model=BaseResponse[SubscriberCountResponse])
async def get_subscriber_count(
    repository: SubscriberRepository = Depends(get_subscriber_repository),
) -> BaseResponse[SubscriberCountResponse]:
    """Return the active-subscriber count, e.g. for a frontend trust signal."""
    try:
        count = repository.count_active()
        return BaseResponse[SubscriberCountResponse](
            success=True,
            message="Subscriber count loaded",
            data=SubscriberCountResponse(count=count),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to count subscribers: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to count subscribers: {exc}")
