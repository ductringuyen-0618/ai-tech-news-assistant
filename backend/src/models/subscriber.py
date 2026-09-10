"""
Subscriber API Models
=====================

Pydantic models for the digest email-capture API. Backs the "SUBSCRIBE AT
/DIGEST" footer promise with a real (capture-only) signup form: no email is
actually sent by this pass — see ``backend/src/api/routes/subscribers.py``
for the follow-up TODO.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Deliberately simple (not RFC 5322 exhaustive) — good enough to reject
# obvious typos without pulling in the `email-validator` dependency, which
# isn't in requirements.txt.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SubscriberCreate(BaseModel):
    """Shape accepted by POST /api/subscribers."""

    email: str = Field(..., description="Email address to subscribe to the digest")

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned or not _EMAIL_RE.match(cleaned):
            raise ValueError("Invalid email address")
        return cleaned


class SubscriberResponse(BaseModel):
    """Shape returned for a single subscriber."""

    id: int
    email: str
    subscribed_at: datetime
    is_active: bool


class SubscriberCountResponse(BaseModel):
    """Shape returned by GET /api/subscribers/count."""

    count: int = Field(..., description="Number of active subscribers")
