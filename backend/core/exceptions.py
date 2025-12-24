"""
Custom exceptions for AILLM
"""


class AILLMException(Exception):
    """Base exception for AILLM"""
    pass


class AgentException(AILLMException):
    """Exception raised by agents"""
    pass


class LLMException(AILLMException):
    """Exception raised by LLM providers"""
    pass


class ToolException(AILLMException):
    """Exception raised by tools"""
    pass


class SafetyException(AILLMException):
    """Exception raised by safety guard"""
    pass


class ConfigurationException(AILLMException):
    """Exception raised for configuration errors"""
    pass


class MemoryException(AILLMException):
    """Exception raised by memory system"""
    pass

