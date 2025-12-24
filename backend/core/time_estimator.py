"""
Time Estimator - Оценка времени выполнения задач
Учитывает что на малых моделях обработка может занять до часа
"""

import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from .logger import get_logger
logger = get_logger(__name__)

from .resource_aware_selector import ResourceLevel
from .model_performance_tracker import get_performance_tracker


class ExecutionTimeCategory(Enum):
    """Категории времени выполнения"""
    FAST = "fast"  # < 1 минута
    NORMAL = "normal"  # 1-5 минут
    SLOW = "slow"  # 5-15 минут
    VERY_SLOW = "very_slow"  # 15-30 минут
    EXTREMELY_SLOW = "extremely_slow"  # 30-60 минут


@dataclass
class TimeEstimate:
    """Оценка времени выполнения"""
    estimated_seconds: float
    estimated_minutes: float
    category: ExecutionTimeCategory
    confidence: float  # 0.0 - 1.0
    warning_message: Optional[str] = None
    factors: Dict[str, Any] = None


class TimeEstimator:
    """
    Оценщик времени выполнения задач
    
    Учитывает:
    - Размер модели (1B vs 70B)
    - Сложность задачи
    - Исторические метрики производительности
    - Доступные ресурсы
    """
    
    def __init__(self):
        self.performance_tracker = get_performance_tracker()
        
        # Базовые скорости генерации (токенов в секунду) по размеру модели
        self.base_speeds = {
            "1b": 80.0,  # Очень быстрые модели
            "2b": 70.0,
            "3b": 60.0,
            "7b": 30.0,  # Средние модели
            "13b": 15.0,
            "14b": 12.0,
            "30b": 8.0,  # Большие модели
            "70b": 5.0,  # Очень большие модели
        }
        
        # Множители сложности
        self.complexity_multipliers = {
            "low": 1.0,
            "medium": 2.5,
            "high": 5.0
        }
        
        # Множители для типов задач
        self.task_type_multipliers = {
            "simple_chat": 0.5,
            "code_generation": 3.0,
            "analysis": 2.0,
            "research": 4.0,
            "complex_project": 10.0  # Для создания целых проектов
        }
    
    def estimate_execution_time(
        self,
        task: str,
        model: str,
        resource_level: ResourceLevel,
        complexity: str = "medium",
        task_type: Optional[str] = None,
        estimated_tokens: Optional[int] = None
    ) -> TimeEstimate:
        """
        Оценивает время выполнения задачи
        
        Args:
            task: Текст задачи
            model: Название модели
            resource_level: Уровень ресурсов
            complexity: Сложность задачи
            task_type: Тип задачи
            estimated_tokens: Оценка количества токенов (если известна)
        
        Returns:
            TimeEstimate с оценкой времени и предупреждением
        """
        # Оцениваем количество токенов если не указано
        if not estimated_tokens:
            estimated_tokens = self._estimate_tokens(task, complexity, task_type)
        
        # Определяем базовую скорость модели
        base_speed = self._get_model_speed(model, resource_level)
        
        # Корректируем на основе исторических метрик
        metrics = self.performance_tracker.get_metrics("ollama", model)
        if metrics.avg_tokens_per_sec > 0:
            # Используем реальную скорость если доступна
            base_speed = metrics.avg_tokens_per_sec
            confidence = 0.8
        else:
            confidence = 0.5  # Меньшая уверенность для оценок
        
        # Применяем множители
        complexity_mult = self.complexity_multipliers.get(complexity, 2.0)
        task_mult = self.task_type_multipliers.get(task_type, 1.0) if task_type else 1.0
        
        # Для малых моделей на сложных задачах - дополнительный множитель
        if resource_level in [ResourceLevel.MINIMAL, ResourceLevel.LOW] and complexity == "high":
            complexity_mult *= 2.0  # Малые модели медленнее на сложных задачах
        
        # Вычисляем время
        tokens_per_second = base_speed / (complexity_mult * task_mult)
        estimated_seconds = estimated_tokens / tokens_per_second if tokens_per_second > 0 else 300
        
        # Для малых моделей добавляем overhead на обработку
        if resource_level in [ResourceLevel.MINIMAL, ResourceLevel.LOW]:
            estimated_seconds *= 1.3  # +30% overhead
        
        estimated_minutes = estimated_seconds / 60.0
        
        # Определяем категорию
        category = self._categorize_time(estimated_minutes)
        
        # Формируем предупреждение если нужно
        warning_message = self._generate_warning(
            estimated_minutes,
            category,
            resource_level,
            model
        )
        
        factors = {
            "estimated_tokens": estimated_tokens,
            "base_speed": base_speed,
            "complexity_multiplier": complexity_mult,
            "task_multiplier": task_mult,
            "resource_level": resource_level.value
        }
        
        return TimeEstimate(
            estimated_seconds=estimated_seconds,
            estimated_minutes=estimated_minutes,
            category=category,
            confidence=confidence,
            warning_message=warning_message,
            factors=factors
        )
    
    def _estimate_tokens(
        self,
        task: str,
        complexity: str,
        task_type: Optional[str] = None
    ) -> int:
        """Оценивает количество токенов для задачи"""
        # Базовая оценка: ~4 символа на токен
        base_tokens = len(task) // 4
        
        # Множители
        multipliers = {
            "low": 1.0,
            "medium": 2.0,
            "high": 4.0
        }
        
        complexity_mult = multipliers.get(complexity, 2.0)
        
        # Для сложных проектов - значительно больше токенов
        if task_type == "complex_project":
            base_tokens *= 10
        
        return int(base_tokens * complexity_mult)
    
    def _get_model_speed(self, model: str, resource_level: ResourceLevel) -> float:
        """Определяет базовую скорость модели"""
        model_lower = model.lower()
        
        # Ищем размер модели в названии
        for size, speed in self.base_speeds.items():
            if size in model_lower:
                return speed
        
        # Если не нашли, определяем по resource_level
        level_speeds = {
            ResourceLevel.MINIMAL: 50.0,  # Малые модели быстрее
            ResourceLevel.LOW: 40.0,
            ResourceLevel.MEDIUM: 20.0,
            ResourceLevel.HIGH: 10.0,
            ResourceLevel.MAXIMUM: 5.0  # Большие модели медленнее
        }
        
        return level_speeds.get(resource_level, 20.0)
    
    def _categorize_time(self, minutes: float) -> ExecutionTimeCategory:
        """Категоризирует время выполнения"""
        if minutes < 1:
            return ExecutionTimeCategory.FAST
        elif minutes < 5:
            return ExecutionTimeCategory.NORMAL
        elif minutes < 15:
            return ExecutionTimeCategory.SLOW
        elif minutes < 30:
            return ExecutionTimeCategory.VERY_SLOW
        else:
            return ExecutionTimeCategory.EXTREMELY_SLOW
    
    def _generate_warning(
        self,
        estimated_minutes: float,
        category: ExecutionTimeCategory,
        resource_level: ResourceLevel,
        model: str
    ) -> Optional[str]:
        """Генерирует предупреждение о времени выполнения"""
        if category == ExecutionTimeCategory.FAST:
            return None
        
        if category == ExecutionTimeCategory.NORMAL:
            return f"⏱️ Ожидаемое время выполнения: ~{estimated_minutes:.1f} минут"
        
        if category == ExecutionTimeCategory.SLOW:
            return (
                f"⚠️ ВНИМАНИЕ: Ожидаемое время выполнения: ~{estimated_minutes:.1f} минут. "
                f"Это нормально для малых моделей ({model}). Пожалуйста, подождите."
            )
        
        if category == ExecutionTimeCategory.VERY_SLOW:
            return (
                f"⚠️ ВНИМАНИЕ: Ожидаемое время выполнения: ~{estimated_minutes:.1f} минут "
                f"(до {int(estimated_minutes) + 5} минут). "
                f"Малая модель ({model}) обрабатывает сложную задачу. Это нормально для отладки. "
                f"Пожалуйста, не прерывайте процесс."
            )
        
        # EXTREMELY_SLOW
        return (
            f"🚨 ВАЖНО: Ожидаемое время выполнения: ~{estimated_minutes:.1f} минут "
            f"(может занять до 60 минут). "
            f"Малая модель ({model}) обрабатывает очень сложную задачу. "
            f"Это нормально для отладки на ограниченных ресурсах. "
            f"Система работает, пожалуйста, не прерывайте процесс. "
            f"Рекомендуется использовать более мощную модель для продакшена."
        )

