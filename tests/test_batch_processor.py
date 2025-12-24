"""
Tests for batch processor
"""

import pytest
import asyncio
from backend.core.batch_processor import BatchProcessor


@pytest.mark.asyncio
async def test_batch_processor_initialization():
    """Test batch processor initialization"""
    processor = BatchProcessor(max_concurrent=5)
    assert processor.max_concurrent == 5


@pytest.mark.asyncio
async def test_process_batch():
    """Test processing a batch"""
    processor = BatchProcessor(max_concurrent=2)
    
    async def simple_processor(task_data):
        await asyncio.sleep(0.1)
        return {"result": f"Processed {task_data['id']}"}
    
    tasks = [
        {"id": 1, "data": "task1"},
        {"id": 2, "data": "task2"},
        {"id": 3, "data": "task3"}
    ]
    
    results = await processor.process_batch(tasks, simple_processor)
    
    assert len(results) == 3
    assert all(r["success"] for r in results)
    assert results[0]["result"]["result"] == "Processed 1"


@pytest.mark.asyncio
async def test_process_batch_with_errors():
    """Test processing batch with errors"""
    processor = BatchProcessor(max_concurrent=2)
    
    async def failing_processor(task_data):
        if task_data["id"] == 2:
            raise ValueError("Test error")
        return {"result": "success"}
    
    tasks = [
        {"id": 1},
        {"id": 2},
        {"id": 3}
    ]
    
    results = await processor.process_batch(tasks, failing_processor)
    
    assert len(results) == 3
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[1]["error"] == "Test error"
    assert results[2]["success"] is True


@pytest.mark.asyncio
async def test_process_batch_progress_callback():
    """Test batch processing with progress callback"""
    processor = BatchProcessor(max_concurrent=2)
    
    progress_updates = []
    
    async def progress_callback(completed, total, result):
        progress_updates.append((completed, total))
    
    async def simple_processor(task_data):
        await asyncio.sleep(0.1)
        return {"result": "success"}
    
    tasks = [{"id": i} for i in range(5)]
    
    await processor.process_batch(tasks, simple_processor, progress_callback)
    
    assert len(progress_updates) == 5
    assert progress_updates[-1] == (5, 5)

