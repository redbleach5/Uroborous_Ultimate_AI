"""
OpenAI LLM Provider
"""

import os
import time
from typing import List, Optional, AsyncIterator
from openai import AsyncOpenAI
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseLLMProvider, LLMMessage, LLMResponse
from ..core.exceptions import LLMException
from ..core.model_performance_tracker import get_performance_tracker


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.client: Optional[AsyncOpenAI] = None
        
        if not self.api_key:
            raise LLMException("OpenAI API key not provided")
    
    async def initialize(self) -> None:
        """Initialize OpenAI client"""
        try:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            logger.info("OpenAI provider initialized")
        except Exception as e:
            raise LLMException(f"Failed to initialize OpenAI provider: {e}") from e
    
    async def shutdown(self) -> None:
        """Shutdown OpenAI client"""
        if self.client:
            await self.client.close()
    
    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> LLMResponse:
        """Generate response from OpenAI"""
        if not self.client:
            raise LLMException("OpenAI client not initialized")
        
        # Performance tracking
        tracker = get_performance_tracker()
        start_time = time.time()
        
        # Check cache
        cache_key = self._get_cache_key(messages, model, temperature, **kwargs)
        cached = await self._get_cached(cache_key)
        if cached:
            return LLMResponse(
                content=cached,
                model=model or self.default_model,
                metadata={"cached": True}
            )
        
        model_name = model or self.default_model
        
        try:
            # Convert messages to OpenAI format
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            response = await self.client.chat.completions.create(
                model=model_name,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            content = response.choices[0].message.content or ""
            
            # Cache response
            self._set_cached(cache_key, content)
            
            # Build usage dict
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else None
            
            # Record successful request metrics
            duration = time.time() - start_time
            total_tokens = usage_dict.get("total_tokens", 0) if usage_dict else 0
            tracker.record_request(
                provider="openai",
                model=model_name,
                duration=duration,
                tokens=total_tokens,
                success=True
            )
            
            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage_dict,
                finish_reason=response.choices[0].finish_reason,
                metadata={"provider": "openai", "thinking_mode": False},
                has_thinking=False
            )
        except Exception as e:
            # Record failed request
            duration = time.time() - start_time
            tracker.record_request(
                provider="openai",
                model=model_name,
                duration=duration,
                tokens=0,
                success=False,
                error_type=type(e).__name__
            )
            raise LLMException(f"OpenAI API error: {e}") from e
    
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response from OpenAI"""
        if not self.client:
            raise LLMException("OpenAI client not initialized")
        
        model_name = model or self.default_model
        
        try:
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            stream = await self.client.chat.completions.create(
                model=model_name,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMException(f"OpenAI streaming error: {e}") from e
    
    async def list_models(self) -> List[str]:
        """List available OpenAI models"""
        if not self.client:
            raise LLMException("OpenAI client not initialized")
        
        try:
            models = await self.client.models.list()
            return [model.id for model in models.data if "gpt" in model.id.lower()]
        except Exception as e:
            logger.warning(f"Failed to list OpenAI models: {e}")
            # Return common models as fallback
            return [
                "gpt-4-turbo-preview",
                "gpt-4",
                "gpt-3.5-turbo",
                "gpt-3.5-turbo-16k"
            ]

