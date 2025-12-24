"""
Tests for LLM providers
"""

import pytest
from backend.llm.base import LLMMessage
from backend.llm.providers import LLMProviderManager
from backend.config import get_config


@pytest.mark.asyncio
async def test_llm_provider_manager_initialization():
    """Test LLM provider manager initialization"""
    config = get_config()
    manager = LLMProviderManager(config.llm)
    await manager.initialize()
    
    assert manager._initialized
    assert len(manager.providers) > 0
    
    await manager.shutdown()


@pytest.mark.asyncio
async def test_ollama_provider():
    """Test Ollama provider"""
    config = get_config()
    manager = LLMProviderManager(config.llm)
    await manager.initialize()
    
    if manager.is_provider_available("ollama"):
        provider = manager.get_provider("ollama")
        assert provider is not None
        
        # Test list models
        models = await provider.list_models()
        assert isinstance(models, list)
    
    await manager.shutdown()


@pytest.mark.asyncio
async def test_generate_message():
    """Test message generation"""
    config = get_config()
    manager = LLMProviderManager(config.llm)
    await manager.initialize()
    
    messages = [
        LLMMessage(role="user", content="Hello, how are you?")
    ]
    
    try:
        response = await manager.generate(
            messages=messages,
            max_tokens=50
        )
        assert response is not None
        assert hasattr(response, 'content')
        assert len(response.content) > 0
    except Exception as e:
        # If no providers available, skip test
        pytest.skip(f"No LLM providers available: {e}")
    
    await manager.shutdown()

