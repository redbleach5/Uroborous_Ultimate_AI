"""
Tests for validators
"""

import pytest
from backend.core.validators import (
    validate_task_input, validate_code_input, validate_tool_input,
    validate_project_index_input, validate_workflow_input,
    TaskRequest, CodeRequest, ToolExecutionRequest, ProjectIndexRequest, WorkflowRequest
)


def test_validate_task_input_valid():
    """Test valid task input"""
    data = {
        "task": "Create a Python function",
        "agent_type": "code_writer",
        "context": {}
    }
    result = validate_task_input(data)
    assert isinstance(result, TaskRequest)
    assert result.task == "Create a Python function"
    assert result.agent_type == "code_writer"


def test_validate_task_input_empty_task():
    """Test task input with empty task"""
    data = {"task": ""}
    with pytest.raises(ValueError):
        validate_task_input(data)


def test_validate_task_input_invalid_agent():
    """Test task input with invalid agent type"""
    data = {
        "task": "Test task",
        "agent_type": "invalid_agent"
    }
    with pytest.raises(ValueError):
        validate_task_input(data)


def test_validate_code_input_valid():
    """Test valid code input"""
    data = {
        "task": "Generate code",
        "file_path": "test.py"
    }
    result = validate_code_input(data)
    assert isinstance(result, CodeRequest)
    assert result.task == "Generate code"


def test_validate_code_input_empty_task():
    """Test code input with empty task"""
    data = {"task": ""}
    with pytest.raises(ValueError):
        validate_code_input(data)


def test_validate_tool_input_valid():
    """Test valid tool input"""
    data = {
        "tool_name": "read_file",
        "input": {"file_path": "test.txt"}
    }
    result = validate_tool_input(data)
    assert isinstance(result, ToolExecutionRequest)
    assert result.tool_name == "read_file"


def test_validate_tool_input_empty_name():
    """Test tool input with empty name"""
    data = {"tool_name": ""}
    with pytest.raises(ValueError):
        validate_tool_input(data)


def test_validate_project_index_input_valid():
    """Test valid project index input"""
    data = {
        "project_path": "/path/to/project",
        "max_file_size": 500000
    }
    result = validate_project_index_input(data)
    assert isinstance(result, ProjectIndexRequest)
    assert result.project_path == "/path/to/project"


def test_validate_project_index_input_empty_path():
    """Test project index input with empty path"""
    data = {"project_path": ""}
    with pytest.raises(ValueError):
        validate_project_index_input(data)


def test_validate_workflow_input_valid():
    """Test valid workflow input"""
    data = {
        "name": "test_workflow",
        "steps": [
            {
                "name": "step1",
                "type": "agent",
                "agent_type": "code_writer",
                "task": "Generate code"
            }
        ],
        "stop_on_error": True
    }
    result = validate_workflow_input(data)
    assert isinstance(result, WorkflowRequest)
    assert result.name == "test_workflow"
    assert len(result.steps) == 1


def test_validate_workflow_input_no_steps():
    """Test workflow input with no steps"""
    data = {
        "name": "test_workflow",
        "steps": []
    }
    with pytest.raises(ValueError):
        validate_workflow_input(data)


def test_validate_workflow_input_duplicate_step_names():
    """Test workflow input with duplicate step names"""
    data = {
        "name": "test_workflow",
        "steps": [
            {"name": "step1", "type": "agent"},
            {"name": "step1", "type": "tool"}
        ]
    }
    with pytest.raises(ValueError):
        validate_workflow_input(data)


def test_validate_workflow_input_invalid_step_type():
    """Test workflow input with invalid step type"""
    data = {
        "name": "test_workflow",
        "steps": [
            {"name": "step1", "type": "invalid_type"}
        ]
    }
    with pytest.raises(ValueError):
        validate_workflow_input(data)

