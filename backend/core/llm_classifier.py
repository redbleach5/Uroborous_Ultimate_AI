"""
Универсальный модуль для классификации через LLM
Заменяет эвристики на интеллектуальную LLM-классификацию
"""

from typing import Dict, Any, Optional, List
import asyncio
import json
import hashlib
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage
from .constants import ConfidenceThresholds


# Предопределенные схемы классификации
REQUEST_TYPE_SCHEMA = {
    "types": {
        "simple_chat": "Простые приветствия и разговорные сообщения",
        "question": "Вопросы пользователя",
        "execution_task": "Задачи на выполнение (генерация кода, анализ и т.д.)"
    },
    "examples": [
        {
            "text": "Привет!",
            "result": {"type": "simple_chat", "confidence": 0.95, "reasoning": "Простое приветствие"}
        },
        {
            "text": "Как работает эта система?",
            "result": {"type": "question", "confidence": 0.9, "reasoning": "Вопрос о работе системы"}
        },
        {
            "text": "Сгенерируй игру змейка",
            "result": {"type": "execution_task", "confidence": 0.95, "reasoning": "Задача на генерацию кода"}
        }
    ]
}

TASK_TYPE_SCHEMA = {
    "types": {
        "modify": "Модификация существующего кода",
        "review": "Проверка и ревью кода",
        "generate": "Генерация нового кода",
        "general": "Общая задача"
    },
    "examples": [
        {
            "text": "Измени функцию чтобы она возвращала список",
            "result": {"type": "modify", "confidence": 0.9, "reasoning": "Модификация существующего кода"}
        },
        {
            "text": "Проверь этот код на ошибки",
            "result": {"type": "review", "confidence": 0.9, "reasoning": "Проверка кода"}
        },
        {
            "text": "Создай REST API",
            "result": {"type": "generate", "confidence": 0.95, "reasoning": "Генерация нового кода"}
        }
    ]
}

AGENT_SELECTION_SCHEMA = {
    "types": {
        "code_writer": "Задачи на генерацию или модификацию кода",
        "react": "Общие задачи, требующие использования инструментов",
        "research": "Исследовательские задачи, анализ проекта",
        "data_analysis": "Задачи анализа данных",
        "workflow": "Задачи создания workflow",
        "integration": "Задачи интеграции с внешними системами",
        "monitoring": "Задачи мониторинга и диагностики"
    },
    "examples": [
        {
            "text": "Сгенерируй функцию для работы с базой данных",
            "result": {"type": "code_writer", "confidence": 0.95, "reasoning": "Генерация кода"}
        },
        {
            "text": "Изучи структуру проекта и найди все API endpoints",
            "result": {"type": "research", "confidence": 0.9, "reasoning": "Исследование проекта"}
        },
        {
            "text": "Проанализируй данные из CSV файла",
            "result": {"type": "data_analysis", "confidence": 0.9, "reasoning": "Анализ данных"}
        }
    ]
}


