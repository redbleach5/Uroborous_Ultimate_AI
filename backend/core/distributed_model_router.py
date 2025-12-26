"""
Distributed Model Router - Маршрутизация моделей между несколькими Ollama серверами

Ключевые возможности:
- Автоматическое обнаружение моделей на всех сконфигурированных серверах
- Интеллектуальная маршрутизация: запрос идёт на сервер, где есть нужная модель
- Fallback: если сервер недоступен, пробуем другой с альтернативной моделью
- Балансировка нагрузки: распределение запросов при наличии модели на нескольких серверах
"""

import asyncio
import time
import httpx
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from .logger import get_logger

logger = get_logger(__name__)


class ServerPriority(Enum):
    """Приоритет сервера"""
    PRIMARY = 1      # Основной (обычно мощный удалённый)
    SECONDARY = 2    # Вторичный (например, localhost)
    FALLBACK = 3     # Резервный


@dataclass
class OllamaServer:
    """Информация об Ollama сервере"""
    url: str
    name: str
    priority: ServerPriority = ServerPriority.PRIMARY
    available_models: List[str] = field(default_factory=list)
    is_available: bool = False
    last_check: float = 0.0
    response_time_ms: float = 0.0
    gpu_memory_gb: Optional[float] = None
    gpu_count: int = 0


@dataclass
class ModelLocation:
    """Где найдена модель"""
    model: str
    server: OllamaServer
    is_running: bool = False  # Уже загружена в память?
    estimated_load_time_sec: float = 0.0


@dataclass
class RoutingDecision:
    """Решение о маршрутизации"""
    model: str
    server_url: str
    server_name: str
    reason: str
    alternatives: List[Tuple[str, str]] = field(default_factory=list)  # [(model, server_url), ...]
    used_fallback: bool = False


