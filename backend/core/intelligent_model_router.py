"""
Интеллектуальный маршрутизатор моделей

Вместо жёстких списков использует:
- Динамический скоринг на основе возможностей моделей
- Исторические метрики производительности
- Адаптивное обучение на результатах
"""

import re
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import httpx

from .logger import get_logger
from .model_performance_tracker import get_performance_tracker, ModelPerformanceTracker
from .constants import (
    CapabilityThresholds, ScoringWeights, PerformanceThresholds,
    ModelAdjustments, Timeouts
)

logger = get_logger(__name__)


class ModelCapability(Enum):
    """Возможности модели"""
    FAST_RESPONSE = "fast_response"       # Быстрый ответ
    CODE_GENERATION = "code_generation"   # Генерация кода
    REASONING = "reasoning"               # Логические рассуждения
    MULTILINGUAL = "multilingual"         # Многоязычность
    INSTRUCTION_FOLLOWING = "instruction" # Следование инструкциям
    CREATIVE = "creative"                 # Креативность
    FACTUAL = "factual"                   # Фактологическая точность
    LONG_CONTEXT = "long_context"         # Длинный контекст


@dataclass
class ModelProfile:
    """Профиль модели с её характеристиками"""
    name: str
    size_b: float  # Размер в миллиардах параметров
    capabilities: Dict[ModelCapability, float] = field(default_factory=dict)  # 0.0-1.0
    base_speed_score: float = 0.5  # Базовая скорость (0.0-1.0)
    quality_score: float = 0.5     # Базовое качество (0.0-1.0)
    
    @classmethod
    def from_model_name(cls, name: str) -> 'ModelProfile':
        """Автоматически определяет профиль по имени модели"""
        # Извлекаем размер
        size_b = cls._extract_size(name)
        
        # Определяем возможности по названию
        capabilities = cls._infer_capabilities(name, size_b)
        
        # Скорость обратно пропорциональна размеру
        base_speed = max(0.1, 1.0 - (size_b / 30))  # 30b = минимальная скорость
        
        # Качество пропорционально размеру (с насыщением)
        quality = min(0.95, 0.3 + (size_b / 20))  # 20b = почти максимум
        
        return cls(
            name=name,
            size_b=size_b,
            capabilities=capabilities,
            base_speed_score=base_speed,
            quality_score=quality
        )
    
    @staticmethod
    def _extract_size(name: str) -> float:
        """Извлекает размер модели из названия"""
        # Ищем паттерны: 1b, 3b, 7b, 14b, 70b и т.д.
        match = re.search(r':?(\d+(?:\.\d+)?)[bB]', name)
        if match:
            return float(match.group(1))
        
        # Ищем после двоеточия
        if ':' in name:
            tag = name.split(':')[1]
            match = re.search(r'(\d+(?:\.\d+)?)', tag)
            if match:
                return float(match.group(1))
        
        # По умолчанию предполагаем средний размер
        return 7.0
    
    @staticmethod
    def _infer_capabilities(name: str, size_b: float) -> Dict[ModelCapability, float]:
        """Определяет возможности модели по названию"""
        caps = {}
        name_lower = name.lower()
        
        # Кодовые модели
        if any(kw in name_lower for kw in ['coder', 'code', 'deepseek-coder', 'stable-code']):
            caps[ModelCapability.CODE_GENERATION] = CapabilityThresholds.HIGH_CAPABILITY
            caps[ModelCapability.INSTRUCTION_FOLLOWING] = CapabilityThresholds.HIGH_QUALITY_MIN
        
        # Модели для рассуждений
        if any(kw in name_lower for kw in ['r1', 'reasoning', 'think']):
            caps[ModelCapability.REASONING] = CapabilityThresholds.HIGH_CAPABILITY
        
        # Быстрые маленькие модели
        if size_b <= CapabilityThresholds.SMALL_MODEL_MAX_SIZE:
            caps[ModelCapability.FAST_RESPONSE] = CapabilityThresholds.HIGH_CAPABILITY
        elif size_b <= CapabilityThresholds.MEDIUM_MODEL_MAX_SIZE:
            caps[ModelCapability.FAST_RESPONSE] = CapabilityThresholds.MEDIUM_CAPABILITY - 0.1
        
        # Gemma хороша для многоязычности и инструкций
        if 'gemma' in name_lower:
            caps[ModelCapability.MULTILINGUAL] = CapabilityThresholds.GOOD_CAPABILITY
            caps[ModelCapability.INSTRUCTION_FOLLOWING] = CapabilityThresholds.GOOD_CAPABILITY
            if size_b >= 4:
                caps[ModelCapability.FACTUAL] = CapabilityThresholds.HIGH_QUALITY_MIN
        
        # Qwen - хороший универсал
        if 'qwen' in name_lower:
            caps[ModelCapability.MULTILINGUAL] = CapabilityThresholds.HIGH_CAPABILITY
            caps[ModelCapability.INSTRUCTION_FOLLOWING] = CapabilityThresholds.GOOD_CAPABILITY
            if size_b >= CapabilityThresholds.MEDIUM_MODEL_MAX_SIZE:
                caps[ModelCapability.REASONING] = 0.75
                caps[ModelCapability.FACTUAL] = CapabilityThresholds.HIGH_QUALITY_MIN
        
        # Llama - хороший английский, средний русский
        if 'llama' in name_lower:
            caps[ModelCapability.REASONING] = CapabilityThresholds.MEDIUM_CAPABILITY
            if size_b >= 8:
                caps[ModelCapability.LONG_CONTEXT] = CapabilityThresholds.HIGH_QUALITY_MIN
        
        # Большие модели лучше в качестве
        if size_b >= CapabilityThresholds.LARGE_MODEL_MIN_SIZE:
            caps[ModelCapability.REASONING] = max(caps.get(ModelCapability.REASONING, 0), CapabilityThresholds.GOOD_CAPABILITY)
            caps[ModelCapability.FACTUAL] = max(caps.get(ModelCapability.FACTUAL, 0), CapabilityThresholds.GOOD_CAPABILITY)
        
        return caps


