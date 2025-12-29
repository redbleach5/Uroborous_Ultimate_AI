"""
Batch processing for multiple tasks
"""

from typing import List, Dict, Any, Optional, Callable
import asyncio
import time
from dataclasses import dataclass
from .logger import get_logger
logger = get_logger(__name__)



@dataclass
class CircuitBreakerState:
    """State for circuit breaker pattern"""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    half_open_attempts: int = 0


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures in batch processing.
    
    States:
    - CLOSED: Normal operation, requests go through
    - OPEN: Too many failures, requests are rejected
    - HALF_OPEN: Testing if system recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        failure_rate_threshold: float = 0.5,
    ):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Successes needed to close circuit from half-open
            timeout: Seconds before trying half-open after circuit opens
            failure_rate_threshold: Failure rate (0-1) that triggers open
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.failure_rate_threshold = failure_rate_threshold
        self._state = CircuitBreakerState()
    
    def record_success(self):
        """Record a successful operation"""
        self._state.successes += 1
        
        if self._state.is_open:
            self._state.half_open_attempts += 1
            if self._state.half_open_attempts >= self.success_threshold:
                # Close the circuit
                self._state.is_open = False
                self._state.failures = 0
                self._state.half_open_attempts = 0
                logger.info("Circuit breaker CLOSED - system recovered")
    
    def record_failure(self):
        """Record a failed operation"""
        self._state.failures += 1
        self._state.last_failure_time = time.time()
        
        total = self._state.failures + self._state.successes
        if total >= 5:  # Minimum sample size
            failure_rate = self._state.failures / total
            if failure_rate >= self.failure_rate_threshold:
                if not self._state.is_open:
                    self._state.is_open = True
                    logger.warning(
                        f"Circuit breaker OPEN - failure rate {failure_rate:.0%} "
                        f"({self._state.failures}/{total} failed)"
                    )
        
        if self._state.failures >= self.failure_threshold:
            if not self._state.is_open:
                self._state.is_open = True
                logger.warning(
                    f"Circuit breaker OPEN - {self._state.failures} consecutive failures"
                )
    
    def is_allowed(self) -> bool:
        """Check if operation is allowed"""
        if not self._state.is_open:
            return True
        
        # Check if timeout has passed for half-open
        elapsed = time.time() - self._state.last_failure_time
        if elapsed >= self.timeout:
            logger.info("Circuit breaker HALF-OPEN - testing recovery")
            return True
        
        return False
    
    def get_state(self) -> str:
        """Get current circuit breaker state"""
        if not self._state.is_open:
            return "CLOSED"
        
        elapsed = time.time() - self._state.last_failure_time
        if elapsed >= self.timeout:
            return "HALF_OPEN"
        
        return "OPEN"
    
    def reset(self):
        """Reset circuit breaker to initial state"""
        self._state = CircuitBreakerState()


