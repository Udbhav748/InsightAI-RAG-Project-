"""Individual login-based accounts (User) and JWT issuance/verification.

Distinct from tenant_service.py, which resolves an API-key client_name
to a tenant. This module additionally *creates* a tenant: each signup
gets its own personal Tenant (1:1), created in the same transaction as
the User row. That's what makes per-user privacy free — Document/
ChatSession are already scoped by tenant_id, so a dedicated tenant per
user isolates them from everyone else using the exact same columns and
ownership-check code that already exists for API-key clients. See
app/api/v1/routes/auth.py for the routes that call this module, and
app/core/auth.py's require_auth for how an issued JWT gets back to
(tenant_id, role) on every subsequent request.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.database import SessionLocal, db_enabled
from app.core.exceptions import AuthConfigurationError, EmailAlreadyRegisteredError, UnauthorizedError
from app.models.db_models import Tenant, User
from app.services.tenant_service import effective_role

logger = logging.getLogger(__name__)


def _session():
    if not db_enabled():
        raise RuntimeError("Database not configured")
    return SessionLocal()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(email: str, password: str) -> tuple[int, int, str]:
    """Create a personal Tenant + User for a new signup, in one
    transaction. Returns (user_id, tenant_id, role). Raises
    EmailAlreadyRegisteredError if the email is already taken.

    slug is a generated uuid, not the raw email — Tenant.slug already
    has its own uniqueness/format expectations from the API-key world
    (client_name values), and a generated id keeps this path from
    colliding with or depending on that format.
    """
    with _session() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            raise EmailAlreadyRegisteredError(f"An account with email {email} already exists.")

        tenant = Tenant(slug=f"user-{uuid.uuid4()}", name=email)
        db.add(tenant)
        db.flush()  # assigns tenant.id without committing yet

        user = User(email=email, password_hash=_hash_password(password), tenant_id=tenant.id)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.refresh(tenant)

        logger.info(
            "user_created",
            extra={"extra_fields": {"user_id": user.id, "tenant_id": tenant.id}},
        )
        return user.id, tenant.id, effective_role(email, tenant.role)


def authenticate_user(email: str, password: str) -> tuple[int, int, str]:
    """Verify email/password. Returns (user_id, tenant_id, role).

    Raises UnauthorizedError on any mismatch — deliberately the same
    error and message for "no such email" and "wrong password" so a
    caller can't enumerate registered emails from the response alone.
    """
    with _session() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None or not _verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.")

        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        stored_role = tenant.role if tenant is not None else "member"
        return user.id, user.tenant_id, effective_role(email, stored_role)


def get_user_by_id(user_id: int) -> tuple[str, int, str] | None:
    """Return (email, tenant_id, role) for GET /auth/me, or None if the
    user (or its tenant) no longer exists."""
    with _session() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        stored_role = tenant.role if tenant is not None else "member"
        return user.email, user.tenant_id, effective_role(user.email, stored_role)


def create_access_token(user_id: int, email: str) -> str:
    """Issue a JWT identifying this user. Raises AuthConfigurationError
    if JWT_SECRET_KEY isn't set — fails loud rather than signing with an
    empty/weak secret, the same posture missing-API-key checks already
    use elsewhere in this codebase."""
    if not settings.jwt_secret_key:
        raise AuthConfigurationError(
            "JWT_SECRET_KEY is not configured; individual user login is unavailable."
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user_id encoded in a valid, unexpired token, or None
    if the token is missing, expired, malformed, or signed with a
    different secret. Never raises — require_auth treats None as "not a
    JWT-authenticated request" and falls through to the API-key path."""
    if not settings.jwt_secret_key:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
