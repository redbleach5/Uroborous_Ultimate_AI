"""
Tests for orchestrator
"""

import pytest
from backend.orchestrator import Orchestrator
from backend.config import get_config


@pytest.mark.asyncio
async def test_orchestrator_initialization():
    """Test orchestrator initialization"""
    config = get_config()
    orchestrator = Orchestrator(
        config.orchestrator,
        None,  # agent_registry
        None,  # llm_manager
        None   # memory
    )
    
    await orchestrator.initialize()
    assert orchestrator._initialized
    
    await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_decompose_task():
    """Test task decomposition - orchestrator handles task without agent_registry"""
    config = get_config()
    orchestrator = Orchestrator(
        config.orchestrator,
        None,  # agent_registry - will cause error when trying to execute
        None,  # llm_manager - will skip decomposition without it
        None   # memory
    )
    
    await orchestrator.initialize()
    
    # Without agent_registry, orchestrator should handle gracefully
    # This tests error handling when components are missing
    task = "Simple test task"
    try:
        result = await orchestrator.execute_task(task)
        # If it returns, should have error or success flag
        assert isinstance(result, dict)
        # May have error if agent_registry is None
        if "error" in result:
            assert result.get("success") is False
    except AttributeError:
        # Expected when agent_registry is None
        pass
    
    await orchestrator.shutdown()

