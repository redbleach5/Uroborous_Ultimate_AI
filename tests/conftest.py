"""
Pytest configuration and fixtures
"""

import pytest
import asyncio
from backend.config import get_config, reload_config


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config():
    """Get configuration"""
    return get_config()


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config before each test"""
    reload_config()
    yield
    reload_config()

