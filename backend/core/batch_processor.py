"""
Batch processing for multiple tasks
"""

from typing import List, Dict, Any, Optional, Callable
import asyncio
from .logger import get_logger
logger = get_logger(__name__)

from .exceptions import AILLMException


class BatchProcessor:
    """Process multiple tasks in batch"""
    
    def __init__(
        self,
        max_concurrent: int = 10,  # Увеличено для 30 моделей
        model_selector: Optional[Any] = None
    ):
        """
        Initialize batch processor
        
        Args:
            max_concurrent: Maximum concurrent tasks (увеличено для 30 моделей)
            model_selector: SmartModelSelector для оптимизации выбора моделей
        """
        self.max_concurrent = max_concurrent
        self.model_selector = model_selector
    
    async def process_batch(
        self,
        tasks: List[Dict[str, Any]],
        processor: Callable,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of tasks
        
        Args:
            tasks: List of task dictionaries
            processor: Async function to process each task
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of results
        """
        semaphore = asyncio.Semaphore(min(self.max_concurrent, len(tasks)))
        results = []
        
        async def process_with_semaphore(task_data: Dict[str, Any], index: int):
            try:
                async with semaphore:
                    result = await processor(task_data)
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
        
        return results
    
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
            return await engine.execute_task(
                task=request["task"],
                agent_type="code_writer",
                context={
                    "file_path": request.get("file_path"),
                    "existing_code": request.get("existing_code"),
                    "requirements": request.get("requirements")
                }
            )
        
        return await self.process_batch(code_requests, process_code_request)

