"""
WorkflowAgent - Manages and executes workflows
"""

import asyncio
import ast
import sys
import io
import traceback
from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException


class WorkflowAgent(BaseAgent):
    """Agent for managing and executing workflows"""
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute workflow task
        
        Args:
            task: Workflow task description
            context: Additional context including workflow definition
            
        Returns:
            Workflow execution result
        """
        logger.info(f"WorkflowAgent executing task: {task}")
        
        # Get workflow definition from context or task
        workflow_definition = context.get("workflow") or {}
        
        if not workflow_definition:
            # Try to parse workflow from task
            workflow_definition = await self._parse_workflow_from_task(task)
        
        # Validate workflow
        if not self._validate_workflow(workflow_definition):
            return {
                "success": False,
                "error": "Invalid workflow definition"
            }
        
        # Execute workflow steps
        steps = workflow_definition.get("steps", [])
        results = []
        
        for step in steps:
            step_result = await self._execute_step(step, context)
            results.append(step_result)
            
            # Stop on error if configured
            if not step_result.get("success") and workflow_definition.get("stop_on_error", True):
                return {
                    "success": False,
                    "error": f"Workflow stopped at step: {step.get('name')}",
                    "results": results
                }
        
        return {
            "success": True,
            "workflow": workflow_definition.get("name", "unnamed"),
            "steps_executed": len(steps),
            "results": results
        }
    
    async def _parse_workflow_from_task(self, task: str) -> Dict[str, Any]:
        """Parse workflow definition from task description"""
        # Get context for LLM
        context_text = await self._get_context(task)
        
        system_prompt = """You are a workflow parser. Your task is to extract workflow definition from task description.

Workflow format:
{
  "name": "workflow_name",
  "steps": [
    {
      "name": "step1",
      "type": "agent|tool|code",
      "task": "description",
      "agent_type": "code_writer" (if type is agent),
      "dependencies": [] (step names that must complete first)
    }
  ],
  "stop_on_error": true
}

Return only valid JSON workflow definition."""
        
        user_prompt = f"""Task: {task}

{context_text if context_text else ""}

