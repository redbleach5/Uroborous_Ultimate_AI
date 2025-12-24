"""
Tool Registry - Manages all available tools
"""

from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput
from typing import Union
from ..safety.guard import SafetyGuard
from ..core.exceptions import ToolException


class ToolRegistry:
    """Registry for managing tools"""
    
    def __init__(
        self,
        config: Any,  # ToolsConfig or Dict
        safety_guard: Optional[SafetyGuard] = None
    ):
        """
        Initialize tool registry
        
        Args:
            config: Tools configuration (ToolsConfig or dict)
            safety_guard: Safety guard instance
        """
        self.config = config
        self.safety_guard = safety_guard
        self.tools: Dict[str, BaseTool] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize and register all tools"""
        if self._initialized:
            return
        
        logger.info("Initializing Tool Registry...")
        
        # Handle both Pydantic model and dict
        if hasattr(self.config, "categories"):
            categories = self.config.categories if self.config.categories else {}
        elif isinstance(self.config, dict):
            categories = self.config.get("categories", {})
        else:
            categories = {}
        
        # Helper function to get category value
        def get_category(cat_name: str, default: bool = True) -> bool:
            if isinstance(categories, dict):
                return categories.get(cat_name, default)
            else:
                return getattr(categories, cat_name, default) if categories else default
        
        # Register file tools
        if get_category("file", True):
            from .file_tools import ReadFileTool, WriteFileTool, ListFilesTool
            self.register_tool(ReadFileTool(self.safety_guard))
            self.register_tool(WriteFileTool(self.safety_guard))
            self.register_tool(ListFilesTool(self.safety_guard))
        
        # Register shell tools
        if get_category("shell", True):
            from .shell_tools import ExecuteCommandTool
            self.register_tool(ExecuteCommandTool(self.safety_guard))
        
        # Register git tools
        if get_category("git", True):
            from .git_tools import (
                GitStatusTool, GitCommitTool, GitBranchTool,
                GitDiffTool, GitLogTool
            )
            self.register_tool(GitStatusTool(self.safety_guard))
            self.register_tool(GitCommitTool(self.safety_guard))
            self.register_tool(GitBranchTool(self.safety_guard))
            self.register_tool(GitDiffTool(self.safety_guard))
            self.register_tool(GitLogTool(self.safety_guard))
        
        # Register web tools
        if get_category("web", True):
            from .web_tools import WebSearchTool, APICallTool
            self.register_tool(WebSearchTool(self.safety_guard))
            self.register_tool(APICallTool(self.safety_guard))
        
        # Register database tools
        if get_category("database", True):
            from .database_tools import DatabaseQueryTool
            self.register_tool(DatabaseQueryTool(self.safety_guard))
        
        logger.info(f"Registered {len(self.tools)} tools")
        self._initialized = True
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool"""
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    async def execute_tool(self, tool_name: str, input_data: Dict[str, Any]) -> ToolOutput:
        """
        Execute a tool
        
        Args:
            tool_name: Name of tool
            input_data: Input parameters
            
        Returns:
            ToolOutput with execution result
            
        Raises:
            ToolException: If tool not found, invalid input, or execution raises an exception
        """
        if tool_name not in self.tools:
            raise ToolException(f"Tool '{tool_name}' not found")
        
        tool = self.tools[tool_name]
        
        # Validate input
        if not tool.validate_input(input_data):
            raise ToolException(f"Invalid input for tool '{tool_name}'")
        
        # Execute tool
        try:
            result = await tool.execute(input_data)
            # Return ToolOutput even if success=False - execution errors are valid results
            return result
        except Exception as e:
            # Only raise exception for unexpected errors during execution
            raise ToolException(f"Tool execution error: {e}") from e
    
    async def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """List all available tools"""
        return {
            name: {
                "name": tool.name,
                "description": tool.description
            }
            for name, tool in self.tools.items()
        }
    
    async def shutdown(self) -> None:
        """Shutdown tool registry"""
        self.tools.clear()
        self._initialized = False

