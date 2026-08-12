import json
import hashlib
from typing import Any, Optional, Union
from datetime import timedelta
import redis
from backend.app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class CacheService:
    """Caching service for frequently accessed data"""
    
    def __init__(self):
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Initialize Redis connection"""
        try:
            if settings.REDIS_URL:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Connected to Redis cache")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
            self.redis_client = None
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from arguments"""
        key_parts = [str(arg) for arg in args]
        key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
        key_string = ":".join(key_parts)
        hash_key = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix}:{hash_key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
        
        return None
    
    def set(self, key: str, value: Any, expire: Union[int, timedelta] = 3600) -> bool:
        """Set value in cache with expiration"""
        if not self.redis_client:
            return False
        
        try:
            serialized_value = json.dumps(value, default=str)
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            
            return self.redis_client.setex(key, expire, serialized_value)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        if not self.redis_client:
            return False
        
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def get_or_set(self, key: str, default_factory, expire: Union[int, timedelta] = 3600) -> Any:
        """Get value from cache or set it using factory function"""
        value = self.get(key)
        if value is not None:
            return value
        
        value = default_factory()
        self.set(key, value, expire)
        return value

# Global cache service instance
cache_service = CacheService()

# Cache decorators
def cached(expire: Union[int, timedelta] = 3600, key_prefix: str = "cache"):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache_service._generate_key(
                key_prefix, 
                func.__name__, 
                *args, 
                **kwargs
            )
            
            # Try to get from cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache_service.set(cache_key, result, expire)
            logger.debug(f"Cached result for {cache_key}")
            
            return result
        return wrapper
    return decorator