@dataclass
class TaskRequirements:
    """Требования задачи"""
    required_capabilities: Dict[ModelCapability, float] = field(default_factory=dict)
    min_quality: float = 0.5
    prefer_speed: bool = False
    estimated_tokens: int = 500
    
    @classmethod
    def from_task_analysis(cls, task: str, task_type: str, complexity: str) -> 'TaskRequirements':
        """Создаёт требования на основе анализа задачи"""
        requirements = {}
        min_quality = 0.5
        prefer_speed = False
        
        task_lower = task.lower()
        
        # Анализ по ключевым словам
        if any(kw in task_lower for kw in ['код', 'code', 'функци', 'класс', 'python', 'javascript']):
            requirements[ModelCapability.CODE_GENERATION] = 0.8
            min_quality = 0.7
        
        if any(kw in task_lower for kw in ['почему', 'объясни', 'логик', 'причин', 'анализ']):
            requirements[ModelCapability.REASONING] = 0.7
            min_quality = 0.7
        
        if any(kw in task_lower for kw in ['стоит', 'цена', 'новост', 'факт', 'данные', 'статистик']):
            requirements[ModelCapability.FACTUAL] = 0.8
            min_quality = 0.7
        
        if any(kw in task_lower for kw in ['привет', 'как дела', 'спасибо']):
            prefer_speed = True
            min_quality = 0.3
        
        # Анализ по типу задачи
        if task_type == "code":
            requirements[ModelCapability.CODE_GENERATION] = 0.8
        elif task_type == "research":
            requirements[ModelCapability.FACTUAL] = 0.7
            requirements[ModelCapability.INSTRUCTION_FOLLOWING] = 0.7
        elif task_type == "reasoning":
            requirements[ModelCapability.REASONING] = 0.8
        
        # Анализ по сложности
        if complexity in ["trivial", "simple"]:
            prefer_speed = True
            min_quality = max(0.3, min_quality - 0.2)
        elif complexity in ["complex", "very_complex"]:
            min_quality = max(min_quality, 0.8)
            prefer_speed = False
        
        # Оценка токенов
        estimated_tokens = len(task.split()) * 10  # Грубая оценка
        if complexity == "complex":
            estimated_tokens *= 3
        
        return cls(
            required_capabilities=requirements,
            min_quality=min_quality,
            prefer_speed=prefer_speed,
            estimated_tokens=estimated_tokens
        )


