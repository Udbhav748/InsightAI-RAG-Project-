"""Adaptive Semantic Response Cache Service for InsightAI-RAG.

Supports dual-mode caching:
1. Redis: Distributed, persistent caching for multi-worker production deployments (10k+ users).
2. In-Memory: Thread-safe LRU + TTL cache with zero-configuration fallback for local development.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class _InMemoryCacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class AdaptiveCacheService:
    """Adaptive Cache Service supporting Redis with automatic in-memory fallback."""

    def __init__(self, max_in_memory_items: int = 1000) -> None:
        self.max_in_memory_items = max_in_memory_items
        self._lock = threading.Lock()
        self._in_memory_store: dict[str, _InMemoryCacheEntry] = {}
        self._lru_keys: list[str] = []
        self._redis_client: Any = None
        self._hits: int = 0
        self._misses: int = 0
        self._connect_redis()

    def _connect_redis(self) -> None:
        """Initialize Redis connection if REDIS_URL is configured."""
        if not settings.redis_url:
            self._redis_client = None
            return

        try:
            import redis

            client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
                retry_on_timeout=False,
            )
            client.ping()
            self._redis_client = client
            logger.info("Connected to Redis distributed cache (%s)", settings.redis_url)
        except Exception as e:
            logger.warning(
                "Redis connection failed (%s). Falling back to in-memory TTL cache.", e
            )
            self._redis_client = None

    @property
    def is_redis_active(self) -> bool:
        """Return True if Redis client is connected and active."""
        if self._redis_client is None:
            return False
        try:
            self._redis_client.ping()
            return True
        except Exception:
            return False

    @property
    def active_engine(self) -> str:
        """Return 'redis' if Redis is active, else 'in_memory'."""
        return "redis" if self.is_redis_active else "in_memory"

    def _generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        """Generate a deterministic SHA-256 hashed cache key."""
        key_parts = [str(arg) for arg in args]
        key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
        key_string = ":".join(key_parts)
        hash_key = hashlib.sha256(key_string.encode("utf-8")).hexdigest()[:32]
        return f"{prefix}:{hash_key}"

    def get(self, key: str) -> Any | None:
        """Get value from active cache (Redis or In-Memory)."""
        # 1. Try Redis if active
        if self.is_redis_active:
            try:
                raw = self._redis_client.get(key)
                if raw is not None:
                    self._hits += 1
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        return raw
                self._misses += 1
                return None
            except Exception as e:
                logger.debug("Redis get failed (%s), checking in-memory fallback", e)

        # 2. In-Memory fallback with TTL and LRU
        with self._lock:
            entry = self._in_memory_store.get(key)
            if entry is not None:
                if entry.is_expired():
                    self._in_memory_store.pop(key, None)
                    if key in self._lru_keys:
                        self._lru_keys.remove(key)
                    self._misses += 1
                    return None

                # Move key to front of LRU
                if key in self._lru_keys:
                    self._lru_keys.remove(key)
                self._lru_keys.insert(0, key)
                self._hits += 1
                return entry.value

            self._misses += 1
            return None

    def set(
        self,
        key: str,
        value: Any,
        expire: int | timedelta = 3600,
    ) -> bool:
        """Set value in cache with expiration."""
        ttl_seconds = int(expire.total_seconds()) if isinstance(expire, timedelta) else int(expire)
        if ttl_seconds <= 0:
            return False

        # 1. Set in Redis if active
        if self.is_redis_active:
            try:
                if isinstance(value, (dict, list, int, float, bool)):
                    serialized = json.dumps(value, default=str)
                elif hasattr(value, "model_dump"):
                    serialized = json.dumps(value.model_dump(), default=str)
                else:
                    serialized = str(value)

                self._redis_client.setex(key, ttl_seconds, serialized)
                return True
            except Exception as e:
                logger.debug("Redis set failed (%s), setting in-memory fallback", e)

        # 2. Set in-memory store
        with self._lock:
            # Evict LRU if capacity exceeded
            if len(self._lru_keys) >= self.max_in_memory_items and key not in self._in_memory_store:
                oldest_key = self._lru_keys.pop()
                self._in_memory_store.pop(oldest_key, None)

            expires_at = time.monotonic() + ttl_seconds
            self._in_memory_store[key] = _InMemoryCacheEntry(value, expires_at)

            if key in self._lru_keys:
                self._lru_keys.remove(key)
            self._lru_keys.insert(0, key)
            return True

    def delete(self, key: str) -> bool:
        """Delete key from both Redis and in-memory cache."""
        deleted = False
        if self.is_redis_active:
            try:
                deleted = bool(self._redis_client.delete(key))
            except Exception as e:
                logger.debug("Redis delete failed (%s)", e)

        with self._lock:
            if key in self._in_memory_store:
                self._in_memory_store.pop(key, None)
                if key in self._lru_keys:
                    self._lru_keys.remove(key)
                deleted = True

        return deleted

    def clear(self) -> None:
        """Flush the active cache."""
        if self.is_redis_active:
            try:
                self._redis_client.flushdb()
            except Exception as e:
                logger.debug("Redis flushdb failed (%s)", e)

        with self._lock:
            self._in_memory_store.clear()
            self._lru_keys.clear()

    def get_stats(self) -> dict[str, Any]:
        """Return cache health and usage metrics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "engine": self.active_engine,
            "is_redis_active": self.is_redis_active,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 2),
            "in_memory_items": len(self._in_memory_store),
            "max_in_memory_capacity": self.max_in_memory_items,
        }


# Singleton global instance
cache_service = AdaptiveCacheService()


def cached(
    expire: int | timedelta = 3600,
    key_prefix: str = "cache",
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator for caching async function results."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = cache_service._generate_key(key_prefix, func.__name__, *args, **kwargs)
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug("Cache hit for key %s", cache_key)
                return cached_result

            result = await func(*args, **kwargs)
            cache_service.set(cache_key, result, expire)
            logger.debug("Cached result for key %s", cache_key)
            return result

        return wrapper

    return decorator
