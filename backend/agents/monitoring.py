"""
MonitoringAgent - Monitors system performance and metrics
"""

from typing import Dict, Any, Optional
from datetime import datetime
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException


class MonitoringAgent(BaseAgent):
    """Agent for monitoring and performance evaluation"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics_history: list = []
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute monitoring task
        
        Args:
            task: Monitoring task description
            context: Additional context (metrics to monitor, thresholds, etc.)
            
        Returns:
            Monitoring results
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"MonitoringAgent executing task: {task}")
        
        system_prompt = """You are a monitoring and observability expert. Your task is to monitor systems, analyze metrics, and provide insights.

Capabilities:
- Performance monitoring
- Metric collection and analysis
- Alerting and notifications
- Trend analysis
- Anomaly detection
- Resource usage monitoring
- Model performance tracking
- A/B testing analysis

Provide monitoring dashboards, alerts, and recommendations."""
        
        user_prompt = f"""Monitoring Task: {task}

"""
        
        if context:
            if "metrics" in context:
                user_prompt += f"Metrics to monitor: {context['metrics']}\n"
            if "thresholds" in context:
                user_prompt += f"Thresholds: {context['thresholds']}\n"
            if "time_range" in context:
                user_prompt += f"Time range: {context['time_range']}\n"
        
        user_prompt += "\nPlease provide monitoring analysis and recommendations."
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        try:
            analysis = await self._get_llm_response(messages)
            
            # Collect current metrics
            current_metrics = await self._collect_metrics()
            
            result = {
                "agent": self.name,
                "task": task,
                "analysis": analysis,
                "current_metrics": current_metrics,
                "timestamp": datetime.now().isoformat(),
                "success": True
            }
            
            # Save metrics to history
            self.metrics_history.append({
                "timestamp": datetime.now().isoformat(),
                "metrics": current_metrics
            })
            
            # Keep only last 1000 entries
            if len(self.metrics_history) > 1000:
                self.metrics_history = self.metrics_history[-1000:]
            
            return result
            
        except Exception as e:
            logger.error(f"MonitoringAgent error: {e}")
            raise AgentException(f"Monitoring failed: {e}") from e
    
    async def _collect_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics"""
        import psutil
        import os
        
        try:
            process = psutil.Process(os.getpid())
            
            return {
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "threads": process.num_threads(),
                "system_cpu": psutil.cpu_percent(interval=0.1),
                "system_memory": psutil.virtual_memory().percent
            }
        except ImportError:
            # psutil not available
            return {
                "cpu_percent": 0,
                "memory_mb": 0,
                "threads": 0,
                "system_cpu": 0,
                "system_memory": 0
            }
        except Exception as e:
            logger.warning(f"Failed to collect metrics: {e}")
            return {}
    
    def get_metrics_history(self, limit: int = 100) -> list:
        """Get metrics history"""
        return self.metrics_history[-limit:]

