"""
File manipulation tools
"""

import aiofiles
from pathlib import Path
from typing import Dict, Any
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput


class ReadFileTool(BaseTool):
    """Tool for reading files"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="read_file",
            description="Чтение содержимого файла",
            safety_guard=safety_guard
        )
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Read file"""
        file_path = input_data.get("file_path")
        if not file_path:
            return ToolOutput(success=False, result=None, error="file_path required")
        
        # Safety check
        if self.safety_guard:
            if not self.safety_guard.validate_path(file_path):
                return ToolOutput(success=False, result=None, error="Invalid or unsafe path")
        
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolOutput(success=False, result=None, error=f"File not found: {file_path}")
            
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
            
            return ToolOutput(success=True, result={"content": content, "path": str(path)})
        except Exception as e:
            logger.error(f"ReadFileTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))


class WriteFileTool(BaseTool):
    """Tool for writing files"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="write_file",
            description="Запись содержимого в файл",
            safety_guard=safety_guard
        )
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Write file"""
        file_path = input_data.get("file_path")
        content = input_data.get("content", "")
        
        if not file_path:
            return ToolOutput(success=False, result=None, error="file_path required")
        
        # Safety check
        if self.safety_guard:
            if not self.safety_guard.validate_path(file_path):
                return ToolOutput(success=False, result=None, error="Invalid or unsafe path")
        
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
            
            return ToolOutput(success=True, result={"path": str(path), "written": len(content)})
        except Exception as e:
            logger.error(f"WriteFileTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))


class ListFilesTool(BaseTool):
    """Tool for listing files in directory"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="list_files",
            description="Список файлов в директории",
            safety_guard=safety_guard
        )
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """List files"""
        dir_path = input_data.get("dir_path", ".")
        recursive = input_data.get("recursive", False)
        
        # Safety check
        if self.safety_guard:
            if not self.safety_guard.validate_path(dir_path):
                return ToolOutput(success=False, result=None, error="Invalid or unsafe path")
        
        try:
            path = Path(dir_path)
            if not path.exists():
                return ToolOutput(success=False, result=None, error=f"Directory not found: {dir_path}")
            
            if recursive:
                files = [str(p) for p in path.rglob("*") if p.is_file()]
            else:
                files = [str(p) for p in path.iterdir() if p.is_file()]
            
            return ToolOutput(success=True, result={"files": files, "count": len(files)})
        except Exception as e:
            logger.error(f"ListFilesTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))