@dataclass
class ScoredModel:
    """Модель с её оценкой"""
    profile: ModelProfile
    server_url: str
    server_name: str
    total_score: float
    capability_score: float
    performance_score: float
    speed_score: float
    quality_score: float
    reason: str


class IntelligentModelRouter:
    """
    Интеллектуальный маршрутизатор, выбирающий модели на основе:
    - Возможностей модели (capabilities)
    - Исторической производительности (performance tracker)
    - Требований задачи
    - Доступных ресурсов
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.performance_tracker = get_performance_tracker()
        
        # Кэш профилей моделей
        self._model_profiles: Dict[str, ModelProfile] = {}
        
        # Серверы и их модели
        self._servers: Dict[str, Dict[str, Any]] = {}
        
        # Веса для скоринга (могут адаптироваться)
        self.scoring_weights = {
            "capability": ScoringWeights.CAPABILITY,
            "performance": ScoringWeights.PERFORMANCE,
            "speed": ScoringWeights.SPEED,
            "quality": ScoringWeights.QUALITY
        }
        
        # Configurable discovery settings
        ollama_config = config.get("llm", {}).get("providers", {}).get("ollama", {})
        self._last_discovery = 0
        self._discovery_interval = ollama_config.get("discovery_interval", Timeouts.DISCOVERY_INTERVAL)
        self._timeout = ollama_config.get("discovery_timeout", Timeouts.DISCOVERY_TIMEOUT)
        
        # Thread-safe discovery with asyncio.Lock
        self._discovery_lock: Optional[asyncio.Lock] = None
        self._init_lock = threading.Lock()  # For thread-safe lazy init of asyncio.Lock
        
        self._initialize_from_config()
    
    def _get_discovery_lock(self) -> asyncio.Lock:
        """Lazy initialization of discovery lock (must be created in event loop)
        
        Thread-safe: uses threading.Lock to prevent race conditions during
        asyncio.Lock creation from multiple threads.
        """
        with self._init_lock:
            if self._discovery_lock is None:
                self._discovery_lock = asyncio.Lock()
        return self._discovery_lock
    
    def _initialize_from_config(self):
        """Инициализация серверов из конфига"""
        ollama_config = self.config.get("llm", {}).get("providers", {}).get("ollama", {})
        
        base_url = ollama_config.get("base_url", "http://localhost:11434")
        self._servers["localhost"] = {
            "url": base_url,
            "name": "localhost",
            "models": [],
            "is_available": False,
            "response_time_ms": 0
        }
        
        for server in ollama_config.get("additional_servers", []):
            name = server.get("name", server.get("url", "unknown"))
            self._servers[name] = {
                "url": server.get("url"),
                "name": name,
                "models": [],
                "is_available": False,
                "response_time_ms": 0
            }
    
    async def discover_servers(self):
        """
        Обнаружение серверов и их моделей.
        
        Thread-safe: использует asyncio.Lock для предотвращения race conditions.
        """
        import time
        lock = self._get_discovery_lock()
        
        async with lock:
            current_time = time.time()
            
            # Проверяем кэш внутри lock
            if current_time - self._last_discovery < self._discovery_interval:
                return
            
            async def check_server(name: str, info: Dict):
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        start = time.time()
                        response = await client.get(f"{info['url']}/api/tags")
                        elapsed = (time.time() - start) * 1000
                        
                        if response.status_code == 200:
                            data = response.json()
                            models = [m["name"] for m in data.get("models", [])]
                            
                            info["models"] = models
                            info["is_available"] = True
                            info["response_time_ms"] = elapsed
                            
                            # Создаём профили для новых моделей
                            for model in models:
                                if model not in self._model_profiles:
                                    self._model_profiles[model] = ModelProfile.from_model_name(model)
                            
                            logger.debug(f"Server {name}: {len(models)} models, {elapsed:.0f}ms")
                except Exception as e:
                    info["is_available"] = False
                    logger.debug(f"Server {name} unavailable: {e}")
            
            await asyncio.gather(*[
                check_server(name, info) 
                for name, info in self._servers.items()
            ])
            
            self._last_discovery = current_time
    
    def _get_model_profile(self, model_name: str) -> ModelProfile:
        """Получает или создаёт профиль модели"""
        if model_name not in self._model_profiles:
            self._model_profiles[model_name] = ModelProfile.from_model_name(model_name)
        return self._model_profiles[model_name]
    
    def _calculate_capability_score(
        self, 
        profile: ModelProfile, 
        requirements: TaskRequirements
    ) -> float:
        """Вычисляет соответствие возможностей модели требованиям"""
        if not requirements.required_capabilities:
            return CapabilityThresholds.MEDIUM_CAPABILITY  # Нет требований = средний балл
        
        scores = []
        for cap, required_level in requirements.required_capabilities.items():
            model_level = profile.capabilities.get(cap, CapabilityThresholds.LOW_CAPABILITY)
            # Насколько модель покрывает требование
            coverage = min(1.0, model_level / max(required_level, 0.1))
            scores.append(coverage)
        
        return sum(scores) / len(scores) if scores else CapabilityThresholds.DEFAULT_CAPABILITY
    
    def _get_performance_score(self, model_name: str, provider: str = "ollama") -> float:
        """Получает историческую производительность модели"""
        metrics = self.performance_tracker.get_metrics(provider, model_name)
        
        if metrics.total_requests < PerformanceThresholds.MIN_REQUESTS_FOR_METRICS:
            # Недостаточно данных - используем эвристику
            profile = self._get_model_profile(model_name)
            return profile.quality_score * CapabilityThresholds.HIGH_QUALITY_MIN
        
        # Используем реальные метрики
        success_rate = metrics.successful_requests / max(metrics.total_requests, 1)
        
        # Нормализуем performance_score
        normalized_perf = min(1.0, metrics.performance_score / 100)
        
        return (success_rate * PerformanceThresholds.SUCCESS_RATE_WEIGHT + 
                normalized_perf * PerformanceThresholds.PERFORMANCE_WEIGHT)
    
    def _calculate_speed_score(
        self, 
        profile: ModelProfile, 
        server_response_time: float
    ) -> float:
        """Вычисляет оценку скорости"""
        # Базовая скорость модели
        base_speed = profile.base_speed_score
        
        # Корректируем на время отклика сервера
        server_factor = max(0.5, 1.0 - (server_response_time / PerformanceThresholds.ACCEPTABLE_RESPONSE_TIME))
        
        return base_speed * server_factor
    
    async def select_model(
        self,
        task: str,
        task_type: str = "chat",
        complexity: str = "simple",
        preferred_model: Optional[str] = None
    ) -> ScoredModel:
        """
        Интеллектуальный выбор модели
        
        Returns:
            ScoredModel с лучшей моделью и её оценками
        """
        await self.discover_servers()
        
        # Анализируем требования задачи
        requirements = TaskRequirements.from_task_analysis(task, task_type, complexity)
        
        # Собираем всех кандидатов
        candidates: List[ScoredModel] = []
        
        for server_name, server_info in self._servers.items():
            if not server_info["is_available"]:
                continue
            
            for model_name in server_info["models"]:
                profile = self._get_model_profile(model_name)
                
                # Вычисляем компоненты скора
                capability_score = self._calculate_capability_score(profile, requirements)
                performance_score = self._get_performance_score(model_name)
                speed_score = self._calculate_speed_score(profile, server_info["response_time_ms"])
                quality_score = profile.quality_score
                
                # Проверяем минимальное качество
                if quality_score < requirements.min_quality and not requirements.prefer_speed:
                    continue
                
                # Вычисляем общий скор
                if requirements.prefer_speed:
                    # Для быстрых задач увеличиваем вес скорости
                    total_score = (
                        capability_score * ScoringWeights.SPEED_PREFERRED_CAPABILITY +
                        performance_score * ScoringWeights.SPEED_PREFERRED_PERFORMANCE +
                        speed_score * ScoringWeights.SPEED_PREFERRED_SPEED +
                        quality_score * ScoringWeights.SPEED_PREFERRED_QUALITY
                    )
                else:
                    total_score = (
                        capability_score * self.scoring_weights["capability"] +
                        performance_score * self.scoring_weights["performance"] +
                        speed_score * self.scoring_weights["speed"] +
                        quality_score * self.scoring_weights["quality"]
                    )
                
                # Бонус для предпочитаемой модели
                if preferred_model and model_name == preferred_model:
                    total_score *= ModelAdjustments.PREFERRED_MODEL_BONUS
                
                # Штраф для qwen моделей в не-кодовых задачах (склонны переключаться на китайский)
                model_lower = model_name.lower()
                is_qwen_non_coder = 'qwen' in model_lower and 'coder' not in model_lower
                is_code_task = task_type in ['code', 'ide']
                if is_qwen_non_coder and not is_code_task:
                    total_score *= ModelAdjustments.QWEN_NON_CODER_PENALTY
                    logger.debug(f"Applied penalty to {model_name} (qwen non-coder in non-code task)")
                
                # Бонус для gemma в русскоязычных чат/research задачах
                if 'gemma' in model_lower and task_type in ['chat', 'research', 'general']:
                    total_score *= ModelAdjustments.GEMMA_CHAT_BONUS
                
                reason_parts = []
                if capability_score > CapabilityThresholds.MEDIUM_CAPABILITY:
                    reason_parts.append("good capabilities")
                if performance_score > CapabilityThresholds.MEDIUM_CAPABILITY:
                    reason_parts.append("proven performance")
                if speed_score > CapabilityThresholds.MEDIUM_CAPABILITY:
                    reason_parts.append("fast")
                
                candidates.append(ScoredModel(
                    profile=profile,
                    server_url=server_info["url"],
                    server_name=server_name,
                    total_score=total_score,
                    capability_score=capability_score,
                    performance_score=performance_score,
                    speed_score=speed_score,
                    quality_score=quality_score,
                    reason=", ".join(reason_parts) if reason_parts else "available"
                ))
        
        if not candidates:
            raise ConnectionError("No suitable models found on any server")
        
        # Сортируем по общему скору
        candidates.sort(key=lambda x: x.total_score, reverse=True)
        
        best = candidates[0]
        logger.info(
            f"Selected {best.profile.name} @ {best.server_name} "
            f"(score: {best.total_score:.2f}, caps: {best.capability_score:.2f}, "
            f"perf: {best.performance_score:.2f}, speed: {best.speed_score:.2f})"
        )
        
        return best
    
    def get_all_models_ranked(self, task_type: str = "chat") -> List[Dict[str, Any]]:
        """Возвращает все модели с их рейтингами"""
        requirements = TaskRequirements.from_task_analysis("", task_type, "simple")
        
        results = []
        for server_name, server_info in self._servers.items():
            if not server_info["is_available"]:
                continue
            
            for model_name in server_info["models"]:
                profile = self._get_model_profile(model_name)
                
                results.append({
                    "model": model_name,
                    "server": server_name,
                    "size_b": profile.size_b,
                    "capabilities": {cap.value: score for cap, score in profile.capabilities.items()},
                    "quality_score": profile.quality_score,
                    "speed_score": profile.base_speed_score,
                    "performance_score": self._get_performance_score(model_name)
                })
        
        return sorted(results, key=lambda x: x["quality_score"], reverse=True)

