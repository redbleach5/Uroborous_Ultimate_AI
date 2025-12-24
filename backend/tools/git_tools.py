"""
Git tools
"""

from typing import Dict, Any
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput
from .shell_tools import ExecuteCommandTool


class GitStatusTool(BaseTool):
    """Tool for checking git status"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="git_status",
            description="Получить статус git репозитория",
            safety_guard=safety_guard
        )
        self.cmd_tool = ExecuteCommandTool(safety_guard)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Get git status"""
        result = await self.cmd_tool.execute({"command": "git status"})
        return result


class GitCommitTool(BaseTool):
    """Tool for making git commits"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="git_commit",
            description="Создать git коммит",
            safety_guard=safety_guard
        )
        self.cmd_tool = ExecuteCommandTool(safety_guard)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Create git commit"""
        message = input_data.get("message", "Auto commit")
        add_all = input_data.get("add_all", False)
        
        commands = []
        if add_all:
            commands.append("git add -A")
        commands.append(f'git commit -m "{message}"')
        
        for cmd in commands:
            result = await self.cmd_tool.execute({"command": cmd})
            if not result.success:
                return result
        
        return ToolOutput(success=True, result={"message": "Commit created successfully"})


class GitBranchTool(BaseTool):
    """Tool for managing git branches"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="git_branch",
            description="Создать, список или переключить git ветки",
            safety_guard=safety_guard
        )
        self.cmd_tool = ExecuteCommandTool(safety_guard)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Manage git branches"""
        action = input_data.get("action", "list")  # list, create, switch, delete
        
        if action == "list":
            result = await self.cmd_tool.execute({"command": "git branch -a"})
            return result
        elif action == "create":
            branch_name = input_data.get("branch_name")
            if not branch_name:
                return ToolOutput(success=False, result=None, error="branch_name required")
            result = await self.cmd_tool.execute({"command": f"git checkout -b {branch_name}"})
            return result
        elif action == "switch":
            branch_name = input_data.get("branch_name")
            if not branch_name:
                return ToolOutput(success=False, result=None, error="branch_name required")
            result = await self.cmd_tool.execute({"command": f"git checkout {branch_name}"})
            return result
        elif action == "delete":
            branch_name = input_data.get("branch_name")
            if not branch_name:
                return ToolOutput(success=False, result=None, error="branch_name required")
            force = input_data.get("force", False)
            cmd = f"git branch -D {branch_name}" if force else f"git branch -d {branch_name}"
            result = await self.cmd_tool.execute({"command": cmd})
            return result
        else:
            return ToolOutput(success=False, result=None, error=f"Unknown action: {action}")


class GitDiffTool(BaseTool):
    """Tool for viewing git diffs"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="git_diff",
            description="Просмотр различий в git",
            safety_guard=safety_guard
        )
        self.cmd_tool = ExecuteCommandTool(safety_guard)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """View git diff"""
        file_path = input_data.get("file_path")
        commit1 = input_data.get("commit1")
        commit2 = input_data.get("commit2")
        
        if commit1 and commit2:
            cmd = f"git diff {commit1} {commit2}"
        elif file_path:
            cmd = f"git diff {file_path}"
        else:
            cmd = "git diff"
        
        result = await self.cmd_tool.execute({"command": cmd})
        return result


class GitLogTool(BaseTool):
    """Tool for viewing git log"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="git_log",
            description="Просмотр истории git коммитов",
            safety_guard=safety_guard
        )
        self.cmd_tool = ExecuteCommandTool(safety_guard)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """View git log"""
        n = input_data.get("n", 10)  # Number of commits
        file_path = input_data.get("file_path")
        
        cmd = f"git log -n {n} --oneline"
        if file_path:
            cmd += f" -- {file_path}"
        
        result = await self.cmd_tool.execute({"command": cmd})
        return result
