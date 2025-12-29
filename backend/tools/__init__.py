"""
Tools for agents to use

Core tools:
- File tools: read_file, write_file, list_files
- Shell tools: execute_command
- Git tools: git_status, git_commit, git_branch, git_diff, git_log
- Web tools: web_search, api_call
- Database tools: database_query

Extended tools (from OWL integration):
- Browser tools: browser_navigate, browser_click, browser_fill, browser_screenshot, browser_execute_script
- Document tools: document_extract, zip_extract, document_info
"""

from .registry import ToolRegistry
from .base import BaseTool, ToolOutput

# Browser tools (optional - requires playwright)
try:
    from .browser_tools import (
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserFillTool,
        BrowserScreenshotTool,
        BrowserExecuteScriptTool,
    )
    HAS_BROWSER_TOOLS = True
except ImportError:
    HAS_BROWSER_TOOLS = False

# Document tools (optional - requires various parsers)
try:
    from .document_tools import (
        DocumentExtractTool,
        ZipExtractTool,
        DocumentInfoTool,
    )
    HAS_DOCUMENT_TOOLS = True
except ImportError:
    HAS_DOCUMENT_TOOLS = False

__all__ = [
    "ToolRegistry",
    "BaseTool",
    "ToolOutput",
    "HAS_BROWSER_TOOLS",
    "HAS_DOCUMENT_TOOLS",
]

