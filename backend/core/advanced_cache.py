"""
Advanced Cache - Многоуровневое кэширование для оптимизации производительности
"""

import hashlib
import json
import time
from typing import Dict, Any, Optional, OrderedDict
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict as LRUDict
from .logger import get_logger
logger = get_logger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, distributed caching disabled")


class AdvancedCache:
    """
    Многоуровневое кэширование:
    1. Memory cache (быстрый, ограниченный размер)
    2. Disk cache (медленнее, но больше места)
    3. Redis cache (distributed, для масштабирования)
    """
    
    def __init__(
        self,
        memory_size: int = 1000,
        disk_cache_dir: str = "cache",
        redis_url: Optional[str] = None,
        ttl: int = 3600  # Time to live в секундах
    ):
        # Используем OrderedDict для LRU кэша
        self.memory_cache: LRUDict[str, Dict[str, Any]] = LRUDict()
        self.memory_size = memory_size
        self.disk_cache_dir = Path(disk_cache_dir)
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        
        # Redis для distributed caching
        self.redis_client = None
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()
                logger.info("Redis cache initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis: {e}")
    
    def _generate_key(self, data: Any) -> str:
        """Генерирует ключ кэша из данных"""
        if isinstance(data, str):
            key_str = data
        else:
            key_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Получает значение из кэша (проверяет все уровни)"""
        # 1. Memory cache (самый быстрый) - LRU: перемещаем в конец при доступе
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if self._is_valid(entry):
                logger.debug(f"Cache HIT (memory): {key[:16]}")
                # LRU: перемещаем в конец (most recently used)
                self.memory_cache.move_to_end(key)
                return entry["value"]
            else:
                # Удаляем устаревший entry
                del self.memory_cache[key]
        
        # 2. Redis cache
        if self.redis_client:
            try:
                cached = self.redis_client.get(f"cache:{key}")
                if cached:
                    entry = json.loads(cached)
                    if self._is_valid(entry):
                        logger.debug(f"Cache HIT (redis): {key[:16]}")
                        # Поднимаем в memory cache
                        self._set_memory(key, entry["value"])
                        return entry["value"]
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        # 3. Disk cache
        cache_file = self.disk_cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    entry = json.load(f)
                if self._is_valid(entry):
                    logger.debug(f"Cache HIT (disk): {key[:16]}")
                    # Поднимаем в memory cache
                    self._set_memory(key, entry["value"])
                    return entry["value"]
                else:
                    # Удаляем устаревший файл
                    cache_file.unlink()
            except Exception as e:
                logger.warning(f"Disk cache error: {e}")
        
        logger.debug(f"Cache MISS: {key[:16]}")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Сохраняет значение во все уровни кэша"""
        ttl = ttl or self.ttl
        entry = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        # 1. Memory cache
        self._set_memory(key, value, entry)
        
        # 2. Redis cache (async, не блокирует)
        if self.redis_client:
            try:
                self.redis_client.setex(
                    f"cache:{key}",
                    ttl,
                    json.dumps(entry)
                )
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        
        # 3. Disk cache (async, не блокирует основной поток)
        try:
            cache_file = self.disk_cache_dir / f"{key}.json"
            with open(cache_file, 'w') as f:
                json.dump(entry, f)
        except Exception as e:
            logger.warning(f"Disk cache write error: {e}")
    
    def _set_memory(self, key: str, value: Any, entry: Optional[Dict] = None):
        """Устанавливает значение в memory cache с LRU eviction"""
        if entry is None:
            entry = {
                "value": value,
                "timestamp": time.time(),
                "ttl": self.ttl
            }
        
        # LRU eviction: если кэш переполнен, удаляем самую старую запись (первую в OrderedDict)
        if len(self.memory_cache) >= self.memory_size:
            # Удаляем самую старую запись (первая в OrderedDict)
            if self.memory_cache:
                oldest_key = next(iter(self.memory_cache))
                del self.memory_cache[oldest_key]
                logger.debug(f"LRU eviction: removed {oldest_key[:16]}")
        
        # Добавляем новую запись в конец (most recently used)
        self.memory_cache[key] = entry
        # Перемещаем в конец для LRU
        self.memory_cache.move_to_end(key)
    
    def _is_valid(self, entry: Dict[str, Any]) -> bool:
        """Проверяет, не истек ли срок действия кэша"""
        timestamp = entry.get("timestamp", 0)
        ttl = entry.get("ttl", self.ttl)
        return time.time() - timestamp < ttl
    
    def invalidate(self, key: str):
        """Инвалидирует кэш по ключу"""
        # Memory
        if key in self.memory_cache:
            del self.memory_cache[key]
        
        # Redis
        if self.redis_client:
            try:
                self.redis_client.delete(f"cache:{key}")
            except Exception as e:
                logger.debug(f"Failed to delete cache key from Redis: {e}")
                # Continue - Redis is optional
        
        # Disk
        cache_file = self.disk_cache_dir / f"{key}.json"
        if cache_file.exists():
            cache_file.unlink()
    
    def clear(self):
        """Очищает весь кэш"""
        self.memory_cache.clear()
        
        if self.redis_client:
            try:
                # Удаляем все ключи кэша
                keys = self.redis_client.keys("cache:*")
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.debug(f"Failed to clear Redis cache: {e}")
                # Continue - Redis is optional
        
        # Disk
        for cache_file in self.disk_cache_dir.glob("*.json"):
            cache_file.unlink()
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша"""
        return {
            "memory_entries": len(self.memory_cache),
            "memory_size_limit": self.memory_size,
            "disk_entries": len(list(self.disk_cache_dir.glob("*.json"))),
            "redis_available": self.redis_client is not None
        }

