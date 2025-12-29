"""
AgentCommunicator - Система межагентной коммуникации

Позволяет агентам:
1. Отправлять сообщения другим агентам
2. Делегировать подзадачи
3. Запрашивать помощь
4. Обмениваться контекстом
5. Координировать работу над сложными задачами
"""

import asyncio
import uuid
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict

from ..core.logger import get_logger

if TYPE_CHECKING:
    from .base import AgentRegistry

logger = get_logger(__name__)


class MessageType(Enum):
    """Типы сообщений между агентами"""
    REQUEST = "request"           # Запрос на выполнение задачи
    RESPONSE = "response"         # Ответ на запрос
    DELEGATION = "delegation"     # Делегирование подзадачи
    HELP_REQUEST = "help_request" # Запрос помощи
    STATUS = "status"             # Статус выполнения
    FEEDBACK = "feedback"         # Обратная связь о результате
    BROADCAST = "broadcast"       # Широковещательное сообщение
    CANCEL = "cancel"             # Отмена задачи


class MessagePriority(Enum):
    """Приоритеты сообщений"""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class AgentMessage:
    """Сообщение между агентами"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""                           # Имя отправителя
    receiver: str = ""                         # Имя получателя ("*" для broadcast)
    message_type: MessageType = MessageType.REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    content: Dict[str, Any] = field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None   # Общий контекст
    parent_message_id: Optional[str] = None    # ID родительского сообщения
    requires_response: bool = True
    timeout: float = 60.0                      # Таймаут ожидания ответа
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь"""
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "content": self.content,
            "context": self.context,
            "parent_message_id": self.parent_message_id,
            "requires_response": self.requires_response,
            "timestamp": self.timestamp
        }


