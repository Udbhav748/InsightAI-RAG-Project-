"""Per-client API key authentication with basic rate limiting.

A small table of keys (sha256_hash -> client_name) loaded from
Settings.api_key_table. Clients send their key in the X-API-Key header.
On success, the client_name is stored in request.state.client_name for
downstream audit logging. No JWT, sessions, or RBAC — just the smallest
real improvement over one shared secret that's demonstrably per-client.

Lookup is O(1) via dict keyed by hash — no linear scan, no bcrypt cost.

Rate limiting: simple per-client sliding window (default 60 req/min per key).
Uses an in-memory store with thread-safe operations. Not persisted —
resets on restart, which is acceptable for a free-tier demo.
"""

import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Header, Request

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.services.tenant_service import find_api_key, resolve_tenant

logger = logging.getLogger(__name__)


@dataclass
class _RateLimitBucket:
    """Sliding-window request counter for a single client."""
    requests: list[float] = field(default_factory=list)  # timestamps
    lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_record(self, limit: int, window_sec: int) -> bool:
        """Return True if request allowed, False if rate limited.
        
        Removes timestamps older than window_sec, then checks count.
        """
        now = time.time()
        with self.lock:
            # Drop expired
            cutoff = now - window_sec
            self.requests = [ts for ts in self.requests if ts > cutoff]
            if len(self.requests) >= limit:
                return False
            self.requests.append(now)
            return True


# Global rate limit store (in-memory, per client_name)
_rate_limit_store: dict[str, _RateLimitBucket] = {}
_rate_limit_lock = threading.Lock()

# Config (could be moved to Settings later)
_RATE_LIMIT_PER_MINUTE = 60
_RATE_LIMIT_WINDOW_SEC = 60


def _check_rate_limit(client_name: str) -> bool:
    """Check and record a request for the given client. Returns True if allowed."""
    with _rate_limit_lock:
        bucket = _rate_limit_store.get(client_name)
        if bucket is None:
            bucket = _RateLimitBucket()
            _rate_limit_store[client_name] = bucket
    return bucket.check_and_record(_RATE_LIMIT_PER_MINUTE, _RATE_LIMIT_WINDOW_SEC)


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key is None:
        logger.warning(
            "audit_event",
            extra={"extra_fields": {"event": "auth_failed", "path": request.url.path, "reason": "missing_header"}},
        )
        raise UnauthorizedError("Missing or invalid API key.")

    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    key_table = settings.api_key_table
    client_name = key_table.get(key_hash)
    if client_name is None:
        # Not an env-configured key — try the DB api_keys table (covers
        # keys added directly to PostgreSQL, not present in API_KEYS env).
        db_lookup = find_api_key(key_hash)
        if db_lookup is not None:
            client_name, _tenant_id = db_lookup
    if client_name is not None:
        # Check rate limit
        if not _check_rate_limit(client_name):
            logger.warning(
                "audit_event",
                extra={"extra_fields": {"event": "rate_limited", "path": request.url.path, "client": client_name}},
            )
            raise UnauthorizedError("Rate limit exceeded. Please slow down.")
        # Resolve the tenant for this client (creating the row on first
        # sight when the DB is enabled); None when the DB is disabled,
        # in which case downstream persistence is also disabled.
        tenant_id = resolve_tenant(client_name)
        request.state.client_name = client_name
        request.state.tenant_id = tenant_id
        return

    logger.warning(
        "audit_event",
        extra={"extra_fields": {"event": "auth_failed", "path": request.url.path, "reason": "invalid_key"}},
    )
    raise UnauthorizedError("Missing or invalid API key.")
