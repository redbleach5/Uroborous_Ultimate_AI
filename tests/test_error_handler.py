"""
Tests for error handler
"""

import pytest
import asyncio
from backend.core.error_handler import ErrorHandler


@pytest.mark.asyncio
async def test_error_handler_retry_success():
    """Test retry with successful execution"""
    handler = ErrorHandler(max_retries=3, retry_delay=0.1)
    
    call_count = 0
    
    async def success_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = await handler.retry_with_backoff(success_func)
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_error_handler_retry_failure():
    """Test retry with failures"""
    handler = ErrorHandler(max_retries=3, retry_delay=0.1)
    
    call_count = 0
    
    async def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Test error")
    
    with pytest.raises(ValueError):
        await handler.retry_with_backoff(failing_func)
    
    assert call_count == 3  # Should retry 3 times


@pytest.mark.asyncio
async def test_error_handler_retry_recovery():
    """Test retry with recovery after failures"""
    handler = ErrorHandler(max_retries=3, retry_delay=0.1)
    
    call_count = 0
    
    async def recovering_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Test error")
        return "success"
    
    result = await handler.retry_with_backoff(recovering_func)
    assert result == "success"
    assert call_count == 2


def test_error_handler_handle_error():
    """Test error handling"""
    handler = ErrorHandler()
    
    error = ConnectionError("Connection failed")
    error_info = handler.handle_error(error, {"context": "test"})
    
    assert error_info["error_type"] == "ConnectionError"
    assert error_info["error_message"] == "Connection failed"
    assert len(error_info["suggestions"]) > 0


def test_error_handler_handle_network_error():
    """Test handling network errors"""
    handler = ErrorHandler()
    
    error = ConnectionError("Network error")
    error_info = handler.handle_error(error)
    
    assert "Check network connectivity" in error_info["suggestions"]


def test_error_handler_handle_timeout_error():
    """Test handling timeout errors"""
    handler = ErrorHandler()
    
    error = TimeoutError("Request timeout")
    error_info = handler.handle_error(error)
    
    assert "Increase timeout settings" in error_info["suggestions"]

