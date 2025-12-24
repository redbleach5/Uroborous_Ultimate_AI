"""
Tests for agents
"""

import pytest
from backend.agents.base import BaseAgent
from backend.config import get_config


@pytest.mark.asyncio
async def test_agent_registry_initialization():
    """Test agent registry initialization"""
    from backend.agents.base import AgentRegistry
    from backend.llm.providers import LLMProviderManager
    from backend.config import get_config
    
    config = get_config()
    llm_manager = LLMProviderManager(config.llm)
    await llm_manager.initialize()
    
    registry = AgentRegistry(
        config.agents,
        llm_manager,
        None,  # tool_registry
        None,  # context_manager
        None   # memory
    )
    
    await registry.initialize()
    
    assert registry._initialized
    agents = registry.list_agents()
    assert len(agents) > 0
    
    await registry.shutdown()
    await llm_manager.shutdown()


@pytest.mark.asyncio
async def test_code_writer_agent():
    """Test CodeWriterAgent"""
    from backend.agents.code_writer import CodeWriterAgent
    from backend.llm.providers import LLMProviderManager
    from backend.config import get_config
    
    config = get_config()
    llm_manager = LLMProviderManager(config.llm)
    await llm_manager.initialize()
    
    agent = CodeWriterAgent(
        "code_writer",
        config.agents.code_writer.dict(),
        llm_manager,
        None,
        None,
        None
    )
    
    await agent.initialize()
    assert agent._initialized
    
    await agent.shutdown()
    await llm_manager.shutdown()

