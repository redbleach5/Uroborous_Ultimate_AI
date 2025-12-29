"""
Safety utilities for preventing crashes
"""

import signal
import sys
from functools import wraps
from typing import Callable
from .logger import get_logger
logger = get_logger(__name__)


def safe_execute(func: Callable) -> Callable:
    """
    Decorator to safely execute function with timeout and error handling
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except KeyboardInterrupt:
            logger.warning("Operation interrupted by user")
            raise
        except SystemExit:
            raise
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            raise
    
    return wrapper


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

