"""
Ollama LLM Provider (Local models) with retry and exponential backoff
"""

import httpx
import json
import re
import time
import asyncio
from typing import List, Optional, AsyncIterator, Dict, Any
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseLLMProvider, LLMMessage, LLMResponse
from ..core.exceptions import LLMException
from ..core.model_performance_tracker import get_performance_tracker


async def retry_with_backoff(
    coroutine_func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError),
    on_retry: callable = None
):
    """
    Execute a coroutine with exponential backoff retry logic.
    
    Args:
        coroutine_func: Async function to execute (called on each attempt)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential calculation
        retryable_exceptions: Tuple of exceptions that should trigger retry
        on_retry: Optional callback(attempt, error, delay) called before each retry
        
    Returns:
        Result of the coroutine
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coroutine_func()
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                # Calculate delay with exponential backoff and jitter
                delay = min(
                    base_delay * (exponential_base ** attempt),
                    max_delay
                )
                # Add random jitter (±20%) to prevent thundering herd
                import random
                jitter = delay * 0.2 * (random.random() * 2 - 1)
                delay = max(0.1, delay + jitter)
                
                if on_retry:
                    on_retry(attempt + 1, e, delay)
                else:
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{max_retries} after error: {e}. "
                        f"Waiting {delay:.2f}s before next attempt..."
                    )
                
                await asyncio.sleep(delay)
            else:
                # Last attempt failed
                logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
    
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in retry_with_backoff")


class OllamaProvider(BaseLLMProvider):
    """Ollama local models provider with automatic server fallback"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.auto_detect_models = config.get("auto_detect_models", True)
        self.recommended_models = config.get("recommended_models", {})
        self.client: Optional[httpx.AsyncClient] = None
        self._available_models: List[str] = []
        
        # Fallback URLs для автоматического переключения серверов
        self.fallback_urls = config.get("fallback_urls", [])
        self.additional_servers = config.get("additional_servers", [])
        self._all_server_urls: List[str] = self._build_server_list()
        self._current_server_index = 0
        self._working_url: Optional[str] = None  # Последний работающий URL
    
    def _build_server_list(self) -> List[str]:
        """Строит список всех серверов для fallback"""
        urls = [self.base_url]
        
        # Добавляем fallback URLs
        for url in self.fallback_urls:
            if not url.startswith("http"):
                url = f"http://{url}"
            if url not in urls:
                urls.append(url)
        
        # Добавляем additional_servers
        for server in self.additional_servers:
            url = server.get("url", "")
            if url and url not in urls:
                urls.append(url)
        
        # Всегда добавляем localhost как последний fallback
        localhost = "http://localhost:11434"
        if localhost not in urls:
            urls.append(localhost)
        
        return urls
    
    async def initialize(self) -> None:
        """Initialize Ollama client and detect available models
        
        Автоматически пробует все сконфигурированные серверы (base_url, fallback_urls, additional_servers).
        Использует первый работающий сервер.
        
        Оптимизировано для работы с 30+ моделями 60B+ параметров:
        - Connection pooling (50 keepalive, 100 max connections)
        - HTTP/2 для лучшей производительности
        - AdvancedCache для многоуровневого кэширования
        """
        # Инициализируем AdvancedCache
        cache_config = self.config.get("cache", {})
        from ..core.advanced_cache import AdvancedCache
        self.advanced_cache = AdvancedCache(
            memory_size=cache_config.get("memory_size", 2000),
            disk_cache_dir=cache_config.get("disk_cache_dir", "cache/ollama"),
            redis_url=cache_config.get("redis_url"),
            ttl=cache_config.get("ttl", 7200)
        )
        
        # Пробуем подключиться к каждому серверу из списка
        connected = False
        last_error = None
        
        for idx, server_url in enumerate(self._all_server_urls):
            logger.info(f"Trying Ollama server {idx + 1}/{len(self._all_server_urls)}: {server_url}")
            
            try:
                client = await self._create_client(server_url)
                
                # Test connection
                response = await client.get("/api/tags", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    models = [model["name"] for model in data.get("models", [])]
                    
                    if models:  # Сервер работает и имеет модели
                        self.client = client
                        self.base_url = server_url
                        self._working_url = server_url
                        self._current_server_index = idx
                        self._available_models = models
                        connected = True
                        logger.info(f"✅ Connected to Ollama at {server_url} with {len(models)} models")
                        break
                    else:
                        logger.warning(f"Server {server_url} has no models, trying next...")
                        await client.aclose()
                else:
                    logger.warning(f"Server {server_url} returned status {response.status_code}")
                    await client.aclose()
                    
            except Exception as e:
                last_error = e
                logger.debug(f"Failed to connect to {server_url}: {e}")
                continue
        
        if not connected:
            logger.warning(f"Could not connect to any Ollama server. Last error: {last_error}")
            # Создаем клиент для base_url как fallback (может заработать позже)
            self.client = await self._create_client(self.base_url)
            self._available_models = []
        
        # Выбираем дефолтную модель
        self._select_default_model()
    
    async def _create_client(self, base_url: str) -> httpx.AsyncClient:
        """Создаёт httpx клиент с оптимальными настройками"""
        try:
            return httpx.AsyncClient(
                base_url=base_url,
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=100,
                    keepalive_expiry=30.0
                ),
                http2=True
            )
        except Exception as e:
            if "h2" in str(e).lower() or "http2" in str(e).lower():
                logger.debug("HTTP/2 not available, using HTTP/1.1")
                return httpx.AsyncClient(
                    base_url=base_url,
                    timeout=self.timeout,
                    limits=httpx.Limits(
                        max_keepalive_connections=50,
                        max_connections=100,
                        keepalive_expiry=30.0
                    ),
                    http2=False
                )
            raise
    
    def _select_default_model(self) -> None:
        """Выбирает дефолтную модель из доступных"""
        if not self.default_model or self.default_model not in self._available_models:
            if self._available_models:
                fallback_model = None
                
                # Приоритет: recommended_models.chat
                if self.recommended_models and "chat" in self.recommended_models:
                    for recommended in self.recommended_models["chat"]:
                        for available in self._available_models:
                            if recommended in available or available.startswith(recommended):
                                fallback_model = available
                                break
                        if fallback_model:
                            break
                
                # Затем другие категории
                if not fallback_model and self.recommended_models:
                    for category, models in self.recommended_models.items():
                        if category == "chat":
                            continue
                        for recommended in models:
                            for available in self._available_models:
                                if recommended in available or available.startswith(recommended):
                                    fallback_model = available
                                    break
                            if fallback_model:
                                break
                        if fallback_model:
                            break
                
                # Если не нашли в рекомендуемых - первая доступная
                if not fallback_model:
                    fallback_model = self._available_models[0]
                
                if self.default_model:
                    logger.warning(f"Model '{self.default_model}' not available. Using '{fallback_model}'")
                else:
                    logger.info(f"Auto-detected default model: '{fallback_model}'")
                self.default_model = fallback_model
    
    def select_model_for_complexity(self, complexity: str, code_files: int = 0, total_lines: int = 0) -> str:
        """
        Выбирает оптимальную модель на основе сложности задачи.
        
        Args:
            complexity: "simple", "medium", "complex"
            code_files: количество файлов кода
            total_lines: количество строк кода
            
        Returns:
            Название оптимальной модели
        """
        if not self._available_models:
            return self.default_model or "llama3.2:3b"
        
        # Классификация моделей по размеру (параметры)
        large_models = []  # 14B+ для сложных задач
        medium_models = []  # 7-13B для средних задач
        small_models = []   # <7B для простых задач
        
        for model in self._available_models:
            model_lower = model.lower()
            
            # Определяем размер модели по имени
            if any(x in model_lower for x in [':70b', ':32b', ':14b', ':13b', '70b', '32b', '14b', '13b']):
                large_models.append(model)
            elif any(x in model_lower for x in [':7b', ':8b', '7b', '8b']):
                medium_models.append(model)
            else:
                small_models.append(model)
        
        # Определяем требуемый размер модели
        is_complex = (
            complexity == "complex" or 
            code_files > 50 or 
            total_lines > 10000
        )
        is_medium = (
            complexity == "medium" or 
            code_files > 20 or 
            total_lines > 3000
        )
        
        # Выбираем модель
        selected = None
        reason = ""
        
        if is_complex:
            if large_models:
                selected = large_models[0]
                reason = f"Выбрана мощная модель для сложного проекта ({code_files} файлов, {total_lines:,} строк)"
            elif medium_models:
                selected = medium_models[0]
                reason = "Используется средняя модель (большие модели недоступны)"
            else:
                selected = small_models[0] if small_models else self.default_model
                reason = "Используется доступная модель (рекомендуется установить модель 14B+)"
        elif is_medium:
            if medium_models:
                selected = medium_models[0]
                reason = "Выбрана модель для проекта средней сложности"
            elif large_models:
                selected = large_models[0]
                reason = "Используется мощная модель для качества"
            else:
                selected = small_models[0] if small_models else self.default_model
                reason = "Используется доступная модель"
        else:
            # Простой проект - можно использовать маленькую модель для скорости
            if small_models:
                selected = small_models[0]
                reason = "Быстрая модель для простого проекта"
            elif medium_models:
                selected = medium_models[0]
                reason = "Используется средняя модель"
            else:
                selected = large_models[0] if large_models else self.default_model
                reason = "Используется доступная модель"
        
        logger.info(f"[ModelSelector] {reason}: {selected}")
        return selected or self.default_model or "llama3.2:3b"
    
    def get_available_models(self) -> List[str]:
        """Возвращает список доступных моделей"""
        return self._available_models.copy()
    
    async def shutdown(self) -> None:
        """Shutdown Ollama client"""
        if self.client:
            await self.client.aclose()
    
    async def _try_next_server(self) -> bool:
        """Пробует подключиться к следующему серверу из списка
        
        Returns:
            True если удалось подключиться к другому серверу
        """
        if len(self._all_server_urls) <= 1:
            return False
        
        original_index = self._current_server_index
        
        for _ in range(len(self._all_server_urls)):
            self._current_server_index = (self._current_server_index + 1) % len(self._all_server_urls)
            
            if self._current_server_index == original_index:
                break  # Прошли полный круг
            
            server_url = self._all_server_urls[self._current_server_index]
            logger.info(f"🔄 Trying fallback server: {server_url}")
            
            try:
                client = await self._create_client(server_url)
                response = await client.get("/api/tags", timeout=5.0)
                
                if response.status_code == 200:
                    data = response.json()
                    models = [model["name"] for model in data.get("models", [])]
                    
                    if models:
                        # Закрываем старый клиент
                        if self.client:
                            await self.client.aclose()
                        
                        self.client = client
                        self.base_url = server_url
                        self._working_url = server_url
                        self._available_models = models
                        self._select_default_model()
                        
                        logger.info(f"✅ Switched to fallback server {server_url} with {len(models)} models")
                        return True
                    else:
                        await client.aclose()
                else:
                    await client.aclose()
                    
            except Exception as e:
                logger.debug(f"Fallback server {server_url} failed: {e}")
                continue
        
        logger.warning("All fallback servers exhausted")
        return False
    
    async def get_working_url(self) -> str:
        """Возвращает текущий работающий URL сервера"""
        return self._working_url or self.base_url
    
    def _select_best_model(self, task_type: Optional[str] = None, model: Optional[str] = None) -> str:
        """
        Умный выбор лучшей Ollama модели на основе типа задачи
        
        Args:
            task_type: Тип задачи (code, chat, analysis, reasoning)
            model: Предпочтительная модель (если указана, используется)
            
        Returns:
            Имя модели для использования
        """
        # Если модель передана явно - всегда использовать её (IntelligentModelRouter уже выбрал лучшую)
        if model:
            logger.debug(f"Using explicitly requested model: {model}")
            return model
        
        # Если нет доступных моделей, используем default
        if not self._available_models:
            return self.default_model
        
        # Умный выбор на основе типа задачи
        if task_type and self.recommended_models:
            recommended = self.recommended_models.get(task_type, [])
            for rec_model in recommended:
                if rec_model in self._available_models:
                    logger.debug(f"Selected recommended model '{rec_model}' for task type '{task_type}'")
                    return rec_model
        
        # Fallback: используем первую доступную или default
        if self.default_model in self._available_models:
            return self.default_model
        
        return self._available_models[0]
    
    def _check_thinking_support(self, model_name: str) -> bool:
        """
        Проверяет, поддерживает ли модель нативный thinking mode
        
        Args:
            model_name: Имя модели
            
        Returns:
            True если модель поддерживает thinking mode
        """
        # Модели, которые поддерживают нативный thinking mode в Ollama
        # (обновляется по мере добавления поддержки в Ollama)
        thinking_models = [
            "llama3.3",  # Llama 3.3 и новее поддерживают thinking
            "llama3.2",  # Llama 3.2 может поддерживать
            "qwen2.5",   # Qwen 2.5 поддерживает reasoning
            "deepseek",  # DeepSeek модели поддерживают thinking
        ]
        
        # Проверяем, содержит ли имя модели ключевые слова
        model_lower = model_name.lower()
        return any(thinking_model.lower() in model_lower for thinking_model in thinking_models)
    
    def _parse_ndjson_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse NDJSON (Newline Delimited JSON) response from Ollama.
        Ollama streaming responses contain multiple JSON objects separated by newlines.
        
        Args:
            response_text: Raw response text containing NDJSON
            
        Returns:
            Merged response dict with combined content, or None if parsing fails
        """
        content_parts = []
        final_data = None
        
        for line in response_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    # Extract content from message
                    if "message" in obj and isinstance(obj["message"], dict):
                        msg_content = obj["message"].get("content", "")
                        if msg_content:
                            content_parts.append(msg_content)
                    elif "content" in obj:
                        content_parts.append(obj["content"])
                    # Keep the last object for metadata (done, model, eval_count, etc.)
                    final_data = obj
            except json.JSONDecodeError:
                continue
        
        if content_parts and final_data:
            # Combine all content parts
            combined_content = "".join(content_parts)
            if "message" in final_data and isinstance(final_data["message"], dict):
                final_data["message"]["content"] = combined_content
            else:
                final_data["message"] = {"content": combined_content}
            logger.debug(f"Parsed {len(content_parts)} NDJSON chunks")
            return final_data
        
        if final_data:
            return final_data
        
        # Fallback: try regex extraction for malformed responses
        return self._extract_content_regex(response_text)
    
    def _extract_content_regex(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Fallback content extraction using regex for malformed JSON.
        
        Args:
            text: Raw response text
            
        Returns:
            Dict with extracted content or None
        """
        patterns = [
            r'"message"\s*:\s*\{[^}]*"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
            r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                content = match.group(1)
                # Decode escape sequences
                content = content.replace('\\n', '\n').replace('\\t', '\t')
                content = content.replace('\\"', '"').replace('\\\\', '\\')
                logger.debug("Extracted content using regex fallback")
                return {"message": {"content": content}}
        
        return None
    
    def _enhance_prompt_for_thinking(self, messages: List[LLMMessage], thinking_mode: bool, model_name: str) -> List[LLMMessage]:
        """
        Подготавливает промпты для thinking mode
        
        Если модель поддерживает нативный thinking mode, использует минимальные инструкции.
        Иначе использует расширенную эмуляцию через промпты.
        
        Args:
            messages: Исходные сообщения
            thinking_mode: Включить thinking mode
            model_name: Имя модели для проверки поддержки
            
        Returns:
            Обновленные сообщения с thinking инструкциями
        """
        if not thinking_mode:
            return messages
        
        # Проверяем поддержку нативного thinking mode
        supports_native_thinking = self._check_thinking_support(model_name)
        
        if supports_native_thinking:
            # Минимальные инструкции для моделей с нативной поддержкой
            thinking_instructions = """\n\nUse your built-in thinking capabilities to reason through this problem step by step before providing your answer."""
            logger.debug(f"Model {model_name} supports native thinking mode")
        else:
            # Расширенная эмуляция для моделей без нативной поддержки
            thinking_instructions = """\n\nIMPORTANT: Use deep reasoning and step-by-step thinking. Before responding, think through:
1. What is the core problem or question?
2. What are the key factors to consider?
3. What are the possible approaches or solutions?
4. What are the pros and cons of each approach?
5. What is the best solution and why?

Show your reasoning process clearly. Think deeply before providing your final answer."""
            logger.debug(f"Model {model_name} does not support native thinking, using emulation")
        
        enhanced_messages = []
        for msg in messages:
            if msg.role == "system":
                # Добавляем thinking инструкции к системному промпту
                enhanced_content = msg.content + thinking_instructions
                enhanced_messages.append(LLMMessage(role=msg.role, content=enhanced_content))
            else:
                enhanced_messages.append(msg)
        
        # Если нет системного сообщения, добавляем его
        if not any(msg.role == "system" for msg in messages):
            enhanced_messages.insert(0, LLMMessage(
                role="system",
                content=f"You are an AI assistant with exceptional reasoning capabilities.{thinking_instructions}"
            ))
        
        return enhanced_messages
    
    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response from Ollama.
        
        Args:
            messages: List of messages
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            thinking_mode: Enable thinking mode
            **kwargs: Additional parameters including:
                - server_url: Override server URL for this request only (thread-safe)
                - task_type: Type of task for smart model selection
        """
        if not self.client:
            raise LLMException("Ollama client not initialized")
        
        # Performance tracking
        tracker = get_performance_tracker()
        start_time = time.time()
        
        # Extract server_url override (thread-safe: uses separate client for request)
        server_url_override = kwargs.pop("server_url", None)
        
        # Check cache
        cache_key = self._get_cache_key(messages, model, temperature, **kwargs)
        cached = await self._get_cached(cache_key)
        if cached:
            return LLMResponse(
                content=cached,
                model=model or self.default_model,
                metadata={"cached": True, "provider": "ollama"}
            )
        
        # Умный выбор модели на основе типа задачи
        task_type = kwargs.pop("task_type", None)  # code, chat, analysis, reasoning
        model_name = self._select_best_model(task_type=task_type, model=model)
        
        # Подготавливаем промпты для thinking mode
        # Используем нативную поддержку если доступна, иначе эмуляцию
        enhanced_messages = self._enhance_prompt_for_thinking(messages, thinking_mode, model_name)
        if thinking_mode:
            supports_native = self._check_thinking_support(model_name)
            mode_type = "native" if supports_native else "emulated"
            logger.debug(f"Using {mode_type} thinking mode for Ollama model {model_name}")
        
        try:
            # Convert messages to Ollama format
            # Ollama uses a single prompt string or messages array
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in enhanced_messages
            ]
            
            request_data = {
                "model": model_name,
                "messages": ollama_messages,
                "options": {
                    "temperature": temperature,
                    **kwargs
                }
            }
            
            # Добавляем нативный thinking mode параметр, если модель поддерживает
            # Ollama API может поддерживать параметр "thinking" для моделей с нативной поддержкой
            if thinking_mode and self._check_thinking_support(model_name):
                # Пробуем добавить нативный thinking параметр
                # Формат может варьироваться в зависимости от версии Ollama API
                thinking_budget = kwargs.get("thinking_budget_tokens", 4096)
                
                # Вариант 1: Параметр на верхнем уровне (если поддерживается)
                if "thinking" not in request_data:
                    request_data["thinking"] = {
                        "enabled": True,
                        "budget_tokens": thinking_budget
                    }
                    logger.debug(f"Added native thinking parameter for {model_name}")
                
                # Вариант 2: Параметр в options (альтернативный формат)
                # Некоторые версии Ollama могут требовать thinking в options
                if "thinking" not in request_data.get("options", {}):
                    request_data.setdefault("options", {})["thinking"] = True
                    request_data["options"]["thinking_budget"] = thinking_budget
            
            if max_tokens:
                request_data["options"]["num_predict"] = max_tokens
            
            # Determine which client to use (thread-safe server override)
            client_to_use = self.client
            temp_client = None
            effective_url = self.base_url
            
            if server_url_override and server_url_override != self.base_url:
                # Create temporary client for this request only (thread-safe)
                effective_url = server_url_override
                temp_client = httpx.AsyncClient(
                    base_url=server_url_override,
                    timeout=self.timeout,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )
                client_to_use = temp_client
                logger.debug(f"Using temporary client for server: {server_url_override}")
            
            logger.debug(f"Making Ollama request to {effective_url}/api/chat for model {model_name}")
            response = await client_to_use.post("/api/chat", json=request_data)
            logger.debug(f"Ollama response received: status={response.status_code}")
            response.raise_for_status()
            
            # Безопасный парсинг JSON с обработкой ошибок
            response_text = response.text
            
            # Инициализируем переменные
            data = None
            content = ""
            
            try:
                # Try standard parsing first
                data = response.json()
            except json.JSONDecodeError as json_error:
                # Ollama returns NDJSON (Newline Delimited JSON) for streaming-like responses
                # Optimized parsing using efficient NDJSON approach
                logger.debug(f"Standard JSON failed, parsing as NDJSON: {json_error}")
                
                data = self._parse_ndjson_response(response_text)
            
            # Извлекаем content с дополнительной проверкой
            if data:
                # Стандартный путь: message.content
                if isinstance(data, dict):
                    if "message" in data and isinstance(data["message"], dict):
                        content = data["message"].get("content", "")
                    elif "content" in data:
                        content = data["content"]
                    else:
                        # Ищем content в любой вложенной структуре
                        for key, value in data.items():
                            if isinstance(value, dict) and "content" in value:
                                content = value["content"]
                                break
                            elif isinstance(value, str) and len(value) > 10 and key != "model":
                                # Используем строковое значение как контент, если оно достаточно длинное
                                content = value
                                break
            
            # Если все еще нет content, используем fallback методы
            if not content or len(content) < 5:
                logger.warning("Could not extract meaningful content from Ollama response, using fallback")
                # Пробуем извлечь любой осмысленный текст из response_text
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # Пропускаем JSON структуру и метаданные
                    if (line and not line.startswith('{') and 
                        '"model"' not in line and 
                        '"done"' not in line and
                        len(line) > 10):
                        content = line
                        break
                
                if not content:
                    # Последняя попытка - используем весь текст, очищенный от JSON
                    cleaned_text = re.sub(r'\{[^}]*\}', '', response_text)
                    cleaned_text = re.sub(r'["{}]', '', cleaned_text).strip()
                    if cleaned_text and len(cleaned_text) > 5:
                        content = cleaned_text
                    else:
                        content = "Ошибка: не удалось извлечь ответ от модели"
                        logger.error(f"Failed to extract content from Ollama response. Raw response: {response_text[:200]}")
            
            # Cache response
            self._set_cached(cache_key, content)
            
            # Формируем usage в правильном формате (словарь, а не число)
            usage_dict = None
            if data and isinstance(data, dict):
                eval_count = data.get("eval_count", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)
                if eval_count or prompt_eval_count:
                    usage_dict = {
                        "prompt_tokens": int(prompt_eval_count) if prompt_eval_count else 0,
                        "completion_tokens": int(eval_count) if eval_count else 0,
                        "total_tokens": int(prompt_eval_count + eval_count) if (prompt_eval_count or eval_count) else 0
                    }
            
            # Извлекаем thinking content из ответа
            thinking_content = None
            supports_native = self._check_thinking_support(model_name)
            
            if thinking_mode:
                # Для моделей с нативной поддержкой thinking mode
                # Ollama может возвращать thinking в отдельном поле ответа
                if data and isinstance(data, dict):
                    # Проверяем наличие thinking в ответе
                    if "thinking" in data:
                        thinking_content = data["thinking"]
                    elif "message" in data and isinstance(data["message"], dict):
                        if "thinking" in data["message"]:
                            thinking_content = data["message"]["thinking"]
                    
                    # Если thinking не найден в структурированном ответе,
                    # пытаемся извлечь из content (для эмуляции или моделей без нативной поддержки)
                    if not thinking_content and content:
                        reasoning_markers = [
                            "Let me think", "Thinking:", "Reasoning:", "Analysis:",
                            "Думаю:", "Рассуждение:", "Анализ:", "<think>", "</think>"
                        ]
                        for marker in reasoning_markers:
                            if marker.lower() in content.lower():
                                # Найдено reasoning в ответе
                                marker_pos = content.lower().find(marker.lower())
                                # Извлекаем thinking блок (до следующего маркера или до конца)
                                end_marker = content.lower().find("</think>", marker_pos)
                                if end_marker > marker_pos:
                                    thinking_content = content[marker_pos:end_marker + 8]
                                else:
                                    # Берем следующий абзац как thinking
                                    next_para = content.find("\n\n", marker_pos)
                                    if next_para > marker_pos:
                                        thinking_content = content[marker_pos:next_para]
                                    else:
                                        thinking_content = content[marker_pos:marker_pos + 500]
                                break
            
            # Record successful request metrics
            duration = time.time() - start_time
            total_tokens = usage_dict.get("total_tokens", 0) if usage_dict else 0
            tracker.record_request(
                provider="ollama",
                model=model_name,
                duration=duration,
                tokens=total_tokens,
                success=True
            )
            
            return LLMResponse(
                content=content,
                model=model_name,
                usage=usage_dict,
                finish_reason=data.get("done_reason") if data and isinstance(data, dict) else None,
                metadata={
                    "provider": "ollama",
                    "done": data.get("done", False) if data and isinstance(data, dict) else False,
                    "thinking_mode": thinking_mode,
                    "thinking_native": supports_native,  # Указываем, используется ли нативный thinking
                    "thinking_emulated": thinking_mode and not supports_native,  # Эмуляция только если не нативный
                    "server_url": effective_url  # Какой сервер использовался
                },
                thinking=thinking_content,
                has_thinking=thinking_content is not None
            )
        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
            # Пробуем fallback сервер при ошибках подключения с exponential backoff
            logger.warning(f"Ollama request failed: {e}. Trying fallback server with exponential backoff...")
            
            # Check retry count and try with backoff
            retry_count = kwargs.get("_retry_count", 0)
            max_retries = 3
            
            if retry_count < max_retries:
                # Calculate exponential backoff delay
                base_delay = 1.0
                delay = min(base_delay * (2 ** retry_count), 30.0)
                
                # Add jitter to prevent thundering herd
                import random
                jitter = delay * 0.2 * (random.random() * 2 - 1)
                delay = max(0.1, delay + jitter)
                
                logger.info(
                    f"Retry attempt {retry_count + 1}/{max_retries} with {delay:.2f}s backoff..."
                )
                
                # Wait before retry
                await asyncio.sleep(delay)
                
                # Try switching to fallback server
                if await self._try_next_server():
                    logger.info(f"Switched to fallback server: {self.base_url}")
                
                try:
                    return await self.generate(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        thinking_mode=thinking_mode,
                        _retry_count=retry_count + 1,
                        **kwargs
                    )
                except Exception as retry_error:
                    logger.error(f"Retry on fallback server also failed: {retry_error}")
            
            # Record failed request
            duration = time.time() - start_time
            tracker.record_request(
                provider="ollama",
                model=model or self.default_model,
                duration=duration,
                tokens=0,
                success=False,
                error_type="HTTPError"
            )
            raise LLMException(f"Ollama API error after {retry_count + 1} attempts: {e}") from e
        except Exception as e:
            # Для других ошибок также пробуем fallback с exponential backoff
            if "connect" in str(e).lower() or "timeout" in str(e).lower():
                logger.warning(f"Connection error: {e}. Trying fallback server with backoff...")
                
                retry_count = kwargs.get("_retry_count", 0)
                max_retries = 3
                
                if retry_count < max_retries:
                    # Calculate exponential backoff delay
                    base_delay = 1.0
                    delay = min(base_delay * (2 ** retry_count), 30.0)
                    
                    # Add jitter
                    import random
                    jitter = delay * 0.2 * (random.random() * 2 - 1)
                    delay = max(0.1, delay + jitter)
                    
                    logger.info(
                        f"Retry attempt {retry_count + 1}/{max_retries} with {delay:.2f}s backoff..."
                    )
                    
                    await asyncio.sleep(delay)
                    
                    if await self._try_next_server():
                        logger.info(f"Switched to fallback server: {self.base_url}")
                    
                    try:
                        return await self.generate(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            thinking_mode=thinking_mode,
                            _retry_count=retry_count + 1,
                            **kwargs
                        )
                    except Exception as retry_error:
                        logger.error(f"Retry on fallback server also failed: {retry_error}")
            
            # Record failed request
            duration = time.time() - start_time
            tracker.record_request(
                provider="ollama",
                model=model or self.default_model,
                duration=duration,
                tokens=0,
                success=False,
                error_type=type(e).__name__
            )
            raise LLMException(f"Ollama error after retries: {e}") from e
        finally:
            # Always close temporary client to prevent resource leaks
            if temp_client is not None:
                try:
                    await temp_client.aclose()
                except Exception as close_error:
                    logger.debug(f"Error closing temporary client: {close_error}")
    
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response from Ollama"""
        if not self.client:
            raise LLMException("Ollama client not initialized")
        
        model_name = model or self.default_model
        
        try:
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            request_data = {
                "model": model_name,
                "messages": ollama_messages,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    **kwargs
                }
            }
            
            if max_tokens:
                request_data["options"]["num_predict"] = max_tokens
            
            async with self.client.stream("POST", "/api/chat", json=request_data) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            # Пробуем парсить как JSON
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            # Если не JSON, пробуем извлечь текст
                            json_match = re.search(r'\{.*"content".*\}', line, re.DOTALL)
                            if json_match:
                                try:
                                    data = json.loads(json_match.group())
                                    if "message" in data and "content" in data["message"]:
                                        yield data["message"]["content"]
                                except (json.JSONDecodeError, KeyError, TypeError):
                                    # Если не получилось, пропускаем строку
                                    continue
                            else:
                                # Если похоже на текст, возвращаем как есть
                                if line.strip() and not line.startswith('{'):
                                    yield line
                                continue
        except httpx.HTTPError as e:
            raise LLMException(f"Ollama streaming error: {e}") from e
        except Exception as e:
            raise LLMException(f"Ollama streaming error: {e}") from e
    
    async def list_models(self) -> List[str]:
        """List available Ollama models"""
        if not self.client:
            return []
        
        if self._available_models:
            return self._available_models
        
        try:
            response = await self.client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                self._available_models = [model["name"] for model in data.get("models", [])]
                return self._available_models
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
        
        # Return recommended models as fallback
        all_recommended = []
        if self.recommended_models:
            for category, models in self.recommended_models.items():
                all_recommended.extend(models)
        return list(set(all_recommended)) if all_recommended else ["llama2"]

