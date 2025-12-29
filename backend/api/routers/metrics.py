"""
Metrics router
"""

from fastapi import APIRouter, Request

from ...core.metrics import metrics_collector

router = APIRouter()


@router.get("/metrics/stats")
async def get_stats(request: Request):
    """Получить статистику производительности"""
    return metrics_collector.get_all_stats()


@router.get("/metrics/agent/{agent_name}")
async def get_agent_stats(agent_name: str, request: Request):
    """Получить статистику для агента"""
    return metrics_collector.get_agent_stats(agent_name)


@router.get("/metrics/tool/{tool_name}")
async def get_tool_stats(tool_name: str, request: Request):
    """Получить статистику для инструмента"""
    return metrics_collector.get_tool_stats(tool_name)


@router.get("/metrics/llm/{provider}/{model}")
async def get_llm_stats(provider: str, model: str, request: Request):
    """Получить статистику для LLM провайдера/модели"""
    return metrics_collector.get_llm_stats(provider, model)


@router.get("/metrics/recent")
async def get_recent_metrics(minutes: int = 60, request: Request = None):
    """Получить метрики за последние N минут"""
    return metrics_collector.get_recent_metrics(minutes)


@router.post("/metrics/reset")
async def reset_metrics(request: Request):
    """Сбросить все метрики"""
    metrics_collector.reset()
    return {"message": "Метрики сброшены"}

