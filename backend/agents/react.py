"""
ReactAgent - ReAct (Reasoning + Acting) agent for interactive problem solving
"""

import json
import re
from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException, ToolException


class ReactAgent(BaseAgent):
    """ReAct agent that reasons and acts using tools"""
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute task using ReAct approach
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            Result with reasoning and actions
        """
        logger.info(f"ReactAgent executing task: {task}")
        
        if not self.tool_registry:
            raise AgentException("Tool registry required for ReactAgent")
        
        # Get available tools
        tools = await self.tool_registry.list_tools()
        tool_descriptions = "\n".join([
            f"- {name}: {tool.get('description', '')}"
            for name, tool in tools.items()
        ])
        
        system_prompt = f"""You are a helpful AI assistant that can use tools to solve problems. You excel at deep reasoning and step-by-step problem solving.

Available tools:
{tool_descriptions}

Use the following format:
Thought: [your deep reasoning - think step by step, consider multiple approaches, analyze the problem thoroughly]
Action: [tool_name]
Action Input: [tool_input as JSON]
Observation: [result from tool]
... (repeat Thought/Action/Action Input/Observation as needed)
Final Answer: [your final answer]

IMPORTANT GUIDELINES:
- Always think deeply before acting. Consider the problem from multiple angles.
- Break down complex problems into smaller, manageable steps.
- Consider edge cases and potential errors before executing tools.
- Reflect on tool results and adjust your approach if needed.
- Use systematic reasoning to ensure accuracy and completeness.
- When uncertain, think through the implications of each possible action.

You can use tools multiple times. Always think before acting."""
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=f"Task: {task}")
        ]
        
        iteration = 0
        max_iterations = self.max_iterations
        
        while iteration < max_iterations:
            iteration += 1
            
            # Get LLM response with thinking mode enabled for complex reasoning
            # Use thinking mode for complex tasks or when explicitly configured
            use_thinking = self.use_thinking_mode or (
                len(task) > 100 or 
                any(keyword in task.lower() for keyword in ["complex", "analyze", "plan", "design", "optimize", "сложн", "анализ", "план"])
            )
            
            response = await self._get_llm_response(messages, use_thinking=use_thinking)
            messages.append(LLMMessage(role="assistant", content=response))
            
            # Parse response for Thought/Action/Action Input
            thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|Final Answer:|$)", response, re.DOTALL)
            action_match = re.search(r"Action:\s*(\w+)", response)
            action_input_match = re.search(r"Action Input:\s*(.+?)(?=Observation:|$)", response, re.DOTALL)
            final_answer_match = re.search(r"Final Answer:\s*(.+?)$", response, re.DOTALL)
            
            if final_answer_match:
                # Task complete
                final_answer = final_answer_match.group(1).strip()
                logger.info(f"ReactAgent completed task in {iteration} iterations")
                
                return {
                    "agent": self.name,
                    "task": task,
                    "final_answer": final_answer,
                    "iterations": iteration,
                    "success": True
                }
            
            if action_match and action_input_match:
                # Execute tool
                tool_name = action_match.group(1).strip()
                action_input_str = action_input_match.group(1).strip()
                
                try:
                    # Parse action input as JSON
                    try:
                        action_input = json.loads(action_input_str)
                    except json.JSONDecodeError:
                        # If not JSON, treat as string
                        action_input = action_input_str
                    
                    # Execute tool
                    tool_output = await self.tool_registry.execute_tool(
                        tool_name,
                        action_input
                    )
                    
                    if tool_output.success:
                        observation = f"Tool '{tool_name}' executed successfully. Result: {tool_output.result}"
                    else:
                        observation = f"Tool '{tool_name}' execution failed. Error: {tool_output.error}"
                    messages.append(LLMMessage(
                        role="user",
                        content=f"Observation: {observation}"
                    ))
                    
                except ToolException as e:
                    observation = f"Tool '{tool_name}' failed: {str(e)}"
                    messages.append(LLMMessage(
                        role="user",
                        content=f"Observation: {observation}"
                    ))
                except Exception as e:
                    observation = f"Error executing tool '{tool_name}': {str(e)}"
                    messages.append(LLMMessage(
                        role="user",
                        content=f"Observation: {observation}"
                    ))
            else:
                # No clear action, continue reasoning
                logger.warning(f"Could not parse action from response: {response[:200]}")
                messages.append(LLMMessage(
                    role="user",
                    content="Please provide a Thought, Action, and Action Input, or a Final Answer."
                ))
        
        # Max iterations reached
        logger.warning(f"ReactAgent reached max iterations ({max_iterations})")
        return {
            "agent": self.name,
            "task": task,
            "error": "Max iterations reached",
            "iterations": iteration,
            "success": False
        }

