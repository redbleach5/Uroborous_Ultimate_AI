"""
Distributed Model Router - Обнаружение и управление Ollama серверами

УПРОЩЁННАЯ ВЕРСИЯ:
- Только обнаружение серверов и моделей
- Маршрутизация по имени модели
- Логика выбора модели делегирована IntelligentModelRouter

Ключевые возможности:
- Автоматическое обнаружение моделей на всех серверах
- Индексация: какие модели на каких серверах
- Проверка доступности серверов
"""

import asyncio
import time
import httpx
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
from .logger import get_logger

logger = get_logger(__name__)


class ServerPriority(Enum):
    """Приоритет сервера"""
    PRIMARY = 1
    SECONDARY = 2
    FALLBACK = 3


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


@dataclass
class RoutingDecision:
    """Решение о маршрутизации"""
    model: str
    server_url: str
    server_name: str
    reason: str
    alternatives: List[Tuple[str, str]] = field(default_factory=list)
    used_fallback: bool = False


class DistributedModelRouter:
    """
    Упрощённый маршрутизатор - только обнаружение и индексация серверов.
    Логика выбора модели делегирована IntelligentModelRouter.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.servers: Dict[str, OllamaServer] = {}
        self.model_index: Dict[str, List[OllamaServer]] = {}
        
        # Configurable timeouts
        ollama_config = config.get("llm", {}).get("providers", {}).get("ollama", {})
        self._cache_ttl = ollama_config.get("discovery_cache_ttl", 30)  # Кэш на 30 секунд
        self._last_discovery = 0.0
        self._timeout = ollama_config.get("discovery_timeout", 2.0)
        
        # Thread-safe discovery with asyncio.Lock
        self._discovery_lock: Optional[asyncio.Lock] = None
        
        self._initialize_servers_from_config()
    
    def _get_discovery_lock(self) -> asyncio.Lock:
        """Lazy initialization of discovery lock (must be created in event loop)"""
        if self._discovery_lock is None:
            self._discovery_lock = asyncio.Lock()
        return self._discovery_lock
    
    def _initialize_servers_from_config(self):
        """Инициализирует список серверов из конфигурации"""
        ollama_config = self.config.get("llm", {}).get("providers", {}).get("ollama", {})
        
        # Дополнительные серверы из additional_servers
        for server_cfg in ollama_config.get("additional_servers", []):
            url = server_cfg.get("url")
            name = server_cfg.get("name", url)
            priority_str = server_cfg.get("priority", "SECONDARY")
            
            try:
                priority = ServerPriority[priority_str]
            except KeyError:
                priority = ServerPriority.SECONDARY
            
            self._add_server(name, url, priority)
            logger.debug(f"Added server: {name} ({url}) priority={priority.name}")
        
        # base_url как дополнительный сервер
        base_url = ollama_config.get("base_url", "http://localhost:11434")
        if not any(s.url == base_url for s in self.servers.values()):
            self._add_server("localhost", base_url, ServerPriority.SECONDARY)
            logger.debug(f"Added base server: localhost ({base_url})")
        
        logger.info(f"Initialized with {len(self.servers)} Ollama server(s)")
    
    def _add_server(self, name: str, url: str, priority: ServerPriority):
        """Добавляет сервер"""
        self.servers[name] = OllamaServer(
            url=url,
            name=name,
            priority=priority
        )
    
    async def discover_all_servers(self) -> Dict[str, OllamaServer]:
        """
        Обнаруживает все серверы и их модели.
        
        Thread-safe: использует asyncio.Lock для предотвращения race conditions.
        Если discovery уже выполняется в другом coroutine, ждёт его завершения.
        
        Returns:
            Dict[str, OllamaServer]: Словарь всех серверов
        """
        lock = self._get_discovery_lock()
        
        async with lock:
            current_time = time.time()
            
            # Проверяем кэш внутри lock, чтобы избежать повторного discovery
            if current_time - self._last_discovery < self._cache_ttl:
                return self.servers
            
            await self._do_discovery()
            self._last_discovery = current_time
            
        return self.servers
    
    async def _do_discovery(self):
        """Выполняет обнаружение серверов"""
        logger.info("Discovering Ollama servers and models...")
        
        tasks = [self._check_server(server) for server in self.servers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обновляем индекс моделей
        self.model_index.clear()
        for server in self.servers.values():
            if server.is_available:
                for model in server.available_models:
                    if model not in self.model_index:
                        self.model_index[model] = []
                    self.model_index[model].append(server)
        
        # Сортируем серверы по приоритету
        for servers_list in self.model_index.values():
            servers_list.sort(key=lambda s: s.priority.value)
        
        available = sum(1 for s in self.servers.values() if s.is_available)
        logger.info(f"Discovery complete: {available}/{len(self.servers)} servers, {len(self.model_index)} models")
    
    async def _check_server(self, server: OllamaServer):
        """Проверяет доступность сервера"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                start = time.time()
                response = await client.get(f"{server.url}/api/tags")
                elapsed = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    server.available_models = [m["name"] for m in data.get("models", [])]
                    server.is_available = True
                    server.response_time_ms = elapsed
                    server.last_check = time.time()
                    
                    logger.info(f"Server {server.name} ({server.url}): {len(server.available_models)} models, {elapsed:.0f}ms")
                else:
                    server.is_available = False
        except Exception as e:
            server.is_available = False
            logger.debug(f"Server {server.name} unavailable: {e}")
    
    async def find_model(self, model_name: str) -> Optional[RoutingDecision]:
        """
        Находит сервер с указанной моделью.
        Это ПРОСТАЯ функция - только поиск, без логики выбора.
        """
        await self.discover_all_servers()
        
        # Точное совпадение
        servers = self.model_index.get(model_name, [])
        if servers:
            server = servers[0]
            return RoutingDecision(
                model=model_name,
                server_url=server.url,
                server_name=server.name,
                reason=f"Found on {server.name}"
            )
        
        # Частичное совпадение (gemma3 → gemma3:4b)
        base_name = model_name.split(":")[0] if ":" in model_name else model_name
        for indexed_model, indexed_servers in self.model_index.items():
            if indexed_model.startswith(base_name) and indexed_servers:
                server = indexed_servers[0]
                return RoutingDecision(
                    model=indexed_model,
                    server_url=server.url,
                    server_name=server.name,
                    reason=f"Partial match: {model_name} → {indexed_model}"
                )
        
        return None
    
    def get_all_available_models(self) -> List[str]:
        """Возвращает все доступные модели"""
        return list(self.model_index.keys())
    
    def get_available_servers(self) -> List[OllamaServer]:
        """Возвращает доступные серверы"""
        return [s for s in self.servers.values() if s.is_available]
    
    async def get_best_server(self) -> Optional[OllamaServer]:
        """Возвращает лучший доступный сервер (по приоритету и скорости)"""
        await self.discover_all_servers()
        
        available = self.get_available_servers()
        if not available:
            return None
        
        # Сортируем по приоритету, затем по времени отклика
        return min(available, key=lambda s: (s.priority.value, s.response_time_ms))


# Legacy alias for backwards compatibility
async def route_request(*args, **kwargs):
    """
    DEPRECATED: Используйте IntelligentModelRouter.select_model() вместо этого.
    Эта функция оставлена только для совместимости.
    """
    logger.warning("route_request() is deprecated. Use IntelligentModelRouter instead.")
    return None
