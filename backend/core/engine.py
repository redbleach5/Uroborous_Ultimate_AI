"""
Core Engine (IDAEngine) - Central coordinator for all components
"""

import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..config import get_config, Config
from .logger import get_logger

# Инициализируем логгер для этого модуля
logger = get_logger(__name__)
from .exceptions import AILLMException, ConfigurationException
from ..llm.providers import LLMProviderManager
from ..rag.vector_store import VectorStore
from ..rag.context_manager import ContextManager
from ..agents.base import AgentRegistry
from ..orchestrator import Orchestrator
from ..tools.registry import ToolRegistry
from ..safety.guard import SafetyGuard
from ..memory.long_term import LongTermMemory
from .metrics import metrics_collector
from .batch_processor import BatchProcessor
from .intelligent_monitor import get_monitor, initialize_monitor, IssueSeverity
from .pydantic_utils import pydantic_to_dict


class IDAEngine:
    """
    Intelligent Development Assistant Engine
    
    Central coordinator for all AILLM components.
    Manages lifecycle, integration, and error handling.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize IDAEngine
        
        Args:
            config: Configuration object. If None, loads from default location.
        """
        self.config = config or get_config()
        self._initialized = False
        
        # Core components
        self.llm_manager: Optional[LLMProviderManager] = None
        self.vector_store: Optional[VectorStore] = None
        self.context_manager: Optional[ContextManager] = None
        self.agent_registry: Optional[AgentRegistry] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.safety_guard: Optional[SafetyGuard] = None
        self.memory: Optional[LongTermMemory] = None
        self.batch_processor: Optional[BatchProcessor] = None
        
        # Initialize intelligent monitor
        # Всегда используем корневую директорию LOGS_DEBUG
        base_dir = Path(__file__).parent.parent.parent  # Корень проекта
        debug_logs_dir = str(base_dir / "LOGS_DEBUG")
        
        self.monitor = initialize_monitor(
            debug_logs_dir=debug_logs_dir,
            enabled=True
        )
        
        # Task for periodic status updates
        self._status_update_task: Optional[asyncio.Task] = None
        
        logger.info("IDAEngine initialized")
    
    async def initialize(self) -> None:
        """
        Initialize all components
        
        Raises:
            ConfigurationException: If configuration is invalid
            AILLMException: If initialization fails
        """
        if self._initialized:
            logger.warning("Engine already initialized")
            return
        
        try:
            logger.info("Initializing IDAEngine components...")
            
            # Initialize LLM Provider Manager
            if self.config.llm:
                logger.info("Initializing LLM Provider Manager...")
                
                self.llm_manager = LLMProviderManager(self.config.llm)
                await self.llm_manager.initialize()
            
            # Initialize Vector Store
            if self.config.rag and self.config.rag.enabled:
                logger.info("Initializing Vector Store...")
                self.vector_store = VectorStore(self.config.rag)
                await self.vector_store.initialize()
            
            # Initialize Context Manager
            if self.config.context:
                logger.info("Initializing Context Manager...")
                self.context_manager = ContextManager(
                    self.config.context,
                    self.vector_store,
                    self.llm_manager
                )
                await self.context_manager.initialize()
            
            # Initialize Safety Guard
            if self.config.tools and self.config.tools.safety:
                logger.info("Initializing Safety Guard...")
                # Convert Pydantic model to dict if needed
                safety_config = pydantic_to_dict(self.config.tools.safety)
                self.safety_guard = SafetyGuard(safety_config)
            
            # Initialize Tool Registry
            if self.config.tools and self.config.tools.enabled:
                logger.info("Initializing Tool Registry...")
                self.tool_registry = ToolRegistry(
                    self.config.tools,
                    self.safety_guard
                )
                await self.tool_registry.initialize()
            
            # Initialize Batch Processor
            logger.info("Initializing Batch Processor...")
            self.batch_processor = BatchProcessor(max_concurrent=5)
            
            # Initialize Long Term Memory
            if self.config.memory and self.config.memory.enabled:
                logger.info("Initializing Long Term Memory...")
                # Pass vector_store to reuse embeddings model and avoid loading twice
                self.memory = LongTermMemory(self.config.memory, vector_store=self.vector_store)
                await self.memory.initialize()
            
            # Initialize Agent Registry
            logger.info("Initializing Agent Registry...")
            
            self.agent_registry = AgentRegistry(
                self.config.agents,
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await self.agent_registry.initialize()
            
            # Initialize Orchestrator
            if self.config.orchestrator and self.config.orchestrator.enabled:
                logger.info("Initializing Orchestrator...")
                self.orchestrator = Orchestrator(
                    self.config.orchestrator,
                    self.agent_registry,
                    self.llm_manager,
                    self.memory
                )
                await self.orchestrator.initialize()
            
            # Register components with monitor
            self.monitor.register_component("engine", "healthy")
            if self.llm_manager:
                self.monitor.register_component("llm_manager", "healthy")
            if self.vector_store:
                self.monitor.register_component("vector_store", "healthy")
            if self.context_manager:
                self.monitor.register_component("context_manager", "healthy")
            if self.agent_registry:
                self.monitor.register_component("agent_registry", "healthy")
            if self.orchestrator:
                self.monitor.register_component("orchestrator", "healthy")
            if self.tool_registry:
                self.monitor.register_component("tool_registry", "healthy")
            if self.memory:
                self.monitor.register_component("memory", "healthy")
            
            # Start intelligent monitoring
            await self.monitor.start_monitoring(interval=5.0)
            
            # Start periodic component status updates
            self._status_update_task = asyncio.create_task(self._periodic_status_update())
            
            self._initialized = True
            logger.info("IDAEngine initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize IDAEngine: {e}")
            if self.monitor:
                self.monitor.log_exception("engine", e, severity=IssueSeverity.CRITICAL)
            raise AILLMException(f"Initialization failed: {e}") from e
    
    async def update_configuration(self, new_config: Config) -> Dict[str, Any]:
        """
        Dynamically update configuration without full restart
        
        Args:
            new_config: New configuration object
            
        Returns:
            Dict with applied changes and warnings
        """
        if not self._initialized:
            raise AILLMException("Engine must be initialized before updating configuration")
        
        applied_changes = []
        warnings = []
        
        try:
            # Update LLM configuration
            if new_config.llm and self.llm_manager:
                old_provider = self.config.llm.default_provider
                self.config.llm = new_config.llm
                
                # Update default provider if changed
                if new_config.llm.default_provider != old_provider:
                    applied_changes.append(f"Default LLM provider changed to {new_config.llm.default_provider}")
                
                # Reinitialize LLM manager with new config
                await self.llm_manager.shutdown()
                new_llm_manager = LLMProviderManager(self.config.llm)
                await new_llm_manager.initialize()
                self.llm_manager = new_llm_manager
                
                # Обновляем ссылки на llm_manager во всех зависимых компонентах
                if self.context_manager and hasattr(self.context_manager, 'llm_manager'):
                    self.context_manager.llm_manager = self.llm_manager
                
                if self.orchestrator and hasattr(self.orchestrator, 'llm_manager'):
                    self.orchestrator.llm_manager = self.llm_manager
                    # Пересоздаем компоненты orchestrator, которые используют llm_manager
                    from ..core.task_router import TaskRouter
                    from ..core.smart_model_selector import SmartModelSelector
                    from ..core.resource_aware_selector import ResourceAwareSelector
                    from ..core.llm_classifier import LLMClassifier
                    config_dict = pydantic_to_dict(self.config.orchestrator)
                    self.orchestrator.llm_classifier = LLMClassifier(self.llm_manager) if self.llm_manager else None
                    self.orchestrator.task_router = TaskRouter(self.llm_manager, config_dict) if self.llm_manager else None
                    self.orchestrator.model_selector = SmartModelSelector(self.llm_manager, config_dict) if self.llm_manager else None
                    self.orchestrator.resource_aware_selector = ResourceAwareSelector(self.llm_manager, config_dict) if self.llm_manager else None
                
                # Обновляем ссылки в агентах
                if self.agent_registry and hasattr(self.agent_registry, 'agents'):
                    for agent in self.agent_registry.agents.values():
                        if hasattr(agent, 'llm_manager'):
                            agent.llm_manager = self.llm_manager
                
                applied_changes.append("LLM Provider Manager reconfigured")
            
            # Update Tools configuration
            if new_config.tools and self.tool_registry:
                self.config.tools = new_config.tools
                
                # Update safety guard if config changed
                if new_config.tools.safety:
                    safety_config = pydantic_to_dict(new_config.tools.safety)
                    self.safety_guard = SafetyGuard(safety_config)
                    applied_changes.append("Safety Guard reconfigured")
                
                # Tool registry can be updated without full reinit for simple config changes
                # Full reinit only needed if tools structure changed significantly
                if hasattr(self.tool_registry, 'update_config'):
                    await self.tool_registry.update_config(new_config.tools)
                    applied_changes.append("Tool Registry reconfigured")
                else:
                    warnings.append("Tool Registry configuration update may require full restart")
            
            # Update Memory configuration
            if new_config.memory and self.memory:
                # Memory config changes like max_memories, similarity_threshold can be applied dynamically
                self.config.memory = new_config.memory
                if hasattr(self.memory, 'update_config'):
                    await self.memory.update_config(new_config.memory)
                    applied_changes.append("Long Term Memory reconfigured")
                else:
                    warnings.append("Memory configuration update may require restart")
            
            # Update Agents configuration
            if new_config.agents and self.agent_registry:
                self.config.agents = new_config.agents
                if hasattr(self.agent_registry, 'update_config'):
                    await self.agent_registry.update_config(new_config.agents)
                    applied_changes.append("Agent Registry reconfigured")
                else:
                    warnings.append("Agent Registry configuration update requires restart")
            
            # Update Orchestrator configuration
            if new_config.orchestrator and self.orchestrator:
                self.config.orchestrator = new_config.orchestrator
                if hasattr(self.orchestrator, 'update_config'):
                    await self.orchestrator.update_config(new_config.orchestrator)
                    applied_changes.append("Orchestrator reconfigured")
                else:
                    warnings.append("Orchestrator configuration update requires restart")
            
            # Update other configs (logging, performance, etc.)
            if hasattr(new_config, 'logging') and new_config.logging:
                self.config.logging = new_config.logging
                # Динамически применяем настройки логирования
                from ..core.pydantic_utils import pydantic_to_dict
                from ..core.logger import configure_logging
                logging_config = pydantic_to_dict(new_config.logging)
                configure_logging(logging_config)
                applied_changes.append("Logging configuration updated and applied")
            
            if hasattr(new_config, 'performance'):
                self.config.performance = new_config.performance
                applied_changes.append("Performance configuration updated")
            
            logger.info(f"Configuration updated successfully. Applied: {len(applied_changes)} changes")
            
            return {
                "success": True,
                "applied_changes": applied_changes,
                "warnings": warnings,
                "message": f"Configuration updated. {len(applied_changes)} changes applied."
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Failed to update configuration: {e}\n{error_details}")
            if self.monitor:
                self.monitor.log_exception("engine", e, severity=IssueSeverity.ERROR)
            raise AILLMException(f"Configuration update failed: {e}") from e
    
    async def shutdown(self) -> None:
        """Shutdown all components gracefully"""
        logger.info("Shutting down IDAEngine...")
        
        # Stop periodic status updates
        if self._status_update_task and not self._status_update_task.done():
            self._status_update_task.cancel()
            try:
                await self._status_update_task
            except asyncio.CancelledError:
                pass
        
        # Stop monitoring first
        if self.monitor:
            await self.monitor.stop_monitoring()
        
        if self.orchestrator:
            await self.orchestrator.shutdown()
        
        if self.agent_registry:
            await self.agent_registry.shutdown()
        
        if self.memory:
            await self.memory.shutdown()
        
        if self.tool_registry:
            await self.tool_registry.shutdown()
        
        if self.context_manager:
            await self.context_manager.shutdown()
        
        if self.vector_store:
            await self.vector_store.shutdown()
        
        if self.llm_manager:
            await self.llm_manager.shutdown()
        
        self._initialized = False
        logger.info("IDAEngine shutdown complete")
    
    async def execute_task(
        self,
        task: str,
        agent_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        track_metrics: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a task using the orchestrator or a specific agent
        
        Args:
            task: Task description
            agent_type: Type of agent to use. If None, orchestrator decides.
            context: Additional context for the task
            
        Returns:
            Result dictionary with task execution details
        """
        if not self._initialized:
            await self.initialize()
        
        import time
        start_time = time.time()
        
        try:
            logger.debug(
                "Executing task",
                extra={
                    "task": task[:100],
                    "agent_type": agent_type,
                    "has_orchestrator": self.orchestrator is not None,
                    "has_agent_registry": self.agent_registry is not None
                }
            )
            
            if self.orchestrator:
                result = await self.orchestrator.execute_task(task, agent_type, context)
            elif agent_type and self.agent_registry:
                agent = await self.agent_registry.get_agent(agent_type)
                if agent:
                    result = await agent.execute(task, context or {})
                else:
                    raise AILLMException(f"Agent {agent_type} not found")
            else:
                raise AILLMException("No orchestrator or agent available")
            
            logger.debug(
                "Task execution completed",
                extra={
                    "result_success": result.get("success") if isinstance(result, dict) else None,
                    "result_error": result.get("error") if isinstance(result, dict) else None,
                    "result_keys": list(result.keys()) if isinstance(result, dict) else [],
                    "result_type": type(result).__name__
                }
            )
            
            # Track metrics
            duration = time.time() - start_time
            if track_metrics:
                metrics_collector.record_task_execution(
                    task=task,
                    agent_type=agent_type,
                    duration=duration,
                    success=result.get("success", True)
                )
            
            # Monitor performance
            if self.monitor:
                self.monitor.log_performance_metric("engine", "task_execution_duration_ms", duration * 1000)
                if not result.get("success", True):
                    self.monitor.log_exception(
                        "engine",
                        Exception(result.get("error", "Task execution failed")),
                        context={"task": task, "agent_type": agent_type},
                        severity=IssueSeverity.ERROR
                    )
            
            return result
        except Exception as e:
            # Track error in metrics
            duration = time.time() - start_time
            if track_metrics:
                duration = time.time() - start_time
                metrics_collector.record_task_execution(
                    task=task,
                    agent_type=agent_type,
                    duration=duration,
                    success=False
                )
            raise
    
    async def _periodic_status_update(self):
        """Периодическое обновление статусов компонентов в мониторинге"""
        while self._initialized:
            try:
                # Обновляем статусы всех компонентов каждые 30 секунд
                await asyncio.sleep(30)
                
                if not self._initialized:
                    break
                
                # Определяем статус каждого компонента
                status = "healthy"
                
                # Обновляем статус engine
                self.monitor.update_component_status("engine", status, {
                    "initialized": self._initialized,
                    "components_count": sum([
                        self.llm_manager is not None,
                        self.vector_store is not None,
                        self.context_manager is not None,
                        self.agent_registry is not None,
                        self.orchestrator is not None,
                        self.tool_registry is not None,
                        self.memory is not None,
                    ])
                })
                
                # Обновляем статусы других компонентов
                if self.llm_manager:
                    self.monitor.update_component_status("llm_manager", status, {
                        "providers_count": len(self.llm_manager.providers) if hasattr(self.llm_manager, 'providers') else 0
                    })
                
                if self.vector_store:
                    self.monitor.update_component_status("vector_store", status)
                
                if self.context_manager:
                    self.monitor.update_component_status("context_manager", status)
                
                if self.agent_registry:
                    agents_count = len(self.agent_registry.agents) if hasattr(self.agent_registry, 'agents') else 0
                    self.monitor.update_component_status("agent_registry", status, {
                        "agents_count": agents_count
                    })
                
                if self.orchestrator:
                    self.monitor.update_component_status("orchestrator", status)
                
                if self.tool_registry:
                    tools_count = len(self.tool_registry.tools) if hasattr(self.tool_registry, 'tools') else 0
                    self.monitor.update_component_status("tool_registry", status, {
                        "tools_count": tools_count
                    })
                
                if self.memory:
                    self.monitor.update_component_status("memory", status)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic status update: {e}", exc_info=True)
                await asyncio.sleep(30)  # Продолжаем даже при ошибке
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the engine
        
        Returns:
            Status dictionary
        """
        return {
            "status": "ok" if self._initialized else "не_инициализирован",
            "initialized": self._initialized,
            "components": {
                "llm_manager": self.llm_manager is not None,
                "vector_store": self.vector_store is not None,
                "context_manager": self.context_manager is not None,
                "agent_registry": self.agent_registry is not None,
                "orchestrator": self.orchestrator is not None,
                "tool_registry": self.tool_registry is not None,
                "safety_guard": self.safety_guard is not None,
                "memory": self.memory is not None,
            }
        }
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit
        
        Note: This is a synchronous method, but shutdown() is async.
        In FastAPI context, shutdown is handled by lifespan context manager,
        so this method should not be used directly. It's kept for compatibility
        with synchronous context manager usage.
        
        IMPORTANT: This method does NOT call shutdown() to avoid RuntimeError
        when there's an active event loop. Shutdown must be handled explicitly
        through the lifespan context manager in FastAPI or by calling
        await engine.shutdown() directly in async context.
        """
        if self._initialized:
            try:
                # Попытаться получить текущий event loop
                loop = asyncio.get_running_loop()
                # Если loop уже запущен, НЕ вызываем shutdown() здесь
                # Это вызовет RuntimeError: asyncio.run() cannot be called from a running event loop
                logger.debug(
                    "Event loop is running. Shutdown must be handled by lifespan context manager "
                    "or by calling await engine.shutdown() directly in async context."
                )
            except RuntimeError:
                # Если loop не запущен, это означает что мы не в async контексте
                # В этом случае shutdown должен быть вызван явно через lifespan
                logger.warning(
                    "No event loop detected. Shutdown should be handled by lifespan context manager. "
                    "If using IDAEngine as context manager, ensure shutdown() is called explicitly."
                )
                # НЕ вызываем asyncio.run() здесь, так как это может вызвать проблемы
                # если loop запущен в другом потоке или будет запущен позже

