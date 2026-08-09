"""SQLAlchemy engine/session wiring for PostgreSQL persistence.

Optional by design: if Settings.database_url is empty, `engine` and
`SessionLocal` are None and `db_enabled()` returns False. Every consumer
(session store, document repository, auth) checks db_enabled() and falls
back to the legacy in-memory/file behavior, so an ephemeral deployment
that can't host a real Postgres keeps working exactly as before. See
app/core/config.py's database_url docstring.
"""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models (see app/models/db_models.py)."""


# No engine/session when the DB is disabled — every caller guards on
# db_enabled() before touching these. Models imported against this module
# still work without a live connection because they only need the
# declarative metadata, not an engine.
engine = None
SessionLocal = None

if settings.database_url:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def db_enabled() -> bool:
    """True if a DATABASE_URL is configured and we can serve sessions."""
    return engine is not None and SessionLocal is not None


def get_db():
    """FastAPI dependency yielding a scoped session (only valid when
    db_enabled(); routes that may run with the DB disabled must guard
    before depending on this)."""
    if not db_enabled():
        raise RuntimeError("Database not configured (DATABASE_URL is empty)")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist. Idempotent: create_all only
    creates missing tables, never alters existing ones (that's Alembic's
    job — see backend/alembic/). Safe to run on every startup."""
    if not db_enabled():
        logger.info("db_disabled", extra={"extra_fields": {"reason": "no DATABASE_URL"}})
        return
    import app.models.db_models  # noqa: F401  ensure models are registered on Base

    Base.metadata.create_all(bind=engine)
    logger.info("db_ready", extra={"extra_fields": {"url_scheme": settings.database_url.split("://")[0]}})
