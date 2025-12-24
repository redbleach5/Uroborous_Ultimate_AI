"""
Safety Guard - Validates commands and paths for security
"""

import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..core.exceptions import SafetyException


class SafetyGuard:
    """
    Safety guard for validating commands, paths, and URLs
    Protects against SSRF, XSS, and dangerous operations
    """
    
    def __init__(self, config):
        """
        Initialize safety guard
        
        Args:
            config: Safety configuration (dict or Pydantic model)
        """
        self.config = config
        
        # Handle both dict and Pydantic model
        if isinstance(config, dict):
            self.enabled = config.get("enabled", True)
            self.sandbox = config.get("sandbox", False)
            self.allowed_commands = config.get("allowed_commands", [])
            self.blocked_patterns = config.get("blocked_patterns", [])
        else:
            # Pydantic model
            self.enabled = getattr(config, "enabled", True)
            self.sandbox = getattr(config, "sandbox", False)
            self.allowed_commands = getattr(config, "allowed_commands", [])
            self.blocked_patterns = getattr(config, "blocked_patterns", [])
        
        # Default dangerous patterns
        self.default_blocked_patterns = [
            r"rm\s+-rf\s+/",
            r"format\s+c:",
            r"del\s+/f\s+/s",
            r"mkfs",
            r"dd\s+if=",
            r">\s+/dev/",
        ]
        
        # Filter out non-string patterns (dicts, None, etc.) and convert to strings
        valid_patterns = []
        for pattern in self.blocked_patterns:
            if isinstance(pattern, str) and pattern.strip():
                valid_patterns.append(pattern)
            elif isinstance(pattern, dict):
                # Skip empty dicts from YAML config
                logger.warning(f"Skipping invalid pattern (dict): {pattern}")
        
        # Compile regex patterns
        self.blocked_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in valid_patterns + self.default_blocked_patterns
        ]
    
    def validate_command(self, command: str) -> bool:
        """
        Validate shell command for safety
        
        Args:
            command: Command to validate
            
        Returns:
            True if command is safe
            
        Raises:
            SafetyException: If command is dangerous
        """
        if not self.enabled:
            return True
        
        # Check blocked patterns
        for pattern in self.blocked_regex:
            if pattern.search(command):
                logger.warning(f"Blocked dangerous command: {command[:100]}")
                raise SafetyException(f"Command blocked by safety guard: dangerous pattern detected")
        
        # Check allowed commands list (if specified)
        if self.allowed_commands:
            # Extract base command
            base_cmd = command.split()[0] if command.split() else ""
            if base_cmd not in self.allowed_commands:
                logger.warning(f"Command not in allowed list: {base_cmd}")
                raise SafetyException(f"Command not allowed: {base_cmd}")
        
        return True
    
    def validate_path(self, path: str) -> bool:
        """
        Validate file path for safety
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is safe
            
        Raises:
            SafetyException: If path is dangerous
        """
        if not self.enabled:
            return True
        
        try:
            path_obj = Path(path).resolve()
            
            # Check for path traversal
            if ".." in path:
                logger.warning(f"Blocked path traversal attempt: {path}")
                raise SafetyException("Path traversal detected")
            
            # Check for absolute paths to system directories (if sandboxed)
            if self.sandbox:
                dangerous_paths = ["/etc", "/sys", "/proc", "/dev", "C:\\Windows"]
                for dangerous in dangerous_paths:
                    if str(path_obj).startswith(dangerous):
                        logger.warning(f"Blocked access to system path: {path}")
                        raise SafetyException(f"Access to system path blocked: {dangerous}")
            
            return True
        except Exception as e:
            if isinstance(e, SafetyException):
                raise
            logger.error(f"Path validation error: {e}")
            raise SafetyException(f"Invalid path: {e}") from e
    
    def validate_url(self, url: str) -> bool:
        """
        Validate URL for SSRF protection
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL is safe
            
        Raises:
            SafetyException: If URL is dangerous
        """
        if not self.enabled:
            return True
        
        try:
            parsed = urlparse(url)
            
            # Block private IP ranges
            hostname = parsed.hostname
            if hostname:
                # Check for localhost variants
                if hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
                    logger.warning(f"Blocked localhost URL: {url}")
                    raise SafetyException("Localhost URLs blocked for SSRF protection")
                
                # Check for private IP ranges (simplified)
                if hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.startswith("172."):
                    logger.warning(f"Blocked private IP URL: {url}")
                    raise SafetyException("Private IP URLs blocked for SSRF protection")
            
            # Only allow http/https
            if parsed.scheme not in ["http", "https"]:
                logger.warning(f"Blocked non-HTTP URL: {url}")
                raise SafetyException(f"Only HTTP/HTTPS URLs allowed, got: {parsed.scheme}")
            
            return True
        except Exception as e:
            if isinstance(e, SafetyException):
                raise
            logger.error(f"URL validation error: {e}")
            raise SafetyException(f"Invalid URL: {e}") from e

