"""
Browser automation tools using Playwright

Provides web browser automation capabilities:
- Navigation and page interaction
- Screenshots and content extraction
- Form filling and clicking
- JavaScript execution

Requires: playwright (optional, graceful degradation if not installed)
Install: pip install playwright && playwright install chromium
"""

from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
from .base import BaseTool, ToolOutput

logger = get_logger(__name__)

# Try to import playwright (optional dependency)
try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.info("Playwright not installed. Browser tools will be limited. Install with: pip install playwright && playwright install chromium")


class BrowserNavigateTool(BaseTool):
    """Tool for navigating to URLs and extracting page content"""
    
    def __init__(self, safety_guard=None, headless: bool = True):
        super().__init__(
            name="browser_navigate",
            description="Переход на веб-страницу и получение её содержимого",
            safety_guard=safety_guard
        )
        self.headless = headless
        self._playwright: Optional["Playwright"] = None
        self._browser: Optional["Browser"] = None
        self._page: Optional["Page"] = None
        self._initialized = False
    
    async def _ensure_browser(self) -> bool:
        """Ensure browser is initialized"""
        if not HAS_PLAYWRIGHT:
            return False
        
        if self._initialized and self._page:
            return True
        
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            )
            self._page = await self._browser.new_page()
            
            # Set reasonable viewport and user agent
            await self._page.set_viewport_size({"width": 1280, "height": 720})
            
            self._initialized = True
            logger.info("Browser initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Navigate to URL and optionally extract content"""
        url = input_data.get("url")
        extract_text = input_data.get("extract_text", True)
        wait_for = input_data.get("wait_for", "networkidle")
        timeout = input_data.get("timeout", 30000)
        
        if not url:
            return ToolOutput(success=False, result=None, error="url required")
        
        # Safety check
        if self.safety_guard:
            try:
                self.safety_guard.validate_url(url)
            except Exception as e:
                return ToolOutput(success=False, result=None, error=f"URL validation failed: {e}")
        
        if not HAS_PLAYWRIGHT:
            return ToolOutput(
                success=False,
                result=None,
                error="Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        
        try:
            if not await self._ensure_browser():
                return ToolOutput(
                    success=False,
                    result=None,
                    error="Failed to initialize browser"
                )
            
            # Navigate to URL
            response = await self._page.goto(
                url,
                wait_until=wait_for,
                timeout=timeout
            )
            
            result = {
                "url": url,
                "final_url": self._page.url,
                "title": await self._page.title(),
                "status": response.status if response else None,
            }
            
            # Extract text content if requested
            if extract_text:
                try:
                    content = await self._page.inner_text("body")
                    # Limit content length to prevent token overflow
                    result["content"] = content[:10000] if len(content) > 10000 else content
                    result["content_length"] = len(content)
                except Exception as e:
                    result["content"] = f"Could not extract text: {e}"
            
            logger.info(f"Navigated to {url}, title: {result.get('title', 'N/A')[:50]}")
            
            return ToolOutput(success=True, result=result)
            
        except Exception as e:
            logger.error(f"BrowserNavigateTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))
    
    async def shutdown(self) -> None:
        """Close browser and cleanup resources"""
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._initialized = False
            logger.debug("Browser shutdown complete")
        except Exception as e:
            logger.warning(f"Error during browser shutdown: {e}")


class BrowserClickTool(BaseTool):
    """Tool for clicking elements on web pages"""
    
    def __init__(self, safety_guard=None, browser_tool: Optional[BrowserNavigateTool] = None):
        super().__init__(
            name="browser_click",
            description="Клик на элемент веб-страницы по селектору",
            safety_guard=safety_guard
        )
        self._browser_tool = browser_tool
    
    def set_browser_tool(self, browser_tool: BrowserNavigateTool) -> None:
        """Set the browser tool for shared browser instance"""
        self._browser_tool = browser_tool
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Click an element on the page"""
        selector = input_data.get("selector")
        timeout = input_data.get("timeout", 5000)
        
        if not selector:
            return ToolOutput(success=False, result=None, error="selector required")
        
        if not HAS_PLAYWRIGHT:
            return ToolOutput(
                success=False,
                result=None,
                error="Playwright not installed"
            )
        
        if not self._browser_tool or not self._browser_tool._page:
            return ToolOutput(
                success=False,
                result=None,
                error="Browser not initialized. Use browser_navigate first."
            )
        
        try:
            page = self._browser_tool._page
            
            # Wait for element and click
            await page.wait_for_selector(selector, timeout=timeout)
            await page.click(selector)
            
            # Wait for potential navigation
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            return ToolOutput(
                success=True,
                result={
                    "clicked": selector,
                    "current_url": page.url,
                    "current_title": await page.title()
                }
            )
            
        except Exception as e:
            logger.error(f"BrowserClickTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))


class BrowserFillTool(BaseTool):
    """Tool for filling form inputs"""
    
    def __init__(self, safety_guard=None, browser_tool: Optional[BrowserNavigateTool] = None):
        super().__init__(
            name="browser_fill",
            description="Заполнение поля ввода на веб-странице",
            safety_guard=safety_guard
        )
        self._browser_tool = browser_tool
    
    def set_browser_tool(self, browser_tool: BrowserNavigateTool) -> None:
        """Set the browser tool for shared browser instance"""
        self._browser_tool = browser_tool
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Fill a form input"""
        selector = input_data.get("selector")
        text = input_data.get("text", "")
        clear_first = input_data.get("clear_first", True)
        timeout = input_data.get("timeout", 5000)
        
        if not selector:
            return ToolOutput(success=False, result=None, error="selector required")
        
        if not HAS_PLAYWRIGHT:
            return ToolOutput(
                success=False,
                result=None,
                error="Playwright not installed"
            )
        
        if not self._browser_tool or not self._browser_tool._page:
            return ToolOutput(
                success=False,
                result=None,
                error="Browser not initialized. Use browser_navigate first."
            )
        
        try:
            page = self._browser_tool._page
            
            # Wait for element
            await page.wait_for_selector(selector, timeout=timeout)
            
            if clear_first:
                await page.fill(selector, "")
            
            await page.fill(selector, text)
            
            return ToolOutput(
                success=True,
                result={
                    "filled": selector,
                    "text_length": len(text)
                }
            )
            
        except Exception as e:
            logger.error(f"BrowserFillTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))


class BrowserScreenshotTool(BaseTool):
    """Tool for taking page screenshots"""
    
    def __init__(self, safety_guard=None, browser_tool: Optional[BrowserNavigateTool] = None):
        super().__init__(
            name="browser_screenshot",
            description="Снимок экрана веб-страницы",
            safety_guard=safety_guard
        )
        self._browser_tool = browser_tool
    
    def set_browser_tool(self, browser_tool: BrowserNavigateTool) -> None:
        """Set the browser tool for shared browser instance"""
        self._browser_tool = browser_tool
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Take a screenshot"""
        path = input_data.get("path", "screenshot.png")
        full_page = input_data.get("full_page", False)
        
        if not HAS_PLAYWRIGHT:
            return ToolOutput(
                success=False,
                result=None,
                error="Playwright not installed"
            )
        
        if not self._browser_tool or not self._browser_tool._page:
            return ToolOutput(
                success=False,
                result=None,
                error="Browser not initialized. Use browser_navigate first."
            )
        
        # Safety check for path
        if self.safety_guard:
            if not self.safety_guard.validate_path(path):
                return ToolOutput(success=False, result=None, error="Invalid or unsafe path")
        
        try:
            page = self._browser_tool._page
            
            screenshot_bytes = await page.screenshot(
                path=path,
                full_page=full_page,
                type="png"
            )
            
            return ToolOutput(
                success=True,
                result={
                    "path": path,
                    "size_bytes": len(screenshot_bytes),
                    "full_page": full_page,
                    "page_url": page.url
                }
            )
            
        except Exception as e:
            logger.error(f"BrowserScreenshotTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))


class BrowserExecuteScriptTool(BaseTool):
    """Tool for executing JavaScript on page"""
    
    def __init__(self, safety_guard=None, browser_tool: Optional[BrowserNavigateTool] = None):
        super().__init__(
            name="browser_execute_script",
            description="Выполнение JavaScript кода на веб-странице",
            safety_guard=safety_guard
        )
        self._browser_tool = browser_tool
    
    def set_browser_tool(self, browser_tool: BrowserNavigateTool) -> None:
        """Set the browser tool for shared browser instance"""
        self._browser_tool = browser_tool
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Execute JavaScript code"""
        script = input_data.get("script")
        
        if not script:
            return ToolOutput(success=False, result=None, error="script required")
        
        if not HAS_PLAYWRIGHT:
            return ToolOutput(
                success=False,
                result=None,
                error="Playwright not installed"
            )
        
        if not self._browser_tool or not self._browser_tool._page:
            return ToolOutput(
                success=False,
                result=None,
                error="Browser not initialized. Use browser_navigate first."
            )
        
        try:
            page = self._browser_tool._page
            
            result = await page.evaluate(script)
            
            return ToolOutput(
                success=True,
                result={
                    "output": result,
                    "page_url": page.url
                }
            )
            
        except Exception as e:
            logger.error(f"BrowserExecuteScriptTool error: {e}")
            return ToolOutput(success=False, result=None, error=str(e))

