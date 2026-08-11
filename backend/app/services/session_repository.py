"""DB-backed listing/ownership/title for chat sessions — the pieces
`session_store.py`/`postgres_session_store.py` (turn-by-turn history for
the *active* conversation) don't provide. Mirrors
`document_repository.py`'s shape exactly: every function is a no-op /
returns a sensible default when the DB is disabled, so the history-list
routes degrade the same way document listing already does.
"""

import logging

from app.core.database import SessionLocal, db_enabled
from app.models.db_models import ChatSession

logger = logging.getLogger(__name__)


def list_sessions(tenant_id: int | None) -> list[dict]:
    """All sessions for a tenant, most-recently-accessed first. []
    when the DB is disabled or tenant_id is None (no scope to list
    under — matches list_documents(None)'s own behavior for a caller
    with no resolvable tenant, not "everything")."""
    if not db_enabled() or tenant_id is None:
        return []

    with SessionLocal() as db:
        sessions = (
            db.query(ChatSession)
            .filter(ChatSession.tenant_id == tenant_id)
            .order_by(ChatSession.last_accessed_at.desc())
            .all()
        )
        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "created_at": s.created_at,
                "last_accessed_at": s.last_accessed_at,
            }
            for s in sessions
        ]


def get_session_owner(session_id: str) -> int | None:
    """tenant_id that owns session_id, or None if unknown — either the
    DB is disabled or no such session exists. Callers treat "unknown"
    as "can't verify, don't block," the same convention
    document_repository.get_document_owner already uses."""
    if not db_enabled():
        return None
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        return session.tenant_id if session is not None else None


def set_session_title_if_unset(session_id: str, title: str) -> None:
    """Best-effort: populate title from the first user turn, once — a
    failure here must never fail the chat request it's piggybacking on."""
    if not db_enabled():
        return
    try:
        with SessionLocal() as db:
            session = db.get(ChatSession, session_id)
            if session is not None and session.title is None:
                session.title = title[:200]
                db.commit()
    except Exception as exc:
        logger.warning(
            "session_title_set_failed",
            extra={"extra_fields": {"session_id": session_id, "error": str(exc)}},
        )