Extract workflow definition from this task."""
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        try:
            response = await self.llm_manager.generate(
                messages=messages,
                max_tokens=2000
            )
            
            # Parse JSON from response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                workflow = json.loads(json_match.group())
                return workflow
            else:
                logger.warning("Could not parse workflow from LLM response")
                return {
                    "name": "parsing_failed",
                    "steps": [],
                    "error": "Could not parse workflow definition from LLM response"
                }
        except Exception as e:
            logger.error(f"Error parsing workflow: {e}")
            return {
                "name": "parsing_error",
                "steps": [],
                "error": f"Error parsing workflow: {str(e)}"
            }
    
    def _validate_workflow(self, workflow: Dict[str, Any]) -> bool:
        """Validate workflow definition"""
        if not isinstance(workflow, dict):
            return False
        
        if "steps" not in workflow:
            return False
        
        if not isinstance(workflow["steps"], list):
            return False
        
        # Validate each step
        step_names = set()
        for step in workflow["steps"]:
            if not isinstance(step, dict):
                return False
            
            if "name" not in step or "type" not in step:
                return False
            
            if step["name"] in step_names:
                return False  # Duplicate step name
            step_names.add(step["name"])
            
            if step["type"] not in ["agent", "tool", "code"]:
                return False
        
        # Check dependencies
        for step in workflow["steps"]:
            deps = step.get("dependencies", [])
            for dep in deps:
                if dep not in step_names:
                    return False  # Invalid dependency
        
        return True
    
    async def _execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow step"""
        step_type = step.get("type")
        step_name = step.get("name", "unnamed")
        
        logger.info(f"Executing workflow step: {step_name} (type: {step_type})")
        
        try:
            if step_type == "agent":
                agent_type = step.get("agent_type")
                if not agent_type:
                    return {"success": False, "error": "agent_type required for agent steps"}
                
                agent = await self.agent_registry.get_agent(agent_type)
                if not agent:
                    return {"success": False, "error": f"Agent {agent_type} not found"}
                
                task = step.get("task", "")
                result = await agent.execute(task, context)
                return {"success": True, "step": step_name, "result": result}
            
            elif step_type == "tool":
                tool_name = step.get("tool_name")
                if not tool_name:
                    return {"success": False, "error": "tool_name required for tool steps"}
                
                tool_input = step.get("input", {})
                tool_output = await self.tool_registry.execute_tool(tool_name, tool_input)
                if tool_output.success:
                    return {"success": True, "step": step_name, "result": tool_output.result}
                else:
                    return {"success": False, "step": step_name, "error": tool_output.error}
            
            elif step_type == "code":
                # Execute Python code (with safety checks)
                code = step.get("code", "")
                if not code:
                    return {"success": False, "error": "code required for code steps"}
                
                # Execute code safely
                result = await self._execute_code_safely(code, context)
                return result
            
            else:
                return {"success": False, "error": f"Unknown step type: {step_type}"}
        
        except Exception as e:
            logger.error(f"Error executing step {step_name}: {e}")
            return {"success": False, "error": str(e), "step": step_name}
    
    async def _execute_code_safely(self, code: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Python code safely with restrictions
        
        Args:
            code: Python code to execute
            context: Context variables available to code
            
        Returns:
            Execution result
        """
        # Validate code syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {
                "success": False,
                "error": f"Syntax error in code: {str(e)}",
                "step": "code"
            }
        
        # Check for dangerous operations
        dangerous_patterns = [
            "__import__", "eval", "exec", "compile", "open", "file",
            "input", "raw_input", "execfile", "reload", "__builtins__",
            "subprocess", "os.system", "os.popen", "os.spawn", "os.exec",
            "shutil", "pickle", "marshal", "ctypes", "socket", "urllib",
            "requests", "httpx", "aiohttp", "sqlite3", "psycopg2", "pymongo"
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                return {
                    "success": False,
                    "error": f"Dangerous operation detected: {pattern}. Code execution is restricted for security.",
                    "step": "code"
                }
        
        # Allowed safe imports
        safe_modules = {
            "math", "random", "datetime", "time", "json", "collections",
            "itertools", "functools", "operator", "string", "re",
            "decimal", "fractions", "statistics", "numpy", "pandas"
        }
        
        # Parse AST to check imports
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[0] not in safe_modules:
                            return {
                                "success": False,
                                "error": f"Import of '{alias.name}' is not allowed. Only safe modules are permitted.",
                                "step": "code"
                            }
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] not in safe_modules:
                        return {
                            "success": False,
                            "error": f"Import from '{node.module}' is not allowed. Only safe modules are permitted.",
                            "step": "code"
                        }
        except Exception as e:
            logger.warning(f"Error checking imports: {e}")
        
        # Prepare safe execution environment
        safe_builtins = {
            'abs', 'all', 'any', 'bin', 'bool', 'chr', 'dict', 'dir',
            'divmod', 'enumerate', 'filter', 'float', 'format', 'hex',
            'int', 'isinstance', 'len', 'list', 'map', 'max', 'min',
            'oct', 'ord', 'pow', 'print', 'range', 'repr', 'reversed',
            'round', 'set', 'sorted', 'str', 'sum', 'tuple', 'type',
            'zip', 'True', 'False', 'None'
        }
        
        # Create restricted globals
        # Handle both dict and module types for __builtins__
        import builtins
        safe_builtins_dict = {}
        for name in safe_builtins:
            if hasattr(builtins, name):
                safe_builtins_dict[name] = getattr(builtins, name)
        
        restricted_globals = {
            '__builtins__': safe_builtins_dict,
            '__name__': '__main__',
            '__doc__': None
        }
        
        # Add context variables
        restricted_globals.update(context.get("variables", {}))
        
        # Capture stdout/stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Execute code with timeout
            async def run_code():
                try:
                    # Compile and execute in restricted environment
                    compiled_code = compile(code, '<string>', 'exec')
                    exec(compiled_code, restricted_globals, {})
                    return {"success": True, "output": stdout_capture.getvalue()}
                except Exception as e:
                    error_msg = stderr_capture.getvalue() or str(e)
                    return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
            
            # Execute with timeout (30 seconds default)
            timeout = context.get("code_timeout", 30)
            result = await asyncio.wait_for(run_code(), timeout=timeout)
            
            return {
                "success": result.get("success", False),
                "step": "code",
                "output": result.get("output", ""),
                "error": result.get("error"),
                "traceback": result.get("traceback")
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after {timeout} seconds",
                "step": "code"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error: {str(e)}",
                "step": "code",
                "traceback": traceback.format_exc()
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
