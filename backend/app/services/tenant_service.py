"""Tenant resolution and API-key mirroring for PostgreSQL persistence.

Two responsibilities, both no-ops when the DB is disabled (db_enabled()
False — see app/core/database.py):

1. `resolve_tenant(client_name)` returns the tenant_id for a client,
   creating the Tenant row on first sight (idempotent). Used by auth to
   scope every request to a tenant.

2. `seed_keys_from_settings()` mirrors the env-configured API keys
   (Settings.api_key_table: hash -> client_name) into the api_keys table
   at startup, so a deployment that moves to Postgres keeps its existing
   keys working while gaining durable tenant rows. The env table remains
   the fast-path authority for key validity (no DB round-trip per
   request); the DB copy exists for durability/listing and for keys that
   are added directly to the DB later.
"""

import logging
import threading

from app.core.config import settings
from app.core.database import SessionLocal, db_enabled
from app.models.db_models import ApiKey, Tenant

logger = logging.getLogger(__name__)

# Client -> tenant_id cache. Tenants are created once and never renamed/deleted
# in this app, so caching a resolved id (once it exists) is safe and avoids a
# DB query on every authenticated request. Guarded by a lock because auth runs
# from the thread pool.
_tenant_cache: dict[str, int] = {}
_tenant_cache_lock = threading.Lock()


def _session():
    if not db_enabled():
        raise RuntimeError("Database not configured")
    return SessionLocal()


def resolve_tenant(client_name: str) -> int | None:
    """Return the tenant_id for a client, creating the tenant row if
    needed. Returns None when the DB is disabled."""
    if not db_enabled():
        return None

    with _tenant_cache_lock:
        cached = _tenant_cache.get(client_name)
        if cached is not None:
            return cached

    with _session() as db:
        tenant = db.query(Tenant).filter(Tenant.slug == client_name).first()
        if tenant is not None:
            tenant_id = tenant.id
        else:
            tenant = Tenant(slug=client_name, name=client_name)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            logger.info(
                "tenant_created",
                extra={"extra_fields": {"client_name": client_name, "tenant_id": tenant.id}},
            )
            tenant_id = tenant.id

    with _tenant_cache_lock:
        _tenant_cache[client_name] = tenant_id
    return tenant_id


def find_api_key(key_hash: str) -> tuple[str, int] | None:
    """Return (client_name, tenant_id) for a key_hash if present in the
    DB, else None. Lets DB-added keys (not in the env table) authenticate.
    """
    if not db_enabled():
        return None
    with _session() as db:
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if api_key is None:
            return None
        return api_key.client_name, api_key.tenant_id


def seed_keys_from_settings() -> None:
    """Mirror env-configured API keys into the DB (idempotent). No-op if
    the DB is disabled. Runs at startup so existing clients get durable
    tenant rows without manual migration."""
    if not db_enabled():
        return

    with _session() as db:
        for key_hash, client_name in settings.api_key_table.items():
            tenant = db.query(Tenant).filter(Tenant.slug == client_name).first()
            if tenant is None:
                tenant = Tenant(slug=client_name, name=client_name)
                db.add(tenant)
                db.flush()

            exists = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
            if exists is None:
                db.add(ApiKey(key_hash=key_hash, client_name=client_name, tenant_id=tenant.id))

        db.commit()

    logger.info(
        "api_keys_seeded",
        extra={"extra_fields": {"key_count": len(settings.api_key_table)}},
    )
