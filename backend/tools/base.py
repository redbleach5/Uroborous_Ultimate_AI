"""
Base Tool class
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel


class ToolInput(BaseModel):
    """Input for tool execution"""
    pass


class ToolOutput(BaseModel):
    """Output from tool execution"""
    success: bool
    result: Any
    error: Optional[str] = None


class BaseTool(ABC):
    """Base class for all tools"""
    
    def __init__(self, name: str, description: str, safety_guard=None):
        """
        Initialize tool
        
        Args:
            name: Tool name
            description: Tool description
            safety_guard: Safety guard instance
        """
        self.name = name
        self.description = description
        self.safety_guard = safety_guard
    
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """
        Execute tool
        
        Args:
            input_data: Input parameters
            
        Returns:
            ToolOutput
        """
        pass
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input data"""
        return True

