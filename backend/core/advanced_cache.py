"""
Advanced Cache - Многоуровневое кэширование для оптимизации производительности
"""

import hashlib
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path
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
        ttl: int = 3600,  # Time to live в секундах
        max_disk_size_mb: int = 500  # Maximum disk cache size in MB
    ):
        # Используем OrderedDict для LRU кэша
        self.memory_cache: LRUDict[str, Dict[str, Any]] = LRUDict()
        self.memory_size = memory_size
        self.disk_cache_dir = Path(disk_cache_dir)
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.max_disk_size_mb = max_disk_size_mb
        self._last_disk_cleanup = time.time()
        
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
            # Periodically cleanup disk cache to stay within limits
            self._maybe_cleanup_disk_cache()
            
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
    
    def _get_disk_cache_size_mb(self) -> float:
        """Returns current disk cache size in MB"""
        total_size = 0
        try:
            for cache_file in self.disk_cache_dir.glob("*.json"):
                total_size += cache_file.stat().st_size
        except Exception as e:
            logger.debug(f"Error calculating disk cache size: {e}")
        return total_size / (1024 * 1024)
    
    def _cleanup_disk_cache(self, target_size_mb: Optional[float] = None):
        """
        Clean up disk cache to stay within size limits.
        Removes oldest files first (LRU-like behavior).
        
        Args:
            target_size_mb: Target size to reduce to. If None, uses max_disk_size_mb * 0.8
        """
        try:
            target = target_size_mb or (self.max_disk_size_mb * 0.8)
            current_size = self._get_disk_cache_size_mb()
            
            if current_size <= target:
                return
            
            logger.info(f"Disk cache cleanup: {current_size:.1f}MB -> {target:.1f}MB")
            
            # Get all cache files with modification time
            cache_files = []
            for cache_file in self.disk_cache_dir.glob("*.json"):
                try:
                    stat = cache_file.stat()
                    cache_files.append((cache_file, stat.st_mtime, stat.st_size))
                except Exception:
                    continue
            
            # Sort by modification time (oldest first)
            cache_files.sort(key=lambda x: x[1])
            
            # Remove files until we reach target size
            removed_count = 0
            for cache_file, mtime, size in cache_files:
                if current_size <= target:
                    break
                try:
                    cache_file.unlink()
                    current_size -= size / (1024 * 1024)
                    removed_count += 1
                except Exception as e:
                    logger.debug(f"Failed to remove cache file {cache_file}: {e}")
            
            if removed_count > 0:
                logger.info(f"Disk cache cleanup: removed {removed_count} files")
                
        except Exception as e:
            logger.warning(f"Disk cache cleanup error: {e}")
    
    def _maybe_cleanup_disk_cache(self):
        """Periodically check and cleanup disk cache (every 5 minutes)"""
        now = time.time()
        if now - self._last_disk_cleanup > 300:  # 5 minutes
            self._last_disk_cleanup = now
            if self._get_disk_cache_size_mb() > self.max_disk_size_mb:
                self._cleanup_disk_cache()
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша"""
        disk_size_mb = self._get_disk_cache_size_mb()
        return {
            "memory_entries": len(self.memory_cache),
            "memory_size_limit": self.memory_size,
            "disk_entries": len(list(self.disk_cache_dir.glob("*.json"))),
            "disk_size_mb": round(disk_size_mb, 2),
            "disk_size_limit_mb": self.max_disk_size_mb,
            "redis_available": self.redis_client is not None
        }

