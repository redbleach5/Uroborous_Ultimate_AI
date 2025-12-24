"""
Base LLM Provider interface
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Message in LLM conversation"""
    role: str  # system, user, assistant
    content: str


class LLMResponse(BaseModel):
    """Response from LLM"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    thinking: Optional[str] = None  # Reasoning/thinking trace for thinking models
    has_thinking: bool = False  # Whether this response includes thinking


class BaseLLMProvider(ABC):
    """Base class for LLM providers"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider
        
        Args:
            config: Provider configuration
        """
        self.config = config
        self.name = config.get("name", "unknown")
        self.enabled = config.get("enabled", True)
        self.default_model = config.get("default_model", "")
        self.timeout = config.get("timeout", 60)
        self.max_retries = config.get("max_retries", 3)
        self.cache_enabled = config.get("cache_enabled", True)
        self._cache: Dict[str, str] = {}
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the provider"""
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response from LLM
        
        Args:
            messages: List of messages in conversation
            model: Model name. If None, uses default_model
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            thinking_mode: Enable thinking/reasoning mode for models that support it
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse object
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream response from LLM
        
        Args:
            messages: List of messages in conversation
            model: Model name. If None, uses default_model
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            thinking_mode: Enable thinking/reasoning mode for models that support it
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Chunks of response text
        """
        pass
    
    @abstractmethod
    async def list_models(self) -> List[str]:
        """
        List available models
        
        Returns:
            List of model names
        """
        pass
    
    def _get_cache_key(
        self,
        messages: List[LLMMessage],
        model: Optional[str],
        temperature: float,
        **kwargs
    ) -> str:
        """Generate cache key for request"""
        import hashlib
        import json
        
        key_data = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "model": model or self.default_model,
            "temperature": temperature,
            **kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    async def _get_cached(self, cache_key: str) -> Optional[str]:
        """Get cached response"""
        if not self.cache_enabled:
            return None
        return self._cache.get(cache_key)
    
    def _set_cached(self, cache_key: str, response: str) -> None:
        """Cache response"""
        if not self.cache_enabled:
            return
        # Simple in-memory cache (can be extended to use Redis, etc.)
        self._cache[cache_key] = response
        # Limit cache size
        if len(self._cache) > 1000:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._cache.keys())[:100]
            for key in keys_to_remove:
                del self._cache[key]