class DistributedModelRouter:
    """
    Маршрутизатор для распределения запросов между несколькими Ollama серверами
    
    Пример использования:
        router = DistributedModelRouter(config)
        await router.discover_all_servers()
        
        # Найти сервер с нужной моделью
        decision = await router.route_request(
            preferred_model="gemma3:12b",
            task_type="chat",
            complexity="simple"
        )
        
        # Использовать decision.server_url и decision.model
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.servers: Dict[str, OllamaServer] = {}
        self.model_index: Dict[str, List[OllamaServer]] = {}  # model -> [servers]
        
        # Конфигурация - оптимизирована для быстрого отклика
        self._cache_ttl = 300  # Кэш на 5 минут (реже проверяем серверы)
        self._last_discovery = 0.0
        self._timeout = 2.0  # Быстрый таймаут (2 сек вместо 5)
        self._discovery_in_progress = False  # Флаг для неблокирующего discovery
        
        # Модели по категориям для fallback
        # Категории моделей с приоритетом (первые = лучше)
        # ВАЖНО: для CPU-only систем приоритет у маленьких моделей!
        self.model_categories = {
            "fast": [
                "gemma3:1b", "qwen2.5-coder:1.5b", "qwen2.5:1.5b",
                "llama3.2:1b", "phi3:3b"
            ],
            "chat": [
                "gemma3:1b", "gemma3:4b", "llama3.2:3b",  # Маленькие первые!
                "gemma3:12b", "qwen2.5:14b", "llama3.1:8b"
            ],
            "code": [
                # Для CPU: маленькие кодовые модели ПЕРВЫЕ
                "qwen2.5-coder:1.5b", "stable-code:latest", "stable-code",
                "qwen2.5-coder:7b", "deepseek-coder:6.7b", "deepseek-coder",
                "codellama:7b", "codellama",
                "qwen2.5-coder:14b", "deepseek-coder-v2:16b"  # Большие последние
            ],
            "reasoning": [
                "gemma3:1b", "gemma3:4b",  # Маленькие для CPU
                "qwen3:8b", "qwen3:14b", "deepseek-r1:14b", "llama3.3:70b"
            ],
            "analysis": [
                "gemma3:1b", "gemma3:4b",  # Маленькие для CPU
                "gemma3:12b", "qwen2.5:14b", "llama3.1:8b"
            ]
        }
        
        self._initialize_servers_from_config()
    
    def _initialize_servers_from_config(self):
        """Инициализирует список серверов из конфигурации
        
        Порядок приоритетов:
        1. additional_servers с явным priority (PRIMARY для мощного GPU сервера)
        2. base_url как SECONDARY (безопасный fallback)
        3. fallback_urls как FALLBACK
        """
        ollama_config = self.config.get("llm", {}).get("providers", {}).get("ollama", {})
        
        # СНАЧАЛА добавляем additional_servers с явными приоритетами
        # Это позволяет мощному GPU серверу быть PRIMARY
        additional_servers = ollama_config.get("additional_servers", [])
        for server_config in additional_servers:
            url = server_config.get("url")
            name = server_config.get("name", url)
            priority_str = server_config.get("priority", "SECONDARY").upper()
            priority = ServerPriority[priority_str]
            if url:
                self._add_server(url, name, priority)
                logger.debug(f"Added additional server: {name} ({url}) priority={priority_str}")
        
        # ЗАТЕМ добавляем base_url как SECONDARY (fallback по умолчанию)
        primary_url = ollama_config.get("base_url", "http://localhost:11434")
        if primary_url not in self.servers:
            self._add_server(primary_url, "base", ServerPriority.SECONDARY)
        
        # Добавляем localhost если он отличается от primary и ещё не добавлен
        localhost_url = "http://localhost:11434"
        if localhost_url not in self.servers:
            if "localhost" not in primary_url and "127.0.0.1" not in primary_url:
                self._add_server(localhost_url, "localhost_fallback", ServerPriority.FALLBACK)
        
        # Добавляем fallback URLs
        fallback_urls = ollama_config.get("fallback_urls", [])
        for i, url in enumerate(fallback_urls):
            if not url.startswith("http"):
                url = f"http://{url}"
            if url not in self.servers:
                self._add_server(url, f"fallback_{i+1}", ServerPriority.FALLBACK)
        
        logger.info(f"Initialized with {len(self.servers)} Ollama server(s)")
    
    def _add_server(self, url: str, name: str, priority: ServerPriority):
        """Добавляет сервер в реестр"""
        url = url.rstrip("/")
        if url not in self.servers:
            self.servers[url] = OllamaServer(
                url=url,
                name=name,
                priority=priority
            )
            logger.debug(f"Added server: {name} ({url}) with priority {priority.name}")
    
    async def discover_all_servers(self, force: bool = False) -> Dict[str, OllamaServer]:
        """
        Обнаруживает все доступные серверы и их модели
        
        ОПТИМИЗАЦИЯ: Не блокирует запросы если есть кэш
        
        Args:
            force: Принудительно обновить кэш
            
        Returns:
            Dict со всеми серверами и их статусами
        """
        current_time = time.time()
        cache_expired = current_time - self._last_discovery >= self._cache_ttl
        
        # Если кэш валидный — сразу возвращаем
        if not force and not cache_expired:
            return self.servers
        
        # Если уже идёт discovery — не запускаем второй
        if self._discovery_in_progress:
            return self.servers
        
        # Если есть хоть какие-то данные и кэш просто истёк — используем старые данные
        # и запускаем обновление в фоне
        has_any_data = any(s.is_available for s in self.servers.values())
        
        if has_any_data and cache_expired and not force:
            # Запускаем обновление в фоне, не блокируя
            asyncio.create_task(self._background_discovery())
            return self.servers
        
        # Первый запуск или force — делаем синхронно но быстро
        await self._do_discovery()
        return self.servers
    
    async def _background_discovery(self):
        """Фоновое обновление серверов"""
        try:
            self._discovery_in_progress = True
            await self._do_discovery()
        finally:
            self._discovery_in_progress = False
    
    async def _do_discovery(self):
        """Выполняет discovery с таймаутом"""
        logger.info("Discovering Ollama servers and models...")
        
        try:
            # Параллельно проверяем все серверы с общим таймаутом
            tasks = [self._check_server(url) for url in self.servers.keys()]
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=6.0  # Максимум 6 секунд на всё discovery
            )
        except asyncio.TimeoutError:
            logger.warning("Discovery timed out, using partial results")
        
        # Перестраиваем индекс моделей
        self._rebuild_model_index()
        self._last_discovery = time.time()
        
        # Логируем результаты
        available_count = sum(1 for s in self.servers.values() if s.is_available)
        total_models = len(self.model_index)
        logger.info(f"Discovery complete: {available_count}/{len(self.servers)} servers available, {total_models} unique models")
    
    async def _check_server(self, url: str) -> bool:
        """Проверяет доступность сервера и получает его модели"""
        server = self.servers.get(url)
        if not server:
            return False
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Получаем список моделей
                response = await client.get(f"{url}/api/tags")
                response.raise_for_status()
                
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                
                # Обновляем информацию о сервере
                server.available_models = models
                server.is_available = True
                server.response_time_ms = (time.time() - start_time) * 1000
                server.last_check = time.time()
                
                logger.info(f"Server {server.name} ({url}): {len(models)} models, {server.response_time_ms:.0f}ms")
                
                # Попробуем получить информацию о запущенных моделях
                try:
                    ps_response = await client.get(f"{url}/api/ps")
                    if ps_response.status_code == 200:
                        ps_data = ps_response.json()
                        running = [m["name"] for m in ps_data.get("models", [])]
                        logger.debug(f"Server {server.name}: running models: {running}")
                except:
                    pass
                
                return True
                
        except Exception as e:
            server.is_available = False
            server.last_check = time.time()
            logger.warning(f"Server {server.name} ({url}) unavailable: {e}")
            return False
    
    def _rebuild_model_index(self):
        """Перестраивает индекс: модель -> серверы где она есть"""
        self.model_index.clear()
        
        for server in self.servers.values():
            if server.is_available:
                for model in server.available_models:
                    if model not in self.model_index:
                        self.model_index[model] = []
                    self.model_index[model].append(server)
        
        # Сортируем серверы по приоритету для каждой модели
        for model in self.model_index:
            self.model_index[model].sort(key=lambda s: s.priority.value)
    
    async def route_request(
        self,
        preferred_model: Optional[str] = None,
        task_type: str = "chat",
        complexity: str = "simple",
        require_fast: bool = False
    ) -> RoutingDecision:
        """
        Определяет на какой сервер отправить запрос
        
        Args:
            preferred_model: Предпочитаемая модель
            task_type: Тип задачи (chat, code, reasoning, analysis)
            complexity: Сложность (trivial, simple, moderate, complex)
            require_fast: Требуется быстрый ответ (использовать маленькие модели)
            
        Returns:
            RoutingDecision с информацией о сервере и модели
        """
        # Обновляем информацию о серверах если нужно
        await self.discover_all_servers()
        
        # Нет доступных серверов
        available_servers = [s for s in self.servers.values() if s.is_available]
        if not available_servers:
            logger.error("No Ollama servers available!")
            raise ConnectionError("No Ollama servers available")
        
        # Определяем категорию моделей на основе сложности
        if require_fast or complexity in ["trivial", "simple"]:
            model_category = "fast"
        else:
            model_category = task_type if task_type in self.model_categories else "chat"
        
        # Ищем нужную модель
        candidates = self._get_model_candidates(preferred_model, model_category)
        
        # Пробуем найти модель на доступных серверах (с частичным совпадением)
        for model in candidates:
            # Точное совпадение
            servers = self.model_index.get(model, [])
            
            # Частичное совпадение если точного нет
            if not servers:
                base_name = model.split(":")[0] if ":" in model else model
                for indexed_model, indexed_servers in self.model_index.items():
                    if indexed_model.startswith(base_name) and indexed_servers:
                        servers = indexed_servers
                        model = indexed_model  # Используем найденную модель
                        logger.debug(f"Partial match: {base_name} -> {indexed_model}")
                        break
            
            if servers:
                # Берём первый доступный сервер (уже отсортирован по приоритету)
                server = servers[0]
                
                # Собираем альтернативы
                alternatives = []
                for alt_model in candidates[1:]:
                    alt_servers = self.model_index.get(alt_model, [])
                    if alt_servers:
                        alternatives.append((alt_model, alt_servers[0].url))
                
                return RoutingDecision(
                    model=model,
                    server_url=server.url,
                    server_name=server.name,
                    reason=f"Model {model} found on {server.name}",
                    alternatives=alternatives[:3],
                    used_fallback=model != preferred_model and preferred_model is not None
                )
        
        # Fallback: берём любую модель на самом приоритетном доступном сервере
        best_server = min(available_servers, key=lambda s: s.priority.value)
        if best_server.available_models:
            # Выбираем модель по категории
            for cat_model in self.model_categories.get(model_category, []):
                if cat_model in best_server.available_models:
                    return RoutingDecision(
                        model=cat_model,
                        server_url=best_server.url,
                        server_name=best_server.name,
                        reason=f"Fallback: using {cat_model} on {best_server.name}",
                        used_fallback=True
                    )
            
            # Берём первую доступную модель
            fallback_model = best_server.available_models[0]
            return RoutingDecision(
                model=fallback_model,
                server_url=best_server.url,
                server_name=best_server.name,
                reason=f"Fallback: using first available model {fallback_model} on {best_server.name}",
                used_fallback=True
            )
        
        raise ValueError(f"No suitable model found for task_type={task_type}, complexity={complexity}")
    
    def _get_model_candidates(
        self,
        preferred_model: Optional[str],
        category: str
    ) -> List[str]:
        """Возвращает список кандидатов моделей в порядке приоритета"""
        candidates = []
        
        # Сначала preferred_model
        if preferred_model:
            candidates.append(preferred_model)
            # Добавляем варианты с/без тега
            if ":" in preferred_model:
                base_name = preferred_model.split(":")[0]
                candidates.append(base_name)
            else:
                candidates.append(f"{preferred_model}:latest")
        
        # Затем модели из категории
        category_models = self.model_categories.get(category, [])
        for model in category_models:
            if model not in candidates:
                candidates.append(model)
        
        # Добавляем общие fallback модели
        for fallback in ["gemma3:4b", "llama3.1:8b", "qwen2.5:7b"]:
            if fallback not in candidates:
                candidates.append(fallback)
        
        return candidates
    
    def get_model_location(self, model: str) -> Optional[List[OllamaServer]]:
        """Возвращает серверы где есть указанная модель"""
        return self.model_index.get(model)
    
    def get_all_available_models(self) -> Dict[str, List[str]]:
        """Возвращает все доступные модели с указанием серверов"""
        result = {}
        for model, servers in self.model_index.items():
            result[model] = [s.name for s in servers]
        return result
    
    async def get_best_server_for_task(
        self,
        task_type: str = "chat"
    ) -> Optional[OllamaServer]:
        """
        Возвращает лучший сервер для типа задачи
        
        Учитывает:
        - Доступность сервера
        - Наличие подходящих моделей
        - Время отклика
        - Приоритет
        """
        await self.discover_all_servers()
        
        category_models = set(self.model_categories.get(task_type, []))
        
        best_server = None
        best_score = -1
        
        for server in self.servers.values():
            if not server.is_available:
                continue
            
            # Считаем score
            matching_models = len(set(server.available_models) & category_models)
            priority_score = 10 - server.priority.value
            speed_score = max(0, 10 - server.response_time_ms / 100)  # Меньше = лучше
            
            score = matching_models * 5 + priority_score * 3 + speed_score
            
            if score > best_score:
                best_score = score
                best_server = server
        
        return best_server

