"""
UncertaintySearchMixin - Автоматический веб-поиск при неуверенности модели

Позволяет агентам:
1. Детектировать неуверенность в своих ответах
2. Автоматически искать недостающую информацию в интернете
3. Дополнять ответы актуальными данными
4. Повышать точность при работе со сложными проектами
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from ..core.logger import get_logger
from ..llm.base import LLMMessage

logger = get_logger(__name__)


class UncertaintySearchMixin:
    """
    Миксин для автоматического веб-поиска при неуверенности модели.
    
    Использование:
    ```python
    class MyAgent(BaseAgent, UncertaintySearchMixin):
        async def _execute_impl(self, task, context):
            response = await self._get_llm_response(messages)
            
            # Проверяем и дополняем при неуверенности
            enhanced_response = await self.enhance_with_search_if_uncertain(
                response=response,
                task=task,
                context=context
            )
            return enhanced_response
    ```
    """
    
    # Паттерны, указывающие на неуверенность модели
    UNCERTAINTY_PATTERNS = [
        # Русский
        r"не уверен",
        r"не знаю точно",
        r"возможно",
        r"вероятно",
        r"может быть",
        r"не могу сказать",
        r"мне неизвестно",
        r"требует уточнения",
        r"нужно проверить",
        r"не располагаю.*информацией",
        r"мои данные.*устарели",
        r"не имею.*доступа",
        r"рекомендую.*проверить",
        r"точно не могу",
        r"сложно сказать",
        # English
        r"i'?m not sure",
        r"i don'?t know",
        r"might be",
        r"could be",
        r"possibly",
        r"probably",
        r"uncertain",
        r"need to verify",
        r"my knowledge.*cutoff",
        r"as of my.*training",
    ]
    
    # Паттерны задач, требующих актуальной информации
    REQUIRES_CURRENT_INFO_PATTERNS = [
        r"последн(ий|яя|ие|юю)",
        r"актуальн(ый|ая|ые|ую)",
        r"текущ(ий|ая|ие|ую)",
        r"сегодня|вчера|на этой неделе",
        r"новост(и|ей|ь)",
        r"релиз|версия",
        r"цен(а|ы)|стоимость",
        r"курс|котировки",
        r"погода",
        r"latest|current|today|recent",
        r"price|cost|rate",
        r"version|release",
        r"news|update",
    ]
    
    # Технические темы, где важна актуальность
    TECHNICAL_TOPICS_PATTERNS = [
        r"api|sdk|library|framework",
        r"документация|documentation",
        r"установк(а|и)|install",
        r"зависимост(и|ей)|dependenc",
        r"настройк(а|и)|config",
        r"баг|bug|issue|ошибка",
        r"уязвимост(ь|и)|vulnerability|security",
    ]
    
    def __init__(self):
        """Инициализация миксина"""
        self._uncertainty_threshold = 0.6  # Порог уверенности для поиска
        self._search_cache: Dict[str, Any] = {}  # Кэш результатов поиска
    
    def detect_uncertainty(self, response: str) -> Tuple[bool, float, List[str]]:
        """
        Определяет уровень неуверенности в ответе модели.
        
        Args:
            response: Ответ модели
            
        Returns:
            (is_uncertain, confidence_score, detected_patterns)
        """
        response_lower = response.lower()
        detected_patterns = []
        
        # Проверяем паттерны неуверенности
        for pattern in self.UNCERTAINTY_PATTERNS:
            if re.search(pattern, response_lower, re.IGNORECASE):
                detected_patterns.append(pattern)
        
        # Рассчитываем уверенность (чем больше паттернов - тем меньше уверенность)
        if detected_patterns:
            # Каждый паттерн снижает уверенность на 15%
            confidence = max(0.1, 1.0 - len(detected_patterns) * 0.15)
        else:
            confidence = 0.95  # Высокая уверенность по умолчанию
        
        is_uncertain = confidence < self._uncertainty_threshold
        
        if is_uncertain:
            logger.info(
                f"Detected uncertainty in response: confidence={confidence:.2f}, "
                f"patterns={detected_patterns[:3]}"
            )
        
        return is_uncertain, confidence, detected_patterns
    
    def task_requires_current_info(self, task: str) -> Tuple[bool, List[str]]:
        """
        Определяет, требует ли задача актуальной информации.
        
        Args:
            task: Описание задачи
            
        Returns:
            (requires_search, matched_keywords)
        """
        task_lower = task.lower()
        matched = []
        
        # Проверяем паттерны актуальности
        for pattern in self.REQUIRES_CURRENT_INFO_PATTERNS:
            if re.search(pattern, task_lower, re.IGNORECASE):
                matched.append(pattern)
        
        # Проверяем технические темы
        for pattern in self.TECHNICAL_TOPICS_PATTERNS:
            if re.search(pattern, task_lower, re.IGNORECASE):
                matched.append(pattern)
        
        requires = len(matched) >= 1
        
        if requires:
            logger.info(f"Task requires current info: {matched[:3]}")
        
        return requires, matched
    
    async def search_for_missing_info(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None,
        max_results: int = 5
    ) -> Optional[str]:
        """
        Выполняет веб-поиск для получения недостающей информации.
        
        Args:
            query: Поисковый запрос
            context: Дополнительный контекст
            
        Returns:
            Отформатированные результаты поиска или None
        """
        # Проверяем кэш
        cache_key = query.lower().strip()[:100]
        if cache_key in self._search_cache:
            logger.debug(f"Using cached search results for: {query[:50]}")
            return self._search_cache[cache_key]
        
        # Получаем tool_registry (должен быть у агента)
        tool_registry = getattr(self, 'tool_registry', None)
        if not tool_registry:
            logger.warning("No tool_registry available for web search")
            return None
        
        try:
            logger.info(f"🔍 Performing uncertainty-triggered web search: {query[:60]}")
            
            search_result = await tool_registry.execute_tool(
                "web_search",
                {"query": query, "max_results": max_results}
            )
            
            if not search_result.success:
                logger.warning(f"Web search failed: {search_result.error}")
                return None
            
            results = search_result.result.get("results", [])
            if not results:
                logger.info("Web search returned no results")
                return None
            
            # Форматируем результаты
            formatted = "\n\n📡 **АКТУАЛЬНАЯ ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА:**\n"
            formatted += "=" * 50 + "\n"
            
            for i, result in enumerate(results[:max_results], 1):
                title = result.get('title', '').strip()
                url = result.get('url', '').strip()
                snippet = result.get('snippet', '').strip()
                
                formatted += f"\n**[{i}] {title}**\n"
                if snippet:
                    formatted += f"{snippet}\n"
                formatted += f"🔗 {url}\n"
            
            formatted += "\n" + "=" * 50
            formatted += "\n*Используй эту информацию для дополнения ответа*\n"
            
            # Кэшируем
            self._search_cache[cache_key] = formatted
            
            logger.info(f"Web search found {len(results)} results for uncertainty query")
            return formatted
            
        except Exception as e:
            logger.error(f"Error during uncertainty web search: {e}")
            return None
    
    async def enhance_with_search_if_uncertain(
        self,
        response: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        force_search: bool = False
    ) -> Dict[str, Any]:
        """
        Проверяет ответ на неуверенность и дополняет веб-поиском при необходимости.
        
        Args:
            response: Исходный ответ модели
            task: Задача
            context: Контекст
            force_search: Принудительный поиск
            
        Returns:
            {
                "response": str,  # Финальный ответ
                "enhanced": bool,  # Был ли дополнен
                "confidence": float,  # Уровень уверенности
                "search_performed": bool,
                "search_results_count": int
            }
        """
        result = {
            "response": response,
            "enhanced": False,
            "confidence": 0.95,
            "search_performed": False,
            "search_results_count": 0
        }
        
        # Проверяем неуверенность
        is_uncertain, confidence, patterns = self.detect_uncertainty(response)
        result["confidence"] = confidence
        
        # Проверяем, требует ли задача актуальной информации
        requires_current, _ = self.task_requires_current_info(task)
        
        should_search = force_search or is_uncertain or requires_current
        
        if not should_search:
            return result
        
        # Формируем поисковый запрос
        search_query = self._create_search_query(task, response, patterns)
        
        # Выполняем поиск
        search_results = await self.search_for_missing_info(search_query, context)
        
        if search_results:
            result["search_performed"] = True
            result["search_results_count"] = search_results.count("[")
            
            # Получаем LLM для улучшения ответа
            llm_manager = getattr(self, 'llm_manager', None)
            if llm_manager:
                enhanced_response = await self._enhance_response_with_search(
                    original_response=response,
                    task=task,
                    search_results=search_results,
                    llm_manager=llm_manager
                )
                if enhanced_response:
                    result["response"] = enhanced_response
                    result["enhanced"] = True
                    logger.info("✅ Response enhanced with web search results")
            else:
                # Просто добавляем результаты поиска к ответу
                result["response"] = response + "\n\n" + search_results
                result["enhanced"] = True
        
        return result
    
    def _create_search_query(
        self, 
        task: str, 
        response: str, 
        uncertainty_patterns: List[str]
    ) -> str:
        """Создаёт оптимальный поисковый запрос"""
        # Берём ключевые слова из задачи
        # Удаляем стоп-слова
        stop_words = {
            "как", "что", "где", "когда", "почему", "какой", "какая", "какие",
            "the", "a", "an", "is", "are", "was", "were", "how", "what", "where"
        }
        
        words = task.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Ограничиваем длину запроса
        query = " ".join(keywords[:10])
        
        return query
    
    async def _enhance_response_with_search(
        self,
        original_response: str,
        task: str,
        search_results: str,
        llm_manager: Any
    ) -> Optional[str]:
        """Улучшает ответ с использованием найденной информации"""
        try:
            messages = [
                LLMMessage(
                    role="system",
                    content="""Ты помощник, который улучшает ответы используя актуальную информацию.

ПРАВИЛА:
1. Используй информацию из веб-поиска для дополнения ответа
2. Не придумывай факты - только то, что есть в результатах поиска
3. Укажи источники (URL) для ключевых фактов
4. Сохрани структуру и стиль оригинального ответа
5. Отвечай на русском языке"""
                ),
                LLMMessage(
                    role="user",
                    content=f"""ЗАДАЧА: {task}

ОРИГИНАЛЬНЫЙ ОТВЕТ:
{original_response}

РЕЗУЛЬТАТЫ ВЕБ-ПОИСКА:
{search_results}

Улучши оригинальный ответ, добавив актуальную информацию из веб-поиска. 
Если информация из поиска не релевантна - верни оригинальный ответ без изменений."""
                )
            ]
            
            response = await llm_manager.generate(
                messages=messages,
                temperature=0.3,  # Низкая температура для точности
                max_tokens=1500
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error enhancing response: {e}")
            return None
    
    def clear_search_cache(self):
        """Очищает кэш поиска"""
        self._search_cache.clear()
        logger.debug("Search cache cleared")

