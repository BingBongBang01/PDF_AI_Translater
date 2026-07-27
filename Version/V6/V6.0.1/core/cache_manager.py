import time
from typing import Any, Dict, Optional
from core.logger import logger
from core.exceptions import CacheException

class CacheEntry:
    def __init__(self, key: str, value: Any, ttl: Optional[int]):
        self.key = key
        self.value = value
        self.timestamp = time.time()
        self.ttl = ttl
        self.last_accessed = time.time()

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

class CacheManager:
    """Manages memory and disk caching with LRU and TTL support."""
    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self._cache: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry:
            if entry.is_expired():
                self.delete(key)
                return None
            entry.last_accessed = time.time()
            return entry.value
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if len(self._cache) >= self.max_items:
            self._evict_lru()
        self._cache[key] = CacheEntry(key, value, ttl)

    def delete(self, key: str):
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        self._cache.clear()

    def _evict_lru(self):
        if not self._cache:
            return
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        self.delete(lru_key)
        
    def cleanup_expired(self):
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for k in expired_keys:
            self.delete(k)

    def cleanup(self, max_size_mb: int = 512):
        logger.info(f"Running cache cleanup, target max size: {max_size_mb} MB")
        if len(self._cache) > 500:
            logger.info("Evicting half of cache keys to free memory.")
            keys = sorted(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
            for k in keys[:len(keys)//2]:
                self.delete(k)
