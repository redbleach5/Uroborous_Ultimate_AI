"""
Base Agent class with reflection and communication capabilities
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING, AsyncIterator
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
from .reflection_mixin import ReflectionMixin
from .uncertainty_search_mixin import UncertaintySearchMixin

if TYPE_CHECKING:
    from .communicator import AgentCommunicator


class BaseAgent(ABC, ReflectionMixin, UncertaintySearchMixin):
    """
    Base class for all agents with reflection, communication, and uncertainty search capabilities.
    
    Features:
    - Automatic reflection and self-correction
    - Inter-agent communication via AgentCommunicator
    - Task delegation to other agents
    - Quality tracking and improvement
    - Automatic web search when uncertain (UncertaintySearchMixin)
    """
    
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
        # Initialize mixins
        ReflectionMixin.__init__(self)
        UncertaintySearchMixin.__init__(self)
        
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
        
        # Текущий контекст выполнения (для distributed routing)
        self._current_execution_context: Dict[str, Any] = {}
        
        # Communication
        self._communicator: Optional["AgentCommunicator"] = None
        
        # Configure reflection from config
        reflection_config = config.get("reflection", {})
        self.configure_reflection(
            enabled=reflection_config.get("enabled", True),
            max_retries=reflection_config.get("max_retries", 2),
            min_quality_threshold=reflection_config.get("min_quality_threshold", 60.0)
        )
    
    async def initialize(self) -> None:
        """Initialize agent"""
        if not self.enabled:
            logger.warning(f"Agent {self.name} is disabled")
            return
        
        if not self.llm_manager:
            raise AgentException(f"LLM manager required for agent {self.name}")
        
        self._initialized = True
        logger.info(f"Agent {self.name} initialized")
    
    def set_communicator(self, communicator: "AgentCommunicator") -> None:
        """Set the agent communicator for inter-agent communication"""
        self._communicator = communicator
    
    async def execute(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a task with optional reflection and self-correction.
        
        Args:
            task: Task description
            context: Additional context (может содержать preferred_model и ollama_server_url для distributed routing)
            
        Returns:
            Result dictionary with optional reflection data
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        ctx = context or {}
        
        # === INTELLIGENT MODEL SELECTION ===
        # If no preferred_model in context, try to get recommended model from memory
        if "preferred_model" not in ctx and self.memory:
            try:
                recommended = await self.get_recommended_model()
                if recommended:
                    ctx["_memory_recommended_model"] = recommended
                    logger.debug(f"Agent {self.name}: Memory recommends model: {recommended}")
            except Exception as e:
                logger.debug(f"Agent {self.name}: Could not get model recommendation: {e}")
        
        # Сохраняем контекст для distributed routing (чтобы _get_llm_response мог использовать)
        self._current_execution_context = ctx
        
        try:
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_start",
                task=task,
                context=ctx
            )
            
            # Check if reflection is enabled and not in correction mode
            use_reflection = (
                self._reflection_enabled and 
                not ctx.get("_correction_mode", False) and
                not ctx.get("_skip_reflection", False)
            )
            
            if use_reflection:
                # Execute with reflection loop
                result = await self.execute_with_reflection(
                    task=task,
                    context=ctx,
                    execute_fn=self._execute_impl
                )
            else:
                # Direct execution without reflection
                result = await self._execute_impl(task, ctx)
            
            duration = time.time() - start_time
            result["_execution_time"] = duration
            
            # === RECORD SUCCESS TO MEMORY ===
            if result.get("success", True) and self.memory:
                try:
                    # Get the solution from result
                    solution = (
                        result.get("code") or 
                        result.get("final_answer") or 
                        result.get("analysis") or 
                        result.get("report") or 
                        str(result.get("result", ""))[:1000]
                    )
                    if solution and len(solution) > 50:  # Only save non-trivial solutions
                        model_used = ctx.get("preferred_model") or self.default_model
                        await self.save_to_memory(
                            task=task[:500],
                            solution=solution[:2000],
                            metadata={"duration": duration, "reflection": result.get("_reflection")},
                            model_used=model_used
                        )
                except Exception as e:
                    logger.debug(f"Agent {self.name}: Could not save to memory: {e}")
            
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_complete",
                task=task,
                context=ctx,
                result=result,
                duration=duration
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # === RECORD FAILURE TO MEMORY ===
            try:
                await self.record_failure(
                    task=task[:500],
                    error_type=type(e).__name__,
                    error_message=str(e)[:500],
                    error_context={"duration": duration, "context_keys": list(ctx.keys())}
                )
            except Exception as record_error:
                logger.debug(f"Agent {self.name}: Could not record failure: {record_error}")
            
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_error",
                task=task,
                context=ctx,
                result={"success": False, "error": str(e)},
                duration=duration
            )
            raise
        finally:
            # Очищаем контекст выполнения чтобы не влиять на следующие вызовы
            self._current_execution_context = {}
    
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
    
    async def execute_stream(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        """
        Execute a task with streaming output.
        
        Yields chunks of the response as they are generated.
        Falls back to non-streaming if the provider doesn't support streaming.
        
        Args:
            task: Task description
            context: Additional context
            
        Yields:
            String chunks of the response
            
        Example:
            async for chunk in agent.execute_stream("Write a function"):
                print(chunk, end="", flush=True)
        """
        if not self._initialized:
            await self.initialize()
        
        ctx = context or {}
        self._current_execution_context = ctx
        
        try:
            structured_logger.log_agent_action(
                agent_name=self.name,
                action="execute_stream_start",
                task=task,
                context=ctx
            )
            
            # Get system prompt and user message
            system_prompt = self._get_streaming_system_prompt()
            
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=task)
            ]
            
            # Try streaming if provider supports it
            if self.llm_manager and hasattr(self.llm_manager, 'stream'):
                try:
                    async for chunk in self._stream_llm_response(messages, ctx):
                        yield chunk
                    return
                except NotImplementedError:
                    pass  # Fall back to non-streaming
                except Exception as e:
                    logger.warning(f"Streaming failed, falling back to regular: {e}")
            
            # Fallback to non-streaming
            result = await self.execute(task, context)
            
            # Yield the result as a single chunk
            if "code" in result:
                yield result["code"]
            elif "final_answer" in result:
                yield result["final_answer"]
            elif "analysis" in result:
                yield result["analysis"]
            elif "report" in result:
                yield result["report"]
            else:
                yield str(result.get("result", result))
                
        finally:
            self._current_execution_context = {}
    
    async def _stream_llm_response(
        self,
        messages: List[LLMMessage],
        context: Dict[str, Any]
    ) -> AsyncIterator[str]:
        """
        Stream response from LLM provider.
        
        Override in subclasses for custom streaming behavior.
        """
        if not self.llm_manager:
            raise AgentException("LLM manager not available")
        
        # Determine provider
        provider = None
        if self.llm_manager.is_provider_available("ollama"):
            provider = "ollama"
        
        # Get the provider instance
        provider_instance = self.llm_manager.providers.get(provider or "ollama")
        if not provider_instance:
            raise NotImplementedError("No streaming provider available")
        
        # Check if provider supports streaming
        if not hasattr(provider_instance, 'stream'):
            raise NotImplementedError("Provider does not support streaming")
        
        # Determine model
        model = (
            context.get("preferred_model") or
            self._current_execution_context.get("preferred_model") or
            self.default_model
        )
        
        # Stream the response
        async for chunk in provider_instance.stream(
            messages=messages,
            model=model,
            temperature=self.temperature
        ):
            yield chunk
    
    def _get_streaming_system_prompt(self) -> str:
        """
        Get system prompt for streaming execution.
        Override in subclasses for agent-specific prompts.
        """
        return f"""You are {self.name}, an AI assistant.
