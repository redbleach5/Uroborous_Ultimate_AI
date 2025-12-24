"""
Agents for various tasks
"""

from .base import BaseAgent, AgentRegistry
from .code_writer import CodeWriterAgent
from .react import ReactAgent
from .research import ResearchAgent
from .data_analysis import DataAnalysisAgent
from .workflow import WorkflowAgent
from .integration import IntegrationAgent
from .monitoring import MonitoringAgent

__all__ = [
    "BaseAgent",
    "AgentRegistry",
    "CodeWriterAgent",
    "ReactAgent",
    "ResearchAgent",
    "DataAnalysisAgent",
    "WorkflowAgent",
    "IntegrationAgent",
    "MonitoringAgent",
]

