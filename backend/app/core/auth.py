"""Shared-secret API key authentication.

A single static key (Settings.api_key) that clients send in the X-API-Key
header. This only gates access to the API as a whole — no per-user
identity, sessions, or JWTs. Those are documented as future work.
"""

import logging

from fastapi import Header, Request

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        logger.warning(
            "audit_event",
            extra={"extra_fields": {"event": "auth_failed", "path": request.url.path}},
        )
        raise UnauthorizedError("Missing or invalid API key.")
