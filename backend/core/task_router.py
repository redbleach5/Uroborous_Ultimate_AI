"""
TaskRouter - Интеллектуальная маршрутизация задач
Использует легкие модели для анализа и принятия решений
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage
from .llm_classifier import LLMClassifier, REQUEST_TYPE_SCHEMA


@dataclass
class TaskRouting:
    """Результат маршрутизации задачи"""
    task: str
    complexity: str  # "low", "medium", "high"
    task_type: str  # "simple_chat", "code_generation", "reasoning", etc.
    selected_provider: Optional[str] = None
    confidence: float = 0.5
    reason: str = ""


class TaskRouter:
    """Маршрутизатор задач, использующий модели для принятия решений"""
    
    def __init__(
        self,
        llm_manager: LLMProviderManager,
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_manager = llm_manager
        self.config = config or {}
        self.llm_classifier = LLMClassifier(llm_manager) if llm_manager else None
        self.routing_history: list = []
    
    async def route_task(self, task: str, context: Optional[Dict[str, Any]] = None) -> TaskRouting:
        """
        Автоматическая маршрутизация задачи с использованием моделей для анализа
        
        Args:
            task: Текст задачи
            context: Дополнительный контекст
        
        Returns:
            TaskRouting с информацией о выбранной модели и обработке
        """
        # Шаг 1: Используем легкую модель для быстрого анализа задачи
        analysis = await self._analyze_task_with_light_model(task)
        
        # Шаг 2: Выбираем провайдер на основе анализа
        task_type = analysis.get("task_type", "general")
        task_complexity = analysis.get("complexity", "medium")
        
        # Выбираем провайдер в зависимости от сложности
        selected_provider = self._select_provider_for_task(task_type, task_complexity)
        
        routing = TaskRouting(
            task=task,
            complexity=task_complexity,
            task_type=task_type,
            selected_provider=selected_provider,
            confidence=analysis.get("confidence", 0.5),
            reason=f"Анализ: {analysis.get('reasoning', '')}"
        )
        
        # Сохраняем в историю
        self.routing_history.append({
            "timestamp": datetime.now(),
            "routing": routing,
            "analysis": analysis
        })
        
        logger.info(f"Task routed: type={routing.task_type}, complexity={routing.complexity}, provider={routing.selected_provider}")
        
        return routing
    
    async def _analyze_task_with_light_model(self, task: str) -> Dict[str, Any]:
        """
        Быстрый анализ задачи с помощью легкой модели или LLMClassifier
        """
        # Используем LLMClassifier если доступен
        if self.llm_classifier:
            try:
                result = await self.llm_classifier.classify(
                    text=task,
                    classification_schema=REQUEST_TYPE_SCHEMA,
                    use_cache=True
                )
                
                if result.get("confidence", 0) > 0.7:
                    # Определяем сложность на основе типа задачи
                    task_type = result.get("type", "execution_task")
                    complexity = self._determine_complexity(task, task_type)
                    
                    return {
                        "task_type": task_type,
                        "complexity": complexity,
                        "reasoning": result.get("reasoning", ""),
                        "confidence": result.get("confidence", 0.5),
                        "source": "llm_classifier"
                    }
            except Exception as e:
                logger.warning(f"LLMClassifier failed: {e}, using fallback")
        
        # Fallback на эвристику
        return self._heuristic_analysis(task)
    
    def _heuristic_analysis(self, task: str) -> Dict[str, Any]:
        """Эвристический анализ задачи (fallback)"""
        task_lower = task.lower()
        
        # Определяем тип задачи
        if any(word in task_lower for word in ["привет", "здравствуй", "hello", "hi"]):
            task_type = "simple_chat"
            complexity = "low"
        elif any(word in task_lower for word in ["создай", "напиши", "генерируй", "create", "generate", "игра", "game"]):
            task_type = "code_generation"
            complexity = "medium" if len(task) < 200 else "high"
        elif any(word in task_lower for word in ["проанализируй", "анализ", "изучи", "analyze"]):
            task_type = "analysis"
            complexity = "high"
        elif any(word in task_lower for word in ["объясни", "что такое", "как работает"]):
            task_type = "reasoning"
            complexity = "medium"
        elif "?" in task:
            task_type = "question"
            complexity = "low" if len(task) < 100 else "medium"
        else:
            task_type = "execution_task"
            complexity = "medium"
        
        return {
            "task_type": task_type,
            "complexity": complexity,
            "reasoning": f"Эвристический анализ: {task_type}",
            "confidence": 0.5,
            "source": "heuristic"
        }
    
    def _determine_complexity(self, task: str, task_type: str) -> str:
        """Определяет сложность задачи"""
        task_len = len(task)
        
        if task_type == "simple_chat":
            return "low"
        elif task_type == "question":
            return "low" if task_len < 100 else "medium"
        elif task_type == "code_generation":
            # Сложные проекты (игры, приложения, системы)
            complex_keywords = ["игра", "game", "приложение", "app", "система", "system", "framework", "фреймворк"]
            if any(keyword in task.lower() for keyword in complex_keywords):
                return "high"
            return "medium" if task_len < 300 else "high"
        elif task_type == "analysis":
            return "high"
        else:
            return "medium" if task_len < 200 else "high"
    
    def _select_provider_for_task(self, task_type: str, complexity: str) -> Optional[str]:
        """Выбирает провайдер для задачи
        
        PRIORITY: Ollama всегда в приоритете для локальной работы
        """
        if not self.llm_manager:
            return None
        
        # PRIORITY: Ollama всегда в приоритете (локальные модели)
        if self.llm_manager.is_provider_available("ollama"):
            logger.debug(f"Selecting Ollama provider for task_type={task_type}, complexity={complexity}")
            return "ollama"
        
        # Fallback на другие провайдеры только если Ollama недоступен
        # Для простых задач используем быстрые модели
        if complexity == "low" or task_type == "simple_chat":
            # Ищем быстрые модели
            for provider in ["openai", "anthropic"]:
                if self.llm_manager.is_provider_available(provider):
                    return provider
        
        # Для сложных задач используем более мощные модели
        # Fallback на первый доступный
        if self.llm_manager.providers:
            return list(self.llm_manager.providers.keys())[0]
        
        return None
    
    async def process_task(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Обработка задачи с автоматической маршрутизацией
        
        Returns:
            Результат обработки задачи
        """
        # Маршрутизируем задачу
        routing = await self.route_task(task, context)
        
        # Обрабатываем задачу через выбранную модель
        if not self.llm_manager:
            return {
                "success": False,
                "error": "LLM manager not available"
            }
        
        # Формируем промпт на основе типа задачи
        prompt = self._build_prompt(task, routing, context)
        
        try:
            # Генерируем ответ
            messages = [
                LLMMessage(role="system", content=self._get_system_prompt(routing.task_type)),
                LLMMessage(role="user", content=prompt)
            ]
            
            response = await self.llm_manager.generate(
                messages=messages,
                provider_name=routing.selected_provider,
                temperature=0.7 if routing.complexity == "high" else 0.5,
                max_tokens=4000 if routing.complexity == "high" else 2000
            )
            
            return {
                "success": True,
                "result": response.content,
                "routing": routing,
                "model": response.model
            }
        except Exception as e:
            logger.error(f"Task processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "routing": routing
            }
    
    def _get_system_prompt(self, task_type: str) -> str:
        """Получает системный промпт для типа задачи"""
        prompts = {
            "code_generation": "Ты - опытный разработчик. Генерируй полный, рабочий код с комментариями и обработкой ошибок.",
            "analysis": "Ты - эксперт по анализу. Проводи глубокий анализ и предоставляй детальные выводы.",
            "reasoning": "Ты - эксперт по объяснению сложных концепций. Объясняй понятно и структурированно.",
            "question": "Ты - помощник. Отвечай на вопросы четко и по делу.",
            "simple_chat": "Ты - дружелюбный помощник. Поддерживай естественный разговор."
        }
        return prompts.get(task_type, "Ты - полезный AI ассистент. Помогай пользователю решать задачи.")
    
    def _build_prompt(self, task: str, routing: TaskRouting, context: Optional[Dict[str, Any]]) -> str:
        """Строит промпт для задачи"""
        prompt = task
        
        if context:
            if "previous_results" in context:
                prompt += "\n\nКонтекст предыдущих шагов:\n"
                for i, prev in enumerate(context["previous_results"][:3], 1):
                    if prev.get("success"):
                        prompt += f"{i}. {prev.get('subtask', '')[:100]}\n"
        
        return prompt

