"""
Tests for document processing tools
"""

import pytest
import os
import json
import tempfile
from pathlib import Path

from backend.tools.document_tools import (
    DocumentExtractTool,
    ZipExtractTool,
    DocumentInfoTool,
)


class TestDocumentExtractTool:
    """Tests for DocumentExtractTool"""
    
    @pytest.fixture
    def tool(self):
        return DocumentExtractTool(safety_guard=None)
    
    @pytest.mark.asyncio
    async def test_extract_json(self, tool):
        """Test JSON extraction"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success
            assert "content" in result.result
            assert "key" in result.result["content"]
            assert result.result["extension"] == "json"
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_extract_text(self, tool):
        """Test text file extraction"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello, World!\nThis is a test.")
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success
            assert "Hello, World!" in result.result["content"]
            assert result.result["extension"] == "txt"
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_extract_python_file(self, tool):
        """Test Python file extraction"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    print('Hello')")
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success
            assert "def hello" in result.result["content"]
            assert result.result["extension"] == "py"
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file"""
        result = await tool.execute({"file_path": "/nonexistent/file.txt"})
        
        assert not result.success
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_unsupported_format(self, tool):
        """Test handling of unsupported file format"""
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert not result.success
            assert "unsupported" in result.error.lower()
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_missing_file_path(self, tool):
        """Test handling of missing file_path parameter"""
        result = await tool.execute({})
        
        assert not result.success
        assert "required" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_truncation(self, tool):
        """Test content truncation for large files"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("x" * 100000)  # 100KB of text
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path, "max_chars": 1000})
            
            assert result.success
            assert result.result["truncated"]
            assert result.result["char_count"] == 100000
            assert len(result.result["content"]) < 2000  # Less than original
        finally:
            os.unlink(temp_path)


class TestZipExtractTool:
    """Tests for ZipExtractTool"""
    
    @pytest.fixture
    def tool(self):
        return ZipExtractTool(safety_guard=None)
    
    @pytest.mark.asyncio
    async def test_extract_zip(self, tool):
        """Test ZIP extraction"""
        import zipfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a zip file
            zip_path = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr("file1.txt", "content1")
                zf.writestr("file2.txt", "content2")
            
            result = await tool.execute({
                "file_path": zip_path,
                "target_dir": os.path.join(tmpdir, "extracted")
            })
            
            assert result.success
            assert result.result["file_count"] == 2
            assert "file1.txt" in result.result["files"]
    
    @pytest.mark.asyncio
    async def test_invalid_zip(self, tool):
        """Test handling of invalid ZIP file"""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(b"not a zip file")
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert not result.success
            assert "invalid" in result.error.lower() or "corrupted" in result.error.lower()
        finally:
            os.unlink(temp_path)


class TestDocumentInfoTool:
    """Tests for DocumentInfoTool"""
    
    @pytest.fixture
    def tool(self):
        return DocumentInfoTool(safety_guard=None)
    
    @pytest.mark.asyncio
    async def test_get_info(self, tool):
        """Test getting file info"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello, World!")
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success
            assert result.result["extension"] == "txt"
            assert result.result["size_bytes"] > 0
            assert "size_human" in result.result
            assert result.result["is_supported"]
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_unsupported_info(self, tool):
        """Test info for unsupported file type"""
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            temp_path = f.name
        
        try:
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success
            assert not result.result["is_supported"]
        finally:
            os.unlink(temp_path)

