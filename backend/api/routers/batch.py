"""
Batch processing router
"""

from fastapi import APIRouter, HTTPException, Request
from typing import List, Dict, Any
from pydantic import BaseModel

router = APIRouter()


class BatchTaskRequest(BaseModel):
    tasks: List[str]
    agent_type: str = None
    context: Dict[str, Any] = {}


class BatchCodeRequest(BaseModel):
    requests: List[Dict[str, Any]]


@router.post("/batch/tasks")
async def process_batch_tasks(request: Request, batch_request: BatchTaskRequest):
    """Обработать пакет задач"""
    engine = request.app.state.engine
    
    if not engine or not engine.batch_processor:
        raise HTTPException(status_code=503, detail="Движок или batch processor не инициализирован")
    
    try:
        results = await engine.batch_processor.process_tasks_batch(
            engine=engine,
            tasks=batch_request.tasks,
            agent_type=batch_request.agent_type,
            context=batch_request.context
        )
        
        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/code")
async def process_batch_code(request: Request, batch_request: BatchCodeRequest):
    """Обработать пакет запросов на генерацию кода"""
    engine = request.app.state.engine
    
    if not engine or not engine.batch_processor:
        raise HTTPException(status_code=503, detail="Движок или batch processor не инициализирован")
    
    try:
        results = await engine.batch_processor.process_code_generation_batch(
            engine=engine,
            code_requests=batch_request.requests
        )
        
        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

