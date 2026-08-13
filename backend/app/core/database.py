"""SQLAlchemy engine/session wiring for PostgreSQL persistence.

Optional by design: if Settings.database_url is empty, `engine` and
`SessionLocal` are None and `db_enabled()` returns False. Every consumer
(session store, document repository, auth) checks db_enabled() and falls
back to the legacy in-memory/file behavior, so an ephemeral deployment
that can't host a real Postgres keeps working exactly as before. See
app/core/config.py's database_url docstring.
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
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
    # Bounded first-connect: with an unbounded connect attempt, a down
    # Postgres (Docker Desktop stopped, container not running) hangs the
    # whole startup on an OS-level socket connect instead of failing fast.
    # pool_pre_ping only protects *already-pooled* connections on reuse; it
    # does nothing for the very first connect, which is the case that hung.
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
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


def run_migrations() -> None:
    """Apply any pending Alembic migrations to the configured database.

    create_all() only creates tables that don't exist yet — it can never run
    an ALTER TABLE on an existing one and has zero awareness of Alembic's
    version history. A written migration that never reaches the live database
    (the documents.collection incident) breaks every query on that table with
    a 500, and it will recur for every future migration unless they're applied
    automatically. This runs `alembic upgrade head` programmatically via
    Alembic's API, so startup itself applies whatever is pending.

    Idempotent: `upgrade head` on an already-current database is a no-op.
    """
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    # Make the script location absolute so it resolves regardless of CWD.
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    # env.py calls fileConfig(config.config_file_name) which would clobber
    # this process's configured structured logging; it checks the
    # `skip_logging_setup` attribute first (see alembic/env.py).
    cfg.attributes["skip_logging_setup"] = True
    command.upgrade(cfg, "head")


def init_db() -> None:
    """Bring the schema up to date on every startup, then create tables.

    Preferred path: run pending Alembic migrations (run_migrations) so ALTERs
    and new tables reach the live DB automatically. Fallback for a database
    with no Alembic history yet (no alembic_version table — a genuinely fresh
    DB, or one previously built by the old create_all-only path, which is
    exactly how the documents.collection bug was able to slip through):
    Base.metadata.create_all() mirrors the legacy graceful behavior, then the
    DB is stamped at head so it enters Alembic's history and every FUTURE
    migration applies automatically instead of being skipped again.

    A database that is unreachable (Docker Desktop / insightai-postgres
    container down) fails fast after database_connect_timeout_seconds instead
    of hanging, logging one actionable line before re-raising.
    """
    if not db_enabled():
        logger.info("db_disabled", extra={"extra_fields": {"reason": "no DATABASE_URL"}})
        return
    import app.models.db_models  # noqa: F401  ensure models are registered on Base

    try:
        run_migrations()
    except OperationalError:
        host = _database_host_for_log()
        logger.error(
            "db_unreachable",
            extra={
                "extra_fields": {
                    "host": host,
                    "hint": f"Postgres unreachable at {host} - is Docker Desktop / the insightai-postgres container running?",
                }
            },
        )
        raise
    except Exception as exc:
        if _has_alembic_history():
            # Not a no-history fallback: a real migration failure on a DB
            # Alembic already manages. Don't paper over it with create_all.
            logger.error(
                "db_migrations_failed",
                extra={"extra_fields": {"error": str(exc)}},
            )
            raise
        logger.warning(
            "db_no_alembic_history_using_create_all",
            extra={"extra_fields": {"reason": str(exc)}},
        )
        Base.metadata.create_all(bind=engine)
        _stamp_migrations_at_head()
    logger.info(
        "db_ready", extra={"extra_fields": {"url_scheme": settings.database_url.split("://")[0]}}
    )


def _stamp_migrations_at_head() -> None:
    """Record the DB as being at migration head (alembic_version table).

    Called after the create_all() fallback so a pre-Alembic database enters
    Alembic's version history: without this, every future startup would take
    the same create_all fallback and the next real migration would be skipped
    silently forever.
    """
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.attributes["skip_logging_setup"] = True
    command.stamp(cfg, "head")


def _has_alembic_history() -> bool:
    """True if the target DB has ever been through Alembic (an
    alembic_version table exists). A fresh DB that only ever used create_all()
    has no such table — that's the no-history fallback case in init_db."""
    return inspect(engine).has_table("alembic_version")


def _database_host_for_log() -> str:
    """Best-effort host[:port] from the DATABASE_URL, for the unreachable-DB
    error line. Never let logging itself raise on a malformed URL."""
    try:
        return settings.database_url.split("@")[-1].split("/")[0]
    except Exception:
        return settings.database_url or "<unknown>"
