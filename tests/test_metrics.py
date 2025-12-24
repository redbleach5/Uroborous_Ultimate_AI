"""
Tests for metrics
"""

import pytest
import time
from backend.core.metrics import MetricsCollector


def test_metrics_collector_initialization():
    """Test metrics collector initialization"""
    collector = MetricsCollector(max_history=100)
    assert collector.max_history == 100


def test_record_agent_execution():
    """Test recording agent execution"""
    collector = MetricsCollector()
    
    collector.record_agent_execution(
        agent_name="test_agent",
        duration=1.5,
        success=True,
        tokens_used=100
    )
    
    stats = collector.get_agent_stats("test_agent")
    assert stats["total_executions"] == 1
    assert stats["success_rate"] == 1.0
    assert stats["avg_duration"] == 1.5
    assert stats["total_tokens"] == 100


def test_record_tool_execution():
    """Test recording tool execution"""
    collector = MetricsCollector()
    
    collector.record_tool_execution(
        tool_name="test_tool",
        duration=0.5,
        success=True
    )
    
    stats = collector.get_tool_stats("test_tool")
    assert stats["total_executions"] == 1
    assert stats["success_rate"] == 1.0
    assert stats["avg_duration"] == 0.5


def test_record_llm_request():
    """Test recording LLM request"""
    collector = MetricsCollector()
    
    collector.record_llm_request(
        provider="openai",
        model="gpt-4",
        duration=2.0,
        tokens=200,
        success=True
    )
    
    stats = collector.get_llm_stats("openai", "gpt-4")
    assert stats["total_requests"] == 1
    assert stats["success_rate"] == 1.0
    assert stats["total_tokens"] == 200


def test_record_task_execution():
    """Test recording task execution"""
    collector = MetricsCollector()
    
    collector.record_task_execution(
        task="Test task",
        agent_type="code_writer",
        duration=1.0,
        success=True
    )
    
    stats = collector.get_all_stats()
    assert stats["tasks"]["total"] == 1
    assert stats["tasks"]["success"] == 1
    assert stats["tasks"]["success_rate"] == 1.0


def test_get_all_stats():
    """Test getting all statistics"""
    collector = MetricsCollector()
    
    collector.record_agent_execution("agent1", 1.0, True)
    collector.record_tool_execution("tool1", 0.5, True)
    collector.record_task_execution("task1", "agent1", 1.0, True)
    
    stats = collector.get_all_stats()
    assert "agents" in stats
    assert "tools" in stats
    assert "tasks" in stats
    assert "counters" in stats


def test_reset_metrics():
    """Test resetting metrics"""
    collector = MetricsCollector()
    
    collector.record_agent_execution("agent1", 1.0, True)
    collector.record_task_execution("task1", "agent1", 1.0, True)
    
    assert collector.get_all_stats()["tasks"]["total"] == 1
    
    collector.reset()
    
    assert collector.get_all_stats()["tasks"]["total"] == 0

