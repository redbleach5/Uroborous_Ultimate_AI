"""
Shell command execution tools
"""

import asyncio
from typing import Dict, Any
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput


class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="execute_command",
            description="Выполнение shell команды",
            safety_guard=safety_guard
        )
        # reasonable defaults to avoid hanging executions
        self.default_timeout = 60  # seconds
        self.max_output_len = 20000  # chars per stream
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Execute shell command"""
        command = input_data.get("command")
        timeout = input_data.get("timeout", self.default_timeout)
        if not command:
            return ToolOutput(success=False, result=None, error="command required")
        
        # Safety check
        if self.safety_guard:
            if not self.safety_guard.validate_command(command):
                return ToolOutput(success=False, result=None, error="Command not allowed by safety guard")
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return ToolOutput(
                    success=False,
                    result={
                        "stdout": "",
                        "stderr": "",
                        "returncode": None,
                        "timeout": timeout,
                    },
                    error=f"Command timed out after {timeout}s",
                )

            def _trim(text: str) -> str:
                if len(text) > self.max_output_len:
                    return text[: self.max_output_len] + f"\n...[truncated {len(text) - self.max_output_len} chars]"
                return text

            stdout_decoded = _trim(stdout.decode("utf-8", errors="ignore"))
            stderr_decoded = _trim(stderr.decode("utf-8", errors="ignore"))

            return ToolOutput(
                success=process.returncode == 0,
                result={
                    "stdout": stdout_decoded,
                    "stderr": stderr_decoded,
                    "returncode": process.returncode
                },
                error=stderr_decoded if process.returncode != 0 else None
            )
        except Exception as e:
            logger.error(f"ExecuteCommandTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))

