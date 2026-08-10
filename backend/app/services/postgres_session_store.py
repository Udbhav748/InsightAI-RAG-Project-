"""PostgreSQL-backed chat session store.

Implements the same public interface as InMemorySessionStore
(services/session_store.py); session_store.get_session_store() returns
this implementation when the DB is enabled, else the in-memory one.
Unlike the in-memory store — which is bounded in memory and wiped on
restart — this one persists sessions/turns to PostgreSQL, surviving
restarts and horizontal processes.

Retention mirrors the in-memory store's bounds so the DB can't grow
without limit: max_sessions (LRU by last_accessed_at) and
max_turns_per_session per session.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.db_models import ChatSession, ChatTurn

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresSessionStore:
    def __init__(self, max_sessions: int = 1000, max_turns_per_session: int = 50):
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        if max_turns_per_session <= 0:
            raise ValueError("max_turns_per_session must be positive")
        self._max_sessions = max_sessions
        self._max_turns_per_session = max_turns_per_session

    def _evict_lru_if_needed(self, db) -> None:
        """Delete oldest-by-last_accessed sessions beyond max_sessions.
        Called inside an open session; commits are the caller's job."""
        count = db.query(ChatSession).count()
        if count < self._max_sessions:
            return

        overflow = count - self._max_sessions + 1
        stale = (
            db.query(ChatSession)
            .order_by(ChatSession.last_accessed_at.asc())
            .limit(overflow)
            .all()
        )
        for session in stale:
            db.delete(session)
        logger.info(
            "session_evicted_lru",
            extra={"extra_fields": {"evicted": len(stale), "max_sessions": self._max_sessions}},
        )

    def create_session(self, tenant_id: int | None = None) -> str:
        session_id = str(uuid.uuid4())
        with SessionLocal() as db:
            self._evict_lru_if_needed(db)
            db.add(
                ChatSession(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    created_at=_utcnow(),
                    last_accessed_at=_utcnow(),
                )
            )
            db.commit()
        logger.info(
            "session_created", extra={"extra_fields": {"session_id": session_id, "tenant_id": tenant_id}}
        )
        return session_id

    def get_history(self, session_id: str) -> list[dict] | None:
        with SessionLocal() as db:
            session = db.get(ChatSession, session_id)
            if session is None:
                return None
            session.last_accessed_at = _utcnow()
            db.commit()
            return [
                {"role": turn.role, "content": turn.content}
                for turn in session.turns
            ]

    def append_turn(self, session_id: str, role: str, content: str) -> bool:
        with SessionLocal() as db:
            session = db.get(ChatSession, session_id)
            if session is None:
                return False
            session.turns.append(ChatTurn(role=role, content=content, created_at=_utcnow()))
            session.last_accessed_at = _utcnow()
            # Trim to max_turns_per_session (keep most recent)
            if len(session.turns) > self._max_turns_per_session:
                excess = len(session.turns) - self._max_turns_per_session
                for turn in session.turns[:excess]:
                    db.delete(turn)
            db.commit()
        return True

    def get_or_create_session(self, session_id: str | None, tenant_id: int | None = None) -> str:
        """Same ownership rule as InMemorySessionStore.get_or_create_session:
        a session with a known tenant_id that doesn't match the requester's
        is never handed back (starts a fresh session instead of raising);
        either side being unknown (None) skips the check."""
        if session_id is not None:
            with SessionLocal() as db:
                session = db.get(ChatSession, session_id)
                if session is not None and (
                    session.tenant_id is None or tenant_id is None or session.tenant_id == tenant_id
                ):
                    return session_id
        return self.create_session(tenant_id=tenant_id)

    def delete_session(self, session_id: str) -> bool:
        with SessionLocal() as db:
            session = db.get(ChatSession, session_id)
            if session is None:
                return False
            db.delete(session)
            db.commit()
        return True

    def session_exists(self, session_id: str) -> bool:
        with SessionLocal() as db:
            return db.get(ChatSession, session_id) is not None

    def get_session_count(self) -> int:
        with SessionLocal() as db:
            return db.query(ChatSession).count()