@dataclass 
class DelegationResult:
    """Результат делегирования задачи"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    delegated_to: Optional[str] = None
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "delegated_to": self.delegated_to,
            "execution_time": self.execution_time
        }


class AgentCapability(Enum):
    """Возможности агентов"""
    CODE_GENERATION = "code_generation"
    CODE_REFACTORING = "code_refactoring"
    DATA_ANALYSIS = "data_analysis"
    MACHINE_LEARNING = "machine_learning"
    WEB_SEARCH = "web_search"
    RESEARCH = "research"
    REASONING = "reasoning"
    TOOL_USAGE = "tool_usage"
    WORKFLOW = "workflow"
    API_INTEGRATION = "api_integration"
    MONITORING = "monitoring"
    TESTING = "testing"
    VERIFICATION = "verification"


# Маппинг агентов на их возможности
AGENT_CAPABILITIES: Dict[str, List[AgentCapability]] = {
    "code_writer": [
        AgentCapability.CODE_GENERATION,
        AgentCapability.CODE_REFACTORING
    ],
    "data_analysis": [
        AgentCapability.DATA_ANALYSIS,
        AgentCapability.MACHINE_LEARNING
    ],
    "research": [
        AgentCapability.WEB_SEARCH,
        AgentCapability.RESEARCH
    ],
    "react": [
        AgentCapability.REASONING,
        AgentCapability.TOOL_USAGE
    ],
    "workflow": [
        AgentCapability.WORKFLOW
    ],
    "integration": [
        AgentCapability.API_INTEGRATION
    ],
    "monitoring": [
        AgentCapability.MONITORING
    ]
}


class AgentCommunicator:
    """
    Центральная система коммуникации между агентами.
    
    Использование:
    ```python
    communicator = AgentCommunicator(agent_registry)
    await communicator.initialize()
    
    # Делегирование задачи
    result = await communicator.delegate_subtask(
        from_agent="code_writer",
        to_agent="research",
        subtask="Найди документацию по FastAPI",
        context={"project": "my_api"}
    )
    
    # Запрос помощи по возможности
    helper = await communicator.find_agent_for_capability(
        AgentCapability.DATA_ANALYSIS
    )
    ```
    """
    
    def __init__(self, agent_registry: Optional["AgentRegistry"] = None):
        """
        Инициализация коммуникатора
        
        Args:
            agent_registry: Реестр агентов
        """
        self.agent_registry = agent_registry
        self._initialized = False
        
        # Очередь сообщений
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Ожидающие ответа сообщения
        self._pending_responses: Dict[str, asyncio.Future] = {}
        
        # История сообщений
        self._message_history: List[AgentMessage] = []
        
        # Статистика по агентам
        self._agent_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "messages_sent": 0,
            "messages_received": 0,
            "delegations_made": 0,
            "delegations_received": 0,
            "avg_response_time": 0.0,
            "success_rate": 1.0
        })
        
        # Подписчики на события
        self._event_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Кэш возможностей агентов
        self._capability_cache: Dict[AgentCapability, List[str]] = {}
    
    async def initialize(self) -> None:
        """Инициализация коммуникатора"""
        if self._initialized:
            return
        
        # Строим кэш возможностей
        self._build_capability_cache()
        
        self._initialized = True
        logger.info("AgentCommunicator initialized")
    
    def _build_capability_cache(self) -> None:
        """Строит кэш возможностей агентов"""
        self._capability_cache.clear()
        
        for agent_name, capabilities in AGENT_CAPABILITIES.items():
            for cap in capabilities:
                if cap not in self._capability_cache:
                    self._capability_cache[cap] = []
                self._capability_cache[cap].append(agent_name)
        
        logger.debug(f"Built capability cache: {len(self._capability_cache)} capabilities")
    
    async def send_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """
        Отправляет сообщение агенту
        
        Args:
            message: Сообщение для отправки
            
        Returns:
            Ответ от агента (если requires_response=True)
        """
        if not self._initialized:
            await self.initialize()
        
        logger.debug(
            f"Sending message {message.id[:8]} from {message.sender} "
            f"to {message.receiver} (type: {message.message_type.value})"
        )
        
        # Сохраняем в историю
        self._message_history.append(message)
        
        # Обновляем статистику
        self._agent_stats[message.sender]["messages_sent"] += 1
        self._agent_stats[message.receiver]["messages_received"] += 1
        
        # Уведомляем подписчиков
        await self._notify_subscribers("message_sent", message)
        
        # Если нужен ответ - создаём Future
        if message.requires_response:
            future = asyncio.get_event_loop().create_future()
            self._pending_responses[message.id] = future
            
            try:
                # Обрабатываем сообщение
                response = await self._process_message(message)
                
                # Устанавливаем результат
                if not future.done():
                    future.set_result(response)
                
                return response
                
            except asyncio.TimeoutError:
                logger.warning(f"Message {message.id[:8]} timed out")
                if not future.done():
                    future.set_exception(asyncio.TimeoutError())
                raise
            finally:
                self._pending_responses.pop(message.id, None)
        else:
            # Fire and forget
            asyncio.create_task(self._process_message(message))
            return None
    
    async def _process_message(self, message: AgentMessage) -> Dict[str, Any]:
        """Обрабатывает сообщение"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if message.message_type == MessageType.DELEGATION:
                result = await self._handle_delegation(message)
            elif message.message_type == MessageType.HELP_REQUEST:
                result = await self._handle_help_request(message)
            elif message.message_type == MessageType.REQUEST:
                result = await self._handle_request(message)
            elif message.message_type == MessageType.BROADCAST:
                result = await self._handle_broadcast(message)
            else:
                result = {"success": False, "error": f"Unknown message type: {message.message_type}"}
            
            # Обновляем время ответа
            elapsed = asyncio.get_event_loop().time() - start_time
            self._update_response_time(message.receiver, elapsed)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing message {message.id[:8]}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_delegation(self, message: AgentMessage) -> Dict[str, Any]:
        """Обрабатывает делегирование задачи"""
        if not self.agent_registry:
            return {"success": False, "error": "Agent registry not available"}
        
        target_agent = await self.agent_registry.get_agent(message.receiver)
        if not target_agent:
            return {"success": False, "error": f"Agent {message.receiver} not found"}
        
        subtask = message.content.get("subtask", "")
        context = message.context or {}
        
        # Добавляем информацию о делегировании в контекст
        context["_delegated_from"] = message.sender
        context["_delegation_id"] = message.id
        
        try:
            # Выполняем задачу
            result = await asyncio.wait_for(
                target_agent.execute(subtask, context),
                timeout=message.timeout
            )
            
            # Обновляем статистику
            self._agent_stats[message.sender]["delegations_made"] += 1
            self._agent_stats[message.receiver]["delegations_received"] += 1
            
            return {
                "success": result.get("success", True),
                "result": result,
                "delegated_to": message.receiver
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Delegation to {message.receiver} timed out",
                "delegated_to": message.receiver
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "delegated_to": message.receiver
            }
    
    async def _handle_help_request(self, message: AgentMessage) -> Dict[str, Any]:
        """Обрабатывает запрос помощи"""
        capability_str = message.content.get("capability")
        
        if not capability_str:
            return {"success": False, "error": "No capability specified"}
        
        try:
            capability = AgentCapability(capability_str)
        except ValueError:
            return {"success": False, "error": f"Unknown capability: {capability_str}"}
        
        # Находим агента с нужной возможностью
        helper = await self.find_agent_for_capability(capability, exclude=[message.sender])
        
        if helper:
            return {
                "success": True,
                "helper_agent": helper,
                "capability": capability_str
            }
        else:
            return {
                "success": False,
                "error": f"No agent found with capability: {capability_str}"
            }
    
    async def _handle_request(self, message: AgentMessage) -> Dict[str, Any]:
        """Обрабатывает общий запрос"""
        if not self.agent_registry:
            return {"success": False, "error": "Agent registry not available"}
        
        target_agent = await self.agent_registry.get_agent(message.receiver)
        if not target_agent:
            return {"success": False, "error": f"Agent {message.receiver} not found"}
        
        task = message.content.get("task", "")
        context = message.context or {}
        
        try:
            result = await asyncio.wait_for(
                target_agent.execute(task, context),
                timeout=message.timeout
            )
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_broadcast(self, message: AgentMessage) -> Dict[str, Any]:
        """Обрабатывает широковещательное сообщение"""
        if not self.agent_registry:
            return {"success": False, "error": "Agent registry not available"}
        
        results = {}
        agents = self.agent_registry.list_agents()
        
        for agent_name in agents:
            if agent_name == message.sender:
                continue
            
            try:
                agent = await self.agent_registry.get_agent(agent_name)
                if agent and hasattr(agent, 'on_broadcast'):
                    result = await agent.on_broadcast(message.content)
                    results[agent_name] = result
            except Exception as e:
                results[agent_name] = {"error": str(e)}
        
        return {"success": True, "results": results}
    
    async def delegate_subtask(
        self,
        from_agent: str,
        to_agent: str,
        subtask: str,
        context: Optional[Dict[str, Any]] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        timeout: float = 120.0
    ) -> DelegationResult:
        """
        Делегирует подзадачу другому агенту.
        
        Args:
            from_agent: Имя агента-отправителя
            to_agent: Имя агента-получателя
            subtask: Описание подзадачи
            context: Контекст для передачи
            priority: Приоритет задачи
            timeout: Таймаут выполнения
            
        Returns:
            DelegationResult с результатом
        """
        start_time = asyncio.get_event_loop().time()
        
        message = AgentMessage(
            sender=from_agent,
            receiver=to_agent,
            message_type=MessageType.DELEGATION,
            priority=priority,
            content={"subtask": subtask},
            context=context,
            timeout=timeout
        )
        
        try:
            response = await self.send_message(message)
            elapsed = asyncio.get_event_loop().time() - start_time
            
            return DelegationResult(
                success=response.get("success", False),
                result=response.get("result"),
                error=response.get("error"),
                delegated_to=to_agent,
                execution_time=elapsed
            )
            
        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start_time
            return DelegationResult(
                success=False,
                error=str(e),
                delegated_to=to_agent,
                execution_time=elapsed
            )
    
    async def request_help(
        self,
        from_agent: str,
        capability: AgentCapability,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DelegationResult:
        """
        Запрашивает помощь у агента с определённой возможностью.
        
        Args:
            from_agent: Имя агента-отправителя
            capability: Требуемая возможность
            task: Задача для выполнения
            context: Контекст
            
        Returns:
            DelegationResult с результатом
        """
        # Находим подходящего агента
        helper = await self.find_agent_for_capability(capability, exclude=[from_agent])
        
        if not helper:
            return DelegationResult(
                success=False,
                error=f"No agent with capability {capability.value} found"
            )
        
        # Делегируем задачу
        return await self.delegate_subtask(
            from_agent=from_agent,
            to_agent=helper,
            subtask=task,
            context=context
        )
    
    async def find_agent_for_capability(
        self,
        capability: AgentCapability,
        exclude: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Находит агента с указанной возможностью.
        
        Args:
            capability: Требуемая возможность
            exclude: Список агентов для исключения
            
        Returns:
            Имя агента или None
        """
        exclude = exclude or []
        agents = self._capability_cache.get(capability, [])
        
        for agent_name in agents:
            if agent_name in exclude:
                continue
            
            # Проверяем доступность агента
            if self.agent_registry:
                agent = await self.agent_registry.get_agent(agent_name)
                if agent:
                    return agent_name
        
        return None
    
    async def broadcast_to_all(
        self,
        from_agent: str,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Отправляет широковещательное сообщение всем агентам.
        
        Args:
            from_agent: Имя отправителя
            content: Содержимое сообщения
            
        Returns:
            Словарь с ответами от агентов
        """
        message = AgentMessage(
            sender=from_agent,
            receiver="*",
            message_type=MessageType.BROADCAST,
            content=content,
            requires_response=True
        )
        
        return await self.send_message(message)
    
    def _update_response_time(self, agent_name: str, elapsed: float) -> None:
        """Обновляет среднее время ответа агента"""
        stats = self._agent_stats[agent_name]
        current_avg = stats.get("avg_response_time", 0.0)
        total = stats["messages_received"]
        
        if total > 0:
            # Скользящее среднее
            stats["avg_response_time"] = (current_avg * (total - 1) + elapsed) / total
    
    async def _notify_subscribers(self, event: str, data: Any) -> None:
        """Уведомляет подписчиков о событии"""
        for callback in self._event_subscribers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.warning(f"Subscriber error for event {event}: {e}")
    
    def subscribe(self, event: str, callback: Callable) -> None:
        """
        Подписывается на событие.
        
        Events:
        - message_sent: При отправке сообщения
        - delegation_complete: При завершении делегирования
        """
        self._event_subscribers[event].append(callback)
    
    def unsubscribe(self, event: str, callback: Callable) -> None:
        """Отписывается от события"""
        if callback in self._event_subscribers.get(event, []):
            self._event_subscribers[event].remove(callback)
    
    def get_agent_stats(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """Возвращает статистику агентов"""
        if agent_name:
            return dict(self._agent_stats.get(agent_name, {}))
        return {name: dict(stats) for name, stats in self._agent_stats.items()}
    
    def get_message_history(
        self,
        limit: int = 100,
        agent_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Возвращает историю сообщений"""
        history = self._message_history[-limit:]
        
        if agent_filter:
            history = [
                m for m in history
                if m.sender == agent_filter or m.receiver == agent_filter
            ]
        
        return [m.to_dict() for m in history]
    
    async def shutdown(self) -> None:
        """Завершение работы коммуникатора"""
        # Отменяем ожидающие ответы
        for msg_id, future in self._pending_responses.items():
            if not future.done():
                future.cancel()
        
        self._pending_responses.clear()
        self._initialized = False
        logger.info("AgentCommunicator shutdown complete")


# Глобальный экземпляр коммуникатора (будет инициализирован при старте)
_global_communicator: Optional[AgentCommunicator] = None


def get_communicator() -> Optional[AgentCommunicator]:
    """Возвращает глобальный экземпляр коммуникатора"""
    return _global_communicator


def set_communicator(communicator: AgentCommunicator) -> None:
    """Устанавливает глобальный экземпляр коммуникатора"""
    global _global_communicator
    _global_communicator = communicator

