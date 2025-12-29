"""
UnifiedModelRouter - Единая точка входа для выбора модели

Консолидирует функциональность:
- IntelligentModelRouter — динамический скоринг и capabilities
- ResourceAwareSelector — адаптивный выбор по ресурсам  
- TaskRouter — маршрутизация по типу задачи
- SmartModelSelector — выбор по уровням
- DistributedModelRouter — маршрутизация по серверам

Использование:
    router = UnifiedModelRouter(config)
    selection = await router.select_model(task, task_type="code")
    
    # selection содержит:
    # - model: str
    # - server_url: str
    # - provider: str
    # - scores: Dict с оценками
    # - fallbacks: List[str]
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from .logger import get_logger
from .types import ModelTier
from .task_complexity_service import get_complexity_service
from .intelligent_model_router import IntelligentModelRouter, ScoredModel, ModelCapability
from .model_performance_tracker import get_performance_tracker

logger = get_logger(__name__)


@dataclass
class UnifiedModelSelection:
    """Результат унифицированного выбора модели"""
    model: str
    server_url: str
    server_name: str
    provider: str
    tier: ModelTier
    
    # Оценки
    total_score: float
    capability_score: float
    performance_score: float
    speed_score: float
    quality_score: float
    
    # Мета-информация
    complexity_level: str
    reason: str
    fallback_models: List[str] = field(default_factory=list)
    
    # Рекомендации
    recommended_temperature: float = 0.7
    recommended_max_tokens: int = 2000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "server_url": self.server_url,
            "server_name": self.server_name,
            "provider": self.provider,
            "tier": self.tier.value,
            "scores": {
                "total": self.total_score,
                "capability": self.capability_score,
                "performance": self.performance_score,
                "speed": self.speed_score,
                "quality": self.quality_score,
            },
            "complexity_level": self.complexity_level,
            "reason": self.reason,
            "fallback_models": self.fallback_models,
            "recommended_temperature": self.recommended_temperature,
            "recommended_max_tokens": self.recommended_max_tokens,
        }


class IModelRouter(ABC):
    """Интерфейс для роутеров моделей"""
    
    @abstractmethod
    async def select_model(
        self,
        task: str,
        task_type: Optional[str] = None,
        complexity: Optional[str] = None,
        preferred_model: Optional[str] = None
    ) -> UnifiedModelSelection:
        """Выбирает оптимальную модель для задачи"""
        ...
    
    @abstractmethod
    async def discover_models(self) -> List[str]:
        """Обнаруживает доступные модели"""
        ...


class UnifiedModelRouter(IModelRouter):
    """
    Единый маршрутизатор моделей.
    
    Объединяет логику из всех существующих роутеров в один facade.
    Использует IntelligentModelRouter для скоринга и добавляет:
    - Единый анализ сложности через TaskComplexityService
    - Адаптивные рекомендации по температуре и токенам
    - Умные fallbacks
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.complexity_service = get_complexity_service()
        self.performance_tracker = get_performance_tracker()
        
        # Используем IntelligentModelRouter как основной движок
        self.intelligent_router = IntelligentModelRouter(config)
        
        # Температуры по типам задач
        self._temperature_map = {
            "code": 0.1,
            "code_generation": 0.1,
            "analysis": 0.3,
            "research": 0.5,
            "reasoning": 0.4,
            "chat": 0.7,
            "simple_chat": 0.8,
            "creative": 0.9,
            "general": 0.7,
        }
        
        # Токены по сложности
        self._tokens_map = {
            "trivial": 500,
            "simple": 1000,
            "moderate": 2000,
            "complex": 3000,
            "very_complex": 4000,
            "extreme": 6000,
        }
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Инициализация роутера"""
        if self._initialized:
            return
        
        await self.intelligent_router.discover_servers()
        self._initialized = True
        logger.info("UnifiedModelRouter initialized")
    
    async def select_model(
        self,
        task: str,
        task_type: Optional[str] = None,
        complexity: Optional[str] = None,
        preferred_model: Optional[str] = None,
        quality_requirement: Optional[str] = None
    ) -> UnifiedModelSelection:
        """
        Выбирает оптимальную модель для задачи.
        
        Args:
            task: Текст задачи
            task_type: Тип задачи (code, chat, research, analysis, etc.)
            complexity: Сложность (trivial, simple, moderate, complex, very_complex, extreme)
            preferred_model: Предпочитаемая модель (если есть)
            quality_requirement: Требование к качеству (fast, balanced, high)
            
        Returns:
            UnifiedModelSelection с полной информацией о выборе
        """
        if not self._initialized:
            await self.initialize()
        
        # 1. Анализируем сложность через единый сервис
        if not complexity:
            complexity_result = self.complexity_service.analyze(task, task_type=task_type)
            complexity = complexity_result.level.value
        else:
            self._tokens_map.get(complexity, 2000) / 50  # ~50 tokens/sec
        
        # 2. Определяем тип задачи если не указан
        if not task_type:
            task_type = self._infer_task_type(task)
        
        # 3. Получаем выбор от IntelligentModelRouter
        try:
            scored_model = await self.intelligent_router.select_model(
                task=task,
                task_type=task_type,
                complexity=complexity,
                preferred_model=preferred_model
            )
        except ConnectionError as e:
            logger.error(f"No models available: {e}")
            raise
        
        # 4. Определяем tier на основе размера модели
        tier = self._determine_tier(scored_model.profile.size_b, complexity)
        
        # 5. Находим fallback модели
        fallbacks = await self._find_fallbacks(
            scored_model.profile.name,
            task_type,
            complexity
        )
        
        # 6. Определяем оптимальную температуру и токены
        temperature = self._get_optimal_temperature(task_type, complexity)
        max_tokens = self._get_optimal_max_tokens(complexity)
        
        # 7. Формируем результат
        selection = UnifiedModelSelection(
            model=scored_model.profile.name,
            server_url=scored_model.server_url,
            server_name=scored_model.server_name,
            provider="ollama",
            tier=tier,
            total_score=scored_model.total_score,
            capability_score=scored_model.capability_score,
            performance_score=scored_model.performance_score,
            speed_score=scored_model.speed_score,
            quality_score=scored_model.quality_score,
            complexity_level=complexity,
            reason=self._build_reason(scored_model, task_type, complexity),
            fallback_models=fallbacks,
            recommended_temperature=temperature,
            recommended_max_tokens=max_tokens,
        )
        
        logger.info(
            f"UnifiedModelRouter: selected {selection.model} @ {selection.server_name} "
            f"(score: {selection.total_score:.2f}, tier: {tier.value}, "
            f"complexity: {complexity}, temp: {temperature})"
        )
        
        return selection
    
    async def discover_models(self) -> List[str]:
        """Обнаруживает все доступные модели на всех серверах"""
        await self.intelligent_router.discover_servers()
        
        all_models = []
        for server_name, server_info in self.intelligent_router._servers.items():
            if server_info.get("is_available"):
                all_models.extend(server_info.get("models", []))
        
        return list(set(all_models))
    
    async def get_models_ranked(self, task_type: str = "chat") -> List[Dict[str, Any]]:
        """Возвращает все модели с их рейтингами для типа задачи"""
        return self.intelligent_router.get_all_models_ranked(task_type)
    
    def _infer_task_type(self, task: str) -> str:
        """Определяет тип задачи по тексту"""
        task_lower = task.lower()
        
        # Код
        if any(kw in task_lower for kw in [
            "код", "code", "функци", "класс", "python", "javascript",
            "напиши", "создай", "сгенерируй", "игра", "game", "приложение"
        ]):
            return "code"
        
        # Анализ
        if any(kw in task_lower for kw in [
            "проанализируй", "анализ", "analyze", "изучи", "сравни"
        ]):
            return "analysis"
        
        # Исследование
        if any(kw in task_lower for kw in [
            "исследуй", "research", "найди информацию", "что такое"
        ]):
            return "research"
        
        # Рассуждения
        if any(kw in task_lower for kw in [
            "объясни", "почему", "как работает", "логик"
        ]):
            return "reasoning"
        
        # Простой чат
        if any(kw in task_lower for kw in [
            "привет", "здравствуй", "hello", "hi", "как дела"
        ]):
            return "simple_chat"
        
        return "general"
    
    def _determine_tier(self, model_size_b: float, complexity: str) -> ModelTier:
        """Определяет tier модели на основе размера и сложности"""
        # По размеру модели
        if model_size_b >= 30:
            base_tier = ModelTier.POWERFUL
        elif model_size_b >= 7:
            base_tier = ModelTier.BALANCED
        else:
            base_tier = ModelTier.FAST
        
        # Корректируем по сложности
        if complexity in ["complex", "very_complex", "extreme"]:
            # Для сложных задач нужны мощные модели
            if base_tier == ModelTier.FAST:
                return ModelTier.BALANCED
        elif complexity in ["trivial", "simple"]:
            # Для простых задач можно использовать быстрые
            if base_tier == ModelTier.POWERFUL:
                return ModelTier.BALANCED
        
        return base_tier
    
    async def _find_fallbacks(
        self,
        primary_model: str,
        task_type: str,
        complexity: str
    ) -> List[str]:
        """Находит резервные модели"""
        fallbacks = []
        
        try:
            ranked = self.intelligent_router.get_all_models_ranked(task_type)
            
            for model_info in ranked:
                model_name = model_info.get("model", "")
                if model_name != primary_model:
                    fallbacks.append(model_name)
                    if len(fallbacks) >= 3:
                        break
        except Exception as e:
            logger.debug(f"Failed to find fallbacks: {e}")
        
        return fallbacks
    
    def _get_optimal_temperature(self, task_type: str, complexity: str) -> float:
        """Определяет оптимальную температуру"""
        base_temp = self._temperature_map.get(task_type, 0.7)
        
        # Для сложных задач чуть снижаем температуру для стабильности
        if complexity in ["complex", "very_complex", "extreme"]:
            base_temp = max(0.1, base_temp - 0.1)
        
        return base_temp
    
    def _get_optimal_max_tokens(self, complexity: str) -> int:
        """Определяет оптимальное количество токенов"""
        return self._tokens_map.get(complexity, 2000)
    
    def _build_reason(
        self,
        scored_model: ScoredModel,
        task_type: str,
        complexity: str
    ) -> str:
        """Строит объяснение выбора"""
        parts = []
        
        if scored_model.capability_score > 0.7:
            parts.append("strong capabilities")
        if scored_model.performance_score > 0.7:
            parts.append("proven performance")
        if scored_model.speed_score > 0.7:
            parts.append("fast")
        if scored_model.quality_score > 0.8:
            parts.append("high quality")
        
        caps = scored_model.profile.capabilities
        if ModelCapability.CODE_GENERATION in caps and task_type == "code":
            parts.append("code-optimized")
        if ModelCapability.REASONING in caps and task_type == "reasoning":
            parts.append("reasoning-optimized")
        
        if not parts:
            parts.append("best available")
        
        return f"Selected for {task_type}/{complexity}: {', '.join(parts)}"


# Singleton instance
_unified_router: Optional[UnifiedModelRouter] = None


def get_unified_router(config: Optional[Dict[str, Any]] = None) -> UnifiedModelRouter:
    """Получить singleton экземпляр UnifiedModelRouter"""
    global _unified_router
    if _unified_router is None:
        if config is None:
            raise ValueError("Config required for first initialization")
        _unified_router = UnifiedModelRouter(config)
    return _unified_router


async def initialize_unified_router(config: Dict[str, Any]) -> UnifiedModelRouter:
    """Инициализировать и вернуть UnifiedModelRouter"""
    router = get_unified_router(config)
    await router.initialize()
    return router

