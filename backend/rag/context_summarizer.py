"""
Context Summarizer - Умное суммирование контекста для больших проектов
Сохраняет важную информацию без потери качества
"""

from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import re
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage
from ..core.advanced_cache import AdvancedCache


class SummarizationStrategy(Enum):
    """Стратегии суммирования"""
    HIERARCHICAL = "hierarchical"  # Иерархическое суммирование по уровням
    EXTRACTIVE = "extractive"  # Выбор ключевых фрагментов
    ABSTRACTIVE = "abstractive"  # LLM-based суммирование
    HYBRID = "hybrid"  # Комбинация методов
    STRUCTURE_PRESERVING = "structure_preserving"  # Сохранение структуры кода


class ContextSummarizer:
    """
    Умное суммирование контекста для больших проектов
    
    Особенности:
    - Сохранение важной информации (API, функции, классы)
    - Иерархическое суммирование
    - Сохранение структуры кода
    - Кэширование результатов
    """
    
    def __init__(
        self,
        llm_manager: Optional[LLMProviderManager] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize context summarizer
        
        Args:
            llm_manager: LLM provider manager для суммирования
            config: Конфигурация суммирования
        """
        self.llm_manager = llm_manager
        self.config = config or {}
        
        # Стратегия суммирования
        self.strategy = SummarizationStrategy(
            self.config.get("strategy", "hybrid")
        )
        
        # Параметры
        self.max_tokens = self.config.get("max_tokens", 8000)
        self.target_tokens = self.config.get("target_tokens", 4000)
        self.preserve_code = self.config.get("preserve_code", True)
        self.preserve_structure = self.config.get("preserve_structure", True)
        self.importance_threshold = self.config.get("importance_threshold", 0.7)
        
        # Кэширование суммирования
        cache_config = self.config.get("cache", {})
        self.summary_cache = AdvancedCache(
            memory_size=cache_config.get("memory_size", 500),
            disk_cache_dir=cache_config.get("disk_cache_dir", "cache/summaries"),
            redis_url=cache_config.get("redis_url"),
            ttl=cache_config.get("ttl", 7200)  # 2 часа для суммирований
        )
    
    async def summarize(
        self,
        context: str,
        query: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Суммирует контекст с сохранением важной информации
        
        Args:
            context: Исходный контекст
            query: Запрос пользователя (для фокусировки)
            max_tokens: Максимальное количество токенов в результате
        
        Returns:
            Суммированный контекст
        """
        max_tokens = max_tokens or self.target_tokens
        
        # Оцениваем размер контекста
        estimated_tokens = len(context) // 4  # ~4 символа на токен
        
        # Если контекст уже достаточно мал, возвращаем как есть
        if estimated_tokens <= max_tokens:
            return context
        
        # Генерируем ключ кэша
        import hashlib
        import json
        cache_key_data = {
            "context_hash": hashlib.md5(context.encode()).hexdigest()[:16],
            "query": query or "",
            "max_tokens": max_tokens,
            "strategy": self.strategy.value
        }
        cache_key = hashlib.md5(
            json.dumps(cache_key_data, sort_keys=True).encode()
        ).hexdigest()
        
        # Проверяем кэш
        cached_summary = self.summary_cache.get(cache_key)
        if cached_summary:
            logger.debug(f"Summary cache HIT: {len(cached_summary)} chars")
            return cached_summary
        
        logger.info(
            f"Summarizing context: {estimated_tokens} tokens → {max_tokens} tokens "
            f"(strategy: {self.strategy.value})"
        )
        
        # Выбираем стратегию суммирования
        if self.strategy == SummarizationStrategy.HIERARCHICAL:
            summary = await self._hierarchical_summarize(context, query, max_tokens)
        elif self.strategy == SummarizationStrategy.EXTRACTIVE:
            summary = await self._extractive_summarize(context, query, max_tokens)
        elif self.strategy == SummarizationStrategy.ABSTRACTIVE:
            summary = await self._abstractive_summarize(context, query, max_tokens)
        elif self.strategy == SummarizationStrategy.STRUCTURE_PRESERVING:
            summary = await self._structure_preserving_summarize(context, query, max_tokens)
        else:  # HYBRID
            summary = await self._hybrid_summarize(context, query, max_tokens)
        
        # Сохраняем в кэш
        try:
            self.summary_cache.set(cache_key, summary)
        except Exception as e:
            logger.warning(f"Failed to cache summary: {e}")
        
        return summary
    
    async def _hierarchical_summarize(
        self,
        context: str,
        query: Optional[str],
        max_tokens: int
    ) -> str:
        """
        Иерархическое суммирование:
        1. Разбиваем на уровни (файлы, функции, классы)
        2. Суммируем каждый уровень
        3. Объединяем результаты
        """
        # Разбиваем контекст на части
        parts = self._split_into_parts(context)
        
        if len(parts) == 1:
            # Если одна часть, используем абстрактивное суммирование
            return await self._abstractive_summarize(context, query, max_tokens)
        
        # Суммируем каждую часть пропорционально
        tokens_per_part = max_tokens // len(parts)
        summarized_parts = []
        
        for part in parts:
            if len(part) // 4 <= tokens_per_part:
                # Часть уже достаточно мала
                summarized_parts.append(part)
            else:
                # Суммируем часть
                part_summary = await self._abstractive_summarize(
                    part, query, tokens_per_part
                )
                summarized_parts.append(part_summary)
        
        return "\n\n".join(summarized_parts)
    
    async def _extractive_summarize(
        self,
        context: str,
        query: Optional[str],
        max_tokens: int
    ) -> str:
        """
        Extractive суммирование:
        Выбираем наиболее важные фрагменты на основе:
        - Релевантности к запросу
        - Важности (API, функции, классы)
        - Структуры кода
        """
        # Разбиваем на предложения/блоки
        blocks = self._split_into_blocks(context)
        
        # Оцениваем важность каждого блока
        scored_blocks = []
        for block in blocks:
            score = self._score_block_importance(block, query)
            scored_blocks.append((score, block))
        
        # Сортируем по важности
        scored_blocks.sort(reverse=True, key=lambda x: x[0])
        
        # Выбираем блоки до достижения max_tokens
        selected_blocks = []
        current_tokens = 0
        
        for score, block in scored_blocks:
            block_tokens = len(block) // 4
            if current_tokens + block_tokens <= max_tokens:
                selected_blocks.append(block)
                current_tokens += block_tokens
            else:
                # Пробуем добавить часть блока
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 100:  # Минимум 100 токенов
                    partial_block = block[:remaining_tokens * 4]
                    selected_blocks.append(partial_block + "...")
                break
        
        # Восстанавливаем порядок
        block_indices = {block: i for i, (_, block) in enumerate(scored_blocks)}
        selected_blocks.sort(key=lambda b: block_indices.get(b, 0))
        
        return "\n\n".join(selected_blocks)
    
    async def _abstractive_summarize(
        self,
        context: str,
        query: Optional[str],
        max_tokens: int
    ) -> str:
        """
        Abstractive суммирование через LLM
        Сохраняет важную информацию и структуру
        """
        if not self.llm_manager:
            # Fallback на extractive если нет LLM
            return await self._extractive_summarize(context, query, max_tokens)
        
        # Строим промпт для суммирования
        query_context = f"\n\nЗапрос пользователя: {query}" if query else ""
        
        prompt = f"""Ты - эксперт по суммированию кода и документации. 

Твоя задача - создать краткое, но информативное суммирование следующего контекста, СОХРАНЯЯ ВСЮ ВАЖНУЮ ИНФОРМАЦИЮ:

ВАЖНО:
1. Сохрани все определения функций, классов, API endpoints
2. Сохрани структуру кода (импорты, основные классы, методы)
3. Сохрани важные константы и конфигурации
4. Сохрани ключевые комментарии и документацию
5. Удали только повторяющуюся информацию и детали реализации
6. Сохрани примеры использования если они есть

Контекст для суммирования:
{context[:self.max_tokens * 4]}{query_context}

Создай суммирование, которое сохраняет всю важную информацию, но сокращает объем примерно в 2 раза.
Суммирование должно быть структурированным и легко читаемым."""

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            
            response = await self.llm_manager.generate(
                messages=messages,
                temperature=0.3,  # Низкая температура для точности
                max_tokens=max_tokens * 2  # Даем больше токенов для качественного суммирования
            )
            
            summary = response.content.strip()
            
            # Проверяем что суммаризация не слишком длинная
            if len(summary) // 4 > max_tokens * 1.2:
                # Если слишком длинная, рекурсивно суммируем
                summary = await self._abstractive_summarize(
                    summary, query, max_tokens
                )
            
            return summary
        except Exception as e:
            logger.warning(f"Abstractive summarization failed: {e}, using extractive")
            return await self._extractive_summarize(context, query, max_tokens)
    
    async def _structure_preserving_summarize(
        self,
        context: str,
        query: Optional[str],
        max_tokens: int
    ) -> str:
        """
        Суммирование с сохранением структуры кода
        Особенно важно для больших проектов
        """
        # Разбиваем на структурные элементы
        structure_elements = self._extract_structure(context)
        
        # Группируем по типам
        grouped = {
            "imports": [],
            "classes": [],
            "functions": [],
            "constants": [],
            "config": [],
            "other": []
        }
        
        for element_type, element in structure_elements:
            if element_type in grouped:
                grouped[element_type].append(element)
            else:
                grouped["other"].append(element)
        
        # Суммируем каждую группу
        summarized_groups = {}
        tokens_per_group = max_tokens // len(grouped)
        
        for group_type, elements in grouped.items():
            if not elements:
                continue
            
            group_text = "\n\n".join(elements)
            
            if len(group_text) // 4 <= tokens_per_group:
                summarized_groups[group_type] = group_text
            else:
                # Суммируем группу
                summary = await self._abstractive_summarize(
                    group_text, query, tokens_per_group
                )
                summarized_groups[group_type] = summary
        
        # Восстанавливаем структуру
        result_parts = []
        if summarized_groups.get("imports"):
            result_parts.append("=== IMPORTS ===\n" + summarized_groups["imports"])
        if summarized_groups.get("constants"):
            result_parts.append("=== CONSTANTS ===\n" + summarized_groups["constants"])
        if summarized_groups.get("config"):
            result_parts.append("=== CONFIG ===\n" + summarized_groups["config"])
        if summarized_groups.get("classes"):
            result_parts.append("=== CLASSES ===\n" + summarized_groups["classes"])
        if summarized_groups.get("functions"):
            result_parts.append("=== FUNCTIONS ===\n" + summarized_groups["functions"])
        if summarized_groups.get("other"):
            result_parts.append("=== OTHER ===\n" + summarized_groups["other"])
        
        return "\n\n".join(result_parts)
    
    async def _hybrid_summarize(
        self,
        context: str,
        query: Optional[str],
        max_tokens: int
    ) -> str:
        """
        Гибридное суммирование:
        1. Extractive для выбора важных фрагментов
        2. Abstractive для суммирования выбранных фрагментов
        """
        # Сначала extractive для выбора важных частей
        important_parts = await self._extractive_summarize(
            context, query, max_tokens * 2  # Берем больше для выбора
        )
        
        # Затем abstractive для финального суммирования
        final_summary = await self._abstractive_summarize(
            important_parts, query, max_tokens
        )
        
        return final_summary
    
    def _split_into_parts(self, context: str) -> List[str]:
        """Разбивает контекст на логические части"""
        # Разделители для разных типов контента
        separators = [
            "\n\n=== ",  # Заголовки разделов
            "\n\n## ",  # Markdown заголовки
            "\n\nclass ",  # Классы
            "\n\ndef ",  # Функции
            "\n\nasync def ",  # Async функции
            "\n\n---\n",  # Разделители
        ]
        
        parts = [context]
        for sep in separators:
            new_parts = []
            for part in parts:
                if sep in part:
                    new_parts.extend(part.split(sep))
                else:
                    new_parts.append(part)
            parts = new_parts
        
        # Фильтруем пустые части
        return [p.strip() for p in parts if p.strip()]
    
    def _split_into_blocks(self, context: str) -> List[str]:
        """Разбивает контекст на блоки (предложения, параграфы, функции)"""
        # Разбиваем по параграфам
        paragraphs = context.split("\n\n")
        
        blocks = []
        current_block = []
        current_size = 0
        max_block_size = 500  # ~125 токенов на блок
        
        for para in paragraphs:
            para_size = len(para)
            if current_size + para_size > max_block_size and current_block:
                blocks.append("\n\n".join(current_block))
                current_block = [para]
                current_size = para_size
            else:
                current_block.append(para)
                current_size += para_size
        
        if current_block:
            blocks.append("\n\n".join(current_block))
        
        return blocks
    
    def _score_block_importance(
        self,
        block: str,
        query: Optional[str]
    ) -> float:
        """
        Оценивает важность блока (0.0 - 1.0)
        
        Факторы:
        - Релевантность к запросу
        - Наличие важных элементов (функции, классы, API)
        - Позиция в документе
        """
        score = 0.5  # Базовая важность
        
        # Релевантность к запросу
        if query:
            query_lower = query.lower()
            block_lower = block.lower()
            
            # Точное совпадение слов
            query_words = set(query_lower.split())
            block_words = set(block_lower.split())
            common_words = query_words & block_words
            
            if common_words:
                relevance = len(common_words) / len(query_words)
                score += relevance * 0.3
        
        # Важные элементы кода
        important_patterns = [
            r'\bdef\s+\w+',  # Функции
            r'\bclass\s+\w+',  # Классы
            r'\basync\s+def\s+\w+',  # Async функции
            r'@\w+',  # Декораторы
            r'API\s+endpoint',  # API endpoints
            r'@app\.(get|post|put|delete)',  # FastAPI routes
            r'export\s+(function|class|const)',  # JS/TS exports
        ]
        
        for pattern in important_patterns:
            if re.search(pattern, block, re.IGNORECASE):
                score += 0.1
        
        # Документация и комментарии
        if '"""' in block or "'''" in block or '//' in block or '/*' in block:
            score += 0.05
        
        # Ограничиваем до [0, 1]
        return min(1.0, max(0.0, score))
    
    def _extract_structure(self, context: str) -> List[Tuple[str, str]]:
        """
        Извлекает структурные элементы из контекста
        
        Returns:
            List of (type, content) tuples
        """
        elements = []
        
        # Импорты
        import_pattern = r'^(import\s+|from\s+.*\s+import\s+)(.*)$'
        imports = re.findall(import_pattern, context, re.MULTILINE)
        if imports:
            elements.append(("imports", "\n".join([i[0] + i[1] for i in imports])))
        
        # Классы
        class_pattern = r'(class\s+\w+[^:]*:.*?)(?=\nclass\s+\w+|\n\ndef\s+\w+|\Z)'
        classes = re.findall(class_pattern, context, re.DOTALL)
        elements.extend([("classes", c) for c in classes])
        
        # Функции
        func_pattern = r'(def\s+\w+[^:]*:.*?)(?=\n\ndef\s+\w+|\nclass\s+\w+|\Z)'
        functions = re.findall(func_pattern, context, re.DOTALL)
        elements.extend([("functions", f) for f in functions])
        
        # Async функции
        async_func_pattern = r'(async\s+def\s+\w+[^:]*:.*?)(?=\n\ndef\s+\w+|\nclass\s+\w+|\Z)'
        async_funcs = re.findall(async_func_pattern, context, re.DOTALL)
        elements.extend([("functions", f) for f in async_funcs])
        
        # Константы (UPPER_CASE)
        const_pattern = r'^([A-Z_][A-Z0-9_]*\s*=\s*[^\n]+)$'
        constants = re.findall(const_pattern, context, re.MULTILINE)
        if constants:
            elements.append(("constants", "\n".join(constants)))
        
        return elements

