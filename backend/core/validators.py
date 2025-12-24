"""
Input validators for AILLM
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
from .logger import get_logger
logger = get_logger(__name__)


class TaskRequest(BaseModel):
    """Validated task request"""
    task: str = Field(..., min_length=1, max_length=10000, description="Task description")
    agent_type: Optional[str] = Field(None, description="Specific agent type")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    
    @validator('task')
    def validate_task(cls, v):
        if not v or not v.strip():
            raise ValueError("Task cannot be empty")
        return v.strip()
    
    @validator('agent_type')
    def validate_agent_type(cls, v):
        if v is not None:
            valid_agents = [
                "code_writer", "react", "research", "data_analysis",
                "workflow", "integration", "monitoring"
            ]
            if v not in valid_agents:
                raise ValueError(f"Invalid agent type. Must be one of: {valid_agents}")
        return v


class CodeRequest(BaseModel):
    """Validated code generation request"""
    task: str = Field(..., min_length=1, max_length=5000)
    file_path: Optional[str] = Field(None, max_length=500)
    existing_code: Optional[str] = Field(None, max_length=100000)
    requirements: Optional[str] = Field(None, max_length=2000)
    
    @validator('task')
    def validate_task(cls, v):
        if not v or not v.strip():
            raise ValueError("Task cannot be empty")
        return v.strip()


class ToolExecutionRequest(BaseModel):
    """Validated tool execution request"""
    tool_name: str = Field(..., min_length=1, max_length=100)
    input: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('tool_name')
    def validate_tool_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty")
        return v.strip()


class ProjectIndexRequest(BaseModel):
    """Validated project index request"""
    project_path: str = Field(..., min_length=1, max_length=1000)
    extensions: Optional[List[str]] = Field(None)
    max_file_size: Optional[int] = Field(1000000, ge=0, le=100000000)
    
    @validator('project_path')
    def validate_project_path(cls, v):
        if not v or not v.strip():
            raise ValueError("Project path cannot be empty")
        return v.strip()


class WorkflowRequest(BaseModel):
    """Validated workflow request"""
    name: str = Field(..., min_length=1, max_length=200)
    steps: List[Dict[str, Any]] = Field(..., min_items=1)
    stop_on_error: bool = Field(True)
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Workflow name cannot be empty")
        return v.strip()
    
    @validator('steps')
    def validate_steps(cls, v):
        if not v:
            raise ValueError("Workflow must have at least one step")
        
        step_names = set()
        for step in v:
            if not isinstance(step, dict):
                raise ValueError("Each step must be a dictionary")
            
            if "name" not in step:
                raise ValueError("Each step must have a 'name' field")
            
            if "type" not in step:
                raise ValueError("Each step must have a 'type' field")
            
            step_name = step["name"]
            if step_name in step_names:
                raise ValueError(f"Duplicate step name: {step_name}")
            step_names.add(step_name)
            
            step_type = step.get("type")
            if step_type not in ["agent", "tool", "code"]:
                raise ValueError(f"Invalid step type: {step_type}. Must be 'agent', 'tool', or 'code'")
        
        return v


def validate_task_input(data: Dict[str, Any]) -> TaskRequest:
    """Validate and return TaskRequest"""
    try:
        return TaskRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid task request: {e}")


def validate_code_input(data: Dict[str, Any]) -> CodeRequest:
    """Validate and return CodeRequest"""
    try:
        return CodeRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid code request: {e}")


def validate_tool_input(data: Dict[str, Any]) -> ToolExecutionRequest:
    """Validate and return ToolExecutionRequest"""
    try:
        return ToolExecutionRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid tool request: {e}")


def validate_project_index_input(data: Dict[str, Any]) -> ProjectIndexRequest:
    """Validate and return ProjectIndexRequest"""
    try:
        return ProjectIndexRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid project index request: {e}")


def validate_workflow_input(data: Dict[str, Any]) -> WorkflowRequest:
    """Validate and return WorkflowRequest"""
    try:
        return WorkflowRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid workflow request: {e}")