Respond to the user's request clearly and helpfully.
Current time: {self._get_current_datetime_info()}"""
    
    async def shutdown(self) -> None:
        """Shutdown agent"""
        self._initialized = False
    
    # ==================== Inter-Agent Communication ====================
    
    async def delegate_to(
        self,
        agent_type: str,
        subtask: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Delegate a subtask to another agent.
        
        Args:
            agent_type: Type of agent to delegate to (e.g., "research", "code_writer")
            subtask: Description of the subtask
            context: Context to pass to the delegated agent
            timeout: Timeout in seconds
            
        Returns:
            Result from the delegated agent
            
        Raises:
            AgentException: If communicator not available or delegation fails
        """
        if not self._communicator:
            raise AgentException(
                f"Agent {self.name}: Communicator not available for delegation. "
                "Ensure AgentCommunicator is initialized and set."
            )
        
        logger.info(f"Agent {self.name}: Delegating subtask to {agent_type}: {subtask[:50]}...")
        
        result = await self._communicator.delegate_subtask(
            from_agent=self.name,
            to_agent=agent_type,
            subtask=subtask,
            context=context,
            timeout=timeout
        )
        
        if result.success:
            logger.info(
                f"Agent {self.name}: Delegation to {agent_type} successful "
                f"(took {result.execution_time:.2f}s)"
            )
        else:
            logger.warning(
                f"Agent {self.name}: Delegation to {agent_type} failed: {result.error}"
            )
        
        return result.to_dict()
    
    async def request_help(
        self,
        capability: str,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Request help from an agent with a specific capability.
        
        Args:
            capability: Required capability (e.g., "code_generation", "data_analysis")
            task: Task description
            context: Context to pass
            
        Returns:
            Result from the helper agent
        """
        if not self._communicator:
            raise AgentException(
                f"Agent {self.name}: Communicator not available for help request"
            )
        
        from .communicator import AgentCapability
        
        try:
            cap = AgentCapability(capability)
        except ValueError:
            raise AgentException(f"Unknown capability: {capability}")
        
        logger.info(f"Agent {self.name}: Requesting help with capability {capability}")
        
        result = await self._communicator.request_help(
            from_agent=self.name,
            capability=cap,
            task=task,
            context=context
        )
        
        return result.to_dict()
    
    async def broadcast_message(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Broadcast a message to all agents.
        
        Args:
            content: Message content
            
        Returns:
            Responses from all agents
        """
        if not self._communicator:
            raise AgentException(
                f"Agent {self.name}: Communicator not available for broadcast"
            )
        
        return await self._communicator.broadcast_to_all(
            from_agent=self.name,
            content=content
        )
    
    async def on_broadcast(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a broadcast message from another agent.
        Override in subclasses to implement custom broadcast handling.
        
        Args:
            content: Broadcast message content
            
        Returns:
            Response to the broadcast
        """
        # Default implementation - just acknowledge
        return {
            "agent": self.name,
            "acknowledged": True,
            "message": f"Broadcast received by {self.name}"
        }
    
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
        include_few_shot: bool = True,
        include_personalization: bool = True,
        include_error_warnings: bool = True,
        **kwargs
    ) -> str:
        """
        Get response from LLM with automatic few-shot examples injection,
        personalization, and error warnings.
        
        Args:
            messages: List of messages
            provider: Provider name (None = use default, "ollama" = prioritize Ollama)
            use_thinking: Override thinking mode (if None, uses agent config)
            include_few_shot: Whether to include few-shot examples from memory (default True)
            include_personalization: Whether to include user preferences (default True)
            include_error_warnings: Whether to include warnings about past errors (default True)
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
        
        # Extract task from user messages for memory queries
        task_text = ""
        for msg in messages:
            if msg.role == "user":
                task_text = msg.content
                break
        
        # === FULL LONGTTERMMEMORY INTEGRATION ===
        if self.memory and task_text:
            memory_enhancements = []
            
            # 1. Персонализация на основе предпочтений пользователя
            if include_personalization:
                personalization = await self._get_personalization_prompt()
                if personalization:
                    memory_enhancements.append(personalization)
            
            # 2. Предупреждения об ошибках на похожих задачах
            if include_error_warnings:
                error_warnings = await self._get_error_warnings(task_text)
                if error_warnings:
                    memory_enhancements.append(error_warnings)
            
            # 3. Few-shot примеры из успешных решений
            if include_few_shot:
                enhanced_messages = await self._enhance_prompt_with_examples(
                    enhanced_messages, task_text
                )
            
            # Добавляем все улучшения в системный промпт
            if memory_enhancements:
                for i, msg in enumerate(enhanced_messages):
                    if msg.role == "system":
                        enhanced_messages[i] = LLMMessage(
                            role=msg.role,
                            content=msg.content + "\n".join(memory_enhancements)
                        )
                        break
        
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
        
        # Поддержка distributed routing: используем модель/сервер из контекста или kwargs
        # Приоритет: kwargs > _current_execution_context > default_model
        model_to_use = (
            kwargs.pop("preferred_model", None) or 
            self._current_execution_context.get("preferred_model") or 
            self.default_model
        )
        ollama_server_url = (
            kwargs.pop("ollama_server_url", None) or 
            self._current_execution_context.get("ollama_server_url")
        )
        
        # Pass server_url to provider (thread-safe, no global state modification)
        if ollama_server_url and provider == "ollama":
            kwargs["server_url"] = ollama_server_url
            logger.debug(f"Agent {self.name} using Ollama server: {ollama_server_url}")
        
        response = await self.llm_manager.generate(
            messages=enhanced_messages,
            provider_name=provider,
            model=model_to_use,
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
    
    async def _get_few_shot_examples(
        self,
        task: str,
        max_examples: int = 2,
        min_quality: float = 50.0
    ) -> str:
        """
        Get few-shot examples from LongTermMemory for improved prompt quality.
        
        This significantly improves response quality by providing successful
        examples of similar tasks to the LLM.
        
        Args:
            task: Current task description
            max_examples: Maximum number of examples to include
            min_quality: Minimum quality score (0-100) for examples
            
        Returns:
            Formatted few-shot examples string or empty string if none found
        """
        if not self.memory:
            return ""
        
        try:
            # Search for high-quality similar solutions
            similar_tasks = await self.memory.search_similar_tasks_with_quality(
                task=task,
                top_k=max_examples,
                min_quality=min_quality
            )
            
            if not similar_tasks:
                logger.debug(f"Agent {self.name}: No few-shot examples found for task")
                return ""
            
            # Format examples for prompt
            examples_text = "\n\n### SUCCESSFUL EXAMPLES FROM PREVIOUS TASKS:\n"
            examples_text += "(Use these as reference for similar solutions)\n"
            
            for i, item in enumerate(similar_tasks, 1):
                task_text = item.get("task", "")[:300]  # Limit task length
                solution_text = item.get("solution", "")[:800]  # Limit solution length
                quality = item.get("quality_score", 0)
                similarity = item.get("similarity", 0)
                
                examples_text += f"\n**Example {i}** (quality: {quality:.0f}%, similarity: {similarity:.0%}):\n"
                examples_text += f"Task: {task_text}\n"
                
                # Truncate solution if too long
                if len(item.get("solution", "")) > 800:
                    examples_text += f"Solution (truncated):\n{solution_text}...\n"
                else:
                    examples_text += f"Solution:\n{solution_text}\n"
            
            examples_text += "\n### END OF EXAMPLES\n"
            examples_text += "Now solve the current task, using the examples as reference if helpful.\n"
            
            logger.info(
                f"Agent {self.name}: Added {len(similar_tasks)} few-shot examples "
                f"(avg quality: {sum(t.get('quality_score', 0) for t in similar_tasks) / len(similar_tasks):.0f}%)"
            )
            
            return examples_text
            
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to get few-shot examples: {e}")
            return ""
    
    async def _enhance_prompt_with_examples(
        self,
        messages: List[LLMMessage],
        task: str
    ) -> List[LLMMessage]:
        """
        Enhance messages with few-shot examples from memory.
        
        Adds examples to the system prompt or as a separate message.
        
        Args:
            messages: Original list of messages
            task: Current task for finding similar examples
            
        Returns:
            Enhanced messages with few-shot examples
        """
        # Get few-shot examples
        examples = await self._get_few_shot_examples(task)
        
        if not examples:
            return messages
        
        # Find system message and enhance it
        enhanced_messages = []
        system_enhanced = False
        
        for msg in messages:
            if msg.role == "system" and not system_enhanced:
                # Add examples to system prompt
                enhanced_content = msg.content + examples
                enhanced_messages.append(LLMMessage(
                    role=msg.role,
                    content=enhanced_content
                ))
                system_enhanced = True
            else:
                enhanced_messages.append(msg)
        
        # If no system message, add examples as first user context
        if not system_enhanced and enhanced_messages:
            # Insert examples before the last user message
            for i in range(len(enhanced_messages) - 1, -1, -1):
                if enhanced_messages[i].role == "user":
                    enhanced_messages[i] = LLMMessage(
                        role="user",
                        content=examples + "\n\n" + enhanced_messages[i].content
                    )
                    break
        
        return enhanced_messages
    
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
    
    # ==================== LONGTTERMMEMORY INTEGRATION ====================
    
    async def _get_personalization_prompt(self, user_id: str = "default") -> str:
        """
        Получить персонализированные инструкции на основе предпочтений пользователя.
        
        Returns:
            Персонализированные инструкции для промпта или пустая строка
        """
        if not self.memory:
            return ""
        
        try:
            return await self.memory.get_personalization_prompt(user_id)
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to get personalization: {e}")
            return ""
    
    async def _get_error_warnings(self, task: str) -> str:
        """
        Получить предупреждения о прошлых ошибках на похожих задачах.
        
        Args:
            task: Текущая задача
            
        Returns:
            Предупреждения для промпта или пустая строка
        """
        if not self.memory:
            return ""
        
        try:
            return await self.memory.get_error_avoidance_prompt(task, agent=self.name)
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to get error warnings: {e}")
            return ""
    
    async def save_to_memory(
        self,
        task: str,
        solution: str,
        metadata: Optional[Dict[str, Any]] = None,
        model_used: Optional[str] = None
    ) -> Optional[int]:
        """
        Сохранить решение в долгосрочную память.
        
        Args:
            task: Описание задачи
            solution: Решение
            metadata: Дополнительные метаданные
            model_used: Модель, которая сгенерировала решение
            
        Returns:
            ID сохраненной записи или None
        """
        if not self.memory:
            return None
        
        try:
            task_type = self._determine_task_type()
            return await self.memory.save_solution(
                task=task,
                solution=solution,
                agent=self.name,
                metadata=metadata,
                task_type=task_type,
                model_used=model_used
            )
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to save to memory: {e}")
            return None
    
    async def record_failure(
        self,
        task: str,
        error_type: str,
        error_message: str,
        error_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Записать неудачную задачу для предотвращения повторных ошибок.
        
        Args:
            task: Описание задачи
            error_type: Тип ошибки
            error_message: Сообщение об ошибке
            error_context: Контекст ошибки
        """
        if not self.memory:
            return
        
        try:
            await self.memory.save_failed_task(
                task=task,
                agent=self.name,
                error_type=error_type,
                error_message=error_message,
                error_context=error_context
            )
            logger.info(f"Agent {self.name}: Recorded failure for learning: {error_type}")
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to record failure: {e}")
    
    async def get_recommended_model(self) -> Optional[str]:
        """
        Получить рекомендуемую модель для типа задач этого агента.
        
        Returns:
            Имя рекомендуемой модели или None
        """
        if not self.memory:
            return None
        
        try:
            task_type = self._determine_task_type()
            if task_type:
                best = await self.memory.get_best_model_for_task_type(task_type)
                if best:
                    logger.debug(
                        f"Agent {self.name}: Recommended model for {task_type}: "
                        f"{best['model_name']} (success: {best['success_rate']:.0%})"
                    )
                    return best["model_name"]
            return None
        except Exception as e:
            logger.warning(f"Agent {self.name}: Failed to get recommended model: {e}")
            return None


class AgentRegistry:
    """Registry for managing all agents with inter-agent communication"""
    
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
        
        # Agent communicator for inter-agent communication
        self._communicator: Optional["AgentCommunicator"] = None
    
    async def initialize(self) -> None:
        """Initialize all agents and set up inter-agent communication"""
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
        from .communicator import AgentCommunicator, set_communicator
        
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
        
        # Initialize AgentCommunicator for inter-agent communication
        self._communicator = AgentCommunicator(self)
        await self._communicator.initialize()
        
        # Set communicator for all agents
        for agent in self.agents.values():
            agent.set_communicator(self._communicator)
        
        # Set global communicator
        set_communicator(self._communicator)
        
        logger.info(f"Initialized {len(self.agents)} agents with inter-agent communication")
        self._initialized = True
    
    async def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Get agent by type"""
        return self.agents.get(agent_type)
    
    def list_agents(self) -> List[str]:
        """List all available agents"""
        return list(self.agents.keys())
    
    async def update_config(self, new_config: Any) -> None:
        """
        Update agent registry configuration dynamically.
        
        Args:
            new_config: New AgentsConfig
        """
        logger.info("Updating Agent Registry configuration...")
        self.config = new_config
        
        # Update individual agent configurations
        agent_configs = {
            "code_writer": getattr(new_config, "code_writer", None),
            "react": getattr(new_config, "react", None),
            "research": getattr(new_config, "research", None),
            "data_analysis": getattr(new_config, "data_analysis", None),
            "workflow": getattr(new_config, "workflow", None),
            "integration": getattr(new_config, "integration", None),
            "monitoring": getattr(new_config, "monitoring", None),
        }
        
        for agent_name, agent_config in agent_configs.items():
            if agent_config and agent_name in self.agents:
                agent = self.agents[agent_name]
                # Update configurable parameters
                config_dict = pydantic_to_dict(agent_config)
                agent.temperature = config_dict.get("temperature", agent.temperature)
                agent.max_iterations = config_dict.get("max_iterations", agent.max_iterations)
                agent.use_thinking_mode = config_dict.get("use_thinking_mode", agent.use_thinking_mode)
                logger.debug(f"Updated config for agent: {agent_name}")
        
        logger.info("Agent Registry configuration updated")
    
    async def shutdown(self) -> None:
        """Shutdown all agents and communicator"""
        # Shutdown communicator first
        if self._communicator:
            await self._communicator.shutdown()
            self._communicator = None
        
        # Shutdown all agents
        for agent in self.agents.values():
            await agent.shutdown()
        self.agents.clear()
        self._initialized = False
    
    def get_communicator(self) -> Optional["AgentCommunicator"]:
        """Get the agent communicator"""
        return self._communicator

