"""
IntegrationAgent - Integrates with external services
"""

from typing import Dict, Any, Optional
import httpx
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException


class IntegrationAgent(BaseAgent):
    """Agent for integrating with external services and APIs"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_client: Optional[httpx.AsyncClient] = None
    
    async def initialize(self) -> None:
        """Initialize integration agent"""
        await super().initialize()
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def shutdown(self) -> None:
        """Shutdown integration agent"""
        if self.http_client:
            await self.http_client.aclose()
        await super().shutdown()
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute integration task
        
        Args:
            task: Integration task description
            context: Additional context (API endpoints, credentials, etc.)
            
        Returns:
            Integration results
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"IntegrationAgent executing task: {task}")
        
        system_prompt = """You are an integration specialist. Your task is to integrate with external services, APIs, and systems.

Capabilities:
- REST API integration
- GraphQL API integration
- Database connections
- Webhook handling
- Authentication and authorization
- Data transformation
- Error handling and retries
- Rate limiting

Provide integration code and configuration."""
        
        user_prompt = f"""Integration Task: {task}

"""
        
        if context:
            if "api_endpoint" in context:
                user_prompt += f"API endpoint: {context['api_endpoint']}\n"
            if "api_type" in context:
                user_prompt += f"API type: {context['api_type']} (REST/GraphQL)\n"
            if "authentication" in context:
                user_prompt += f"Authentication: {context['authentication']}\n"
        
        user_prompt += "\nPlease provide integration code and configuration."
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        try:
            integration_code = await self._get_llm_response(messages)
            
            result = {
                "agent": self.name,
                "task": task,
                "integration_code": integration_code,
                "success": True
            }
            
            # Save to memory
            if self.memory:
                await self.memory.save_solution(
                    task=task,
                    solution=integration_code,
                    agent=self.name,
                    metadata=context
                )
            
            return result
            
        except Exception as e:
            logger.error(f"IntegrationAgent error: {e}")
            raise AgentException(f"Integration failed: {e}") from e
    
    async def call_api(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call external API
        
        Args:
            url: API endpoint URL
            method: HTTP method
            headers: HTTP headers
            data: Request data
            
        Returns:
            API response
        """
        if not self.http_client:
            raise AgentException("HTTP client not initialized")
        
        try:
            response = await self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                json=data
            )
            response.raise_for_status()
            
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            }
        except httpx.HTTPError as e:
            logger.error(f"API call error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

