"""
Safety Guard - Validates commands and paths for security
"""

import re
import time
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse
from collections import defaultdict
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..core.exceptions import SafetyException


class URLRateLimiter:
    """
    Rate limiter специально для URL запросов.
    Защищает от DDoS и злоупотреблений API.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 30,
        requests_per_hour: int = 300,
        burst_limit: int = 10,  # Максимум запросов за 5 сек
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_limit = burst_limit
        
        # {domain: [timestamps]}
        self._requests: Dict[str, list] = defaultdict(list)
        self._last_cleanup = time.time()
    
    def _cleanup(self):
        """Очистка старых записей"""
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        
        cutoff = now - 3600  # 1 час
        for domain in list(self._requests.keys()):
            self._requests[domain] = [t for t in self._requests[domain] if t > cutoff]
            if not self._requests[domain]:
                del self._requests[domain]
        self._last_cleanup = now
    
    def check_and_record(self, url: str) -> tuple:
        """
        Проверяет rate limit и записывает запрос.
        
        Returns:
            (allowed: bool, error_message: str or None)
        """
        self._cleanup()
        
        try:
            parsed = urlparse(url)
            domain = parsed.hostname or "unknown"
        except Exception:
            domain = "unknown"
        
        now = time.time()
        requests = self._requests[domain]
        
        # Очищаем старые для этого домена
        requests = [t for t in requests if t > now - 3600]
        
        # Проверка burst (5 сек)
        recent_burst = len([t for t in requests if t > now - 5])
        if recent_burst >= self.burst_limit:
            return False, f"Burst limit exceeded for {domain}: {self.burst_limit} requests per 5 sec"
        
        # Проверка минутного лимита
        recent_minute = len([t for t in requests if t > now - 60])
        if recent_minute >= self.requests_per_minute:
            return False, f"Rate limit exceeded for {domain}: {self.requests_per_minute}/min"
        
        # Проверка часового лимита
        if len(requests) >= self.requests_per_hour:
            return False, f"Rate limit exceeded for {domain}: {self.requests_per_hour}/hour"
        
        # Разрешено - записываем
        requests.append(now)
        self._requests[domain] = requests
        return True, None
    
    def get_stats(self, domain: str = None) -> Dict:
        """Возвращает статистику запросов"""
        now = time.time()
        if domain:
            requests = self._requests.get(domain, [])
            return {
                "domain": domain,
                "last_minute": len([t for t in requests if t > now - 60]),
                "last_hour": len(requests),
            }
        
        return {
            "total_domains": len(self._requests),
            "total_requests_hour": sum(len(v) for v in self._requests.values()),
        }


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
        
        # URL Rate Limiter
        rate_limit_config = config.get("rate_limit", {}) if isinstance(config, dict) else getattr(config, "rate_limit", {}) or {}
        self._url_rate_limiter = URLRateLimiter(
            requests_per_minute=rate_limit_config.get("requests_per_minute", 30),
            requests_per_hour=rate_limit_config.get("requests_per_hour", 300),
            burst_limit=rate_limit_config.get("burst_limit", 10),
        )
    
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
                raise SafetyException("Command blocked by safety guard: dangerous pattern detected")
        
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
    
    def validate_url(self, url: str, check_rate_limit: bool = True) -> bool:
        """
        Validate URL for SSRF protection and rate limiting
        
        Args:
            url: URL to validate
            check_rate_limit: Whether to check and record rate limit (default True)
            
        Returns:
            True if URL is safe
            
        Raises:
            SafetyException: If URL is dangerous or rate limited
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
            
            # Rate limit check (prevents DDoS/abuse)
            if check_rate_limit:
                allowed, error = self._url_rate_limiter.check_and_record(url)
                if not allowed:
                    logger.warning(f"URL rate limited: {url[:50]}... - {error}")
                    raise SafetyException(f"URL rate limit: {error}")
            
            return True
        except Exception as e:
            if isinstance(e, SafetyException):
                raise
            logger.error(f"URL validation error: {e}")
            raise SafetyException(f"Invalid URL: {e}") from e
    
    def get_url_rate_limit_stats(self, domain: str = None) -> Dict:
        """Get URL rate limiting statistics"""
        return self._url_rate_limiter.get_stats(domain)

