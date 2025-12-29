"""
Agents for various tasks with reflection and inter-agent communication
"""

from .base import BaseAgent, AgentRegistry
from .code_writer import CodeWriterAgent
from .react import ReactAgent
from .research import ResearchAgent
from .data_analysis import DataAnalysisAgent
from .workflow import WorkflowAgent
from .integration import IntegrationAgent
from .monitoring import MonitoringAgent
from .reflection_mixin import ReflectionMixin, ReflectionResult, ReflectionQuality
from .uncertainty_search_mixin import UncertaintySearchMixin
from .self_consistency_mixin import SelfConsistencyMixin
from .communicator import (
    AgentCommunicator,
    AgentMessage,
    AgentCapability,
    MessageType,
    MessagePriority,
    DelegationResult,
    get_communicator,
    set_communicator
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentRegistry",
    # Agents
    "CodeWriterAgent",
    "ReactAgent",
    "ResearchAgent",
    "DataAnalysisAgent",
    "WorkflowAgent",
    "IntegrationAgent",
    "MonitoringAgent",
    # Reflection
    "ReflectionMixin",
    "ReflectionResult",
    "ReflectionQuality",
    # Uncertainty Search
    "UncertaintySearchMixin",
    # Self-Consistency
    "SelfConsistencyMixin",
    # Communication
    "AgentCommunicator",
    "AgentMessage",
    "AgentCapability",
    "MessageType",
    "MessagePriority",
    "DelegationResult",
    "get_communicator",
    "set_communicator",
]