class BatchProcessor:
    """Process multiple tasks in batch with auto-scaling and circuit breaker support"""
    
    def __init__(
        self,
        max_concurrent: int = 10,
        model_selector: Optional[Any] = None,
        resource_aware: bool = True,
        resource_selector: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        circuit_breaker_enabled: bool = True,
    ):
        """
        Initialize batch processor
        
        Args:
            max_concurrent: Maximum concurrent tasks (base value)
            model_selector: SmartModelSelector для оптимизации выбора моделей
            resource_aware: Auto-scale based on available resources
            resource_selector: Внешний ResourceAwareSelector (предпочтительно)
            config: Конфигурация для создания ResourceAwareSelector
            circuit_breaker_enabled: Enable circuit breaker for failure protection
        """
        self.base_max_concurrent = max_concurrent
        self.max_concurrent = max_concurrent
        self.model_selector = model_selector
        self.resource_aware = resource_aware
        self._resource_selector = resource_selector
        self._config = config or {}
        
        # Circuit breaker for batch processing
        self.circuit_breaker_enabled = circuit_breaker_enabled
        cb_config = (config or {}).get("circuit_breaker", {})
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=cb_config.get("failure_threshold", 5),
            success_threshold=cb_config.get("success_threshold", 2),
            timeout=cb_config.get("timeout", 30.0),
            failure_rate_threshold=cb_config.get("failure_rate_threshold", 0.5),
        )
    
    async def _auto_scale_concurrent(self) -> int:
        """
        Автоматически масштабирует max_concurrent под доступные ресурсы
        Поддерживает multi-GPU конфигурации
        """
        if not self.resource_aware:
            return self.base_max_concurrent
        
        try:
            # Ленивая инициализация ResourceAwareSelector с конфигом
            if self._resource_selector is None:
                from .resource_aware_selector import ResourceAwareSelector
                self._resource_selector = ResourceAwareSelector(config=self._config)
            
            resources = await self._resource_selector.discover_resources()
            
            # Используем capacity из ResourceAwareSelector
            scaled_concurrent = max(self.base_max_concurrent, resources.estimated_capacity)
            
            if scaled_concurrent != self.max_concurrent:
                logger.info(
                    f"Auto-scaled max_concurrent: {self.max_concurrent} -> {scaled_concurrent} "
                    f"(GPUs: {resources.gpu_count}, VRAM: {resources.total_gpu_memory_gb or 0:.1f} GB)"
                )
                self.max_concurrent = scaled_concurrent
            
            return self.max_concurrent
        except Exception as e:
            logger.warning(f"Failed to auto-scale: {e}, using base value")
            return self.base_max_concurrent
    
    async def process_batch(
        self,
        tasks: List[Dict[str, Any]],
        processor: Callable,
        progress_callback: Optional[Callable] = None,
        stop_on_circuit_open: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of tasks with circuit breaker protection.
        
        Args:
            tasks: List of task dictionaries
            processor: Async function to process each task
            progress_callback: Optional callback for progress updates
            stop_on_circuit_open: Stop processing when circuit breaker opens
            
        Returns:
            List of results
        """
        # Авто-масштабирование под доступные ресурсы
        max_concurrent = await self._auto_scale_concurrent()
        semaphore = asyncio.Semaphore(min(max_concurrent, len(tasks)))
        results = []
        circuit_opened = False
        
        # Reset circuit breaker for new batch
        if self.circuit_breaker_enabled:
            self._circuit_breaker.reset()
        
        async def process_with_semaphore(task_data: Dict[str, Any], index: int):
            nonlocal circuit_opened
            
            # Check circuit breaker before processing
            if self.circuit_breaker_enabled and stop_on_circuit_open:
                if not self._circuit_breaker.is_allowed():
                    circuit_opened = True
                    return {
                        "index": index,
                        "task": task_data,
                        "result": None,
                        "success": False,
                        "error": "Circuit breaker open - batch processing stopped due to high failure rate",
                        "skipped": True,
                    }
            
            try:
                async with semaphore:
                    result = await processor(task_data)
                    
                    # Record success
                    if self.circuit_breaker_enabled:
                        self._circuit_breaker.record_success()
                    
                    return {
                        "index": index,
                        "task": task_data,
                        "result": result,
                        "success": True
                    }
            except Exception as e:
                logger.error(f"Error processing task {index}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                
                # Record failure
                if self.circuit_breaker_enabled:
                    self._circuit_breaker.record_failure()
                
                return {
                    "index": index,
                    "task": task_data,
                    "result": None,
                    "success": False,
                    "error": str(e)
                }
        
        # Process all tasks
        tasks_with_indices = [
            (task, i) for i, task in enumerate(tasks)
        ]
        
        coroutines = [
            process_with_semaphore(task, idx)
            for task, idx in tasks_with_indices
        ]
        
        # Execute with progress tracking and error handling
        completed = 0
        total = len(coroutines)
        
        try:
            for coro in asyncio.as_completed(coroutines):
                # Early exit if circuit opened
                if circuit_opened and stop_on_circuit_open:
                    # Cancel remaining tasks
                    remaining = total - completed
                    logger.warning(
                        f"Circuit breaker opened - skipping {remaining} remaining tasks"
                    )
                    # Add skipped results for remaining tasks
                    for i in range(completed, total):
                        results.append({
                            "index": i,
                            "task": {},
                            "result": None,
                            "success": False,
                            "error": "Skipped due to circuit breaker",
                            "skipped": True,
                        })
                    break
                
                try:
                    result = await coro
                    results.append(result)
                    completed += 1
                    
                    if progress_callback:
                        try:
                            await progress_callback(completed, total, result)
                        except Exception as e:
                            logger.warning(f"Progress callback error: {e}")
                except Exception as e:
                    logger.error(f"Error in coroutine: {e}")
                    
                    if self.circuit_breaker_enabled:
                        self._circuit_breaker.record_failure()
                    
                    results.append({
                        "index": completed,
                        "task": {},
                        "result": None,
                        "success": False,
                        "error": str(e)
                    })
                    completed += 1
        except Exception as e:
            logger.error(f"Critical error in batch processing: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        # Sort results by index
        results.sort(key=lambda x: x.get("index", 0))
        
        # Add circuit breaker status to batch result metadata
        if self.circuit_breaker_enabled:
            cb_state = self._circuit_breaker.get_state()
            if cb_state != "CLOSED":
                logger.warning(f"Batch completed with circuit breaker in {cb_state} state")
        
        return results
    
    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state and statistics"""
        return {
            "state": self._circuit_breaker.get_state(),
            "failures": self._circuit_breaker._state.failures,
            "successes": self._circuit_breaker._state.successes,
            "is_open": self._circuit_breaker._state.is_open,
        }
    
    async def process_tasks_batch(
        self,
        engine,
        tasks: List[str],
        agent_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Process batch of tasks using engine
        
        Args:
            engine: IDAEngine instance
            tasks: List of task strings
            agent_type: Optional agent type
            context: Optional context
            
        Returns:
            List of results
        """
        async def process_task(task_data: Dict[str, Any]):
            task = task_data["task"]
            return await engine.execute_task(
                task=task,
                agent_type=task_data.get("agent_type", agent_type),
                context=task_data.get("context", context or {})
            )
        
        task_list = [
            {"task": task, "agent_type": agent_type, "context": context}
            for task in tasks
        ]
        
        return await self.process_batch(task_list, process_task)
    
    async def process_code_generation_batch(
        self,
        engine,
        code_requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process batch of code generation requests
        
        Args:
            engine: IDAEngine instance
            code_requests: List of code request dictionaries
            
        Returns:
            List of results
        """
        async def process_code_request(request: Dict[str, Any]):
            # Не указываем agent_type жёстко - пусть система сама решает
            # Это позволяет batch обрабатывать разные типы задач
            return await engine.execute_task(
                task=request["task"],
                agent_type=request.get("agent_type"),  # Берём из запроса если есть
                context={
                    "file_path": request.get("file_path"),
                    "existing_code": request.get("existing_code"),
                    "requirements": request.get("requirements"),
                    "batch_mode": True
                }
            )
        
        return await self.process_batch(code_requests, process_code_request)

