"""
TaskComplexityService - Единая точка анализа сложности задач

Консолидирует логику из:
- ComplexityAnalyzer
- SmartModelSelector._estimate_complexity()
- TaskRouter._determine_complexity()
- ResourceAwareSelector._estimate_complexity()
- IntelligentModelRouter.TaskRequirements.from_task_analysis()

Использование:
    service = get_complexity_service()
    result = service.analyze(task, task_type="code")
    
    # result.level - ComplexityLevel enum
    # result.estimated_minutes - оценка времени
    # result.recommended_tier - рекомендуемый tier модели
    # result.factors - факторы анализа
"""

import re
from typing import Dict, Optional

from .logger import get_logger
from .types import ComplexityLevel, ModelTier, ComplexityResult

logger = get_logger(__name__)


# Алиас для обратной совместимости
ModelTierRecommendation = ModelTier


class TaskComplexityService:
    """
    Единый сервис анализа сложности задач.
    
    Консолидирует всю логику определения сложности в одном месте.
    """
    
    # Ключевые слова для определения сложности
    COMPLEXITY_KEYWORDS = {
        "extreme": [
            "создай полное приложение", "create full application",
            "напиши полную систему", "build complete system",
            "разработай платформу", "develop platform",
            "создай игру с нуля", "create game from scratch",
            "напиши фреймворк", "write framework",
            "создай IDE", "build IDE",
            "разработай CRM", "develop CRM",
            "создай интернет-магазин", "create e-commerce",
            "полный проект", "full project",
        ],
        "very_complex": [
            "напиши систему", "write system",
            "создай приложение", "create application",
            "разработай API", "develop API",
            "создай бота", "create bot",
            "напиши парсер", "write parser",
            "создай dashboard", "create dashboard",
            "напиши тесты для всего", "write all tests",
            "рефакторинг всего", "refactor everything",
        ],
        "complex": [
            "напиши класс", "write class",
            "создай модуль", "create module",
            "рефакторинг", "refactor",
            "оптимизируй", "optimize",
            "интегрируй", "integrate",
            "добавь функционал", "add functionality",
            "исправь все ошибки", "fix all errors",
            "сложный", "complex",
        ],
        "moderate": [
            "напиши функцию", "write function",
            "объясни код", "explain code",
            "проанализируй", "analyze",
            "сравни", "compare",
            "исследуй", "research",
            "добавь", "add",
            "измени", "modify",
        ],
        "simple": [
            "исправь", "fix",
            "что такое", "what is",
            "как", "how",
            "почему", "why",
            "объясни", "explain",
        ],
        "trivial": [
            "привет", "hello", "hi",
            "здравствуй", "добрый день",
            "спасибо", "thanks",
            "пока", "bye",
            "как дела", "how are you",
        ],
    }
    
    # Паттерны сложности
    COMPLEXITY_PATTERNS = [
        (r'\bигр[уа]', 4.0),
        (r'\bприложени[еяй]', 3.5),
        (r'\bсистем[уа]', 3.5),
        (r'\bфреймворк', 4.5),
        (r'\bплатформ[уа]', 4.0),
        (r'\bAPI\b', 2.5),
        (r'\bбот[а]?\b', 2.5),
        (r'\bкласс[а]?\b', 2.0),
        (r'\bфункци[юя]', 1.5),
        (r'\bмодул[ья]', 2.0),
        (r'\bscript\b', 1.5),
    ]
    
    # Множители по типу задачи
    TASK_TYPE_MULTIPLIERS = {
        "code": 1.3,
        "code_generation": 1.3,
        "analysis": 1.2,
        "research": 1.1,
        "reasoning": 1.1,
        "chat": 0.8,
        "simple_chat": 0.5,
        "creative": 1.0,
        "general": 1.0,
    }
    
    # Базовое время в минутах
    BASE_TIME_ESTIMATES = {
        ComplexityLevel.TRIVIAL: 0.1,
        ComplexityLevel.SIMPLE: 0.3,
        ComplexityLevel.MODERATE: 1.5,
        ComplexityLevel.COMPLEX: 5.0,
        ComplexityLevel.VERY_COMPLEX: 15.0,
        ComplexityLevel.EXTREME: 40.0,
    }
    
    # Рекомендуемые токены
    RECOMMENDED_TOKENS = {
        ComplexityLevel.TRIVIAL: 300,
        ComplexityLevel.SIMPLE: 800,
        ComplexityLevel.MODERATE: 1500,
        ComplexityLevel.COMPLEX: 3000,
        ComplexityLevel.VERY_COMPLEX: 4500,
        ComplexityLevel.EXTREME: 6000,
    }
    
    # Рекомендуемые температуры по типу
    RECOMMENDED_TEMPERATURES = {
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
    
    def __init__(self):
        self._cache: Dict[str, ComplexityResult] = {}
        self._cache_max_size = 1000
    
    def analyze(
        self,
        task: str,
        task_type: Optional[str] = None,
        model: Optional[str] = None,
        use_cache: bool = True
    ) -> ComplexityResult:
        """
        Анализирует сложность задачи.
        
        Args:
            task: Текст задачи
            task_type: Тип задачи (code, chat, research, etc.)
            model: Используемая модель (для корректировки времени)
            use_cache: Использовать кэш
            
        Returns:
            ComplexityResult с полной информацией
        """
        # Проверяем кэш
        cache_key = f"{task[:100]}:{task_type}:{model}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        task_lower = task.lower()
        factors = {}
        
        # 1. Определяем тип задачи если не указан
        if not task_type:
            task_type = self._infer_task_type(task_lower)
        factors["task_type"] = task_type
        
        # 2. Базовая сложность по ключевым словам
        keyword_level = self._detect_by_keywords(task_lower)
        factors["keyword_level"] = keyword_level.value
        
        # 3. Множитель по паттернам
        pattern_multiplier = self._calculate_pattern_multiplier(task_lower)
        factors["pattern_multiplier"] = pattern_multiplier
        
        # 4. Множитель по длине
        length_multiplier = self._calculate_length_multiplier(task)
        factors["length_multiplier"] = length_multiplier
        
        # 5. Множитель по множественным требованиям
        multi_multiplier = self._calculate_multi_requirements_multiplier(task_lower)
        factors["multi_requirements_multiplier"] = multi_multiplier
        
        # 6. Множитель по типу задачи
        type_multiplier = self.TASK_TYPE_MULTIPLIERS.get(task_type, 1.0)
        factors["type_multiplier"] = type_multiplier
        
        # 7. Вычисляем финальный скор
        base_score = self._level_to_score(keyword_level)
        final_score = base_score * pattern_multiplier * length_multiplier * multi_multiplier * type_multiplier
        final_score = min(final_score, 10.0)
        factors["final_score"] = final_score
        
        # 8. Определяем уровень по скору
        level = self._score_to_level(final_score)
        
        # 9. Оценка времени
        estimated_minutes = self._estimate_time(level, model)
        
        # 10. Рекомендуемый tier
        recommended_tier = self._get_recommended_tier(level, task_type)
        
        # 11. Рекомендуемая температура
        recommended_temp = self.RECOMMENDED_TEMPERATURES.get(task_type, 0.7)
        # Снижаем для сложных задач
        if level in [ComplexityLevel.COMPLEX, ComplexityLevel.VERY_COMPLEX, ComplexityLevel.EXTREME]:
            recommended_temp = max(0.1, recommended_temp - 0.1)
        
        # 12. Рекомендуемые токены
        recommended_tokens = self.RECOMMENDED_TOKENS.get(level, 2000)
        
        # 13. Генерируем предупреждение
        warning, should_warn = self._generate_warning(level, estimated_minutes)
        
        result = ComplexityResult(
            level=level,
            score=final_score,
            estimated_minutes=estimated_minutes,
            recommended_tier=recommended_tier,
            recommended_temperature=recommended_temp,
            recommended_max_tokens=recommended_tokens,
            factors=factors,
            warning_message=warning,
            should_warn=should_warn,
        )
        
        # Сохраняем в кэш
        if use_cache:
            if len(self._cache) >= self._cache_max_size:
                # Удаляем половину кэша при переполнении
                keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 2]
                for key in keys_to_remove:
                    del self._cache[key]
            self._cache[cache_key] = result
        
        logger.debug(
            f"TaskComplexity: level={level.value}, score={final_score:.2f}, "
            f"time={estimated_minutes:.1f}min, tier={recommended_tier.value}"
        )
        
        return result
    
    def _infer_task_type(self, task_lower: str) -> str:
        """Определяет тип задачи по тексту"""
        if any(kw in task_lower for kw in [
            "код", "code", "функци", "класс", "python", "javascript",
            "напиши", "создай", "сгенерируй", "игра", "game", "приложение"
        ]):
            return "code"
        
        if any(kw in task_lower for kw in [
            "проанализируй", "анализ", "analyze", "изучи", "сравни"
        ]):
            return "analysis"
        
        if any(kw in task_lower for kw in [
            "исследуй", "research", "найди информацию"
        ]):
            return "research"
        
        if any(kw in task_lower for kw in [
            "объясни", "почему", "как работает", "логик"
        ]):
            return "reasoning"
        
        if any(kw in task_lower for kw in [
            "привет", "здравствуй", "hello", "hi", "как дела"
        ]):
            return "simple_chat"
        
        return "general"
    
    def _detect_by_keywords(self, task_lower: str) -> ComplexityLevel:
        """Определяет базовую сложность по ключевым словам"""
        for level_name, keywords in self.COMPLEXITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in task_lower:
                    return ComplexityLevel[level_name.upper()]
        
        return ComplexityLevel.SIMPLE
    
    def _calculate_pattern_multiplier(self, task_lower: str) -> float:
        """Вычисляет множитель на основе паттернов"""
        multiplier = 1.0
        
        for pattern, weight in self.COMPLEXITY_PATTERNS:
            if re.search(pattern, task_lower, re.IGNORECASE):
                multiplier = max(multiplier, weight)
        
        return multiplier
    
    def _calculate_length_multiplier(self, task: str) -> float:
        """Множитель на основе длины задачи"""
        length = len(task)
        
        if length < 30:
            return 0.7
        elif length < 100:
            return 0.9
        elif length < 300:
            return 1.0
        elif length < 600:
            return 1.2
        elif length < 1000:
            return 1.4
        else:
            return 1.7
    
    def _calculate_multi_requirements_multiplier(self, task_lower: str) -> float:
        """Проверяет наличие множественных требований"""
        multi_keywords = [
            "и также", "а также", "плюс", "кроме того",
            "дополнительно", "ещё", "еще", "потом",
            "после этого", "затем", "and also", "plus",
            "additionally", "then", "after that"
        ]
        
        count = sum(1 for kw in multi_keywords if kw in task_lower)
        
        # Считаем пункты списка
        list_items = len(re.findall(r'^\s*[-•\d]+[.)]?\s+', task_lower, re.MULTILINE))
        count += list_items
        
        if count >= 5:
            return 1.8
        elif count >= 3:
            return 1.4
        elif count >= 1:
            return 1.15
        return 1.0
    
    def _level_to_score(self, level: ComplexityLevel) -> float:
        """Конвертирует уровень в базовый скор"""
        scores = {
            ComplexityLevel.TRIVIAL: 0.5,
            ComplexityLevel.SIMPLE: 1.5,
            ComplexityLevel.MODERATE: 3.0,
            ComplexityLevel.COMPLEX: 5.0,
            ComplexityLevel.VERY_COMPLEX: 7.0,
            ComplexityLevel.EXTREME: 9.0,
        }
        return scores.get(level, 3.0)
    
    def _score_to_level(self, score: float) -> ComplexityLevel:
        """Конвертирует скор в уровень сложности"""
        if score < 1.0:
            return ComplexityLevel.TRIVIAL
        elif score < 2.0:
            return ComplexityLevel.SIMPLE
        elif score < 4.0:
            return ComplexityLevel.MODERATE
        elif score < 6.0:
            return ComplexityLevel.COMPLEX
        elif score < 8.0:
            return ComplexityLevel.VERY_COMPLEX
        else:
            return ComplexityLevel.EXTREME
    
    def _estimate_time(self, level: ComplexityLevel, model: Optional[str]) -> float:
        """Оценивает время в минутах"""
        base_time = self.BASE_TIME_ESTIMATES.get(level, 5.0)
        
        # Корректировка по модели
        if model:
            model_lower = model.lower()
            if any(x in model_lower for x in ["1b", "2b", "3b"]):
                base_time *= 1.8
            elif any(x in model_lower for x in ["7b", "8b"]):
                base_time *= 1.2
            elif any(x in model_lower for x in ["70b", "72b"]):
                base_time *= 0.9
        
        return base_time
    
    def _get_recommended_tier(
        self,
        level: ComplexityLevel,
        task_type: str
    ) -> ModelTierRecommendation:
        """Определяет рекомендуемый tier модели"""
        # Для кода всегда лучше качественные модели
        if task_type in ["code", "code_generation"]:
            if level in [ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE]:
                return ModelTierRecommendation.BALANCED
            else:
                return ModelTierRecommendation.POWERFUL
        
        # По сложности
        if level in [ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE]:
            return ModelTierRecommendation.FAST
        elif level in [ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX]:
            return ModelTierRecommendation.BALANCED
        else:
            return ModelTierRecommendation.POWERFUL
    
    def _generate_warning(
        self,
        level: ComplexityLevel,
        estimated_minutes: float
    ) -> tuple[Optional[str], bool]:
        """Генерирует предупреждение для пользователя"""
        if level in [ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE]:
            return None, False
        
        if level == ComplexityLevel.MODERATE:
            return (
                f"⏱️ Это может занять ~{estimated_minutes:.0f} мин. Выполнение началось...",
                True
            )
        
        if level == ComplexityLevel.COMPLEX:
            return (
                f"⚠️ Сложная задача. Ожидаемое время: ~{estimated_minutes:.0f} мин. "
                "Пожалуйста, подождите...",
                True
            )
        
        if level == ComplexityLevel.VERY_COMPLEX:
            return (
                f"⚠️ Очень сложная задача! Ожидаемое время: ~{estimated_minutes:.0f} мин. "
                "НЕ прерывайте процесс.",
                True
            )
        
        return (
            f"🚨 Экстремально сложная задача! Время: ~{estimated_minutes:.0f} мин (до 60 мин). "
            "Это нормально для таких задач. Система работает!",
            True
        )
    
    def clear_cache(self) -> None:
        """Очищает кэш"""
        self._cache.clear()


# Singleton instance
_complexity_service: Optional[TaskComplexityService] = None


def get_complexity_service() -> TaskComplexityService:
    """Получить singleton экземпляр сервиса"""
    global _complexity_service
    if _complexity_service is None:
        _complexity_service = TaskComplexityService()
    return _complexity_service

