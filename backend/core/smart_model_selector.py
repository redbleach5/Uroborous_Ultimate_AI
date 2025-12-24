"""
SmartModelSelector - Интеллектуальный выбор модели
Автоматически выбирает оптимальную модель на основе сложности задачи
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage


class ModelTier(Enum):
    """Уровни моделей по производительности"""
    FAST = "fast"  # Быстрые модели для простых задач
    BALANCED = "balanced"  # Сбалансированные модели
    POWERFUL = "powerful"  # Мощные модели для сложных задач


@dataclass
class ModelSelection:
    """Результат выбора модели"""
    provider: str
    model: str
    tier: ModelTier
    reason: str
    estimated_tokens: int
    estimated_time: float


class SmartModelSelector:
    """
    Интеллектуальный селектор моделей
    
    Автоматически выбирает оптимальную модель на основе:
    - Сложности задачи
    - Требуемого качества
    - Доступных ресурсов
    - Исторических метрик производительности
    """
    
    def __init__(
        self,
        llm_manager: Optional[LLMProviderManager] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_manager = llm_manager
        self.config = config or {}
        
        # Конфигурация моделей по уровням
        self.model_tiers = self._initialize_model_tiers()
        
        # Метрики производительности (для оптимизации)
        self.performance_metrics: Dict[str, Dict[str, float]] = {}
    
    def _initialize_model_tiers(self) -> Dict[ModelTier, List[Dict[str, Any]]]:
        """Инициализирует конфигурацию моделей по уровням
        
        Оптимизировано для работы с 30+ моделями 60B+ параметров
        """
        # Динамически определяем модели из доступных
        # Пока используем статическую конфигурацию, но можно расширить
        return {
            ModelTier.FAST: [
                {"provider": "ollama", "model": "gemma3:1b", "max_tokens": 500, "speed": "fast"},
                {"provider": "ollama", "model": "tinyllama", "max_tokens": 500, "speed": "fast"},
                # Добавляем быстрые модели для простых задач
                {"provider": "ollama", "model": "phi", "max_tokens": 500, "speed": "fast"},
            ],
            ModelTier.BALANCED: [
                {"provider": "ollama", "model": "llama2", "max_tokens": 2000, "speed": "medium"},
                {"provider": "ollama", "model": "mistral", "max_tokens": 2000, "speed": "medium"},
                {"provider": "ollama", "model": "neural-chat", "max_tokens": 2000, "speed": "medium"},
            ],
            ModelTier.POWERFUL: [
                # Модели 60B+ параметров для сложных задач
                {"provider": "ollama", "model": "llama2:70b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "codellama:70b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "mistral:70b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "llama3:70b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "deepseek-coder:67b", "max_tokens": 4000, "speed": "slow"},
                # Добавляем поддержку других больших моделей
                {"provider": "ollama", "model": "qwen2.5:72b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "mixtral:8x7b", "max_tokens": 4000, "speed": "slow"},
            ]
        }
    
    async def select_model(
        self,
        task: str,
        task_type: Optional[str] = None,
        complexity: Optional[str] = None,
        quality_requirement: str = "balanced"
    ) -> ModelSelection:
        """
        Выбирает оптимальную модель для задачи
        
        Args:
            task: Текст задачи
            task_type: Тип задачи (если известен)
            complexity: Сложность задачи (low, medium, high)
            quality_requirement: Требование к качеству (fast, balanced, high)
        
        Returns:
            ModelSelection с выбранной моделью
        """
        # Определяем сложность, если не указана
        if not complexity:
            complexity = self._estimate_complexity(task, task_type)
        
        # Определяем требуемый уровень модели
        tier = self._determine_tier(complexity, quality_requirement)
        
        # Выбираем конкретную модель из уровня
        model_config = await self._select_from_tier(tier, task)
        
        # Оцениваем производительность
        estimated_tokens = self._estimate_tokens(task, complexity)
        estimated_time = self._estimate_time(model_config, estimated_tokens)
        
        return ModelSelection(
            provider=model_config["provider"],
            model=model_config["model"],
            tier=tier,
            reason=f"Selected {tier.value} tier model for {complexity} complexity task",
            estimated_tokens=estimated_tokens,
            estimated_time=estimated_time
        )
    
    def _estimate_complexity(self, task: str, task_type: Optional[str] = None) -> str:
        """Оценивает сложность задачи"""
        task_len = len(task)
        
        # Простые задачи
        if task_len < 50 or task_type == "simple_chat":
            return "low"
        
        # Сложные проекты
        complex_keywords = [
            "система", "system", "framework", "фреймворк",
            "приложение", "application", "app",
            "игра", "game", "cloud", "облако",
            "IDE", "редактор", "editor"
        ]
        
        if any(keyword in task.lower() for keyword in complex_keywords):
            return "high"
        
        # Средние задачи
        if task_len < 200:
            return "medium"
        else:
            return "high"
    
    def _determine_tier(
        self,
        complexity: str,
        quality_requirement: str
    ) -> ModelTier:
        """Определяет требуемый уровень модели"""
        # Если требуется скорость
        if quality_requirement == "fast":
            return ModelTier.FAST
        
        # Если требуется качество
        if quality_requirement == "high":
            return ModelTier.POWERFUL
        
        # Балансировка на основе сложности
        if complexity == "low":
            return ModelTier.FAST
        elif complexity == "medium":
            return ModelTier.BALANCED
        else:
            return ModelTier.POWERFUL
    
    async def _select_from_tier(
        self,
        tier: ModelTier,
        task: str
    ) -> Dict[str, Any]:
        """Выбирает конкретную модель из уровня
        
        Оптимизировано для работы с 30+ моделями:
        - Проверяет доступность моделей
        - Выбирает на основе метрик производительности
        - Балансирует нагрузку между моделями
        """
        available_models = self.model_tiers.get(tier, [])
        
        if not available_models:
            # Fallback на первый доступный
            return {"provider": "ollama", "model": "gemma3:1b", "max_tokens": 2000}
        
        # Получаем список доступных моделей
        available_actual_models = []
        if self.llm_manager:
            provider = self.llm_manager.providers.get("ollama")
            if provider and hasattr(provider, 'list_models'):
                try:
                    actual_models = await provider.list_models()
                    # Фильтруем только доступные модели из нашего списка
                    for model_config in available_models:
                        model_name = model_config["model"]
                        # Проверяем точное совпадение или частичное (для версий)
                        if model_name in actual_models:
                            available_actual_models.append(model_config)
                        else:
                            # Проверяем частичное совпадение (например, "llama2:70b" vs "llama2")
                            for actual_model in actual_models:
                                if model_name.split(":")[0] in actual_model or actual_model in model_name:
                                    model_config_copy = model_config.copy()
                                    model_config_copy["model"] = actual_model
                                    available_actual_models.append(model_config_copy)
                                    break
                except Exception as e:
                    logger.warning(f"Failed to list models: {e}")
        
        # Если не нашли доступные, используем конфигурацию как есть
        if not available_actual_models:
            available_actual_models = available_models
        
        # Выбираем модель на основе метрик производительности
        if self.performance_metrics and available_actual_models:
            # Сортируем по метрикам (лучшие первыми)
            def score_model(model_config):
                model_name = model_config["model"]
                key = f"ollama:{model_name}"
                metrics = self.performance_metrics.get(key, {})
                
                # Оценка на основе метрик
                score = 0
                if metrics.get("success_count", 0) > 0:
                    success_rate = metrics["success_count"] / max(metrics.get("total_calls", 1), 1)
                    score += success_rate * 50  # До 50 баллов за успешность
                
                if metrics.get("avg_tokens_per_sec", 0) > 0:
                    score += min(metrics["avg_tokens_per_sec"] / 10, 30)  # До 30 баллов за скорость
                
                return score
            
            available_actual_models.sort(key=score_model, reverse=True)
        
        # Выбираем лучшую доступную модель
        selected = available_actual_models[0] if available_actual_models else available_models[0]
        
        return selected
    
    def _estimate_tokens(self, task: str, complexity: str) -> int:
        """Оценивает количество токенов для задачи"""
        # Простая оценка: ~4 символа на токен
        base_tokens = len(task) // 4
        
        # Множитель сложности
        multipliers = {
            "low": 1.0,
            "medium": 2.0,
            "high": 4.0
        }
        
        multiplier = multipliers.get(complexity, 2.0)
        return int(base_tokens * multiplier)
    
    def _estimate_time(
        self,
        model_config: Dict[str, Any],
        tokens: int
    ) -> float:
        """Оценивает время выполнения"""
        # Базовая скорость (токенов в секунду)
        speeds = {
            "fast": 50,  # Быстрые модели
            "medium": 20,  # Средние модели
            "slow": 10  # Медленные модели
        }
        
        speed = speeds.get(model_config.get("speed", "medium"), 20)
        return tokens / speed
    
    def record_performance(
        self,
        provider: str,
        model: str,
        tokens: int,
        duration: float,
        success: bool
    ):
        """Записывает метрики производительности для оптимизации"""
        key = f"{provider}:{model}"
        
        if key not in self.performance_metrics:
            self.performance_metrics[key] = {
                "total_calls": 0,
                "total_tokens": 0,
                "total_duration": 0.0,
                "success_count": 0,
                "avg_tokens_per_sec": 0.0
            }
        
        metrics = self.performance_metrics[key]
        metrics["total_calls"] += 1
        metrics["total_tokens"] += tokens
        metrics["total_duration"] += duration
        if success:
            metrics["success_count"] += 1
        
        # Обновляем среднюю скорость
        if duration > 0:
            metrics["avg_tokens_per_sec"] = tokens / duration
    
    async def get_best_model_for_task(
        self,
        task: str,
        task_type: Optional[str] = None
    ) -> ModelSelection:
        """Возвращает лучшую модель на основе исторических метрик"""
        # Пока используем базовый выбор
        # В будущем можно добавить ML-оптимизацию на основе метрик
        return await self.select_model(task, task_type)

