"""
RAG Cache - Caching for RAG queries
"""

from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
logger = get_logger(__name__)
import hashlib
import json
import time
from functools import lru_cache


class RAGCache:
    """Cache for RAG query results"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        Initialize RAG cache
        
        Args:
            max_size: Maximum number of cached items
            ttl: Time to live in seconds
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, float] = {}
    
    def _make_key(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """Create cache key from query and filters"""
        key_data = {"query": query, "filters": filters or {}}
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, query: str, filters: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached results
        
        Args:
            query: Search query
            filters: Optional filters
            
        Returns:
            Cached results or None
        """
        key = self._make_key(query, filters)
        
        if key not in self._cache:
            return None
        
        cached_item = self._cache[key]
        
        # Check TTL
        if time.time() - cached_item["timestamp"] > self.ttl:
            del self._cache[key]
            if key in self._access_times:
                del self._access_times[key]
            return None
        
        # Update access time
        self._access_times[key] = time.time()
        
        logger.debug(f"Cache hit for query: {query[:50]}...")
        return cached_item["results"]
    
    def set(
        self,
        query: str,
        results: List[Dict[str, Any]],
        filters: Optional[Dict[str, Any]] = None
    ):
        """
        Cache results
        
        Args:
            query: Search query
            results: Results to cache
            filters: Optional filters
        """
        key = self._make_key(query, filters)
        
        # Evict if cache is full
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        
        self._cache[key] = {
            "results": results,
            "timestamp": time.time(),
            "query": query
        }
        self._access_times[key] = time.time()
        
        logger.debug(f"Cached results for query: {query[:50]}...")
    
    def _evict_oldest(self):
        """Evict least recently used item"""
        if not self._access_times:
            # If no access times, evict first item
            if self._cache:
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            return
        
        # Find least recently used
        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]
        del self._cache[lru_key]
        del self._access_times[lru_key]
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
        self._access_times.clear()
        logger.info("RAG cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "keys": list(self._cache.keys())[:10]  # First 10 keys
        }