class LLMClassifier:
    """Универсальный классификатор на основе LLM"""
    
    # Быстрые модели для классификации (маленькие, но достаточные для понимания намерения)
    FAST_CLASSIFICATION_MODELS = [
        "qwen2.5:3b", "qwen2.5:1.5b", "qwen2:1.5b",
        "llama3.2:1b", "llama3.2:3b", "gemma2:2b",
        "phi3:mini", "phi3.5", "tinyllama", "orca-mini"
    ]
    
    def __init__(
        self, 
        llm_manager: Optional[LLMProviderManager] = None, 
        cache_ttl: int = 3600,
        prefer_fast_model: bool = True
    ):
        """
        Args:
            llm_manager: Менеджер LLM провайдеров
            cache_ttl: Время жизни кэша в секундах (по умолчанию 1 час)
            prefer_fast_model: Использовать быструю модель для классификации
        """
        self.llm_manager = llm_manager
        self.cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self.cache_ttl = cache_ttl
        self.prefer_fast_model = prefer_fast_model
        self._lock = asyncio.Lock()
        self._fast_model_cache: Optional[str] = None
    
    async def classify(
        self,
        text: str,
        classification_schema: Dict[str, Any],
        provider: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Классифицирует текст по заданной схеме
        
        Args:
            text: Текст для классификации
            classification_schema: Схема классификации с описанием типов и примеров
            provider: Имя провайдера LLM (если None, выбирается автоматически)
            use_cache: Использовать ли кэш
            
        Returns:
            {
                "type": str,  # Тип из схемы
                "confidence": float,  # 0.0 - 1.0
                "reasoning": str,  # Объяснение
                "metadata": Dict[str, Any]  # Дополнительные данные
            }
        """
        if not self.llm_manager:
            return self._fallback_classification(text, classification_schema)
        
        # Проверяем кэш
        if use_cache:
            cache_key = self._get_cache_key(text, classification_schema)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return cached
        
        # Выбираем провайдер и модель
        selected_provider = provider or self._select_provider()
        if not selected_provider:
            return self._fallback_classification(text, classification_schema)
        
        # Выбираем быструю модель для классификации (если доступна)
        fast_model = await self._get_fast_model(selected_provider) if self.prefer_fast_model else None
        
        # Формируем промпт
        prompt = self._build_classification_prompt(text, classification_schema)
        
        try:
            # Классифицируем через LLM
            messages = [
                LLMMessage(role="system", content="Ты - эксперт по классификации текстов. Отвечай только в формате JSON."),
                LLMMessage(role="user", content=prompt)
            ]
            
            # Используем быструю модель если доступна
            generation_kwargs = {
                "messages": messages,
                "provider_name": selected_provider,
                "temperature": 0.1,  # Низкая температура для детерминированности
                "max_tokens": 300
            }
            if fast_model:
                generation_kwargs["model"] = fast_model
                logger.debug(f"Using fast model for classification: {fast_model}")
            
            response = await asyncio.wait_for(
                self.llm_manager.generate(**generation_kwargs),
                timeout=10.0
            )
            
            if not response or not response.content:
                raise ValueError("Пустой ответ от LLM")
            
            # Парсим JSON из ответа
            result = self._parse_classification_response(response.content, classification_schema)
            
            # Кэшируем результат
            if use_cache:
                await self._save_to_cache(cache_key, result)
            
            return result
            
        except (asyncio.TimeoutError, json.JSONDecodeError, ValueError, Exception) as e:
            logger.warning(f"LLM classification failed, using fallback: {e}")
            return self._fallback_classification(text, classification_schema)
    
    def _build_classification_prompt(self, text: str, schema: Dict[str, Any]) -> str:
        """Строит промпт для классификации"""
        types_desc = schema.get("types", {})
        examples = schema.get("examples", [])
        
        prompt = f"""Проанализируй следующий текст и определи его тип согласно схеме.

Текст: "{text}"

Типы:
"""
        for type_name, description in types_desc.items():
            prompt += f"- {type_name}: {description}\n"
        
        if examples:
            prompt += "\nПримеры:\n"
            for example in examples:
                prompt += f'- "{example["text"]}" -> {json.dumps(example["result"], ensure_ascii=False)}\n'
        
        prompt += """
Ответь ТОЛЬКО в формате JSON:
{
    "type": "тип из схемы",
    "confidence": число от 0.0 до 1.0,
    "reasoning": "краткое объяснение",
    "metadata": {}
}

JSON ответ:"""
        return prompt
    
    def _parse_classification_response(self, content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит ответ LLM"""
        content = content.strip()
        
        # Ищем JSON в ответе
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = content[json_start:json_end]
            result = json.loads(json_str)
            
            # Валидация
            valid_types = list(schema.get("types", {}).keys())
            if result.get("type") not in valid_types:
                result["type"] = valid_types[0] if valid_types else "unknown"
            
            # Нормализация confidence
            confidence = result.get("confidence", ConfidenceThresholds.DEFAULT_CONFIDENCE)
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = ConfidenceThresholds.DEFAULT_CONFIDENCE
            result["confidence"] = max(0.0, min(1.0, confidence))
            
            return result
        
        # Если JSON не найден, используем fallback
        return self._fallback_classification(content, schema)
    
    def _fallback_classification(self, text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback классификация на основе эвристик (паттерн-матчинг)"""
        text_lower = text.lower()
        types = schema.get("types", {})
        
        # Умная классификация с учётом контекста
        # Сначала проверяем специфичные комбинации слов
        
        # Явные маркеры анализа/исследования (высокий приоритет)
        analysis_markers = [
            "проанализируй проект", "анализ проекта", "изучи проект",
            "структура проекта", "архитектура проекта", "обзор проекта",
            "что делает проект", "как устроен", "ревью кода", "code review",
            "analyze project", "project analysis", "review project"
        ]
        if any(marker in text_lower for marker in analysis_markers):
            if "research" in types:
                return {
                    "type": "research",
                    "confidence": 0.9,
                    "reasoning": "Явный запрос на анализ проекта",
                    "metadata": {"fallback": True, "explicit_match": True}
                }
        
        # Явные маркеры генерации кода (высокий приоритет)
        code_gen_with_target = False
        gen_words = ["напиши", "создай", "сгенерируй", "generate", "create", "build", "make"]
        code_targets = ["код", "code", "игру", "game", "приложение", "app", "скрипт", "script", 
                       "функцию", "function", "класс", "class", "бот", "bot", "сайт", "site"]
        
        has_gen_word = any(w in text_lower for w in gen_words)
        has_code_target = any(t in text_lower for t in code_targets)
        
        if has_gen_word and has_code_target:
            if "code_writer" in types:
                return {
                    "type": "code_writer",
                    "confidence": 0.85,
                    "reasoning": "Генерация кода с явной целью",
                    "metadata": {"fallback": True, "explicit_match": True}
                }
        
        # Расширенные паттерны для агентов (используются если нет явного совпадения)
        agent_patterns = {
            "research": [
                "найди", "поищи", "где находится", "как работает", "объясни",
                "расскажи", "что такое", "покажи", "изучи", "проанализируй",
                "find", "search", "explain", "analyze", "research", "review",
                "документация", "структура", "архитектура", "последние версии",
                "новости", "информация", "what is", "how does"
            ],
            "code_writer": [
                "напиши код", "создай код", "реализуй", "добавь функцию",
                "write code", "implement", "build", "develop",
                "функцию для", "класс для", "скрипт для", "программу"
            ],
            "data_analysis": [
                "проанализируй данные", "визуализация", "статистика", "график",
                "analyze data", "visualization", "statistics", "chart", "plot",
                "csv", "dataset", "dataframe", "pandas", "анализ данных"
            ],
            "react": [
                "помоги разобраться", "подумай", "пошагово", "step by step",
                "think through", "reason about", "help me figure"
            ],
            "workflow": [
                "workflow", "пайплайн", "pipeline", "автоматизация", "automation",
                "процесс", "последовательность действий"
            ],
            "integration": [
                "интеграция", "подключи к", "синхронизация",
                "integrate with", "connect to", "sync with"
            ],
            "monitoring": [
                "мониторинг", "логи", "метрики", "диагностика",
                "monitoring", "logs", "metrics", "diagnostics"
            ]
        }
        
        # Проверяем паттерны для агентов
        best_match = None
        best_confidence = 0.0
        
        for agent_type, patterns in agent_patterns.items():
            if agent_type not in types:
                continue
            matches = sum(1 for p in patterns if p in text_lower)
            if matches > 0:
                confidence = min(0.75, 0.35 + matches * 0.15)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = agent_type
        
        if best_match:
            return {
                "type": best_match,
                "confidence": best_confidence,
                "reasoning": f"Паттерн-матчинг: {best_match}",
                "metadata": {"fallback": True, "pattern_based": True}
            }
        
        # Общие паттерны для других схем
        if "привет" in text_lower or "hello" in text_lower or "hi" in text_lower:
            task_type = "simple_chat" if "simple_chat" in types else list(types.keys())[0]
        elif "?" in text:
            task_type = "question" if "question" in types else list(types.keys())[0]
        elif any(word in text_lower for word in ["создай", "напиши", "генерируй", "generate", "create"]):
            task_type = "generate" if "generate" in types else "execution_task" if "execution_task" in types else list(types.keys())[0]
        else:
            # По умолчанию: react (универсальный агент)
            task_type = "react" if "react" in types else list(types.keys())[0] if types else "unknown"
        
        return {
            "type": task_type,
            "confidence": 0.4,  # Низкая уверенность для fallback
            "reasoning": f"Fallback классификация: {task_type}",
            "metadata": {"fallback": True}
        }
    
    def _select_provider(self) -> Optional[str]:
        """Выбирает провайдер для классификации"""
        if not self.llm_manager:
            return None
        
        # Приоритет: быстрые локальные модели
        preferred = ["ollama"]
        for provider_name in preferred:
            if provider_name in self.llm_manager.providers:
                return provider_name
        
        # Fallback на первый доступный
        if self.llm_manager.providers:
            return list(self.llm_manager.providers.keys())[0]
        
        return None
    
    async def _get_fast_model(self, provider_name: str) -> Optional[str]:
        """Выбирает самую быструю доступную модель для классификации"""
        # Используем кэш если есть
        if self._fast_model_cache:
            return self._fast_model_cache
        
        if not self.llm_manager or provider_name != "ollama":
            return None
        
        try:
            # Получаем провайдер
            ollama_provider = self.llm_manager.providers.get("ollama")
            if not ollama_provider:
                return None
            
            # Получаем список доступных моделей
            available_models = await ollama_provider.list_models()
            if not available_models:
                return None
            
            available_model_names = [m.get("name", "") for m in available_models]
            
            # 1. Сначала ищем в списке известных быстрых моделей
            for fast_model in self.FAST_CLASSIFICATION_MODELS:
                for available in available_model_names:
                    if fast_model in available or available.startswith(fast_model.split(":")[0]):
                        self._fast_model_cache = available
                        logger.info(f"Found fast classification model: {available}")
                        return available
            
            # 2. Если не найдена — ищем любую маленькую модель по паттерну размера
            small_model = self._find_small_model_by_size(available_models)
            if small_model:
                self._fast_model_cache = small_model
                logger.info(f"Found small model by size pattern: {small_model}")
                return small_model
            
            # 3. Если совсем ничего — возвращаем None (будет использована модель по умолчанию)
            logger.debug(f"No fast model found, will use default. Available: {available_model_names[:5]}")
            return None
            
        except Exception as e:
            logger.debug(f"Could not get fast model: {e}")
            return None
    
    def _find_small_model_by_size(self, models: list) -> Optional[str]:
        """
        Находит маленькую модель по паттернам в имени или размеру.
        
        Паттерны маленьких моделей:
        - :1b, :1.5b, :2b, :3b, :4b в имени
        - mini, tiny, small, nano, micro в имени
        - размер < 10GB (если доступна информация)
        """
        small_patterns = [
            ":0.5b", ":1b", ":1.5b", ":2b", ":3b", ":4b",
            "mini", "tiny", "small", "nano", "micro"
        ]
        
        # Приоритет: сначала самые маленькие
        for pattern in small_patterns:
            for model in models:
                name = model.get("name", "").lower()
                if pattern in name:
                    return model.get("name")
        
        # Если есть информация о размере — ищем < 10GB
        for model in models:
            size = model.get("size", 0)
            if size and size < 10 * 1024 * 1024 * 1024:  # < 10GB
                return model.get("name")
        
        return None
    
    def _get_cache_key(self, text: str, schema: Dict[str, Any]) -> str:
        """Генерирует ключ кэша"""
        schema_str = json.dumps(schema, sort_keys=True)
        combined = f"{text}:{schema_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    async def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Получает значение из кэша"""
        async with self._lock:
            if key in self.cache:
                value, expiry = self.cache[key]
                import time
                if time.time() < expiry:
                    return value
                else:
                    del self.cache[key]
        return None
    
    async def _save_to_cache(self, key: str, value: Dict[str, Any]):
        """Сохраняет значение в кэш"""
        import time
        async with self._lock:
            expiry = time.time() + self.cache_ttl
            self.cache[key] = (value, expiry)
    
    async def clear_cache(self, pattern: Optional[str] = None):
        """Очищает кэш"""
        async with self._lock:
            if pattern:
                keys_to_delete = [k for k in self.cache.keys() if pattern in k]
                for key in keys_to_delete:
                    del self.cache[key]
            else:
                self.cache.clear()

