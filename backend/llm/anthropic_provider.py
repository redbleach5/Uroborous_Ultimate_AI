"""
Anthropic LLM Provider
"""

import os
import time
from typing import List, Optional, AsyncIterator
from anthropic import AsyncAnthropic
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseLLMProvider, LLMMessage, LLMResponse
from ..core.exceptions import LLMException
from ..core.model_performance_tracker import get_performance_tracker


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
        self.client: Optional[AsyncAnthropic] = None
        
        if not self.api_key:
            raise LLMException("Anthropic API key not provided")
    
    async def initialize(self) -> None:
        """Initialize Anthropic client"""
        try:
            self.client = AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout
            )
            logger.info("Anthropic provider initialized")
        except Exception as e:
            raise LLMException(f"Failed to initialize Anthropic provider: {e}") from e
    
    async def shutdown(self) -> None:
        """Shutdown Anthropic client"""
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
        """Generate response from Anthropic"""
        if not self.client:
            raise LLMException("Anthropic client not initialized")
        
        # Performance tracking
        tracker = get_performance_tracker()
        start_time = time.time()
        
        # Check cache (exclude thinking_mode from cache key if not enabled)
        cache_key = self._get_cache_key(messages, model, temperature, thinking_mode=thinking_mode, **kwargs)
        cached = await self._get_cached(cache_key)
        if cached:
            return LLMResponse(
                content=cached,
                model=model or self.default_model,
                metadata={"cached": True},
                has_thinking=False
            )
        
        model_name = model or self.default_model
        max_tokens = max_tokens or 4096  # Anthropic requires max_tokens
        
        # Check if model supports thinking mode
        thinking_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-5-opus-20241022",
            "claude-3-opus-20240229"
        ]
        supports_thinking = any(tm in model_name for tm in thinking_models)
        use_thinking = thinking_mode and supports_thinking
        
        try:
            # Convert messages to Anthropic format
            # Anthropic uses system message separately
            system_message = None
            conversation_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    system_message = msg.content
                else:
                    conversation_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            # Prepare request parameters
            request_params = {
                "model": model_name,
                "messages": conversation_messages,
                "system": system_message,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # Add thinking mode if supported
            # Note: Thinking mode is available for Claude 3.5 Sonnet and newer models
            if use_thinking:
                try:
                    # Add thinking parameter for Anthropic SDK
                    # Format: thinking parameter with type and budget
                    thinking_budget = kwargs.get("thinking_budget_tokens", 4096)
                    
                    # Check SDK version and use appropriate format
                    # For newer SDK versions, thinking might be a direct parameter
                    if hasattr(self.client.messages, 'create'):
                        # Try the thinking parameter
                        request_params["thinking"] = {
                            "type": "enabled",
                            "budget_tokens": thinking_budget
                        }
                        logger.debug(f"Using thinking mode for model {model_name} with budget {thinking_budget}")
                    else:
                        logger.warning(f"Thinking mode requested but SDK may not support it")
                except Exception as e:
                    logger.warning(f"Failed to enable thinking mode: {e}, continuing without it")
            
            # Add any additional kwargs
            request_params.update({k: v for k, v in kwargs.items() if k != "thinking_budget_tokens"})
            
            response = await self.client.messages.create(**request_params)
            
            # Extract content and thinking
            content = ""
            thinking_content = None
            
            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "thinking" and use_thinking:
                    thinking_content = block.text
            
            # If no text content but thinking exists, use thinking as content
            if not content and thinking_content:
                content = thinking_content
                thinking_content = None
            
            # Cache response (only cache final content, not thinking)
            self._set_cached(cache_key, content)
            
            # Build usage dict
            usage_dict = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            } if hasattr(response, "usage") and response.usage else None
            
            # Record successful request metrics
            duration = time.time() - start_time
            total_tokens = usage_dict.get("total_tokens", 0) if usage_dict else 0
            tracker.record_request(
                provider="anthropic",
                model=model_name,
                duration=duration,
                tokens=total_tokens,
                success=True
            )
            
            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage_dict,
                finish_reason=response.stop_reason,
                metadata={"provider": "anthropic", "thinking_mode": use_thinking},
                thinking=thinking_content,
                has_thinking=thinking_content is not None
            )
        except Exception as e:
            # Record failed request
            duration = time.time() - start_time
            tracker.record_request(
                provider="anthropic",
                model=model_name,
                duration=duration,
                tokens=0,
                success=False,
                error_type=type(e).__name__
            )
            raise LLMException(f"Anthropic API error: {e}") from e
    
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response from Anthropic"""
        if not self.client:
            raise LLMException("Anthropic client not initialized")
        
        model_name = model or self.default_model
        max_tokens = max_tokens or 4096
        
        # Check if model supports thinking mode
        thinking_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-5-opus-20241022",
            "claude-3-opus-20240229"
        ]
        supports_thinking = any(tm in model_name for tm in thinking_models)
        use_thinking = thinking_mode and supports_thinking
        
        try:
            system_message = None
            conversation_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    system_message = msg.content
                else:
                    conversation_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            request_params = {
                "model": model_name,
                "messages": conversation_messages,
                "system": system_message,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            
            # Add thinking mode if supported
            if use_thinking:
                request_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": kwargs.get("thinking_budget_tokens", 4096)
                }
            
            # Add any additional kwargs
            request_params.update({k: v for k, v in kwargs.items() if k != "thinking_budget_tokens"})
            
            stream = await self.client.messages.create(**request_params)
            
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield event.delta.text
                elif event.type == "thinking_delta" and use_thinking:
                    # Optionally yield thinking content
                    if kwargs.get("yield_thinking", False):
                        yield f"[thinking: {event.delta.text}]"
        except Exception as e:
            raise LLMException(f"Anthropic streaming error: {e}") from e
    
    async def list_models(self) -> List[str]:
        """List available Anthropic models"""
        # Anthropic doesn't have a models list endpoint
        # Return known models (including thinking-capable models)
        return [
            "claude-3-5-opus-20241022",  # Supports thinking
            "claude-3-5-sonnet-20241022",  # Supports thinking
            "claude-3-5-sonnet-20240620",  # Supports thinking
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2"
        ]

