"""
Performance metrics collection
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
from .logger import get_logger
logger = get_logger(__name__)


class MetricsCollector:
    """Collects and aggregates performance metrics"""
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize metrics collector
        
        Args:
            max_history: Maximum number of metrics to keep in history
        """
        self.max_history = max_history
        
        # Metrics storage
        self._agent_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._tool_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._llm_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._task_metrics: deque = deque(maxlen=max_history)
        
        # Counters
        self._counters: Dict[str, int] = defaultdict(int)
        
        # Timers
        self._timers: Dict[str, list] = defaultdict(list)
    
    def record_agent_execution(
        self,
        agent_name: str,
        duration: float,
        success: bool,
        tokens_used: Optional[int] = None
    ):
        """Record agent execution metrics"""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "duration": duration,
            "success": success,
            "tokens_used": tokens_used
        }
        self._agent_metrics[agent_name].append(metric)
        
        self._counters[f"agent_{agent_name}_total"] += 1
        if success:
            self._counters[f"agent_{agent_name}_success"] += 1
        else:
            self._counters[f"agent_{agent_name}_errors"] += 1
    
    def record_tool_execution(
        self,
        tool_name: str,
        duration: float,
        success: bool
    ):
        """Record tool execution metrics"""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "duration": duration,
            "success": success
        }
        self._tool_metrics[tool_name].append(metric)
        
        self._counters[f"tool_{tool_name}_total"] += 1
        if success:
            self._counters[f"tool_{tool_name}_success"] += 1
    
    def record_llm_request(
        self,
        provider: str,
        model: str,
        duration: float,
        tokens: Optional[int] = None,
        success: bool = True
    ):
        """Record LLM request metrics"""
        key = f"{provider}/{model}"
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "duration": duration,
            "tokens": tokens,
            "success": success
        }
        self._llm_metrics[key].append(metric)
        
        self._counters[f"llm_{key}_total"] += 1
        if tokens:
            self._counters[f"llm_{key}_tokens"] += tokens
    
    def record_task_execution(
        self,
        task: str,
        agent_type: Optional[str],
        duration: float,
        success: bool
    ):
        """Record task execution metrics"""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "task": task[:100],  # Truncate long tasks
            "agent_type": agent_type,
            "duration": duration,
            "success": success
        }
        self._task_metrics.append(metric)
        
        self._counters["tasks_total"] += 1
        if success:
            self._counters["tasks_success"] += 1
    
    def get_agent_stats(self, agent_name: str) -> Dict[str, Any]:
        """Get statistics for an agent"""
        metrics = list(self._agent_metrics[agent_name])
        
        if not metrics:
            return {
                "agent": agent_name,
                "total_executions": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "total_tokens": 0
            }
        
        durations = [m["duration"] for m in metrics]
        successes = [m["success"] for m in metrics]
        tokens = [m.get("tokens_used", 0) for m in metrics if m.get("tokens_used")]
        
        return {
            "agent": agent_name,
            "total_executions": len(metrics),
            "success_rate": sum(successes) / len(successes) if successes else 0.0,
            "avg_duration": sum(durations) / len(durations) if durations else 0.0,
            "min_duration": min(durations) if durations else 0.0,
            "max_duration": max(durations) if durations else 0.0,
            "total_tokens": sum(tokens),
            "avg_tokens": sum(tokens) / len(tokens) if tokens else 0.0
        }
    
    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        """Get statistics for a tool"""
        metrics = list(self._tool_metrics[tool_name])
        
        if not metrics:
            return {
                "tool": tool_name,
                "total_executions": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0
            }
        
        durations = [m["duration"] for m in metrics]
        successes = [m["success"] for m in metrics]
        
        return {
            "tool": tool_name,
            "total_executions": len(metrics),
            "success_rate": sum(successes) / len(successes) if successes else 0.0,
            "avg_duration": sum(durations) / len(durations) if durations else 0.0,
            "min_duration": min(durations) if durations else 0.0,
            "max_duration": max(durations) if durations else 0.0
        }
    
    def get_llm_stats(self, provider: str, model: str) -> Dict[str, Any]:
        """Get statistics for LLM provider/model"""
        key = f"{provider}/{model}"
        metrics = list(self._llm_metrics[key])
        
        if not metrics:
            return {
                "provider": provider,
                "model": model,
                "total_requests": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "total_tokens": 0
            }
        
        durations = [m["duration"] for m in metrics]
        successes = [m["success"] for m in metrics]
        tokens = [m.get("tokens", 0) for m in metrics if m.get("tokens")]
        
        return {
            "provider": provider,
            "model": model,
            "total_requests": len(metrics),
            "success_rate": sum(successes) / len(successes) if successes else 0.0,
            "avg_duration": sum(durations) / len(durations) if durations else 0.0,
            "total_tokens": sum(tokens),
            "avg_tokens": sum(tokens) / len(tokens) if tokens else 0.0
        }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get all statistics"""
        agent_stats = {
            name: self.get_agent_stats(name)
            for name in self._agent_metrics.keys()
        }
        
        tool_stats = {
            name: self.get_tool_stats(name)
            for name in self._tool_metrics.keys()
        }
        
        llm_stats = {
            key: self.get_llm_stats(*key.split("/"))
            for key in self._llm_metrics.keys()
        }
        
        task_total = self._counters.get("tasks_total", 0)
        task_success = self._counters.get("tasks_success", 0)
        
        return {
            "agents": agent_stats,
            "tools": tool_stats,
            "llm": llm_stats,
            "tasks": {
                "total": task_total,
                "success": task_success,
                "success_rate": task_success / task_total if task_total > 0 else 0.0
            },
            "counters": dict(self._counters)
        }
    
    def get_recent_metrics(self, minutes: int = 60) -> Dict[str, Any]:
        """Get metrics from recent time period"""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        recent_agent_metrics = {}
        for agent_name, metrics in self._agent_metrics.items():
            recent = [
                m for m in metrics
                if datetime.fromisoformat(m["timestamp"]) >= cutoff
            ]
            if recent:
                recent_agent_metrics[agent_name] = recent
        
        recent_task_metrics = [
            m for m in self._task_metrics
            if datetime.fromisoformat(m["timestamp"]) >= cutoff
        ]
        
        return {
            "agents": recent_agent_metrics,
            "tasks": recent_task_metrics,
            "period_minutes": minutes
        }
    
    def reset(self):
        """Reset all metrics"""
        self._agent_metrics.clear()
        self._tool_metrics.clear()
        self._llm_metrics.clear()
        self._task_metrics.clear()
        self._counters.clear()
        self._timers.clear()
        logger.info("Metrics reset")


# Global metrics collector
metrics_collector = MetricsCollector()

