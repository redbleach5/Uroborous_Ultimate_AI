"""
Web search and API tools
"""

import httpx
import re
import asyncio
from typing import Dict, Any, List, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput
from ..core.exceptions import ToolException
from ..safety.guard import SafetyGuard


# Try to use duckduckgo-search library (more reliable than HTML scraping)
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    logger.warning("duckduckgo-search not installed. Install with: pip install duckduckgo-search")


class WebSearchTool(BaseTool):
    """Tool for web search using DuckDuckGo"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="web_search",
            description="Поиск информации в интернете",
            safety_guard=safety_guard
        )
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    async def _search_with_ddgs(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search using duckduckgo-search library (recommended method)
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of search results
        """
        if not HAS_DDGS:
            return []
        
        try:
            # Run sync DDGS in executor to not block async loop
            def do_search():
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, region='ru-ru', max_results=max_results))
                    return results
            
            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(None, do_search)
            
            results = []
            for item in raw_results:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", item.get("link", "")),
                    "snippet": item.get("body", item.get("snippet", ""))
                })
            
            logger.info(f"DDGS search returned {len(results)} results for: {query[:50]}")
            return results
            
        except Exception as e:
            logger.warning(f"DDGS search error: {e}")
            return []
    
    async def _search_duckduckgo_lite(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fallback: Search using DuckDuckGo Lite (text-only, less likely to be blocked)
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of search results
        """
        try:
            # DuckDuckGo Lite endpoint (simpler, text-only)
            url = "https://lite.duckduckgo.com/lite/"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            
            data = {"q": query}
            
            response = await self.client.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            html = response.text
            results = []
            
            # Parse lite results (simpler HTML structure)
            # Pattern for lite version links
            link_pattern = r'<a[^>]*rel="nofollow"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(link_pattern, html)
            
            # Filter out DuckDuckGo internal links
            for link_url, title in matches:
                if link_url.startswith('http') and 'duckduckgo.com' not in link_url:
                    results.append({
                        "title": title.strip(),
                        "url": link_url,
                        "snippet": ""
                    })
                    if len(results) >= max_results:
                        break
            
            return results
            
        except Exception as e:
            logger.warning(f"DuckDuckGo Lite search error: {e}")
            return []
    
    async def _search_duckduckgo_api(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fallback: Use DuckDuckGo Instant Answer API
        Note: This API only returns instant answers, not web results
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of search results
        """
        try:
            api_url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1"
            }
            
            headers = {
                "User-Agent": "AILLM/1.0 (AI Assistant)"
            }
            
            response = await self.client.get(api_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            # Abstract (main answer)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Answer"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("Abstract", "")
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results - len(results)]:
                if isinstance(topic, dict) and "FirstURL" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "")
                    })
            
            return results
            
        except Exception as e:
            logger.warning(f"DuckDuckGo API error: {e}")
            return []
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Search the web using multiple methods"""
        query = input_data.get("query")
        max_results = input_data.get("max_results", 10)
        
        if not query:
            return ToolOutput(success=False, result=None, error="query required")
        
        if max_results > 20:
            max_results = 20
        
        try:
            results = []
            
            # Method 1: Use duckduckgo-search library (best)
            if HAS_DDGS:
                results = await self._search_with_ddgs(query, max_results)
            
            # Method 2: DuckDuckGo Lite (fallback)
            if not results:
                logger.info("Trying DuckDuckGo Lite fallback...")
                results = await self._search_duckduckgo_lite(query, max_results)
            
            # Method 3: DuckDuckGo Instant Answer API (last resort)
            if not results:
                logger.info("Trying DuckDuckGo API fallback...")
                results = await self._search_duckduckgo_api(query, max_results)
            
            if not results:
                return ToolOutput(
                    success=True,
                    result={
                        "query": query,
                        "results": [],
                        "message": "Поиск не дал результатов. DuckDuckGo может блокировать запросы. Установите duckduckgo-search: pip install duckduckgo-search"
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
