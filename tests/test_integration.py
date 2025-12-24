"""
Integration tests
"""

import pytest
from backend.core.engine import IDAEngine
from backend.config import get_config


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_workflow():
    """Test full workflow from task to result"""
    config = get_config()
    engine = IDAEngine(config)
    
    try:
        await engine.initialize()
        
        # Execute a simple task
        result = await engine.execute_task(
            task="Create a simple hello world function in Python",
            agent_type="code_writer"
        )
        
        assert result is not None
        assert "success" in result or "code" in result
        
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_processing():
    """Test batch processing"""
    config = get_config()
    engine = IDAEngine(config)
    
    try:
        await engine.initialize()
        
        if engine.batch_processor:
            tasks = [
                "Create a function to add two numbers",
                "Create a function to multiply two numbers"
            ]
            
            results = await engine.batch_processor.process_tasks_batch(
                engine=engine,
                tasks=tasks,
                agent_type="code_writer"
            )
            
            assert len(results) == 2
            assert all("result" in r for r in results)
        
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_metrics_collection():
    """Test metrics collection during execution"""
    from backend.core.metrics import metrics_collector
    
    config = get_config()
    engine = IDAEngine(config)
    
    try:
        await engine.initialize()
        
        # Execute tasks
        await engine.execute_task(
            task="Test task 1",
            agent_type="code_writer"
        )
        
        await engine.execute_task(
            task="Test task 2",
            agent_type="code_writer"
        )
        
        # Check metrics
        stats = metrics_collector.get_all_stats()
        assert stats["tasks"]["total"] >= 2
        
    finally:
        await engine.shutdown()

