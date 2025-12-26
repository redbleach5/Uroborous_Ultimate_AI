"""
Orchestrator - Decomposes tasks, plans execution, and coordinates agents
"""

import asyncio
from typing import Dict, Any, Optional, List
from .core.logger import get_logger
logger = get_logger(__name__)

from .config import OrchestratorConfig
from .agents.base import AgentRegistry
from .llm.providers import LLMProviderManager
from .llm.base import LLMMessage
from .memory.long_term import LongTermMemory
from .core.exceptions import AILLMException
from .core.error_handler import ErrorHandler
from .core.llm_classifier import LLMClassifier, AGENT_SELECTION_SCHEMA
from .core.task_router import TaskRouter
from .core.smart_model_selector import SmartModelSelector
from .core.resource_aware_selector import ResourceAwareSelector
from .core.prompt_optimizer import PromptOptimizer
from .core.time_estimator import TimeEstimator
from .core.pydantic_utils import pydantic_to_dict


class Orchestrator:
    """
    Orchestrator for task decomposition, planning, and agent coordination
    """
    
    def __init__(
        self,
        config: OrchestratorConfig,
        agent_registry: AgentRegistry,
        llm_manager: LLMProviderManager,
        memory: Optional[LongTermMemory] = None,
        full_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize orchestrator
        
        Args:
            config: Orchestrator configuration
            agent_registry: Agent registry
            llm_manager: LLM provider manager
            memory: Long term memory
            full_config: Полный конфиг приложения (для distributed_mode и др.)
        """
        self.config = config
        self.agent_registry = agent_registry
        self.llm_manager = llm_manager
        self.memory = memory
        self.full_config = full_config or {}
        self.max_parallel_tasks = config.max_parallel_tasks
        self.task_timeout = config.task_timeout
        self.auto_recovery = config.auto_recovery
        self.error_handler = ErrorHandler(max_retries=3, retry_delay=1.0)
        self._initialized = False
        self.llm_classifier = LLMClassifier(llm_manager) if llm_manager else None
        config_dict = pydantic_to_dict(config)
        self.task_router = TaskRouter(llm_manager, config_dict) if llm_manager else None
        self.model_selector = SmartModelSelector(llm_manager, config_dict) if llm_manager else None
        # ResourceAwareSelector нужен полный конфиг для distributed_mode
        self.resource_aware_selector = ResourceAwareSelector(llm_manager, self.full_config) if llm_manager else None
        self.prompt_optimizer = PromptOptimizer()
        self.time_estimator = TimeEstimator()
    
    async def initialize(self) -> None:
        """Initialize orchestrator"""
        self._initialized = True
        logger.info("Orchestrator initialized")
    
    async def execute_task(
        self,
        task: str,
        agent_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a task with automatic decomposition and planning
        
        Args:
            task: Task description
            agent_type: Preferred agent type
            context: Additional context
            
        Returns:
            Task execution result
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Orchestrator executing task: {task}")

        # НЕ форсируем code_writer здесь - пусть LLMClassifier решает
        # Это позволяет системе быть умнее и различать:
        # - "напиши код игры" -> code_writer
        # - "напиши отчёт о проекте" -> research  
        # - "напиши что делает этот код" -> research
        
        # Use TaskRouter for intelligent routing if available and agent not pre-selected
        # Cache routing result to avoid double calls
        routing = None
        task_type_from_routing = None
        complexity_from_routing = None
        
        if self.task_router and not agent_type:
            try:
                routing = await self.task_router.route_task(task, context)
                task_type_from_routing = routing.task_type
                complexity_from_routing = routing.complexity
                logger.info(f"Task routed: type={routing.task_type}, complexity={routing.complexity}")
                
                # For simple tasks, process directly through TaskRouter
                if routing.task_type == "simple_chat" and routing.complexity == "low":
                    result = await self.task_router.process_task(task, context)
                    if result.get("success"):
                        return {
                            "success": True,
                            "result": result.get("result"),
                            "agent": "task_router",
                            "routing": routing
                        }
            except Exception as e:
                logger.warning(f"TaskRouter failed: {e}, falling back to standard execution")
        
        # Adaptive model selection using cached routing result
        adaptive_selection = None
        if self.resource_aware_selector:
            try:
                adaptive_selection = await self.resource_aware_selector.select_adaptive_model(
                    task=task,
                    task_type=task_type_from_routing,
                    complexity=complexity_from_routing
                )
                logger.info(
                    f"Adaptive selection: {adaptive_selection.model} "
                    f"(resource: {adaptive_selection.resource_level.value}, "
                    f"quality: {adaptive_selection.quality_estimate:.2f})"
                    + (f", server: {adaptive_selection.server_name}" if adaptive_selection.server_url else "")
                )
                
                # Передаём выбранную модель и сервер в контекст для агентов
                context = context or {}
                context["preferred_model"] = adaptive_selection.model
                context["preferred_provider"] = adaptive_selection.provider
                if adaptive_selection.server_url:
                    context["ollama_server_url"] = adaptive_selection.server_url
                    context["distributed_routing"] = True
            except Exception as e:
                logger.warning(f"Adaptive selection failed: {e}")
        
        # Check memory for similar tasks (with quality scores)
        similar_solutions = []
        if self.memory:
            # Используем улучшенный поиск с учетом качества решений
            if hasattr(self.memory, 'search_similar_tasks_with_quality'):
                similar_solutions = await self.memory.search_similar_tasks_with_quality(
                    task, top_k=5, min_quality=20.0  # Минимум 20% качества
                )
            else:
                similar_solutions = await self.memory.search_similar_tasks(task)
        
        # Теперь НЕ форсируем агента на основе ключевых слов
        # Вся логика классификации делегирована LLMClassifier в _select_agent()
        # Это делает систему умнее - она понимает контекст, а не просто ищет слова
        
        # Always use LLM for intelligent task understanding and planning (like Manus AI)
        planning_config = pydantic_to_dict(self.config.planning)
        strategy = planning_config.get("strategy", "llm")
        
        # Если agent_type уже задан явно - используем его
        # Иначе пусть LLMClassifier решает в _select_agent()
        if agent_type:
            logger.info(f"Agent type explicitly set to {agent_type}, using it directly")
            subtasks = [task]
        elif strategy == "llm" or strategy == "hybrid" or self.llm_manager:
            subtasks = await self._decompose_task_llm(task, context)
        else:
            subtasks = [task]
        
        # If single simple task, use LLM to select best agent
        if len(subtasks) == 1 and not agent_type:
            # Use LLM reasoning to select the best agent (not keyword matching)
            agent_type = await self._select_agent(task)
        
        if agent_type:
            # Execute with specific agent
            agent = await self.agent_registry.get_agent(agent_type)
            if agent:
                try:
                    # Use error handler for retry with timeout
                    try:
                        result = await asyncio.wait_for(
                            agent.execute(task, context or {}),
                            timeout=self.task_timeout
                        )
                    except asyncio.TimeoutError:
                        # Retry with error handler
                        result = await self.error_handler.retry_with_backoff(
                            agent.execute,
                            task,
                            context or {}
                        )
                    logger.debug(
                        "Agent execution completed",
                        extra={
                            "agent_type": agent_type,
                            "result_type": type(result).__name__,
                            "result_success": result.get("success") if isinstance(result, dict) else None,
                            "result_error": result.get("error") if isinstance(result, dict) else None,
                            "result_keys": list(result.keys()) if isinstance(result, dict) else []
                        }
                    )
                    
                    # Normalize agent result for frontend
                    normalized_result = self._normalize_agent_result(result, agent_type)
                    
                    response = {
                        "task": task,
                        "subtasks": [task],
                        "result": normalized_result,
                        "success": normalized_result.get("success", True),
                        "metadata": {
                            "agent_type": agent_type,
                            "agent_name": agent.name if hasattr(agent, 'name') else agent_type
                        }
                    }
                    
                    logger.debug(
                        "Orchestrator returning response",
                        extra={
                            "response_success": response.get("success"),
                            "response_error": response.get("error"),
                            "response_keys": list(response.keys())
                        }
                    )
                    
                    return response
                except asyncio.TimeoutError:
                    error_info = self.error_handler.handle_error(
                        asyncio.TimeoutError("Task execution timeout"),
                        {"task": task, "agent_type": agent_type}
                    )
                    logger.warning(
                        "Task execution timeout",
                        extra={
                            "error": "Task timeout",
                            "error_info": str(error_info)[:200]
                        }
                    )
                    return {
                        "task": task,
                        "error": "Task timeout",
                        "error_info": error_info,
                        "success": False
                    }
                except Exception as e:
                    logger.error(
                        "Exception in orchestrator agent execution",
                        extra={
                            "error_type": type(e).__name__,
                            "error_message": str(e)[:200],
                            "auto_recovery": self.auto_recovery
                        },
                        exc_info=True
                    )
                    if self.auto_recovery:
                        error_info = self.error_handler.handle_error(e, {"task": task})
                        logger.warning(f"Task failed, attempting recovery: {error_info}")
                        
                        # Recovery logic: try alternative agent or simplified approach
                        try:
                            # Try with react agent as fallback
                            fallback_agent = await self.agent_registry.get_agent("react")
                            if fallback_agent:
                                logger.info("Attempting recovery with react agent")
                                recovery_result = await fallback_agent.execute(
                                    f"Retry task with simplified approach: {task}",
                                    context or {}
                                )
                                if recovery_result.get("success"):
                                    logger.info("Recovery successful with react agent")
                                    return {
                                        "task": task,
                                        "subtasks": [task],
                                        "result": recovery_result,
                                        "success": True,
                                        "recovered": True,
                                        "recovery_method": "fallback_agent",
                                        "metadata": {
                                            "original_error": str(e)[:200],
                                            "recovery_agent": "react"
                                        }
                                    }
                        except Exception as recovery_error:
                            logger.error(f"Recovery attempt failed: {recovery_error}")
                    
                    raise
        
        # Execute subtasks
        if len(subtasks) > 1:
            return await self._execute_subtasks(subtasks, context)
        else:
            # Fallback to react agent
            agent = await self.agent_registry.get_agent("react")
            if agent:
                result = await agent.execute(task, context or {})
                normalized_result = self._normalize_agent_result(result, "react")
                return {
                    "task": task,
                    "subtasks": [task],
                    "result": normalized_result,
                    "success": normalized_result.get("success", True),
                    "metadata": {
                        "agent_type": "react",
                        "fallback": True
                    }
                }
        
        raise AILLMException("No suitable agent found for task")
    
    def _normalize_agent_result(self, result: Dict[str, Any], agent_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Normalize agent result to ensure consistent format for frontend
        
        Args:
            result: Raw agent result
            agent_type: Type of agent that produced the result
            
        Returns:
            Normalized result dictionary
        """
        if not isinstance(result, dict):
            return {
                "success": False,
                "error": f"Invalid result type: {type(result).__name__}",
                "raw_result": str(result)
            }
        
        # Ensure success field exists
        if "success" not in result:
            result["success"] = True
        
        # Normalize based on agent type
        normalized = {
            "success": result.get("success", True),
            "agent": result.get("agent", agent_type),
            "task": result.get("task", ""),
        }
        
        # Extract main content based on agent type
        if agent_type == "code_writer":
            normalized["code"] = result.get("code", "")
            normalized["language"] = result.get("language", "python")
            if result.get("requirements"):
                normalized["requirements"] = result["requirements"]
        elif agent_type == "research":
            normalized["report"] = result.get("report", "")
            normalized["findings"] = result.get("findings", [])
        elif agent_type == "data_analysis":
            normalized["analysis"] = result.get("analysis", "")
            if result.get("automl_result"):
                normalized["automl_result"] = result["automl_result"]
        elif agent_type == "react":
            normalized["answer"] = result.get("answer", result.get("result", ""))
            normalized["iterations"] = result.get("iterations", 0)
            normalized["actions"] = result.get("actions", [])
        elif agent_type == "workflow":
            normalized["workflow"] = result.get("workflow", "")
            normalized["steps_executed"] = result.get("steps_executed", 0)
            normalized["results"] = result.get("results", [])
        else:
            # Generic normalization
            if "code" in result:
                normalized["code"] = result["code"]
            if "report" in result:
                normalized["report"] = result["report"]
            if "analysis" in result:
                normalized["analysis"] = result["analysis"]
            if "result" in result:
                normalized["result"] = result["result"]
        
        # Add error if present
        if result.get("error"):
            normalized["error"] = result["error"]
            normalized["success"] = False
        
        # Preserve metadata
        if result.get("metadata"):
            normalized["metadata"] = result["metadata"]
        
        return normalized
    
    async def _decompose_task_llm(
        self,
        task: str,
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Decompose task using LLM with intelligent planning"""
        if not self.llm_manager:
            return [task]
        
        # Use LLM reasoning to understand task complexity and plan execution
        # Enable thinking mode for complex planning tasks
        prompt = f"""You are an expert project planner with deep analytical capabilities. Analyze the following task and determine the best execution approach using systematic reasoning.

Task: {task}

Think deeply and step by step:
1. What is the user trying to accomplish? Consider the underlying goals, not just the surface request.
2. Is this a simple task that can be done in one step, or a complex project? Analyze complexity factors:
   - Number of components involved
   - Interdependencies between parts
   - Required expertise level
   - Estimated scope and scale
3. If complex, what are the logical steps/phases needed? Consider:
   - Prerequisites and setup requirements
   - Core functionality implementation
   - Integration and testing needs
   - Documentation and deployment
4. What dependencies exist between steps? Map out the dependency graph.

For SIMPLE tasks (single function, small script, straightforward code generation):
- Return ONLY the original task, unchanged

For COMPLEX projects (applications, systems, frameworks, multi-file projects, games):
- Break into logical, actionable subtasks
- Order them by dependencies (setup before implementation, etc.)
- Each subtask should be specific and executable
- IMPORTANT: For code generation tasks (games, apps, systems), the FINAL subtask MUST be the actual code generation (e.g., "Generate the complete snake game code", "Implement the full application code")
- Do NOT create subtasks that are only analysis or planning - they should lead to actual code generation
- Consider: architecture, core features, integration, testing, documentation

Examples:
- Simple: "create a function to add two numbers" → return as-is
- Complex: "create a cloud storage system" → break into: setup project structure, implement API, add authentication, implement file storage, add UI, etc.
- Game: "generate a snake game" → break into: design game structure, implement game loop, add snake movement, add food generation, add collision detection, GENERATE THE COMPLETE SNAKE GAME CODE

Provide your response as a numbered list of subtasks, one per line. If the task is simple, return just the original task exactly as given."""

        messages = [
            LLMMessage(role="system", content="You are an intelligent project planner with exceptional reasoning capabilities. Use deep analytical thinking to understand tasks and plan execution. Think systematically about what the user wants to accomplish, analyze complexity factors, consider dependencies and edge cases, then determine if it's simple or complex, and plan accordingly. Always reason through the implications of your plan."),
            LLMMessage(role="user", content=prompt)
        ]
        
        try:
            # Use thinking mode for task decomposition (complex planning task)
            response = await self.llm_manager.generate(
                messages=messages,
                temperature=0.3,
                max_tokens=1500,  # Increased for complex projects
                thinking_mode=True  # Enable thinking mode for complex planning
            )
            
            # Parse subtasks with better extraction
            content = response.content.strip()
            
            # Проверяем, не является ли ответ JSON объектом от Ollama (ошибка парсинга)
            if content.startswith('{') and '"message"' in content:
                logger.warning("Received JSON object instead of task decomposition, treating as single task")
                return [task]
            
            lines = content.split("\n")
            subtasks = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Пропускаем строки, которые выглядят как JSON объекты
                if line.startswith('{') or line.startswith('"model"') or '"created_at"' in line:
                    continue
                
                # Remove various numbering formats (1., 1), - , *, etc.)
                import re
                # Remove leading numbers, dots, dashes, asterisks
                cleaned = re.sub(r'^[\d\s\.\)\-\*]+', '', line).strip()
                
                # Remove markdown list markers
                if cleaned.startswith("- "):
                    cleaned = cleaned[2:].strip()
                elif cleaned.startswith("* "):
                    cleaned = cleaned[2:].strip()
                
                # Пропускаем слишком короткие или подозрительные строки
                if cleaned and len(cleaned) > 10:  # Minimum meaningful length increased
                    # Пропускаем строки, которые выглядят как JSON поля
                    if not any(json_field in cleaned for json_field in ['"model"', '"created_at"', '"message"', '"role"', '"content"', '"done"']):
                        subtasks.append(cleaned)
            
            # Валидация количества подзадач
            if len(subtasks) > 20:
                logger.error(f"Invalid task decomposition: {len(subtasks)} subtasks detected. This is likely a parsing error.")
                logger.error(f"Response content preview: {content[:500]}")
                # Используем исходную задачу как одну подзадачу
                return [task]
            
            # Filter out pure analysis subtasks for code generation tasks
            code_gen_keywords = ["generate", "сгенерировать", "create", "создать", "write", "написать", "implement", "реализовать", "code", "код"]
            task_lower = task.lower()
            is_code_gen_task = any(keyword in task_lower for keyword in code_gen_keywords)
            
            if is_code_gen_task and len(subtasks) > 1:
                # Filter out subtasks that are only analysis/planning
                filtered_subtasks = []
                analysis_keywords = ["analyze", "анализ", "plan", "план", "think", "думать", "consider", "рассмотреть", "what is", "что такое"]
                
                for subtask in subtasks:
                    subtask_lower = subtask.lower()
                    # Skip pure analysis subtasks
                    is_analysis_only = any(keyword in subtask_lower for keyword in analysis_keywords) and not any(gen_keyword in subtask_lower for gen_keyword in code_gen_keywords)
                    
                    if not is_analysis_only:
                        filtered_subtasks.append(subtask)
                    else:
                        logger.debug(f"Filtered out analysis-only subtask: {subtask[:50]}")
                
                # If we filtered everything out, keep original task
                if filtered_subtasks:
                    logger.info(f"Decomposed task into {len(filtered_subtasks)} subtasks (filtered from {len(subtasks)})")
                    return filtered_subtasks
                else:
                    logger.warning("All subtasks were filtered out, using original task")
                    return [task]
            
            # If we got subtasks, return them; otherwise return original task
            if len(subtasks) > 1:
                logger.info(f"Decomposed task into {len(subtasks)} subtasks")
                return subtasks
            else:
                return [task]
                
        except Exception as e:
            logger.warning(f"Task decomposition failed: {e}")
            return [task]
    
    async def _select_agent(self, task: str) -> Optional[str]:
        """Select best agent for task using LLMClassifier (like Manus AI)"""
        # Use LLMClassifier if available (more reliable and cached)
        if self.llm_classifier:
            try:
                result = await self.llm_classifier.classify(
                    text=task,
                    classification_schema=AGENT_SELECTION_SCHEMA,
                    use_cache=True
                )
                
                if result.get("confidence", 0) > 0.7:
                    selected_agent = result.get("type", "react")
                    logger.info(f"LLMClassifier selected agent: {selected_agent} (confidence: {result.get('confidence', 0):.2f}) for task: {task[:50]}")
                    return selected_agent
            except Exception as e:
                logger.warning(f"LLMClassifier failed: {e}, falling back to direct LLM")
        
        # Fallback to direct LLM call if classifier not available or failed
        if not self.llm_manager:
            return "react"
        
        # Use LLM to understand the task and select the best agent
        prompt = f"""Analyze the following task and determine which agent should handle it using systematic reasoning.

Available agents:
- code_writer: For generating, writing, refactoring code, creating applications, games, scripts, functions, classes, modules
- research: For researching, analyzing information, finding documentation, understanding concepts
- data_analysis: For analyzing data, creating visualizations, statistical analysis, working with datasets
- workflow: For creating workflows, pipelines, automation processes
- react: For complex tasks requiring reasoning and tool usage, interactive problem solving
- integration: For integrating systems, APIs, services
- monitoring: For monitoring, logging, metrics collection

Task: {task}

Think deeply about:
1. What is the user trying to accomplish? Consider the underlying intent and goals.
2. What type of work is required? Analyze the nature of the task (creation, analysis, integration, etc.)
3. Which agent has the best capabilities for this task? Consider:
   - Primary task type and requirements
   - Complexity and scope
   - Required expertise and tools
   - Best fit based on agent strengths

Respond with ONLY the agent name (e.g., "code_writer", "research", etc.), no explanation."""

        messages = [
            LLMMessage(role="system", content="You are an intelligent task analyzer with deep reasoning capabilities. Analyze tasks systematically and select the most appropriate agent based on understanding the user's intent, task complexity, and agent capabilities. Think through the implications of your choice."),
            LLMMessage(role="user", content=prompt)
        ]
        
        try:
            # Используем SmartModelSelector для выбора оптимальной модели
            model_selection = None
            if self.model_selector:
                try:
                    model_selection = await self.model_selector.select_model(
                        task=task,
                        task_type=None,
                        complexity="low",  # Agent selection - простая задача
                        quality_requirement="fast"
                    )
                except Exception as e:
                    logger.warning(f"SmartModelSelector failed: {e}, using default")
            
            response = await self.llm_manager.generate(
                messages=messages,
                provider_name=model_selection.provider if model_selection else None,
                model=model_selection.model if model_selection else None,
                temperature=0.1,  # Low temperature for consistent selection
                max_tokens=50,
                thinking_mode=True  # Enable thinking for better agent selection
            )
            
            agent_name = response.content.strip().lower()
            
            # Remove any markdown formatting or extra text
            agent_name = agent_name.replace("`", "").replace("*", "").strip()
            
            # Validate agent name
            valid_agents = ["code_writer", "research", "data_analysis", "workflow", "react", "integration", "monitoring"]
            
            # Check if response contains a valid agent name
            for valid_agent in valid_agents:
                if valid_agent in agent_name:
                    logger.info(f"LLM selected agent: {valid_agent} for task: {task[:50]}")
                    return valid_agent
            
            # If no valid agent found, try to extract from response
            if "code" in agent_name or "writer" in agent_name:
                return "code_writer"
            elif "research" in agent_name:
                return "research"
            elif "data" in agent_name:
                return "data_analysis"
            elif "workflow" in agent_name:
                return "workflow"
            else:
                logger.warning(f"LLM returned unclear agent selection: {agent_name}, defaulting to react")
                return "react"
                
        except Exception as e:
            logger.warning(f"Failed to select agent using LLM: {e}, defaulting to react")
            return "react"
    
    async def _execute_subtasks(
        self,
        subtasks: List[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute multiple subtasks with context accumulation"""
        results = []
        accumulated_context = context.copy() if context else {}
        
        # For complex projects, execute sequentially to accumulate context
        # For independent tasks, can execute in parallel
        execute_parallel = len(subtasks) <= 3 and all(
            not any(keyword in subtask.lower() for keyword in [
                "setup", "initialize", "configure", "plan", "architecture",
                "настройка", "инициализация", "планирование", "архитектура"
            ])
            for subtask in subtasks
        )
        
        if execute_parallel:
            # Execute in parallel (limited by max_parallel_tasks)
            semaphore = asyncio.Semaphore(self.max_parallel_tasks)
            
            async def execute_subtask(subtask: str):
                async with semaphore:
                    agent_type = await self._select_agent(subtask)
                    agent = await self.agent_registry.get_agent(agent_type or "react")
                    if agent:
                        try:
                            result = await asyncio.wait_for(
                                agent.execute(subtask, accumulated_context),
                                timeout=self.task_timeout
                            )
                            normalized_result = self._normalize_agent_result(result, agent_type)
                            return {
                                "subtask": subtask,
                                "result": normalized_result,
                                "success": normalized_result.get("success", True)
                            }
                        except asyncio.TimeoutError:
                            return {"subtask": subtask, "error": "Timeout", "success": False}
                        except Exception as e:
                            logger.error(f"Subtask execution error: {e}")
                            return {"subtask": subtask, "error": str(e), "success": False}
                    return {"subtask": subtask, "error": "No agent", "success": False}
            
            tasks = [execute_subtask(subtask) for subtask in subtasks]
            gathered_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter exceptions
            for r in gathered_results:
                if isinstance(r, Exception):
                    logger.error(f"Subtask exception: {r}")
                    results.append({"error": str(r), "success": False})
                else:
                    results.append(r)
        else:
            # Execute sequentially to accumulate context
            logger.info(f"Executing {len(subtasks)} subtasks sequentially for context accumulation")
            
            for i, subtask in enumerate(subtasks):
                logger.info(f"Executing subtask {i+1}/{len(subtasks)}: {subtask[:50]}...")
                
                agent_type = await self._select_agent(subtask)
                agent = await self.agent_registry.get_agent(agent_type or "react")
                
                if agent:
                    try:
                        # Add previous results to context
                        if results:
                            accumulated_context["previous_results"] = results
                            accumulated_context["subtask_index"] = i
                            accumulated_context["total_subtasks"] = len(subtasks)
                        
                        result = await asyncio.wait_for(
                            agent.execute(subtask, accumulated_context),
                            timeout=self.task_timeout * 2  # More time for complex subtasks
                        )
                        
                        # Normalize result for consistency
                        normalized_result = self._normalize_agent_result(result, agent_type)
                        results.append({
                            "subtask": subtask,
                            "result": normalized_result,
                            "success": normalized_result.get("success", True),
                            "index": i
                        })
                        
                        # Accumulate successful results in context
                        if result.get("success") and isinstance(result.get("result"), dict):
                            if "code" in result["result"]:
                                accumulated_context.setdefault("generated_files", []).append({
                                    "subtask": subtask,
                                    "code": result["result"]["code"]
                                })
                            if "files" in result["result"]:
                                accumulated_context.setdefault("generated_files", []).extend(
                                    result["result"]["files"]
                                )
                        
                    except asyncio.TimeoutError:
                        logger.warning(f"Subtask {i+1} timeout: {subtask[:50]}")
                        results.append({
                            "subtask": subtask,
                            "error": "Timeout",
                            "success": False,
                            "index": i
                        })
                    except Exception as e:
                        logger.error(f"Subtask {i+1} execution error: {e}")
                        results.append({
                            "subtask": subtask,
                            "error": str(e),
                            "success": False,
                            "index": i
                        })
                else:
                    results.append({
                        "subtask": subtask,
                        "error": "No agent found",
                        "success": False,
                        "index": i
                    })
        
        return {
            "subtasks": subtasks,
            "results": results,
            "success": all(r.get("success", False) for r in results),
            "context_accumulated": not execute_parallel
        }
    
    def _is_code_generation_task(self, task: str) -> bool:
        """
        Unified detection of code generation tasks.
        
        Args:
            task: Task description
            
        Returns:
            True if task is a code generation request
        """
        task_lower = task.lower()
        
        # Keywords indicating code generation intent
        code_gen_markers = [
            "сгенерируй", "напиши", "создай", "создать", "написать", "реализуй",
            "generate", "create", "write", "build", "implement", "develop", "code"
        ]
        
        # Target keywords indicating what to generate
        target_markers = [
            "игра", "game", "приложение", "app", "application",
            "код", "code", "script", "скрипт", "программа", "program",
            "функци", "function", "класс", "class", "модуль", "module",
            "бот", "bot", "сервис", "service", "api", "сайт", "site", "web"
        ]
        
        has_gen_intent = any(marker in task_lower for marker in code_gen_markers)
        has_target = any(marker in task_lower for marker in target_markers)
        
        return has_gen_intent and has_target
    
    async def update_config(self, new_config: OrchestratorConfig) -> None:
        """
        Update orchestrator configuration dynamically.
        
        Args:
            new_config: New OrchestratorConfig
        """
        logger.info("Updating Orchestrator configuration...")
        
        self.config = new_config
        self.max_parallel_tasks = new_config.max_parallel_tasks
        self.task_timeout = new_config.task_timeout
        self.auto_recovery = new_config.auto_recovery
        
        logger.info(
            f"Orchestrator updated: max_parallel_tasks={self.max_parallel_tasks}, "
            f"task_timeout={self.task_timeout}, auto_recovery={self.auto_recovery}"
        )
    
    async def shutdown(self) -> None:
        """Shutdown orchestrator"""
        self._initialized = False

