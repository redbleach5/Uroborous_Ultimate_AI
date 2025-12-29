"""
SmartModelSelector - Интеллектуальный выбор модели
Автоматически выбирает оптимальную модель на основе сложности задачи
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from .logger import get_logger
from .types import ComplexityLevel, ModelTier

logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from .task_complexity_service import get_complexity_service


@dataclass
class SmartModelSelection:
    """Результат выбора модели от SmartModelSelector"""
    provider: str
    model: str
    tier: ModelTier
    reason: str
    estimated_tokens: int
    estimated_time: float


# Алиас для обратной совместимости
ModelSelection = SmartModelSelection


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
        
        # Конфигурация моделей по уровням (будет заполнена динамически)
        self.model_tiers: Dict[ModelTier, List[Dict[str, Any]]] = {
            ModelTier.FAST: [],
            ModelTier.BALANCED: [],
            ModelTier.POWERFUL: [],
        }
        
        # Кэш доступных моделей
        self._available_models_cache: List[str] = []
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300  # 5 минут
        
        # Метрики производительности (для оптимизации)
        self.performance_metrics: Dict[str, Dict[str, float]] = {}
    
    async def _refresh_model_tiers(self) -> None:
        """
        Динамически загружает доступные модели с сервера и распределяет по tier'ам.
        """
        import time
        
        current_time = time.time()
        if current_time - self._cache_timestamp < self._cache_ttl and self._available_models_cache:
            return
        
        available_models = []
        
        # Получаем список моделей с Ollama
        if self.llm_manager:
            ollama_provider = self.llm_manager.providers.get("ollama")
            if ollama_provider and hasattr(ollama_provider, 'list_models'):
                try:
                    available_models = await ollama_provider.list_models()
                    logger.debug(f"Loaded {len(available_models)} models from Ollama")
                except Exception as e:
                    logger.warning(f"Failed to list models from Ollama: {e}")
        
        if not available_models:
            # Fallback на статические модели если не удалось получить список
            self.model_tiers = self._get_fallback_tiers()
            return
        
        # Распределяем модели по tier'ам на основе размера
        fast_models = []
        balanced_models = []
        powerful_models = []
        
        for model_name in available_models:
            model_info = self._classify_model(model_name)
            
            if model_info["tier"] == "fast":
                fast_models.append(model_info)
            elif model_info["tier"] == "balanced":
                balanced_models.append(model_info)
            else:
                powerful_models.append(model_info)
        
        self.model_tiers = {
            ModelTier.FAST: fast_models if fast_models else self._get_fallback_tiers()[ModelTier.FAST],
            ModelTier.BALANCED: balanced_models if balanced_models else self._get_fallback_tiers()[ModelTier.BALANCED],
            ModelTier.POWERFUL: powerful_models if powerful_models else self._get_fallback_tiers()[ModelTier.POWERFUL],
        }
        
        self._available_models_cache = available_models
        self._cache_timestamp = current_time
        
        logger.info(
            f"Model tiers updated: fast={len(fast_models)}, "
            f"balanced={len(balanced_models)}, powerful={len(powerful_models)}"
        )
    
    def _classify_model(self, model_name: str) -> Dict[str, Any]:
        """
        Классифицирует модель по размеру и определяет её tier.
        """
        import re
        
        model_name.lower()
        
        # Извлекаем размер модели
        size_b = 7.0  # Default
        
        match = re.search(r':?(\d+(?:\.\d+)?)[bB]', model_name)
        if match:
            size_b = float(match.group(1))
        elif ':' in model_name:
            tag = model_name.split(':')[1]
            match = re.search(r'(\d+(?:\.\d+)?)', tag)
            if match:
                size_b = float(match.group(1))
        
        # Определяем tier по размеру
        if size_b <= 4:
            tier = "fast"
            speed = "fast"
            max_tokens = 500
        elif size_b <= 14:
            tier = "balanced"
            speed = "medium"
            max_tokens = 2000
        else:
            tier = "powerful"
            speed = "slow"
            max_tokens = 4000
        
        return {
            "provider": "ollama",
            "model": model_name,
            "size_b": size_b,
            "max_tokens": max_tokens,
            "speed": speed,
            "tier": tier,
        }
    
    def _get_fallback_tiers(self) -> Dict[ModelTier, List[Dict[str, Any]]]:
        """Возвращает fallback конфигурацию моделей"""
        return {
            ModelTier.FAST: [
                {"provider": "ollama", "model": "llama3.2:3b", "max_tokens": 500, "speed": "fast"},
                {"provider": "ollama", "model": "gemma2:2b", "max_tokens": 500, "speed": "fast"},
            ],
            ModelTier.BALANCED: [
                {"provider": "ollama", "model": "llama3.2:latest", "max_tokens": 2000, "speed": "medium"},
                {"provider": "ollama", "model": "gemma2:9b", "max_tokens": 2000, "speed": "medium"},
            ],
            ModelTier.POWERFUL: [
                {"provider": "ollama", "model": "llama3.1:70b", "max_tokens": 4000, "speed": "slow"},
                {"provider": "ollama", "model": "qwen2.5:72b", "max_tokens": 4000, "speed": "slow"},
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
        # Динамически обновляем список моделей с сервера
        await self._refresh_model_tiers()
        
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
        """
        Оценивает сложность задачи используя единый TaskComplexityService.
        
        Returns:
            "low", "medium", или "high"
        """
        service = get_complexity_service()
        result = service.analyze(task, task_type=task_type)
        
        # Маппинг ComplexityLevel на простые уровни
        level_mapping = {
            ComplexityLevel.TRIVIAL: "low",
            ComplexityLevel.SIMPLE: "low",
            ComplexityLevel.MODERATE: "medium",
            ComplexityLevel.COMPLEX: "high",
            ComplexityLevel.VERY_COMPLEX: "high",
            ComplexityLevel.EXTREME: "high",
        }
        
        return level_mapping.get(result.level, "medium")
    
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

