"""
Tests for RAG cache
"""

import pytest
import time
from backend.rag.cache import RAGCache


def test_rag_cache_initialization():
    """Test RAG cache initialization"""
    cache = RAGCache(max_size=100, ttl=60)
    assert cache.max_size == 100
    assert cache.ttl == 60


def test_rag_cache_set_and_get():
    """Test setting and getting from cache"""
    cache = RAGCache(max_size=10, ttl=3600)
    
    query = "test query"
    results = [{"content": "result1"}, {"content": "result2"}]
    
    cache.set(query, results)
    cached_results = cache.get(query)
    
    assert cached_results == results


def test_rag_cache_miss():
    """Test cache miss"""
    cache = RAGCache()
    
    result = cache.get("nonexistent query")
    assert result is None


def test_rag_cache_ttl_expiration():
    """Test TTL expiration"""
    cache = RAGCache(max_size=10, ttl=1)  # 1 second TTL
    
    query = "test query"
    results = [{"content": "result"}]
    
    cache.set(query, results)
    
    # Should be in cache
    assert cache.get(query) == results
    
    # Wait for TTL to expire
    time.sleep(1.1)
    
    # Should be expired
    assert cache.get(query) is None


def test_rag_cache_eviction():
    """Test cache eviction when full"""
    cache = RAGCache(max_size=2, ttl=3600)
    
    # Fill cache
    cache.set("query1", [{"content": "result1"}])
    cache.set("query2", [{"content": "result2"}])
    
    # Add one more - should evict oldest
    cache.set("query3", [{"content": "result3"}])
    
    # Cache should have 2 items
    stats = cache.get_stats()
    assert stats["size"] == 2


def test_rag_cache_clear():
    """Test clearing cache"""
    cache = RAGCache()
    
    cache.set("query1", [{"content": "result1"}])
    cache.set("query2", [{"content": "result2"}])
    
    assert cache.get("query1") is not None
    
    cache.clear()
    
    assert cache.get("query1") is None
    assert cache.get("query2") is None


def test_rag_cache_stats():
    """Test cache statistics"""
    cache = RAGCache(max_size=100, ttl=3600)
    
    cache.set("query1", [{"content": "result1"}])
    cache.set("query2", [{"content": "result2"}])
    
    stats = cache.get_stats()
    
    assert stats["size"] == 2
    assert stats["max_size"] == 100
    assert stats["ttl"] == 3600
    assert "keys" in stats

