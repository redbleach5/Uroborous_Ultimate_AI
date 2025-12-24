"""
TwoStageProcessor - Двухэтапная обработка
Быстрая модель для предобработки, мощная для финальных решений
"""

from typing import Dict, Any, Optional, Callable
import asyncio
from enum import Enum
from dataclasses import dataclass
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage


class ProcessingStage(Enum):
    """Этапы обработки"""
    FAST_PREPROCESSING = "fast_preprocessing"
    POWERFUL_PROCESSING = "powerful_processing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ProcessingResult:
    """Результат обработки"""
    stage: ProcessingStage
    data: Dict[str, Any]
    metadata: Dict[str, Any] = None
    error: Optional[str] = None


class TwoStageProcessor:
    """
    Двухэтапный процессор:
    1. Быстрая модель - предобработка, классификация, фильтрация
    2. Мощная модель - финальные решения, генерация, анализ
    """
    
    def __init__(
        self,
        llm_manager: Optional[LLMProviderManager] = None,
        fast_provider: Optional[str] = None,
        powerful_provider: Optional[str] = None,
        progress_callback: Optional[Callable[[ProcessingStage, Dict[str, Any]], None]] = None
    ):
        """
        Args:
            llm_manager: Менеджер LLM провайдеров
            fast_provider: Имя быстрого провайдера (по умолчанию определяется автоматически)
            powerful_provider: Имя мощного провайдера (по умолчанию определяется автоматически)
            progress_callback: Callback для уведомления о прогрессе
        """
        self.llm_manager = llm_manager
        self.progress_callback = progress_callback
        
        # Определяем провайдеры
        if llm_manager:
            self.fast_provider = fast_provider or self._find_fast_provider()
            self.powerful_provider = powerful_provider or self._find_powerful_provider()
        else:
            self.fast_provider = None
            self.powerful_provider = None
    
    def _find_fast_provider(self) -> Optional[str]:
        """Находит быстрый провайдер"""
        if not self.llm_manager:
            return None
        
        # Приоритет: ollama (локальные модели быстрее)
        if "ollama" in self.llm_manager.providers:
            return "ollama"
        elif self.llm_manager.providers:
            return list(self.llm_manager.providers.keys())[0]
        return None
    
    def _find_powerful_provider(self) -> Optional[str]:
        """Находит мощный провайдер"""
        if not self.llm_manager:
            return None
        
        # Приоритет: ollama (может использовать более мощные модели)
        if "ollama" in self.llm_manager.providers:
            return "ollama"
        elif self.llm_manager.providers:
            return list(self.llm_manager.providers.keys())[0]
        return None
    
    async def process(
        self,
        task: str,
        fast_analysis: Optional[Callable[[str], Dict[str, Any]]] = None,
        powerful_processing: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None
    ) -> ProcessingResult:
        """
        Двухэтапная обработка задачи
        
        Args:
            task: Задача для обработки
            fast_analysis: Функция для анализа через быструю модель (опционально)
            powerful_processing: Функция для обработки через мощную модель (опционально)
        
        Returns:
            ProcessingResult с результатом обработки
        """
        if not self.llm_manager:
            return ProcessingResult(
                stage=ProcessingStage.ERROR,
                data={},
                error="LLM manager недоступен"
            )
        
        try:
            # Этап 1: Быстрая предобработка
            await self._notify_progress(ProcessingStage.FAST_PREPROCESSING, {
                "message": "Анализирую задачу...",
                "task": task[:100]
            })
            
            fast_result = await self._fast_preprocessing(
                task,
                fast_analysis
            )
            
            if fast_result.get("error"):
                return ProcessingResult(
                    stage=ProcessingStage.ERROR,
                    data=fast_result,
                    error=fast_result["error"]
                )
            
            # Этап 2: Мощная обработка
            await self._notify_progress(ProcessingStage.POWERFUL_PROCESSING, {
                "message": "Выполняю задачу...",
                "analysis": fast_result
            })
            
            powerful_result = await self._powerful_processing(
                task,
                fast_result,
                powerful_processing
            )
            
            if powerful_result.get("error"):
                return ProcessingResult(
                    stage=ProcessingStage.ERROR,
                    data=powerful_result,
                    error=powerful_result["error"]
                )
            
            # Объединяем результаты
            final_result = {
                "fast_analysis": fast_result,
                "powerful_result": powerful_result,
                "task": task
            }
            
            await self._notify_progress(ProcessingStage.COMPLETED, final_result)
            
            return ProcessingResult(
                stage=ProcessingStage.COMPLETED,
                data=final_result,
                metadata={
                    "fast_provider": self.fast_provider,
                    "powerful_provider": self.powerful_provider
                }
            )
            
        except Exception as e:
            logger.error(f"Two-stage processing error: {e}")
            return ProcessingResult(
                stage=ProcessingStage.ERROR,
                data={},
                error=str(e)
            )
    
    async def _fast_preprocessing(
        self,
        task: str,
        custom_analysis: Optional[Callable[[str], Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Быстрая предобработка через быструю модель"""
        if custom_analysis:
            return await custom_analysis(task)
        
        if not self.fast_provider:
            return {
                "error": "Быстрый провайдер недоступен",
                "task_type": "unknown",
                "complexity": "medium"
            }
        
        # Стандартный анализ задачи
        prompt = f"""Проанализируй задачу и определи:
1. Тип задачи (coding, analysis, question, etc.)
2. Сложность (simple, medium, complex)
3. Ключевые требования
4. Рекомендуемый подход

Задача: {task}

Ответ в формате JSON:
{{
    "task_type": "тип",
    "complexity": "сложность",
    "requirements": ["требование1", "требование2"],
    "approach": "краткое описание подхода"
}}"""
        
        try:
            messages = [
                LLMMessage(role="system", content="Ты - эксперт по анализу задач. Отвечай только в формате JSON."),
                LLMMessage(role="user", content=prompt)
            ]
            
            response = await asyncio.wait_for(
                self.llm_manager.generate(
                    messages=messages,
                    provider_name=self.fast_provider,
                    temperature=0.2,
                    max_tokens=300
                ),
                timeout=5.0  # Быстрая модель должна отвечать быстро
            )
            
            if response and response.content:
                # Парсим JSON из ответа
                import json
                content = response.content.strip()
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    analysis = json.loads(content[json_start:json_end])
                    return {
                        "task_type": analysis.get("task_type", "unknown"),
                        "complexity": analysis.get("complexity", "medium"),
                        "requirements": analysis.get("requirements", []),
                        "approach": analysis.get("approach", ""),
                        "provider": self.fast_provider
                    }
            
            return {
                "task_type": "unknown",
                "complexity": "medium",
                "requirements": [],
                "approach": "",
                "provider": self.fast_provider
            }
            
        except Exception as e:
            logger.warning(f"Fast preprocessing failed: {e}")
            return {
                "error": str(e),
                "task_type": "unknown",
                "complexity": "medium"
            }
    
    async def _powerful_processing(
        self,
        task: str,
        fast_analysis: Dict[str, Any],
        custom_processing: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Мощная обработка через мощную модель"""
        if custom_processing:
            return await custom_processing(task, fast_analysis)
        
        if not self.powerful_provider:
            return {
                "error": "Мощный провайдер недоступен",
                "result": "Не удалось обработать задачу"
            }
        
        # Формируем промпт с учетом анализа быстрой модели
        prompt = f"""На основе анализа задачи выполни её.

Анализ задачи:
- Тип: {fast_analysis.get('task_type', 'unknown')}
- Сложность: {fast_analysis.get('complexity', 'medium')}
- Требования: {', '.join(fast_analysis.get('requirements', []))}
- Подход: {fast_analysis.get('approach', '')}

Задача: {task}

Выполни задачу и предоставь результат."""
        
        try:
            messages = [
                LLMMessage(role="system", content="Ты - опытный AI ассистент. Выполняй задачи качественно и полностью."),
                LLMMessage(role="user", content=prompt)
            ]
            
            response = await asyncio.wait_for(
                self.llm_manager.generate(
                    messages=messages,
                    provider_name=self.powerful_provider,
                    temperature=0.7,
                    max_tokens=2000
                ),
                timeout=120.0  # Мощная модель может работать дольше
            )
            
            if response and response.content:
                return {
                    "result": response.content,
                    "provider": self.powerful_provider,
                    "analysis_used": fast_analysis
                }
            
            return {
                "error": "Пустой ответ от мощной модели",
                "result": ""
            }
            
        except Exception as e:
            logger.error(f"Powerful processing failed: {e}")
            return {
                "error": str(e),
                "result": ""
            }
    
    async def _notify_progress(self, stage: ProcessingStage, data: Dict[str, Any]):
        """Уведомляет о прогрессе обработки"""
        if self.progress_callback:
            try:
                if asyncio.iscoroutinefunction(self.progress_callback):
                    await self.progress_callback(stage, data)
                else:
                    self.progress_callback(stage, data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

