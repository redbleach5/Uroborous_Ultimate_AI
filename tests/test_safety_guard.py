"""
Tests for safety guard
"""

import pytest
from backend.safety.guard import SafetyGuard
from backend.core.exceptions import SafetyException


def test_safety_guard_initialization():
    """Test safety guard initialization"""
    config = {"enabled": True, "sandbox": False}
    guard = SafetyGuard(config)
    assert guard.enabled


def test_validate_command_safe():
    """Test validation of safe commands"""
    config = {"enabled": True}
    guard = SafetyGuard(config)
    
    # Safe commands should pass
    assert guard.validate_command("ls -la") is True
    assert guard.validate_command("git status") is True
    assert guard.validate_command("python script.py") is True


def test_validate_command_dangerous():
    """Test validation of dangerous commands"""
    config = {"enabled": True}
    guard = SafetyGuard(config)
    
    # Dangerous commands should be blocked
    with pytest.raises(SafetyException):
        guard.validate_command("rm -rf /")
    
    with pytest.raises(SafetyException):
        guard.validate_command("format c:")


def test_validate_path_safe():
    """Test validation of safe paths"""
    config = {"enabled": True, "sandbox": False}
    guard = SafetyGuard(config)
    
    assert guard.validate_path("./test.txt") is True
    assert guard.validate_path("src/main.py") is True


def test_validate_path_traversal():
    """Test validation of path traversal attempts"""
    config = {"enabled": True}
    guard = SafetyGuard(config)
    
    with pytest.raises(SafetyException):
        guard.validate_path("../../../etc/passwd")


def test_validate_url_safe():
    """Test validation of safe URLs"""
    config = {"enabled": True}
    guard = SafetyGuard(config)
    
    assert guard.validate_url("https://api.example.com/data") is True
    assert guard.validate_url("http://example.com") is True


def test_validate_url_localhost():
    """Test validation blocks localhost URLs"""
    config = {"enabled": True}
    guard = SafetyGuard(config)
    
    with pytest.raises(SafetyException):
        guard.validate_url("http://localhost:8080")
    
    with pytest.raises(SafetyException):
        guard.validate_url("http://127.0.0.1/api")

