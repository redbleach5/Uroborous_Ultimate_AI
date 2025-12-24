"""
Tests for configuration system
"""

import pytest
from backend.config import load_config, get_config, Config


def test_load_config():
    """Test loading configuration"""
    config = load_config()
    assert config is not None
    assert isinstance(config, Config)


def test_get_config():
    """Test getting global config"""
    config = get_config()
    assert config is not None
    assert hasattr(config, 'llm')
    assert hasattr(config, 'rag')
    assert hasattr(config, 'agents')


def test_llm_config():
    """Test LLM configuration"""
    config = get_config()
    assert config.llm is not None
    assert hasattr(config.llm, 'default_provider')
    assert hasattr(config.llm, 'providers')


def test_agents_config():
    """Test agents configuration"""
    config = get_config()
    assert config.agents is not None
    assert hasattr(config.agents, 'code_writer')
    assert hasattr(config.agents, 'react')

