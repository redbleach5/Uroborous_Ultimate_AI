"""
Base Agent class
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from ..core.logger import get_logger
logger = get_logger(__name__)
import time

from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage
from ..tools.registry import ToolRegistry
from ..rag.context_manager import ContextManager
from ..memory.long_term import LongTermMemory
from ..core.exceptions import AgentException
from ..core.logger import structured_logger
from ..core.pydantic_utils import pydantic_to_dict


class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        llm_manager: Optional[LLMProviderManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        context_manager: Optional[ContextManager] = None,
        memory: Optional[LongTermMemory] = None
    ):
        """
        Initialize agent
        
        Args:
            name: Agent name
            config: Agent configuration
            llm_manager: LLM provider manager
            tool_registry: Tool registry
            context_manager: Context manager
            memory: Long term memory
        """
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)
        self.default_model = config.get("default_model")
        self.temperature = config.get("temperature", 0.7)
        self.max_iterations = config.get("max_iterations", 10)
        self.use_thinking_mode = config.get("use_thinking_mode", False)  # Enable thinking mode for complex reasoning
        
        self.llm_manager = llm_manager
        self.tool_registry = tool_registry
        self.context_manager = context_manager
        self.memory = memory
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize agent"""
        if not self.enabled:
            logger.warning(f"Agent {self.name} is disabled")
            return
        
        if not self.llm_manager:
            raise AgentException(f"LLM manager required for agent {self.name}")
        
        self._initialized = True
        logger.info(f"Agent {self.name} initialized")
    
    async def execute(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a task
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            Result dictionary
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        
        try:
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_start",
                task=task,
                context=context
            )
            
            result = await self._execute_impl(task, context or {})
            
            duration = time.time() - start_time
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_complete",
                task=task,
                context=context,
                result=result,
                duration=duration
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_error",
                task=task,
                context=context,
                result={"success": False, "error": str(e)},
                duration=duration
            )
            raise
    
    @abstractmethod
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Implementation of execute method (to be overridden by subclasses)
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            Result dictionary
        """
        raise NotImplementedError("Subclasses must implement _execute_impl method")
    
    async def shutdown(self) -> None:
        """Shutdown agent"""
        self._initialized = False
    
    def _determine_task_type(self) -> Optional[str]:
        """
        Определяет тип задачи на основе имени агента
        
        Returns:
            Тип задачи (code, chat, analysis, reasoning) или None
        """
        agent_to_task_type = {
            "code_writer": "code",
            "react": "reasoning",
            "research": "analysis",
            "data_analysis": "analysis",
            "workflow": "code",
            "integration": "code",
            "monitoring": "analysis"
        }
        return agent_to_task_type.get(self.name)
    
    async def _get_llm_response(
        self,
        messages: List[LLMMessage],
        provider: Optional[str] = None,
        use_thinking: Optional[bool] = None,
        **kwargs
    ) -> str:
        """
        Get response from LLM
        
        Args:
            messages: List of messages
            provider: Provider name (None = use default, "ollama" = prioritize Ollama)
            use_thinking: Override thinking mode (if None, uses agent config)
            **kwargs: Additional parameters
        """
        if not self.llm_manager:
            raise AgentException("LLM manager not available")
        
        # Добавляем информацию о текущей дате и времени в системный промпт
        current_datetime = self._get_current_datetime_info()
        datetime_info = f"\n\nВАЖНО: Текущая дата и время: {current_datetime}. Используйте эту информацию для предоставления актуальных данных."
        
        # Ищем системный промпт и добавляем информацию о дате/времени
        enhanced_messages = []
        for msg in messages:
            if msg.role == "system":
                # Добавляем информацию о дате/времени, если её еще нет
                if "Текущая дата и время" not in msg.content and "Current date and time" not in msg.content:
                    enhanced_messages.append(LLMMessage(
                        role=msg.role,
                        content=msg.content + datetime_info
                    ))
                else:
                    enhanced_messages.append(msg)
            else:
                enhanced_messages.append(msg)
        
        # Если системного промпта нет, добавляем его
        if not any(msg.role == "system" for msg in enhanced_messages):
            enhanced_messages.insert(0, LLMMessage(
                role="system",
                content=f"Текущая дата и время: {current_datetime}. Используйте эту информацию для предоставления актуальных данных."
            ))
        
        # PRIORITY: Если provider не указан, приоритизируем Ollama
        if provider is None:
            # Проверяем доступность Ollama
            if self.llm_manager.is_provider_available("ollama"):
                provider = "ollama"
                logger.debug(f"Agent {self.name} using Ollama (priority provider)")
        
        # Determine thinking mode: explicit override > agent config > default False
        thinking_mode = use_thinking if use_thinking is not None else self.use_thinking_mode
        
        # Определяем тип задачи для умного выбора модели Ollama
        task_type = kwargs.get("task_type") or self._determine_task_type()
        if task_type:
            kwargs["task_type"] = task_type
        
        response = await self.llm_manager.generate(
            messages=enhanced_messages,
            provider_name=provider,
            model=self.default_model,
            temperature=self.temperature,
            thinking_mode=thinking_mode,
            **kwargs
        )
        
        # Log thinking trace if available
        if response.has_thinking and response.thinking:
            logger.debug(f"Agent {self.name} received thinking trace ({len(response.thinking)} chars)")
        
        return response.content
    
    async def _get_context(self, query: str) -> str:
        """Get relevant context for query"""
        if self.context_manager:
            return await self.context_manager.get_context(query)
        return ""
    
    def _get_current_datetime_info(self) -> str:
        """
        Получить информацию о текущей дате и времени для использования в промптах
        
        Returns:
            Строка с текущей датой и временем в читаемом формате
        """
        now = datetime.now()
        # Форматируем дату и время на русском языке
        weekday_names = {
            0: "Понедельник",
            1: "Вторник",
            2: "Среда",
            3: "Четверг",
            4: "Пятница",
            5: "Суббота",
            6: "Воскресенье"
        }
        month_names = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }
        
        weekday = weekday_names[now.weekday()]
        month = month_names[now.month]
        date_str = f"{now.day} {month} {now.year} года"
        time_str = now.strftime("%H:%M:%S")
        
        return f"{weekday}, {date_str}, {time_str} (UTC{now.strftime('%z')})"


class AgentRegistry:
    """Registry for managing all agents"""
    
    def __init__(
        self,
        config: Any,  # AgentsConfig
        llm_manager: Optional[LLMProviderManager],
        tool_registry: Optional[ToolRegistry],
        context_manager: Optional[ContextManager],
        memory: Optional[LongTermMemory]
    ):
        """
        Initialize agent registry
        
        Args:
            config: Agents configuration
            llm_manager: LLM provider manager
            tool_registry: Tool registry
            context_manager: Context manager
            memory: Long term memory
        """
        self.config = config
        self.llm_manager = llm_manager
        self.tool_registry = tool_registry
        self.context_manager = context_manager
        self.memory = memory
        
        self.agents: Dict[str, BaseAgent] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all agents"""
        if self._initialized:
            return
        
        logger.info("Initializing agents...")
        
        # Import agents here to avoid circular imports
        from .code_writer import CodeWriterAgent
        from .react import ReactAgent
        from .research import ResearchAgent
        from .data_analysis import DataAnalysisAgent
        from .workflow import WorkflowAgent
        from .integration import IntegrationAgent
        from .monitoring import MonitoringAgent
        
        # Initialize CodeWriterAgent
        if hasattr(self.config, "code_writer") and self.config.code_writer.enabled:
            agent = CodeWriterAgent(
                "code_writer",
                pydantic_to_dict(self.config.code_writer),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["code_writer"] = agent
        
        # Initialize ReactAgent
        if hasattr(self.config, "react") and self.config.react.enabled:
            agent = ReactAgent(
                "react",
                pydantic_to_dict(self.config.react),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["react"] = agent
        
        # Initialize ResearchAgent
        if hasattr(self.config, "research") and self.config.research.enabled:
            agent = ResearchAgent(
                "research",
                pydantic_to_dict(self.config.research),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["research"] = agent
        
        # Initialize DataAnalysisAgent
        if hasattr(self.config, "data_analysis") and self.config.data_analysis.enabled:
            agent = DataAnalysisAgent(
                "data_analysis",
                pydantic_to_dict(self.config.data_analysis),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["data_analysis"] = agent
        
        # Initialize WorkflowAgent
        if hasattr(self.config, "workflow") and self.config.workflow.enabled:
            agent = WorkflowAgent(
                "workflow",
                pydantic_to_dict(self.config.workflow),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["workflow"] = agent
        
        # Initialize IntegrationAgent
        if hasattr(self.config, "integration") and self.config.integration.enabled:
            agent = IntegrationAgent(
                "integration",
                pydantic_to_dict(self.config.integration),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["integration"] = agent
        
        # Initialize MonitoringAgent
        if hasattr(self.config, "monitoring") and self.config.monitoring.enabled:
            agent = MonitoringAgent(
                "monitoring",
                pydantic_to_dict(self.config.monitoring),
                self.llm_manager,
                self.tool_registry,
                self.context_manager,
                self.memory
            )
            await agent.initialize()
            self.agents["monitoring"] = agent
        
        logger.info(f"Initialized {len(self.agents)} agents")
        self._initialized = True
    
    async def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Get agent by type"""
        return self.agents.get(agent_type)
    
    def list_agents(self) -> List[str]:
        """List all available agents"""
        return list(self.agents.keys())
    
    async def shutdown(self) -> None:
        """Shutdown all agents"""
        for agent in self.agents.values():
            await agent.shutdown()
        self.agents.clear()
        self._initialized = False

