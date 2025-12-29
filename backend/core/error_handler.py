"""
Error Handler - Advanced error handling and recovery with correlation tracking
"""

import uuid
import contextvars
from typing import Dict, Any, Optional, Callable
from .logger import get_logger
logger = get_logger(__name__)
import asyncio
from functools import wraps
from datetime import datetime

# Context variable for correlation ID (thread-safe)
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    'correlation_id', default=''
)


def get_correlation_id() -> str:
    """Get the current correlation ID"""
    return _correlation_id.get() or ''


def set_correlation_id(correlation_id: str = None) -> str:
    """Set or generate a new correlation ID"""
    cid = correlation_id or f"req-{uuid.uuid4().hex[:12]}"
    _correlation_id.set(cid)
    return cid


def clear_correlation_id():
    """Clear the correlation ID"""
    _correlation_id.set('')


class ErrorHandler:
    """Advanced error handling with retry, recovery, and correlation tracking"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize error handler
        
        Args:
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._error_history: list = []  # Keep last N errors for analysis
        self._max_history = 100
    
    async def retry_with_backoff(
        self,
        func: Callable,
        *args,
        correlation_id: str = None,
        **kwargs
    ) -> Any:
        """
        Execute function with retry and exponential backoff
        
        Args:
            func: Function to execute
            *args: Function arguments
            correlation_id: Optional correlation ID for tracing
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        cid = correlation_id or get_correlation_id() or set_correlation_id()
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"[{cid}] Attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[{cid}] All {self.max_retries} attempts failed. Last error: {e}")
        
        raise last_exception
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: str = None,
    ) -> Dict[str, Any]:
        """
        Handle error and provide recovery suggestions with correlation tracking.
        
        Args:
            error: Exception to handle
            context: Additional context
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            Error information with suggestions and correlation ID
        """
        cid = correlation_id or get_correlation_id() or set_correlation_id()
        timestamp = datetime.utcnow().isoformat()
        
        error_info = {
            "correlation_id": cid,
            "timestamp": timestamp,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
            "suggestions": [],
        }
        
        # Provide suggestions based on error type
        error_name = type(error).__name__
        
        if "Connection" in error_name or "Network" in error_name:
            error_info["suggestions"].extend([
                "Check network connectivity",
                "Verify API endpoints are accessible",
                "Check firewall settings"
            ])
            error_info["category"] = "network"
        elif "Timeout" in error_name:
            error_info["suggestions"].extend([
                "Increase timeout settings",
                "Check system load",
                "Verify service availability"
            ])
            error_info["category"] = "timeout"
        elif "Permission" in error_name or "Access" in error_name:
            error_info["suggestions"].extend([
                "Check file/directory permissions",
                "Verify user has required access",
                "Check safety guard settings"
            ])
            error_info["category"] = "permission"
        elif "Validation" in error_name or "Invalid" in error_name:
            error_info["suggestions"].extend([
                "Verify input data format",
                "Check required fields are present",
                "Review validation rules"
            ])
            error_info["category"] = "validation"
        elif "LLM" in error_name or "Model" in error_name:
            error_info["suggestions"].extend([
                "Check if LLM service is available",
                "Verify model name is correct",
                "Try a different model or provider"
            ])
            error_info["category"] = "llm"
        else:
            error_info["suggestions"].append("Review error message and context")
            error_info["category"] = "unknown"
        
        # Log structured error
        logger.error(
            f"[{cid}] Error handled: {error_name}",
            extra={
                "correlation_id": cid,
                "error_type": error_name,
                "error_message": str(error)[:500],
                "category": error_info["category"],
                "context_keys": list((context or {}).keys()),
            }
        )
        
        # Store in history for analysis
        self._add_to_history(error_info)
        
        return error_info
    
    def _add_to_history(self, error_info: Dict[str, Any]):
        """Add error to history for pattern analysis"""
        self._error_history.append({
            "timestamp": error_info["timestamp"],
            "correlation_id": error_info["correlation_id"],
            "error_type": error_info["error_type"],
            "category": error_info.get("category", "unknown"),
        })
        # Keep only last N errors
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        from collections import Counter
        
        if not self._error_history:
            return {"total_errors": 0, "by_type": {}, "by_category": {}}
        
        types = Counter(e["error_type"] for e in self._error_history)
        categories = Counter(e["category"] for e in self._error_history)
        
        return {
            "total_errors": len(self._error_history),
            "by_type": dict(types.most_common(10)),
            "by_category": dict(categories),
            "recent_correlation_ids": [e["correlation_id"] for e in self._error_history[-5:]],
        }
    
    def find_related_errors(self, correlation_id: str) -> list:
        """Find all errors with the same correlation ID"""
        return [e for e in self._error_history if e["correlation_id"] == correlation_id]


def with_error_handling(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    log_errors: bool = True,
    generate_correlation_id: bool = True,
):
    """
    Decorator for error handling with retry and correlation ID tracking.
    
    Args:
        max_retries: Maximum retries
        retry_delay: Delay between retries
        log_errors: Whether to log errors
        generate_correlation_id: Whether to generate correlation ID if not present
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Ensure correlation ID exists
            cid = get_correlation_id()
            if not cid and generate_correlation_id:
                cid = set_correlation_id()
            
            handler = ErrorHandler(max_retries, retry_delay)
            try:
                return await handler.retry_with_backoff(
                    func, *args, correlation_id=cid, **kwargs
                )
            except Exception as e:
                if log_errors:
                    logger.error(f"[{cid}] Error in {func.__name__}: {e}")
                handler.handle_error(
                    e, 
                    {"function": func.__name__, "args_count": len(args)},
                    correlation_id=cid,
                )
                raise
        return wrapper
    return decorator


class CorrelationContext:
    """Context manager for correlation ID tracking"""
    
    def __init__(self, correlation_id: str = None):
        self.correlation_id = correlation_id
        self._token = None
    
    def __enter__(self):
        self.correlation_id = set_correlation_id(self.correlation_id)
        return self.correlation_id
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        clear_correlation_id()
        return False
    
    async def __aenter__(self):
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)

