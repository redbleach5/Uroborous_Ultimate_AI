"""
Web search and API tools
"""

import httpx
import re
from typing import Dict, Any, List, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput
from ..core.exceptions import ToolException
from ..safety.guard import SafetyGuard


class WebSearchTool(BaseTool):
    """Tool for web search using DuckDuckGo (no API key required)"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="web_search",
            description="Поиск информации в интернете",
            safety_guard=safety_guard
        )
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self.base_url = "https://html.duckduckgo.com/html/"
    
    async def _search_duckduckgo(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search using DuckDuckGo HTML interface
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of search results
        """
        try:
            # DuckDuckGo HTML search
            params = {
                "q": query,
                "kl": "ru-ru"  # Russian language
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = await self.client.get(
                self.base_url,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # Parse HTML results
            html = response.text
            results = []
            
            # Extract results from DuckDuckGo HTML
            # DuckDuckGo uses specific classes for results
            title_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>([^<]+)</a>'
            
            titles = re.findall(title_pattern, html)
            snippets = re.findall(snippet_pattern, html)
            
            # Combine titles and snippets
            for i, (url, title) in enumerate(titles[:max_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                results.append({
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippet.strip()
                })
            
            # If HTML parsing didn't work, try API endpoint (lite version)
            if not results:
                api_url = "https://api.duckduckgo.com/"
                api_params = {
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1"
                }
                
                api_response = await self.client.get(api_url, params=api_params, headers=headers)
                api_response.raise_for_status()
                api_data = api_response.json()
                
                # Extract from API response
                if api_data.get("Results"):
                    for result in api_data["Results"][:max_results]:
                        results.append({
                            "title": result.get("Text", ""),
                            "url": result.get("FirstURL", ""),
                            "snippet": result.get("Text", "")
                        })
                
                # Also check RelatedTopics
                if not results and api_data.get("RelatedTopics"):
                    for topic in api_data["RelatedTopics"][:max_results]:
                        if isinstance(topic, dict) and "FirstURL" in topic:
                            results.append({
                                "title": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                                "snippet": topic.get("Text", "")
                            })
            
            return results[:max_results]
            
        except Exception as e:
            logger.warning(f"DuckDuckGo search error: {e}")
            return []
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Search the web"""
        query = input_data.get("query")
        max_results = input_data.get("max_results", 10)
        
        if not query:
            return ToolOutput(success=False, result=None, error="query required")
        
        if max_results > 20:
            max_results = 20  # Limit to 20 results
        
        try:
            results = await self._search_duckduckgo(query, max_results)
            
            if not results:
                return ToolOutput(
                    success=True,
                    result={
                        "query": query,
                        "results": [],
                        "message": "No results found. Try a different query."
                    }
                )
            
            return ToolOutput(
                success=True,
                result={
                    "query": query,
                    "results": results,
                    "count": len(results)
                }
            )
        except Exception as e:
            logger.error(f"WebSearchTool error: {e}")
            return ToolOutput(
                success=False,
                result=None,
                error=f"Search error: {str(e)}"
            )


class APICallTool(BaseTool):
    """Tool for making API calls"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="api_call",
            description="Выполнение HTTP API запросов",
            safety_guard=safety_guard
        )
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Make API call"""
        url = input_data.get("url")
        method = input_data.get("method", "GET")
        headers = input_data.get("headers", {})
        data = input_data.get("data")
        
        if not url:
            return ToolOutput(success=False, result=None, error="url required")
        
        # Safety check
        if self.safety_guard:
            try:
                self.safety_guard.validate_url(url)
            except Exception as e:
                return ToolOutput(success=False, result=None, error=f"URL validation failed: {e}")
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=headers,
                json=data if method in ["POST", "PUT", "PATCH"] else None,
                params=data if method == "GET" else None
            )
            response.raise_for_status()
            
            return ToolOutput(
                success=True,
                result={
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
                }
            )
        except httpx.HTTPError as e:
            logger.error(f"APICallTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))

