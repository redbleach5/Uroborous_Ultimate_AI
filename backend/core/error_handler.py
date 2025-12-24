"""
Error Handler - Advanced error handling and recovery
"""

from typing import Dict, Any, Optional, Callable
from .logger import get_logger
logger = get_logger(__name__)
import asyncio
from functools import wraps


class ErrorHandler:
    """Advanced error handling with retry and recovery"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize error handler
        
        Args:
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    async def retry_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry and exponential backoff
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries} attempts failed. Last error: {e}")
        
        raise last_exception
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Handle error and provide recovery suggestions
        
        Args:
            error: Exception to handle
            context: Additional context
            
        Returns:
            Error information with suggestions
        """
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
            "suggestions": []
        }
        
        # Provide suggestions based on error type
        error_name = type(error).__name__
        
        if "Connection" in error_name or "Network" in error_name:
            error_info["suggestions"].extend([
                "Check network connectivity",
                "Verify API endpoints are accessible",
                "Check firewall settings"
            ])
        elif "Timeout" in error_name:
            error_info["suggestions"].extend([
                "Increase timeout settings",
                "Check system load",
                "Verify service availability"
            ])
        elif "Permission" in error_name or "Access" in error_name:
            error_info["suggestions"].extend([
                "Check file/directory permissions",
                "Verify user has required access",
                "Check safety guard settings"
            ])
        elif "Validation" in error_name or "Invalid" in error_name:
            error_info["suggestions"].extend([
                "Verify input data format",
                "Check required fields are present",
                "Review validation rules"
            ])
        else:
            error_info["suggestions"].append("Review error message and context")
        
        return error_info


def with_error_handling(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    log_errors: bool = True
):
    """
    Decorator for error handling with retry
    
    Args:
        max_retries: Maximum retries
        retry_delay: Delay between retries
        log_errors: Whether to log errors
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = ErrorHandler(max_retries, retry_delay)
            try:
                return await handler.retry_with_backoff(func, *args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}")
                error_info = handler.handle_error(e, {"function": func.__name__})
                raise
        return wrapper
    return decorator

