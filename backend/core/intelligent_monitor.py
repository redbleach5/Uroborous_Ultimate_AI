"""
Intelligent Monitoring and Debug Logging System
Постоянно мониторит работу проекта и пишет детальные логи при проблемах
"""

import asyncio
import traceback
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
import json
import inspect
import functools

from .logger import get_logger
logger = get_logger(__name__)
import psutil
import threading
import time

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class IssueSeverity(Enum):
    """Уровни серьезности проблем"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Issue:
    """Информация о проблеме"""
    component: str
    severity: IssueSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class ComponentHealth:
    """Состояние здоровья компонента"""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    last_check: datetime
    metrics: Dict[str, Any] = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)
    uptime_seconds: float = 0.0


class IntelligentMonitor:
    """
    Интеллектуальный мониторинг системы
    
    Постоянно отслеживает:
    - Производительность компонентов
    - Использование ресурсов
    - Ошибки и исключения
    - Аномалии в поведении
    - Состояние LLM провайдеров
    - Состояние агентов
    - Состояние инструментов
    """
    
    def __init__(self, debug_logs_dir: str = "LOGS_DEBUG", enabled: bool = True):
        self.enabled = enabled
        self.debug_logs_dir = Path(debug_logs_dir)
        self.debug_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Состояние компонентов
        self.component_health: Dict[str, ComponentHealth] = {}
        
        # История проблем
        self.issues_history: deque = deque(maxlen=1000)
        
        # Метрики производительности
        self.performance_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Пороги для обнаружения проблем
        self.thresholds = {
            "cpu_percent": 90.0,
            "memory_percent": 85.0,
            "response_time_ms": 5000.0,
            "error_rate": 0.1,  # 10% ошибок
            "consecutive_errors": 3,
        }
        
        # Статистика
        self.stats = {
            "total_issues": 0,
            "resolved_issues": 0,
            "critical_issues": 0,
            "monitoring_started": datetime.now(),
        }
        
        # Флаги мониторинга
        self._monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._debug_handler_id: Optional[int] = None
        
        # Настройка логирования в LOGS_DEBUG
        self._setup_debug_logging()
        
        # Регистрация обработчиков исключений
        self._setup_exception_handlers()
        
        logger.info(f"Intelligent Monitor initialized. Debug logs: {self.debug_logs_dir}")
    
    def _setup_debug_logging(self):
        """Настройка логирования в директорию LOGS_DEBUG"""
        debug_log_file = self.debug_logs_dir / "monitor.log"
        
        # Удаляем существующий handler для debug логов, если есть
        if self._debug_handler_id is not None:
            try:
                logger.remove(self._debug_handler_id)
            except (ValueError, TypeError):
                pass
        
        # Добавляем handler для debug логов
        self._debug_handler_id = logger.add(
            str(debug_log_file),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            filter=lambda record: record["level"].name in ["DEBUG", "WARNING", "ERROR", "CRITICAL"],
            serialize=True,  # JSON формат для структурированных логов
            enqueue=True,  # Асинхронная запись
            backtrace=True,  # Полный backtrace
            diagnose=True,  # Диагностическая информация
        )
    
    def _setup_exception_handlers(self):
        """Настройка глобальных обработчиков исключений"""
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Обработчик необработанных исключений"""
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            issue = Issue(
                component="system",
                severity=IssueSeverity.CRITICAL,
                message=f"Unhandled exception: {exc_type.__name__}: {exc_value}",
                details={
                    "exception_type": exc_type.__name__,
                    "exception_value": str(exc_value),
                },
                stack_trace="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            )
            
            self._log_issue(issue)
            logger.exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        
        sys.excepthook = exception_handler
    
    async def start_monitoring(self, interval: float = 5.0):
        """Запуск постоянного мониторинга"""
        if not self.enabled:
            return
        
        if self._monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self._monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop(interval))
        logger.info(f"Intelligent monitoring started (interval: {interval}s)")
    
    async def stop_monitoring(self):
        """Остановка мониторинга"""
        self._monitoring_active = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Intelligent monitoring stopped")
    
    async def _monitoring_loop(self, interval: float):
        """Основной цикл мониторинга"""
        while self._monitoring_active:
            try:
                await self._check_system_resources()
                await self._check_component_health()
                await self._analyze_metrics()
                await self._detect_anomalies()
                
                # Сохраняем состояние каждые 60 секунд
                if int(time.time()) % 60 == 0:
                    await self._save_state()
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
            
            await asyncio.sleep(interval)
    
    async def _check_system_resources(self):
        """Проверка системных ресурсов"""
        try:
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Проверка порогов
            issues = []
            
            if cpu_percent > self.thresholds["cpu_percent"]:
                issues.append(Issue(
                    component="system",
                    severity=IssueSeverity.WARNING,
                    message=f"High CPU usage: {cpu_percent:.1f}%",
                    details={"cpu_percent": cpu_percent, "threshold": self.thresholds["cpu_percent"]},
                ))
            
            if memory_percent > self.thresholds["memory_percent"]:
                issues.append(Issue(
                    component="system",
                    severity=IssueSeverity.WARNING,
                    message=f"High memory usage: {memory_percent:.1f}%",
                    details={
                        "memory_percent": memory_percent,
                        "memory_mb": memory_info.rss / 1024 / 1024,
                        "threshold": self.thresholds["memory_percent"],
                    },
                ))
            
            # Сохраняем метрики
            self.performance_metrics["cpu_percent"].append(cpu_percent)
            self.performance_metrics["memory_percent"].append(memory_percent)
            self.performance_metrics["memory_mb"].append(memory_info.rss / 1024 / 1024)
            
            # Логируем проблемы
            for issue in issues:
                self._log_issue(issue)
            
            # Обновляем состояние компонента
            self._update_component_health("system", {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_mb": memory_info.rss / 1024 / 1024,
            })
            
        except Exception as e:
            logger.error(f"Error checking system resources: {e}", exc_info=True)
    
    async def _check_component_health(self):
        """Проверка здоровья компонентов"""
        # Проверяем компоненты, которые были зарегистрированы
        for component_name, health in self.component_health.items():
            # Проверяем, не слишком ли старые данные
            time_since_check = (datetime.now() - health.last_check).total_seconds()
            if time_since_check > 300:  # 5 минут без обновления
                issue = Issue(
                    component=component_name,
                    severity=IssueSeverity.WARNING,
                    message=f"Component hasn't reported status for {time_since_check:.0f} seconds",
                    details={"time_since_check": time_since_check},
                )
                self._log_issue(issue)
    
    async def _analyze_metrics(self):
        """Анализ метрик для обнаружения аномалий"""
        # Анализируем метрики производительности
        for metric_name, values in self.performance_metrics.items():
            if len(values) < 10:
                continue
            
            recent_values = list(values)[-20:]  # Последние 20 значений
            
            # Вычисляем среднее и стандартное отклонение
            mean = sum(recent_values) / len(recent_values)
            variance = sum((x - mean) ** 2 for x in recent_values) / len(recent_values)
            std_dev = variance ** 0.5
            
            # Настройки порогов для разных типов метрик
            # Для CPU и памяти используем более строгие пороги (5% минимальное отклонение)
            # Для других метрик используем стандартные пороги
            if metric_name in ["cpu_percent", "memory_percent", "memory_mb"]:
                # Минимальное отклонение для системных метрик (повышаем чувствительность для памяти)
                min_deviation = max(mean * 0.20, 2.0) if metric_name.startswith("memory") else mean * 0.05
                # Используем более мягкий порог: 3*std_dev и обязательное минимальное отклонение
                threshold = mean + max(3 * std_dev, min_deviation)
            else:
                # Для других метрик: минимальное отклонение 10% от среднего
                min_deviation = mean * 0.10 if mean > 0 else 2 * std_dev
                threshold = mean + max(2 * std_dev, min_deviation)
            
            # Обнаруживаем аномалии только если отклонение значительное
            anomalies = [v for v in recent_values if v > threshold]
            
            # Дополнительная проверка: не логируем аномалии, если они незначительны
            # (например, для CPU 0.1% -> 0.2% это не критично)
            if metric_name == "cpu_percent" and mean < 1.0:
                # Для низкой загрузки CPU игнорируем небольшие отклонения
                anomalies = [v for v in anomalies if v > mean + 0.5]  # Минимум 0.5% отклонение
            
            if metric_name in ["memory_percent", "memory_mb"] and mean < 10:
                # Для низкого использования памяти требуем минимум 1% отклонение
                min_absolute_deviation = mean * 0.10  # 10% от среднего
                anomalies = [v for v in anomalies if (v - mean) > min_absolute_deviation]
            
            if anomalies:
                issue = Issue(
                    component="metrics",
                    severity=IssueSeverity.WARNING,
                    message=f"Anomaly detected in {metric_name}",
                    details={
                        "metric": metric_name,
                        "mean": mean,
                        "std_dev": std_dev,
                        "threshold": threshold,
                        "anomaly_values": anomalies[-5:],  # Последние 5 аномалий
                        "deviation_percent": ((anomalies[-1] - mean) / mean * 100) if mean > 0 else 0,
                    },
                )
                self._log_issue(issue)
    
    async def _detect_anomalies(self):
        """Обнаружение аномалий в поведении"""
        # Проверяем частоту ошибок
        recent_issues = [i for i in self.issues_history if (datetime.now() - i.timestamp).total_seconds() < 60]
        error_issues = [i for i in recent_issues if i.severity in [IssueSeverity.ERROR, IssueSeverity.CRITICAL]]
        
        if len(recent_issues) > 0:
            error_rate = len(error_issues) / len(recent_issues)
            if error_rate > self.thresholds["error_rate"]:
                issue = Issue(
                    component="system",
                    severity=IssueSeverity.ERROR,
                    message=f"High error rate: {error_rate:.1%}",
                    details={
                        "error_rate": error_rate,
                        "total_issues": len(recent_issues),
                        "error_issues": len(error_issues),
                    },
                )
                self._log_issue(issue)
    
    def register_component(self, name: str, initial_status: str = "healthy"):
        """Регистрация компонента для мониторинга"""
        self.component_health[name] = ComponentHealth(
            name=name,
            status=initial_status,
            last_check=datetime.now(),
        )
        logger.debug(f"Component registered: {name}")
    
    def update_component_status(
        self,
        name: str,
        status: str,
        metrics: Optional[Dict[str, Any]] = None,
        issues: Optional[List[Issue]] = None
    ):
        """Обновление статуса компонента"""
        if name not in self.component_health:
            self.register_component(name, status)
        
        health = self.component_health[name]
        health.status = status
        health.last_check = datetime.now()
        
        if metrics:
            health.metrics.update(metrics)
        
        if issues:
            health.issues.extend(issues)
            for issue in issues:
                self._log_issue(issue)
        
        # Логируем изменение статуса
        if status != "healthy":
            logger.warning(f"Component {name} status: {status}", extra={
                "component": name,
                "status": status,
                "metrics": metrics or {},
            })
    
    def _update_component_health(self, name: str, metrics: Dict[str, Any]):
        """Внутренний метод для обновления здоровья компонента"""
        if name not in self.component_health:
            self.register_component(name)
        
        health = self.component_health[name]
        health.metrics.update(metrics)
        health.last_check = datetime.now()
    
    def log_exception(
        self,
        component: str,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
        severity: IssueSeverity = IssueSeverity.ERROR
    ):
        """Логирование исключения"""
        issue = Issue(
            component=component,
            severity=severity,
            message=f"{type(exception).__name__}: {str(exception)}",
            details={
                "exception_type": type(exception).__name__,
                "exception_value": str(exception),
            },
            stack_trace="".join(traceback.format_exception(type(exception), exception, exception.__traceback__)),
            context=context or {},
        )
        
        self._log_issue(issue)
    
    def log_performance_metric(self, component: str, metric_name: str, value: float):
        """Логирование метрики производительности"""
        key = f"{component}.{metric_name}"
        self.performance_metrics[key].append(value)
        
        # Проверяем пороги
        threshold_key = metric_name.replace("_ms", "_time_ms")
        if threshold_key in self.thresholds and value > self.thresholds[threshold_key]:
            issue = Issue(
                component=component,
                severity=IssueSeverity.WARNING,
                message=f"Performance metric {metric_name} exceeded threshold: {value:.2f}",
                details={
                    "metric": metric_name,
                    "value": value,
                    "threshold": self.thresholds[threshold_key],
                },
            )
            self._log_issue(issue)
    
    def _log_issue(self, issue: Issue):
        """Логирование проблемы в LOGS_DEBUG"""
        if not self.enabled:
            return
        
        self.issues_history.append(issue)
        self.stats["total_issues"] += 1
        
        if issue.severity == IssueSeverity.CRITICAL:
            self.stats["critical_issues"] += 1
        
        # Записываем в debug лог
        log_data = {
            "timestamp": issue.timestamp.isoformat(),
            "component": issue.component,
            "severity": issue.severity.value,
            "message": issue.message,
            "details": issue.details,
            "context": issue.context,
        }
        
        if issue.stack_trace:
            log_data["stack_trace"] = issue.stack_trace
        
        # Выбираем уровень логирования
        log_level = {
            IssueSeverity.INFO: logger.info,
            IssueSeverity.WARNING: logger.warning,
            IssueSeverity.ERROR: logger.error,
            IssueSeverity.CRITICAL: logger.critical,
        }[issue.severity]
        
        log_level(
            f"[{issue.component}] {issue.message}",
            extra={"issue": log_data},
        )
        
        # Дополнительно пишем в отдельный файл для критических проблем
        if issue.severity == IssueSeverity.CRITICAL:
            critical_log_file = self.debug_logs_dir / "critical_issues.log"
            with open(critical_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"CRITICAL ISSUE - {issue.timestamp.isoformat()}\n")
                f.write(f"Component: {issue.component}\n")
                f.write(f"Message: {issue.message}\n")
                f.write(f"Details: {json.dumps(issue.details, indent=2)}\n")
                if issue.stack_trace:
                    f.write(f"\nStack Trace:\n{issue.stack_trace}\n")
                f.write(f"{'='*80}\n")
    
    async def _save_state(self):
        """Сохранение состояния мониторинга"""
        state_file = self.debug_logs_dir / "monitor_state.json"
        
        state = {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "component_health": {
                name: {
                    "name": health.name,
                    "status": health.status,
                    "last_check": health.last_check.isoformat(),
                    "metrics": health.metrics,
                    "uptime_seconds": health.uptime_seconds,
                }
                for name, health in self.component_health.items()
            },
            "recent_issues": [
                {
                    "component": issue.component,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "timestamp": issue.timestamp.isoformat(),
                    "resolved": issue.resolved,
                }
                for issue in list(self.issues_history)[-50:]  # Последние 50 проблем
            ],
        }
        
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving monitor state: {e}")
    
    def get_health_report(self) -> Dict[str, Any]:
        """Получить отчет о здоровье системы"""
        return {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "component_health": {
                name: {
                    "status": health.status,
                    "last_check": health.last_check.isoformat(),
                    "metrics": health.metrics,
                }
                for name, health in self.component_health.items()
            },
            "recent_issues": [
                {
                    "component": issue.component,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "timestamp": issue.timestamp.isoformat(),
                }
                for issue in list(self.issues_history)[-20:]
            ],
        }
    
    def decorator_monitor(self, component: str = None):
        """Декоратор для автоматического мониторинга функций"""
        def decorator(func: Callable):
            comp_name = component or func.__module__ or "unknown"
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    # Логируем метрику производительности
                    self.log_performance_metric(comp_name, f"{func.__name__}_duration_ms", duration * 1000)
                    
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.log_exception(comp_name, e, context={
                        "function": func.__name__,
                        "args": str(args)[:200],
                        "kwargs": str(kwargs)[:200],
                        "duration_ms": duration * 1000,
                    })
                    raise
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    # Логируем метрику производительности
                    self.log_performance_metric(comp_name, f"{func.__name__}_duration_ms", duration * 1000)
                    
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.log_exception(comp_name, e, context={
                        "function": func.__name__,
                        "args": str(args)[:200],
                        "kwargs": str(kwargs)[:200],
                        "duration_ms": duration * 1000,
                    })
                    raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator


# Глобальный экземпляр монитора
_global_monitor: Optional[IntelligentMonitor] = None


def get_monitor() -> IntelligentMonitor:
    """Получить глобальный экземпляр монитора"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = IntelligentMonitor()
    return _global_monitor


def initialize_monitor(debug_logs_dir: str = "LOGS_DEBUG", enabled: bool = True) -> IntelligentMonitor:
    """Инициализация глобального монитора"""
    global _global_monitor
    _global_monitor = IntelligentMonitor(debug_logs_dir=debug_logs_dir, enabled=enabled)
    return _global_monitor

