"""
Resource-Aware Model Selector - Адаптивный выбор модели под доступные ресурсы
Автоматически подстраивается под любое количество ресурсов с минимальной потерей качества

Ключевые возможности:
- Распределённый выбор моделей между несколькими Ollama серверами
- Автоматическая маршрутизация на сервер с нужной моделью
- Fallback на альтернативные модели/серверы
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from .smart_model_selector import SmartModelSelector, ModelTier, ModelSelection
from .model_performance_tracker import get_performance_tracker
from .distributed_model_router import DistributedModelRouter, RoutingDecision


class ResourceLevel(Enum):
    """Уровни доступных ресурсов"""
    MINIMAL = "minimal"  # Малые модели для отладки (1-3B)
    LOW = "low"  # Низкие ресурсы (3-7B)
    MEDIUM = "medium"  # Средние ресурсы (7-13B)
    HIGH = "high"  # Высокие ресурсы (13-30B)
    MAXIMUM = "maximum"  # Максимальные ресурсы (30B+)


@dataclass
class ResourceInfo:
    """Информация о доступных ресурсах"""
    level: ResourceLevel
    available_models: List[str]
    gpu_memory_gb: Optional[float] = None
    gpu_count: int = 1  # Количество GPU
    total_gpu_memory_gb: Optional[float] = None  # Суммарная память всех GPU
    cpu_cores: Optional[int] = None
    total_memory_gb: Optional[float] = None
    estimated_capacity: int = 1  # Количество параллельных запросов
    can_run_large_models: bool = False  # Может ли запускать 70B+ модели


@dataclass
class AdaptiveSelection:
    """Адаптивный выбор модели с учетом ресурсов и распределения между серверами"""
    model: str
    provider: str
    tier: ModelTier
    resource_level: ResourceLevel
    quality_estimate: float  # 0.0 - 1.0, оценка качества относительно идеала
    speed_estimate: float  # Оценка скорости
    reason: str
    fallback_models: List[str]  # Резервные модели если основная недоступна
    # Распределённая маршрутизация
    server_url: Optional[str] = None  # URL сервера где есть модель
    server_name: Optional[str] = None  # Имя сервера
    used_distributed_routing: bool = False  # Была ли использована распределённая маршрутизация
    routing_alternatives: List[Tuple[str, str]] = field(default_factory=list)  # [(model, server_url)]


class ResourceAwareSelector:
    """
    Адаптивный селектор моделей, который подстраивается под доступные ресурсы
    
    Ключевые особенности:
    - Распределённый выбор между несколькими Ollama серверами
    - Автоматическое определение доступных ресурсов
    - Выбор оптимальной модели под ресурсы
    - Адаптация сложности задач под малые модели
    - Fallback на более простые модели при перегрузке
    - Минимальная потеря качества при работе с малыми моделями
    """
    
    def __init__(
        self,
        llm_manager: Optional[LLMProviderManager] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_manager = llm_manager
        self.config = config or {}
        self.smart_selector = SmartModelSelector(llm_manager, config) if llm_manager else None
        self.performance_tracker = get_performance_tracker()
        
        # Распределённый роутер для нескольких серверов
        ollama_config = self.config.get("llm", {}).get("providers", {}).get("ollama", {})
        self.distributed_mode = ollama_config.get("distributed_mode", False)
        self.distributed_router: Optional[DistributedModelRouter] = None
        
        if self.distributed_mode:
            self.distributed_router = DistributedModelRouter(self.config)
            logger.info("Distributed model routing enabled")
        
        # Кэш информации о ресурсах
        self._resource_info: Optional[ResourceInfo] = None
        self._resource_cache_ttl = 300  # 5 минут
        self._last_resource_check = 0.0
        
        # Конфигурация адаптации
        self.adaptation_config = {
            "minimal_quality_threshold": 0.6,  # Минимальное качество для малых моделей
            "enable_prompt_optimization": True,  # Оптимизация промптов для малых моделей
            "enable_task_decomposition": True,  # Декомпозиция сложных задач
            "fallback_enabled": True,  # Включить fallback
            "quality_vs_speed_balance": 0.7  # Баланс качества и скорости (0.0 = скорость, 1.0 = качество)
        }
    
    async def discover_resources(self) -> ResourceInfo:
        """Обнаруживает доступные ресурсы со всех серверов (при распределённом режиме)"""
        # Проверяем кэш
        current_time = time.time()
        if (self._resource_info and 
            current_time - self._last_resource_check < self._resource_cache_ttl):
            return self._resource_info
        
        available_models = []
        resource_level = ResourceLevel.MINIMAL
        
        # ======= РАСПРЕДЕЛЁННЫЙ РЕЖИМ: собираем модели со ВСЕХ серверов =======
        if self.distributed_router:
            try:
                servers = await self.distributed_router.discover_all_servers()
                # Собираем уникальные модели со всех доступных серверов
                all_models = set()
                for server in servers.values():
                    if server.is_available:
                        all_models.update(server.available_models)
                available_models = list(all_models)
                logger.info(f"Distributed discovery: {len(available_models)} models across {len([s for s in servers.values() if s.is_available])} servers")
            except Exception as e:
                logger.warning(f"Distributed discovery failed: {e}, falling back to local")
        
        # Fallback на локальный провайдер если нет распределённого или он не сработал
        if not available_models and self.llm_manager:
            ollama_provider = self.llm_manager.providers.get("ollama")
            if ollama_provider:
                try:
                    available_models = await ollama_provider.list_models()
                    logger.info(f"Local discovery: {len(available_models)} available models")
                except Exception as e:
                    logger.warning(f"Failed to list models: {e}")
        
        # Определяем уровень ресурсов на основе доступных моделей
        resource_level = self._determine_resource_level(available_models)
        
        # Оцениваем GPU память (если доступно)
        gpu_memory, gpu_count, total_gpu_memory = await self._estimate_gpu_memory()
        
        # Оцениваем CPU
        try:
            import os
            cpu_cores = os.cpu_count() or 4
        except:
            cpu_cores = 4
        
        # Оцениваем общую память
        try:
            import psutil
            total_memory_gb = psutil.virtual_memory().total / (1024**3)
        except:
            total_memory_gb = None
        
        # Оцениваем capacity на основе ресурсов (с учётом multi-GPU)
        capacity = self._estimate_capacity(resource_level, gpu_memory, cpu_cores, gpu_count)
        
        # Определяем возможность запуска больших моделей
        # 70B модель требует ~40GB VRAM, с 3x RTX 3090 (72GB) это возможно
        can_run_large = total_gpu_memory is not None and total_gpu_memory >= 40
        
        self._resource_info = ResourceInfo(
            level=resource_level,
            available_models=available_models,
            gpu_memory_gb=gpu_memory,
            gpu_count=gpu_count,
            total_gpu_memory_gb=total_gpu_memory,
            cpu_cores=cpu_cores,
            total_memory_gb=total_memory_gb,
            estimated_capacity=capacity,
            can_run_large_models=can_run_large
        )
        
        self._last_resource_check = current_time
        
        logger.info(
            f"Resource level: {resource_level.value}, "
            f"Models: {len(available_models)}, "
            f"Capacity: {capacity} parallel requests"
        )
        
        return self._resource_info
    
    def _determine_resource_level(self, models: List[str]) -> ResourceLevel:
        """Определяет уровень ресурсов на основе доступных моделей"""
        if not models:
            return ResourceLevel.MINIMAL
        
        # Анализируем модели по размеру
        large_models = 0  # 30B+
        medium_models = 0  # 13-30B
        small_models = 0  # 7-13B
        tiny_models = 0  # <7B
        
        for model in models:
            model_lower = model.lower()
            
            # Определяем размер модели по названию
            if any(x in model_lower for x in ["70b", "72b", "65b", "67b"]):
                large_models += 1
            elif any(x in model_lower for x in ["30b", "34b", "40b"]):
                medium_models += 1
            elif any(x in model_lower for x in ["13b", "14b", "15b", "20b"]):
                small_models += 1
            else:
                # Проверяем на малые модели
                if any(x in model_lower for x in ["1b", "2b", "3b", "7b", "8b"]):
                    tiny_models += 1
                else:
                    # Если не можем определить, считаем маленькой
                    tiny_models += 1
        
        # Определяем уровень ресурсов
        if large_models > 0:
            return ResourceLevel.MAXIMUM
        elif medium_models > 0:
            return ResourceLevel.HIGH
        elif small_models > 0:
            return ResourceLevel.MEDIUM
        elif tiny_models > 0:
            return ResourceLevel.LOW
        else:
            return ResourceLevel.MINIMAL
    
    async def _estimate_gpu_memory(self) -> Tuple[Optional[float], int, Optional[float]]:
        """
        Оценивает доступную GPU память
        
        Returns:
            Tuple[memory_per_gpu, gpu_count, total_memory]
        """
        try:
            import subprocess
            # Пробуем nvidia-smi для всех GPU
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_count = len(lines)
                total_memory = 0.0
                
                for line in lines:
                    parts = line.split(',')
                    if parts:
                        memory_mb = float(parts[0].strip())
                        total_memory += memory_mb
                
                memory_per_gpu = total_memory / gpu_count / 1024  # В GB
                total_memory_gb = total_memory / 1024
                
                logger.info(f"Detected {gpu_count} GPU(s) with {total_memory_gb:.1f} GB total VRAM")
                
                return memory_per_gpu, gpu_count, total_memory_gb
        except Exception as e:
            logger.debug(f"Failed to get GPU memory via nvidia-smi: {e}")
        
        return None, 0, None
    
    def _estimate_capacity(
        self,
        level: ResourceLevel,
        gpu_memory: Optional[float],
        cpu_cores: int,
        gpu_count: int = 1
    ) -> int:
        """
        Оценивает capacity (количество параллельных запросов)
        с учётом multi-GPU конфигурации
        """
        base_capacity = {
            ResourceLevel.MINIMAL: 1,
            ResourceLevel.LOW: 2,
            ResourceLevel.MEDIUM: 5,
            ResourceLevel.HIGH: 10,
            ResourceLevel.MAXIMUM: 20
        }
        
        capacity = base_capacity.get(level, 1)
        
        # Корректируем на основе GPU памяти (на одну карту)
        if gpu_memory:
            if gpu_memory >= 24:  # RTX 3090, RTX 4090, A100
                capacity = min(capacity * 2, 30)
            elif gpu_memory >= 16:  # RTX 4080, A10
                capacity = min(int(capacity * 1.5), 20)
            elif gpu_memory < 8:
                capacity = max(1, capacity // 2)
        
        # MULTI-GPU: увеличиваем capacity пропорционально количеству GPU
        if gpu_count > 1:
            # Каждый дополнительный GPU добавляет ~80% capacity
            # (не 100% из-за overhead на координацию)
            gpu_multiplier = 1 + (gpu_count - 1) * 0.8
            capacity = int(capacity * gpu_multiplier)
            logger.info(f"Multi-GPU capacity boost: {gpu_count} GPUs -> {gpu_multiplier:.1f}x multiplier")
        
        # Корректируем на основе CPU (12900K = 24 threads)
        if cpu_cores >= 24:
            capacity = min(capacity + 10, 50)
        elif cpu_cores >= 16:
            capacity = min(capacity + 5, 40)
        elif cpu_cores < 4:
            capacity = max(1, capacity - 1)
        
        # Верхний предел для стабильности
        return min(capacity, 50)
    
    async def select_adaptive_model(
        self,
        task: str,
        task_type: Optional[str] = None,
        complexity: Optional[str] = None,
        quality_requirement: Optional[str] = None,
        preferred_model: Optional[str] = None
    ) -> AdaptiveSelection:
        """
        Адаптивный выбор модели с учетом доступных ресурсов И распределения между серверами
        
        Args:
            task: Текст задачи
            task_type: Тип задачи
            complexity: Сложность задачи
            quality_requirement: Требование к качеству (fast, balanced, high)
            preferred_model: Предпочитаемая модель
        
        Returns:
            AdaptiveSelection с выбранной моделью, сервером и стратегией адаптации
        """
        # Обнаруживаем ресурсы
        resources = await self.discover_resources()
        
        # Определяем сложность, если не указана
        if not complexity:
            complexity = self._estimate_complexity(task, task_type)
        
        # Адаптируем качество под ресурсы
        quality_requirement = self._adapt_quality_requirement(
            quality_requirement,
            resources.level,
            complexity
        )
        
        # ======= РАСПРЕДЕЛЁННАЯ МАРШРУТИЗАЦИЯ =======
        routing_decision: Optional[RoutingDecision] = None
        if self.distributed_router:
            try:
                require_fast = quality_requirement == "fast" or complexity in ["trivial", "simple"]
                routing_decision = await self.distributed_router.route_request(
                    preferred_model=preferred_model,
                    task_type=task_type or "chat",
                    complexity=complexity,
                    require_fast=require_fast
                )
                logger.info(
                    f"Distributed routing: {routing_decision.model} @ {routing_decision.server_name} "
                    f"(fallback: {routing_decision.used_fallback})"
                )
            except Exception as e:
                logger.warning(f"Distributed routing failed: {e}, using local selection")
        
        # Выбираем модель
        if self.smart_selector:
            try:
                selection = await self.smart_selector.select_model(
                    task=task,
                    task_type=task_type,
                    complexity=complexity,
                    quality_requirement=quality_requirement
                )
                
                # Если есть распределённый роутинг — ВСЕГДА используем его выбор
                # (он учитывает реальные ресурсы и доступность серверов)
                if routing_decision and routing_decision.model:
                    selection.model = routing_decision.model
                    selection.reason = f"Distributed: {routing_decision.reason}"
                    logger.debug(f"Using distributed router selection: {routing_decision.model}")
                else:
                    # Без distributed router — проверяем доступность модели
                    if selection.model not in resources.available_models:
                        selection = self._find_alternative_model(
                            selection,
                            resources,
                            complexity
                        )
                
                # Оцениваем качество относительно идеала
                quality_estimate = self._estimate_quality(
                    selection,
                    resources.level,
                    complexity
                )
                
                # Оцениваем скорость
                speed_estimate = self._estimate_speed(selection, resources)
                
                # Находим fallback модели
                fallback_models = self._find_fallback_models(
                    selection.model,
                    resources,
                    complexity
                )
                
                # Формируем результат с учётом распределённой маршрутизации
                result = AdaptiveSelection(
                    model=selection.model,
                    provider=selection.provider,
                    tier=selection.tier,
                    resource_level=resources.level,
                    quality_estimate=quality_estimate,
                    speed_estimate=speed_estimate,
                    reason=f"Selected for {resources.level.value} resources, "
                           f"quality: {quality_estimate:.2f}, "
                           f"speed: {speed_estimate:.2f}",
                    fallback_models=fallback_models,
                    used_distributed_routing=routing_decision is not None
                )
                
                # Добавляем информацию о сервере если использовали распределённый роутинг
                if routing_decision:
                    result.server_url = routing_decision.server_url
                    result.server_name = routing_decision.server_name
                    result.routing_alternatives = routing_decision.alternatives
                    result.reason = f"Distributed: {routing_decision.server_name} ({routing_decision.reason})"
                
                return result
            except Exception as e:
                logger.warning(f"SmartModelSelector failed: {e}, using fallback")
        
        # Fallback на простой выбор
        fallback = self._fallback_selection(resources, complexity)
        
        # Применяем распределённый роутинг к fallback если есть
        if routing_decision:
            fallback.model = routing_decision.model
            fallback.server_url = routing_decision.server_url
            fallback.server_name = routing_decision.server_name
            fallback.used_distributed_routing = True
            fallback.routing_alternatives = routing_decision.alternatives
            fallback.reason = f"Distributed fallback: {routing_decision.reason}"
        
        return fallback
    
    def _adapt_quality_requirement(
        self,
        quality_requirement: Optional[str],
        resource_level: ResourceLevel,
        complexity: str
    ) -> str:
        """Адаптирует требование к качеству под доступные ресурсы"""
        if not quality_requirement:
            quality_requirement = "balanced"
        
        # Для малых ресурсов снижаем требования к качеству
        if resource_level in [ResourceLevel.MINIMAL, ResourceLevel.LOW]:
            if quality_requirement == "high":
                return "balanced"
            elif quality_requirement == "balanced" and complexity == "high":
                return "fast"  # Для сложных задач на малых ресурсах - скорость
        
        return quality_requirement
    
    def _estimate_complexity(self, task: str, task_type: Optional[str] = None) -> str:
        """Оценивает сложность задачи"""
        task_len = len(task)
        
        if task_len < 50:
            return "low"
        
        complex_keywords = [
            "система", "system", "framework", "фреймворк",
            "приложение", "application", "app",
            "игра", "game", "cloud", "облако",
            "IDE", "редактор", "editor"
        ]
        
        if any(keyword in task.lower() for keyword in complex_keywords):
            return "high"
        
        if task_len < 200:
            return "medium"
        else:
            return "high"
    
    def _find_alternative_model(
        self,
        selection: ModelSelection,
        resources: ResourceInfo,
        complexity: str
    ) -> ModelSelection:
        """Находит альтернативную модель если выбранная недоступна"""
        # Ищем модель того же tier
        tier_models = {
            ModelTier.FAST: ["gemma3:1b", "tinyllama", "phi"],
            ModelTier.BALANCED: ["llama2", "mistral", "neural-chat"],
            ModelTier.POWERFUL: ["llama2:70b", "codellama:70b", "mistral:70b"]
        }
        
        candidates = tier_models.get(selection.tier, [])
        
        # Ищем первую доступную
        for candidate in candidates:
            if candidate in resources.available_models:
                selection.model = candidate
                selection.reason = f"Alternative model selected: {candidate}"
                return selection
        
        # Если не нашли, используем первую доступную
        if resources.available_models:
            selection.model = resources.available_models[0]
            selection.reason = f"Fallback to first available: {selection.model}"
        
        return selection
    
    def _estimate_quality(
        self,
        selection: ModelSelection,
        resource_level: ResourceLevel,
        complexity: str
    ) -> float:
        """Оценивает качество относительно идеала (0.0 - 1.0)"""
        # Базовое качество на основе tier
        tier_quality = {
            ModelTier.FAST: 0.6,
            ModelTier.BALANCED: 0.8,
            ModelTier.POWERFUL: 0.95
        }
        
        base_quality = tier_quality.get(selection.tier, 0.7)
        
        # Корректируем на основе ресурсов
        if resource_level == ResourceLevel.MINIMAL:
            base_quality *= 0.85  # Небольшое снижение для минимальных ресурсов
        elif resource_level == ResourceLevel.LOW:
            base_quality *= 0.9
        
        # Корректируем на основе сложности
        if complexity == "high" and selection.tier == ModelTier.FAST:
            base_quality *= 0.9  # Сложные задачи на быстрых моделях
        
        # Используем метрики производительности если доступны
        tracker = get_performance_tracker()
        metrics = tracker.get_metrics(selection.provider, selection.model)
        
        if metrics.total_requests > 0:
            success_rate = metrics.successful_requests / metrics.total_requests
            base_quality = (base_quality + success_rate) / 2  # Усредняем
        
        return min(1.0, max(0.0, base_quality))
    
    def _estimate_speed(
        self,
        selection: ModelSelection,
        resources: ResourceInfo
    ) -> float:
        """Оценивает скорость (токенов в секунду)"""
        # Базовые скорости по tier
        tier_speed = {
            ModelTier.FAST: 50.0,
            ModelTier.BALANCED: 20.0,
            ModelTier.POWERFUL: 10.0
        }
        
        base_speed = tier_speed.get(selection.tier, 20.0)
        
        # Используем реальные метрики если доступны
        tracker = get_performance_tracker()
        metrics = tracker.get_metrics(selection.provider, selection.model)
        
        if metrics.avg_tokens_per_sec > 0:
            base_speed = metrics.avg_tokens_per_sec
        
        return base_speed
    
    def _find_fallback_models(
        self,
        primary_model: str,
        resources: ResourceInfo,
        complexity: str
    ) -> List[str]:
        """Находит резервные модели для fallback"""
        fallback = []
        
        # Ищем модели того же или более низкого tier
        for model in resources.available_models:
            if model == primary_model:
                continue
            
            # Простые модели для простых задач
            if complexity == "low":
                if any(x in model.lower() for x in ["1b", "2b", "3b", "tiny"]):
                    fallback.append(model)
            # Более мощные для сложных
            elif complexity == "high":
                if any(x in model.lower() for x in ["7b", "13b", "14b", "70b"]):
                    fallback.append(model)
            else:
                fallback.append(model)
        
        # Ограничиваем количество
        return fallback[:3]
    
    def _fallback_selection(
        self,
        resources: ResourceInfo,
        complexity: str
    ) -> AdaptiveSelection:
        """Простой fallback выбор модели"""
        if not resources.available_models:
            raise ValueError("No models available")
        
        # Выбираем первую доступную
        model = resources.available_models[0]
        
        # Определяем tier
        if any(x in model.lower() for x in ["1b", "2b", "3b", "tiny"]):
            tier = ModelTier.FAST
        elif any(x in model.lower() for x in ["70b", "72b", "65b"]):
            tier = ModelTier.POWERFUL
        else:
            tier = ModelTier.BALANCED
        
        return AdaptiveSelection(
            model=model,
            provider="ollama",
            tier=tier,
            resource_level=resources.level,
            quality_estimate=0.7,
            speed_estimate=20.0,
            reason="Fallback selection",
            fallback_models=resources.available_models[1:3] if len(resources.available_models) > 1 else []
        )
    
    def should_optimize_prompt(self, resource_level: ResourceLevel) -> bool:
        """Определяет нужно ли оптимизировать промпт для малых моделей"""
        return (self.adaptation_config["enable_prompt_optimization"] and
                resource_level in [ResourceLevel.MINIMAL, ResourceLevel.LOW])
    
    def should_decompose_task(
        self,
        resource_level: ResourceLevel,
        complexity: str
    ) -> bool:
        """Определяет нужно ли декомпозировать задачу"""
        return (self.adaptation_config["enable_task_decomposition"] and
                resource_level in [ResourceLevel.MINIMAL, ResourceLevel.LOW] and
                complexity == "high")

