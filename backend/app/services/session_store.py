"""In-memory chat session store.

Stores conversation history keyed by session_id. This is an in-memory
store — not persisted to disk — because the current deployment target
(Render free tier) has an ephemeral filesystem that wipes on every
spin-down/redeploy (see docs/OPERATIONS.md "The constraint that shapes
everything below: an ephemeral filesystem"). A file-backed store would
face the exact same problem and wouldn't buy more durability than
in-memory on this environment; it would just add complexity for a
durability guarantee this deployment can't actually provide.

If/when the deployment moves to a platform with a real persistent volume
or a database, this module is the single place to swap in a persistent
backend (e.g. Redis, PostgreSQL, or even a JSON file on a mounted disk).
The public API (get_history, append_turn, create_session) would stay the
same.

Retention: bounded by max_sessions (default 1000) with LRU eviction.
No TTL — session count is capped, not time-based, to avoid OOM on
memory-constrained deployments (Render free tier: 512MB). This is a
deliberate simplification over a full TTL system; the cap alone prevents
unbounded growth.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TypedDict

logger = logging.getLogger(__name__)


class HistoryTurn(TypedDict):
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Session:
    session_id: str
    history: list[HistoryTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


class InMemorySessionStore:
    """Thread-safe in-memory session store for chat history.

    Bounded by max_sessions with LRU eviction to prevent unbounded
    memory growth — the direct cause of the Render free-tier OOM.
    Each session's history is also capped at max_turns_per_session
    to prevent a few heavy sessions from exhausting memory.
    """

    def __init__(self, max_sessions: int = 1000, max_turns_per_session: int = 50):
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        if max_turns_per_session <= 0:
            raise ValueError("max_turns_per_session must be positive")
        self._max_sessions = max_sessions
        self._max_turns_per_session = max_turns_per_session
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _evict_lru_if_needed(self) -> None:
        """Evict least-recently-accessed session if at capacity.
        
        Called with lock held.
        """
        if len(self._sessions) >= self._max_sessions:
            # Find session with oldest last_accessed
            lru_session_id = min(
                self._sessions.keys(),
                key=lambda sid: self._sessions[sid].last_accessed
            )
            evicted = self._sessions.pop(lru_session_id)
            logger.info(
                "session_evicted_lru",
                extra={"extra_fields": {"session_id": lru_session_id, "max_sessions": self._max_sessions}},
            )

    def create_session(self) -> str:
        """Create a new empty session and return its session_id.
        
        Evicts LRU session if at capacity.
        """
        session_id = str(uuid.uuid4())
        with self._lock:
            self._evict_lru_if_needed()
            self._sessions[session_id] = Session(session_id=session_id)
        logger.info("session_created", extra={"extra_fields": {"session_id": session_id}})
        return session_id

    def get_history(self, session_id: str) -> list[HistoryTurn] | None:
        """Return history for session_id, or None if not found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.last_accessed = time.time()
            # Return a copy to prevent external mutation
            return list(session.history)

    def append_turn(self, session_id: str, role: str, content: str) -> bool:
        """Append a turn to the session's history. Returns False if session not found.
        
        Trims oldest turns if history exceeds max_turns_per_session.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.history.append({"role": role, "content": content})
            # Trim to max_turns_per_session (keep most recent)
            if len(session.history) > self._max_turns_per_session:
                session.history = session.history[-self._max_turns_per_session:]
            session.last_accessed = time.time()
        return True

    def get_or_create_session(self, session_id: str | None) -> str:
        """If session_id is provided and exists, return it. Otherwise create new session."""
        if session_id is not None:
            with self._lock:
                if session_id in self._sessions:
                    return session_id
        return self.create_session()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
        return False

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def get_session_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# Global singleton instance
_session_store: InMemorySessionStore | None = None
_session_store_lock = threading.Lock()


def get_session_store() -> InMemorySessionStore:
    """Return the global session store instance (created on first call).
    
    Thread-safe lazy initialization using double-checked locking.
    """
    global _session_store
    if _session_store is None:
        with _session_store_lock:
            if _session_store is None:
                _session_store = InMemorySessionStore()
    return _session_store