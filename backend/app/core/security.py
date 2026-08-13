"""Input validation utilities, an IP-based rate limiter for the
unauthenticated auth surface, and security headers applied to every
response.

This module was previously dead code: the broken `backend.app.core`
import path made it un-importable, and nothing in main.py ever registered
its middlewares. It's now wired in two places:
  - main.py registers security_headers_middleware() on every response.
  - the /auth routes depend on rate_limit_dependency() (see
    routes/auth.py) to put an IP-based sliding-window cap on the
    unauthenticated brute-force surface (login/signup), which has no
    client identity to key a per-client limiter on.

Authenticated requests are rate-limited separately, per identity, in
core/auth.py (API keys and JWT users) — this module deliberately does not
apply an IP cap to them, so a NAT'd office sharing one IP can't starve
itself of the app it's already authenticated to.
"""

import asyncio
import re
import time
from collections import defaultdict

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError


class InputValidator:
    """Input validation utilities for security."""

    # Maximum lengths for various inputs
    MAX_QUERY_LENGTH = 1000
    MAX_DOCUMENT_ID_LENGTH = 100
    MAX_SESSION_ID_LENGTH = 100

    # Allowed characters for document IDs
    DOCUMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]+$")

    @classmethod
    def validate_query(cls, query: str) -> str:
        """Validate and sanitize user query."""
        if not query or not query.strip():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query cannot be empty",
            )

        if len(query) > cls.MAX_QUERY_LENGTH:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query exceeds maximum length of {cls.MAX_QUERY_LENGTH} characters",
            )

        # Remove potentially dangerous characters
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", query)
        return sanitized.strip()

    @classmethod
    def validate_document_id(cls, doc_id: str) -> str:
        """Validate document ID format."""
        from fastapi import HTTPException

        if not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document ID cannot be empty",
            )

        if len(doc_id) > cls.MAX_DOCUMENT_ID_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document ID exceeds maximum length of {cls.MAX_DOCUMENT_ID_LENGTH} characters",
            )

        if not cls.DOCUMENT_ID_PATTERN.match(doc_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document ID contains invalid characters",
            )

        return doc_id

    @classmethod
    def validate_session_id(cls, session_id: str) -> str:
        """Validate session ID format."""
        from fastapi import HTTPException

        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID cannot be empty",
            )

        if len(session_id) > cls.MAX_SESSION_ID_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session ID exceeds maximum length of {cls.MAX_SESSION_ID_LENGTH} characters",
            )

        return session_id


class RateLimiter:
    """Simple in-memory sliding-window rate limiter, keyed by any string
    identity (an IP address for the unauthenticated auth surface).

    Thread- and event-loop-safe: a plain threading.Lock guards the shared
    dict (the check-and-record must be atomic), so the same instance works
    whether the dependency runs in a thread or on the event loop.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_id: str) -> bool:
        """Return True if a request from client_id is allowed, else False.

        Async so the internal asyncio lock keeps concurrent check-and-
        record atomic even across threads dispatched onto the loop.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        async with self._lock:
            pending = self.requests[client_id]
            pending[:] = [req_time for req_time in pending if req_time > cutoff]
            if len(pending) >= self.max_requests:
                return False
            pending.append(now)
            return True


def get_client_ip(request: Request) -> str:
    """Best-effort client IP, honoring the X-Forwarded-For header when
    present (the app sits behind reverse proxies in production) and
    degrading to a stable placeholder when even request.client is None
    (e.g. some test clients / ASGI servers)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # XFF can be a comma-separated chain: "client, proxy1, proxy2".
        # Only trust the leftmost entry (the original client) — but that
        # entry is attacker-controlled unless a trusted proxy overwrites
        # the header, so this is best-effort, not a security boundary.
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client is not None:
        return request.client.host
    return "unknown"


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency: reject a request from this IP if it's exceeded
    the unauthenticated-auth rate limit. Applied to /auth/signup and
    /auth/login (see routes/auth.py) — the only endpoints without an
    identity to key a per-client limiter on. Skipped when
    Settings.rate_limit_enabled is False."""
    if not settings.rate_limit_enabled:
        return
    client_id = get_client_ip(request)
    if not await rate_limiter.is_allowed(client_id):
        raise RateLimitExceededError(
            "Too many requests. Please try again later."
        )


# Global per-IP rate limiter instance for the unauthenticated auth surface.
rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_per_minute,
    window_seconds=settings.rate_limit_window_seconds,
)


# Security headers middleware — registered on the app in main.py so every
# response (including errors) carries a baseline of hardening headers.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    # HSTS is only meaningful (and only safe to advertise) over HTTPS.
    # Including it over plain HTTP would let a MITM strip the header, so
    # gate it on the request scheme.
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response