"""
ReflectionMixin - Добавляет способность к рефлексии и самокоррекции агентам

Позволяет агентам:
1. Анализировать качество своих результатов
2. Выявлять проблемы и недостатки
3. Автоматически исправлять ошибки
4. Улучшать результаты итеративно
5. Сохранять опыт для обучения

Интегрируется с LearningSystem для персистентного обучения.
"""

import json
import re
import time
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from ..core.logger import get_logger
from ..core.learning_system import get_learning_system
from ..llm.base import LLMMessage

if TYPE_CHECKING:
    from ..llm.providers import LLMProviderManager

logger = get_logger(__name__)


class ReflectionQuality(Enum):
    """Уровни качества результата"""
    EXCELLENT = "excellent"  # 90-100%
    GOOD = "good"           # 70-89%
    ACCEPTABLE = "acceptable"  # 50-69%
    POOR = "poor"           # 30-49%
    FAILED = "failed"       # 0-29%


@dataclass
class ReflectionResult:
    """Результат рефлексии"""
    completeness: float = 0.0      # Полнота решения (0-100)
    correctness: float = 0.0       # Корректность (0-100)
    quality: float = 0.0           # Качество кода/текста (0-100)
    overall_score: float = 0.0     # Общая оценка (0-100)
    quality_level: ReflectionQuality = ReflectionQuality.POOR
    issues: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    should_retry: bool = False
    retry_suggestion: Optional[str] = None
    thinking_trace: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь"""
        return {
            "completeness": self.completeness,
            "correctness": self.correctness,
            "quality": self.quality,
            "overall_score": self.overall_score,
            "quality_level": self.quality_level.value,
            "issues": self.issues,
            "improvements": self.improvements,
            "should_retry": self.should_retry,
            "retry_suggestion": self.retry_suggestion,
            "timestamp": self.timestamp
        }


class ReflectionMixin:
    """
    Миксин для добавления способности к рефлексии агентам.
    
    Использование:
    ```python
    class MyAgent(BaseAgent, ReflectionMixin):
        def __init__(self, *args, **kwargs):
            BaseAgent.__init__(self, *args, **kwargs)
            ReflectionMixin.__init__(self)
    ```
    """
    
    # Атрибуты, которые должны быть в классе-наследнике
    llm_manager: Optional["LLMProviderManager"]
    name: str
    
    def __init__(self):
        """Инициализация миксина рефлексии"""
        self._reflection_enabled: bool = True
        self._max_reflection_retries: int = 2
        self._min_quality_threshold: float = 60.0  # Минимальный порог качества
        self._reflection_history: List[ReflectionResult] = []
        self._learning_system = get_learning_system()
    
    def configure_reflection(
        self,
        enabled: bool = True,
        max_retries: int = 2,
        min_quality_threshold: float = 60.0
    ) -> None:
        """
        Настройка параметров рефлексии
        
        Args:
            enabled: Включить/выключить рефлексию
            max_retries: Максимальное количество попыток исправления
            min_quality_threshold: Минимальный порог качества (0-100)
        """
        self._reflection_enabled = enabled
        self._max_reflection_retries = max_retries
        self._min_quality_threshold = min_quality_threshold
    
    async def reflect_on_result(
        self,
        task: str,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ReflectionResult:
        """
        Анализирует результат выполнения задачи.
        
        Args:
            task: Исходная задача
            result: Результат выполнения
            context: Дополнительный контекст
            
        Returns:
            ReflectionResult с оценкой и рекомендациями
        """
        if not self._reflection_enabled:
            return ReflectionResult(
                overall_score=100,
                quality_level=ReflectionQuality.EXCELLENT,
                should_retry=False
            )
        
        logger.debug(f"Agent {self.name}: Starting reflection on result")
        
        # Формируем промпт для рефлексии (теперь async для доступа к learning system)
        reflection_prompt = await self._build_reflection_prompt(task, result, context)
        
        try:
            # Получаем анализ от LLM
            response = await self._get_reflection_response(reflection_prompt)
            
            # Парсим результат
            reflection = self._parse_reflection_response(response)
            
            # Определяем уровень качества
            reflection.quality_level = self._determine_quality_level(reflection.overall_score)
            
            # Определяем, нужен ли retry
            reflection.should_retry = (
                reflection.overall_score < self._min_quality_threshold and
                len(reflection.issues) > 0
            )
            
            # Сохраняем в историю
            self._reflection_history.append(reflection)
            
            logger.info(
                f"Agent {self.name}: Reflection complete - "
                f"score={reflection.overall_score:.1f}, "
                f"quality={reflection.quality_level.value}, "
                f"should_retry={reflection.should_retry}"
            )
            
            return reflection
            
        except Exception as e:
            logger.warning(f"Agent {self.name}: Reflection failed: {e}")
            # Возвращаем базовый результат при ошибке
            return ReflectionResult(
                overall_score=50,
                quality_level=ReflectionQuality.ACCEPTABLE,
                issues=[f"Reflection failed: {str(e)}"],
                should_retry=False
            )
    
    async def _build_reflection_prompt(
        self,
        task: str,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Строит промпт для рефлексии с учётом накопленного опыта"""
        
        # Извлекаем основной контент из результата
        content = ""
        if "code" in result:
            content = f"Код:\n```\n{result['code'][:3000]}\n```"
        elif "report" in result:
            content = f"Отчёт:\n{result['report'][:2000]}"
        elif "analysis" in result:
            content = f"Анализ:\n{result['analysis'][:2000]}"
        elif "final_answer" in result:
            content = f"Ответ:\n{result['final_answer'][:2000]}"
        else:
            content = f"Результат:\n{str(result)[:2000]}"
        
        # Информация об ошибках если есть
        error_info = ""
        if result.get("error"):
            error_info = f"\n\nОШИБКА: {result['error']}"
        
        # Контекст предыдущих попыток
        retry_context = ""
        if self._reflection_history:
            last = self._reflection_history[-1]
            retry_context = f"""
\nПредыдущая попытка:
- Оценка: {last.overall_score:.1f}
- Проблемы: {', '.join(last.issues[:3])}
- Рекомендации: {', '.join(last.improvements[:3])}
"""
        
        # Получаем инсайты из системы обучения
        learning_context = ""
        try:
            insights = await self._learning_system.get_agent_insights(self.name)
            if insights.get("status") == "ok" and insights.get("common_issues"):
                common_issues = [ci["issue"] for ci in insights["common_issues"][:3]]
                if common_issues:
                    learning_context = f"""

ИСТОРИЧЕСКИЕ ПРОБЛЕМЫ АГЕНТА (обрати особое внимание):
{chr(10).join(f'- {issue}' for issue in common_issues)}
"""
        except Exception as e:
            logger.debug(f"Failed to get learning insights: {e}")
        
        return f"""Проанализируй результат выполнения задачи и оцени его качество.

ЗАДАЧА:
{task}

РЕЗУЛЬТАТ:
{content}{error_info}{retry_context}{learning_context}

Оцени по следующим критериям (0-100 для каждого):
1. ПОЛНОТА (completeness): Насколько полно решена задача?
2. КОРРЕКТНОСТЬ (correctness): Насколько правильно решение?
3. КАЧЕСТВО (quality): Насколько хорошо написано (код/текст)?

Выяви:
- ПРОБЛЕМЫ: Что не так или можно улучшить?
- УЛУЧШЕНИЯ: Конкретные рекомендации по исправлению

Ответь СТРОГО в формате JSON:
{{
    "completeness": <0-100>,
    "correctness": <0-100>,
    "quality": <0-100>,
    "issues": ["проблема1", "проблема2"],
    "improvements": ["улучшение1", "улучшение2"],
    "retry_suggestion": "<конкретное указание что исправить, если нужен retry, иначе null>"
}}

ВАЖНО: Будь критичен, но справедлив. Оценивай объективно."""
    
    async def _get_reflection_response(self, prompt: str) -> str:
        """Получает ответ от LLM для рефлексии"""
        if not hasattr(self, 'llm_manager') or not self.llm_manager:
            raise ValueError("LLM manager not available for reflection")
        
        messages = [
            LLMMessage(
                role="system",
                content="""Ты - эксперт по оценке качества и критическому анализу.
Твоя задача - объективно оценить результат работы и выявить проблемы.
Отвечай ТОЛЬКО в формате JSON. Будь конкретен в критике и рекомендациях."""
            ),
            LLMMessage(role="user", content=prompt)
        ]
        
        # Используем быструю модель для рефлексии
        response = await self.llm_manager.generate(
            messages=messages,
            temperature=0.2,  # Низкая температура для консистентности
            max_tokens=800
        )
        
        return response.content
    
    def _parse_reflection_response(self, response: str) -> ReflectionResult:
        """Парсит ответ LLM в ReflectionResult"""
        try:
            # Извлекаем JSON из ответа
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("JSON not found in response")
            
            data = json.loads(json_match.group())
            
            # Валидируем и нормализуем значения
            completeness = max(0, min(100, float(data.get("completeness", 50))))
            correctness = max(0, min(100, float(data.get("correctness", 50))))
            quality = max(0, min(100, float(data.get("quality", 50))))
            
            # Общая оценка как взвешенное среднее
            overall_score = (
                completeness * 0.35 +  # 35% за полноту
                correctness * 0.45 +   # 45% за корректность
                quality * 0.20         # 20% за качество
            )
            
            return ReflectionResult(
                completeness=completeness,
                correctness=correctness,
                quality=quality,
                overall_score=overall_score,
                issues=data.get("issues", [])[:10],  # Ограничиваем количество
                improvements=data.get("improvements", [])[:10],
                retry_suggestion=data.get("retry_suggestion")
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse reflection response: {e}")
            # Возвращаем дефолтный результат
            return ReflectionResult(
                completeness=50,
                correctness=50,
                quality=50,
                overall_score=50,
                issues=["Failed to parse reflection"],
                should_retry=False
            )
    
    def _determine_quality_level(self, score: float) -> ReflectionQuality:
        """Определяет уровень качества по оценке"""
        if score >= 90:
            return ReflectionQuality.EXCELLENT
        elif score >= 70:
            return ReflectionQuality.GOOD
        elif score >= 50:
            return ReflectionQuality.ACCEPTABLE
        elif score >= 30:
            return ReflectionQuality.POOR
        else:
            return ReflectionQuality.FAILED
    
    async def self_correct(
        self,
        task: str,
        original_result: Dict[str, Any],
        reflection: ReflectionResult,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Исправляет результат на основе рефлексии.
        
        Args:
            task: Исходная задача
            original_result: Оригинальный результат
            reflection: Результат рефлексии
            context: Дополнительный контекст
            
        Returns:
            Исправленный результат
        """
        if not reflection.should_retry:
            return original_result
        
        logger.info(f"Agent {self.name}: Self-correcting based on reflection")
        
        # Формируем контекст для исправления
        correction_context = context.copy() if context else {}
        correction_context["_correction_mode"] = True
        correction_context["_original_result"] = original_result
        correction_context["_reflection"] = reflection.to_dict()
        
        # Формируем задачу на исправление
        issues_str = "\n".join(f"- {issue}" for issue in reflection.issues[:5])
        improvements_str = "\n".join(f"- {imp}" for imp in reflection.improvements[:5])
        
        correction_task = f"""ИСПРАВЛЕНИЕ ПРЕДЫДУЩЕГО РЕЗУЛЬТАТА

Исходная задача: {task}

Выявленные проблемы:
{issues_str}

Рекомендации по улучшению:
{improvements_str}

{reflection.retry_suggestion or 'Исправь указанные проблемы и улучши результат.'}

ВАЖНО: Создай УЛУЧШЕННОЕ решение, учитывая все замечания."""
        
        # Вызываем _execute_impl (должен быть определён в наследнике)
        if hasattr(self, '_execute_impl'):
            corrected_result = await self._execute_impl(correction_task, correction_context)
            corrected_result["_corrected"] = True
            corrected_result["_correction_attempt"] = len(self._reflection_history)
            return corrected_result
        
        return original_result
    
    async def execute_with_reflection(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        execute_fn=None
    ) -> Dict[str, Any]:
        """
        Выполняет задачу с циклом рефлексии и самокоррекции.
        Сохраняет результаты в LearningSystem для обучения.
        
        Args:
            task: Задача для выполнения
            context: Контекст выполнения
            execute_fn: Функция выполнения (если не _execute_impl)
            
        Returns:
            Результат с добавленной рефлексией
        """
        start_time = time.time()
        
        # Инициализируем learning system если нужно
        try:
            await self._learning_system.initialize()
        except Exception as e:
            logger.debug(f"Could not initialize learning system: {e}")
        
        if not self._reflection_enabled:
            # Без рефлексии - просто выполняем
            if execute_fn:
                return await execute_fn(task, context or {})
            elif hasattr(self, '_execute_impl'):
                return await self._execute_impl(task, context or {})
            raise ValueError("No execution function available")
        
        # Сбрасываем историю рефлексии для новой задачи
        self._reflection_history = []
        
        # Получаем улучшение промпта на основе накопленного опыта
        prompt_enhancement = None
        try:
            prompt_enhancement = await self._learning_system.get_prompt_enhancement(
                self.name, task
            )
        except Exception as e:
            logger.debug(f"Could not get prompt enhancement: {e}")
        
        # Модифицируем задачу если есть рекомендации
        enhanced_task = task
        if prompt_enhancement:
            enhanced_task = f"{task}\n\n{prompt_enhancement}"
            logger.debug(f"Agent {self.name}: Using enhanced prompt with learning insights")
        
        # Первое выполнение
        if execute_fn:
            result = await execute_fn(enhanced_task, context or {})
        elif hasattr(self, '_execute_impl'):
            result = await self._execute_impl(enhanced_task, context or {})
        else:
            raise ValueError("No execution function available")
        
        total_attempts = 1
        was_corrected = False
        
        # Цикл рефлексии и исправления
        for attempt in range(self._max_reflection_retries):
            # Рефлексия
            reflection = await self.reflect_on_result(task, result, context)
            
            if not reflection.should_retry:
                # Качество достаточное - завершаем
                result["_reflection"] = reflection.to_dict()
                result["_reflection_attempts"] = attempt + 1
                
                # Сохраняем результат в learning system с примером решения
                await self._record_learning(
                    task=task,
                    reflection=reflection,
                    was_corrected=was_corrected,
                    correction_attempts=total_attempts,
                    execution_time=time.time() - start_time,
                    result=result
                )
                
                logger.info(
                    f"Agent {self.name}: Task completed after {attempt + 1} attempt(s) "
                    f"with score {reflection.overall_score:.1f}"
                )
                return result
            
            if attempt < self._max_reflection_retries - 1:
                # Есть ещё попытки - исправляем
                logger.info(
                    f"Agent {self.name}: Attempting correction "
                    f"(attempt {attempt + 2}/{self._max_reflection_retries + 1})"
                )
                result = await self.self_correct(task, result, reflection, context)
                total_attempts += 1
                was_corrected = True
        
        # Исчерпали попытки
        final_reflection = await self.reflect_on_result(task, result, context)
        result["_reflection"] = final_reflection.to_dict()
        result["_reflection_attempts"] = self._max_reflection_retries + 1
        result["_max_retries_reached"] = True
        
        # Сохраняем финальный результат в learning system с примером решения
        await self._record_learning(
            task=task,
            reflection=final_reflection,
            was_corrected=was_corrected,
            correction_attempts=total_attempts,
            execution_time=time.time() - start_time,
            result=result
        )
        
        # Записываем паттерн ошибки если качество низкое
        if final_reflection.overall_score < 50 and final_reflection.issues:
            try:
                for issue in final_reflection.issues[:2]:
                    await self._learning_system.record_error_pattern(
                        agent_name=self.name,
                        error_pattern=issue
                    )
            except Exception as e:
                logger.debug(f"Failed to record error pattern: {e}")
        
        logger.warning(
            f"Agent {self.name}: Max retries reached. "
            f"Final score: {final_reflection.overall_score:.1f}"
        )
        
        return result
    
    async def _record_learning(
        self,
        task: str,
        reflection: ReflectionResult,
        was_corrected: bool,
        correction_attempts: int,
        execution_time: float,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Записывает результат рефлексии в систему обучения с примером решения"""
        try:
            # Извлекаем snippet из результата для few-shot learning
            solution_snippet = None
            if result and reflection.overall_score >= 85:
                # Берём код или ответ как пример успешного решения
                if "code" in result:
                    solution_snippet = result["code"][:1000]
                elif "final_answer" in result:
                    solution_snippet = result["final_answer"][:1000]
                elif "analysis" in result:
                    solution_snippet = result["analysis"][:1000]
                elif "report" in result:
                    solution_snippet = result["report"][:1000]
            
            await self._learning_system.record_reflection(
                agent_name=self.name,
                task=task,
                reflection=reflection.to_dict(),
                was_corrected=was_corrected,
                correction_attempts=correction_attempts,
                execution_time=execution_time,
                solution_snippet=solution_snippet
            )
            logger.debug(
                f"Agent {self.name}: Learning recorded - "
                f"score={reflection.overall_score:.1f}, corrected={was_corrected}, "
                f"snippet={'yes' if solution_snippet else 'no'}"
            )
        except Exception as e:
            logger.debug(f"Failed to record learning: {e}")
    
    def get_reflection_history(self) -> List[Dict[str, Any]]:
        """Возвращает историю рефлексий"""
        return [r.to_dict() for r in self._reflection_history]
    
    def get_average_quality(self) -> float:
        """Возвращает среднее качество по истории рефлексий"""
        if not self._reflection_history:
            return 0.0
        return sum(r.overall_score for r in self._reflection_history) / len(self._reflection_history)

