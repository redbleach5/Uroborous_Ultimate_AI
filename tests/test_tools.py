"""
Tests for tools
"""

import pytest
from backend.tools.registry import ToolRegistry
from backend.tools.file_tools import ReadFileTool, WriteFileTool
from backend.config import get_config
import tempfile
import os


@pytest.mark.asyncio
async def test_tool_registry_initialization():
    """Test tool registry initialization"""
    config = get_config()
    registry = ToolRegistry(config.tools.dict(), None)
    await registry.initialize()
    
    assert registry._initialized
    tools = await registry.list_tools()
    assert len(tools) > 0
    
    await registry.shutdown()


@pytest.mark.asyncio
async def test_read_file_tool():
    """Test read file tool"""
    tool = ReadFileTool()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write("Test content")
        temp_path = f.name
    
    try:
        result = await tool.execute({"file_path": temp_path})
        assert result.success
        assert result.result["content"] == "Test content"
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_write_file_tool():
    """Test write file tool"""
    tool = WriteFileTool()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        temp_path = f.name
    
    try:
        result = await tool.execute({
            "file_path": temp_path,
            "content": "Written content"
        })
        assert result.success
        
        # Verify content
        with open(temp_path, 'r') as f:
            assert f.read() == "Written content"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

