"""
Learning API - Доступ к статистике обучения агентов

Позволяет:
- Получать статистику обучения по агентам
- Просматривать накопленный опыт
- Анализировать эффективность обучения
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from ...core.logger import get_logger
from ...core.learning_system import get_learning_system, initialize_learning_system

logger = get_logger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/stats", summary="Получить глобальную статистику обучения")
async def get_learning_stats() -> Dict[str, Any]:
    """
    Получает глобальную статистику обучения всех агентов.
    
    Returns:
        Статистика обучения включая:
        - Общее количество обученных задач
        - Success rate по агентам
        - Среднее качество результатов
    """
    try:
        learning_system = await initialize_learning_system()
        stats = await learning_system.get_global_learning_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get learning stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/{agent_name}", summary="Получить статистику агента")
async def get_agent_learning(agent_name: str) -> Dict[str, Any]:
    """
    Получает детальную статистику обучения конкретного агента.
    
    Args:
        agent_name: Имя агента (code_writer, research, react, etc.)
    
    Returns:
        Статистика агента с рекомендациями по улучшению
    """
    try:
        learning_system = await initialize_learning_system()
        insights = await learning_system.get_agent_insights(agent_name)
        
        return {
            "success": True,
            "agent": agent_name,
            "insights": insights
        }
        
    except Exception as e:
        logger.error(f"Failed to get agent learning stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/{agent_name}", summary="Получить рекомендации для агента")
async def get_agent_recommendations(
    agent_name: str,
    task: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получает рекомендации по улучшению промптов для агента
    на основе накопленного опыта.
    
    Args:
        agent_name: Имя агента
        task: Опциональное описание задачи для контекстных рекомендаций
    
    Returns:
        Рекомендации по улучшению
    """
    try:
        learning_system = await initialize_learning_system()
        
        result = {
            "success": True,
            "agent": agent_name,
            "recommendations": []
        }
        
        # Получаем insights
        insights = await learning_system.get_agent_insights(agent_name)
        if insights.get("recommendations"):
            result["recommendations"] = insights["recommendations"]
        
        # Если есть задача, получаем контекстное улучшение промпта
        if task:
            enhancement = await learning_system.get_prompt_enhancement(agent_name, task)
            if enhancement:
                result["prompt_enhancement"] = enhancement
            
            # Ищем похожее успешное решение
            similar = await learning_system.get_similar_successful_solution(agent_name, task)
            if similar:
                result["similar_solution"] = similar
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress", summary="Получить прогресс обучения")
async def get_learning_progress() -> Dict[str, Any]:
    """
    Получает общий прогресс обучения системы.
    
    Returns:
        Прогресс обучения с трендами
    """
    try:
        learning_system = await initialize_learning_system()
        stats = await learning_system.get_global_learning_stats()
        
        # Рассчитываем прогресс
        total_tasks = stats.get("total_tasks_learned", 0)
        success_rate = stats.get("global_success_rate", 0)
        
        # Определяем уровень обучения
        if total_tasks < 10:
            level = "начальный"
            level_description = "Система только начинает накапливать опыт"
        elif total_tasks < 50:
            level = "базовый"
            level_description = "Система накапливает базовые паттерны"
        elif total_tasks < 200:
            level = "продвинутый"
            level_description = "Система активно обучается на основе опыта"
        else:
            level = "экспертный"
            level_description = "Система имеет богатый опыт для оптимизации"
        
        # Качество обучения
        if success_rate >= 0.9:
            quality = "отличное"
        elif success_rate >= 0.75:
            quality = "хорошее"
        elif success_rate >= 0.6:
            quality = "среднее"
        else:
            quality = "требует улучшения"
        
        return {
            "success": True,
            "progress": {
                "total_experience": total_tasks,
                "success_rate": success_rate,
                "level": level,
                "level_description": level_description,
                "quality": quality,
                "agents_learning": stats.get("agents_count", 0),
                "total_successful": stats.get("total_successful", 0),
                "total_retries": stats.get("total_retries", 0)
            },
            "agents_summary": {
                name: {
                    "tasks": data.get("total_tasks", 0),
                    "success_rate": data.get("success_rate", 0),
                    "avg_quality": data.get("avg_quality_score", 0)
                }
                for name, data in stats.get("agents", {}).items()
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get learning progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

