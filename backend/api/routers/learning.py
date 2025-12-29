"""
Learning API - Доступ к статистике обучения агентов

Позволяет:
- Получать статистику обучения по агентам
- Просматривать накопленный опыт
- Анализировать эффективность обучения
- Управлять пользовательскими предпочтениями
- Получать рекомендации по моделям
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional

from ...core.logger import get_logger
from ...core.learning_system import initialize_learning_system

logger = get_logger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])


class UserPreference(BaseModel):
    """Модель для установки пользовательского предпочтения"""
    key: str
    value: Any
    user_id: str = "default"


class UserPreferencesUpdate(BaseModel):
    """Модель для массового обновления предпочтений"""
    preferences: Dict[str, Any]
    user_id: str = "default"


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


# ==================== USER PREFERENCES ====================

@router.get("/preferences", summary="Получить предпочтения пользователя")
async def get_user_preferences(
    request: Request,
    user_id: str = "default"
) -> Dict[str, Any]:
    """
    Получает все сохраненные предпочтения пользователя.
    
    Args:
        user_id: ID пользователя (default для общих настроек)
    
    Returns:
        Словарь с предпочтениями пользователя
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            return {
                "success": True,
                "user_id": user_id,
                "preferences": {},
                "message": "Memory system not initialized"
            }
        
        preferences = await engine.memory.get_all_user_preferences(user_id)
        
        return {
            "success": True,
            "user_id": user_id,
            "preferences": preferences
        }
        
    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preferences", summary="Установить предпочтение пользователя")
async def set_user_preference(
    request: Request,
    pref: UserPreference
) -> Dict[str, Any]:
    """
    Устанавливает предпочтение пользователя.
    
    Доступные ключи:
    - language: "ru" или "en"
    - code_style: "pythonic", "verbose", "minimal"
    - detail_level: "brief", "detailed", "exhaustive"
    - preferred_frameworks: ["fastapi", "django", ...]
    - response_format: "markdown", "plain"
    
    Args:
        pref: Объект с ключом, значением и user_id
    
    Returns:
        Подтверждение сохранения
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            raise HTTPException(status_code=503, detail="Memory system not initialized")
        
        await engine.memory.save_user_preference(
            key=pref.key,
            value=pref.value,
            user_id=pref.user_id
        )
        
        return {
            "success": True,
            "message": f"Preference '{pref.key}' saved",
            "user_id": pref.user_id,
            "key": pref.key,
            "value": pref.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set user preference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/preferences", summary="Обновить несколько предпочтений")
async def update_user_preferences(
    request: Request,
    prefs: UserPreferencesUpdate
) -> Dict[str, Any]:
    """
    Обновляет несколько предпочтений пользователя за один запрос.
    
    Args:
        prefs: Объект со словарем предпочтений и user_id
    
    Returns:
        Подтверждение сохранения
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            raise HTTPException(status_code=503, detail="Memory system not initialized")
        
        for key, value in prefs.preferences.items():
            await engine.memory.save_user_preference(
                key=key,
                value=value,
                user_id=prefs.user_id
            )
        
        return {
            "success": True,
            "message": f"Updated {len(prefs.preferences)} preferences",
            "user_id": prefs.user_id,
            "keys": list(prefs.preferences.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MEMORY STATS ====================

@router.get("/memory/stats", summary="Получить статистику памяти")
async def get_memory_stats(request: Request) -> Dict[str, Any]:
    """
    Получает полную статистику долгосрочной памяти.
    
    Returns:
        Статистика включая:
        - Количество сохраненных решений
        - Количество failed задач
        - Рекомендации моделей по типам задач
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            return {
                "success": True,
                "stats": {},
                "message": "Memory system not initialized"
            }
        
        stats = await engine.memory.get_learning_stats()
        model_recommendations = await engine.memory.get_model_task_recommendations()
        
        return {
            "success": True,
            "stats": stats,
            "model_recommendations": model_recommendations
        }
        
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/models", summary="Получить рекомендации моделей")
async def get_model_recommendations(
    request: Request,
    task_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получает рекомендации моделей на основе исторической производительности.
    
    Args:
        task_type: Опциональный фильтр по типу задачи (code, chat, analysis, reasoning, creative)
    
    Returns:
        Рекомендации моделей с метриками
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            return {
                "success": True,
                "recommendations": {},
                "message": "Memory system not initialized"
            }
        
        if task_type:
            best = await engine.memory.get_best_model_for_task_type(task_type)
            return {
                "success": True,
                "task_type": task_type,
                "recommendation": best
            }
        else:
            recommendations = await engine.memory.get_model_task_recommendations()
            return {
                "success": True,
                "recommendations": recommendations
            }
        
    except Exception as e:
        logger.error(f"Failed to get model recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/failed", summary="Получить failed задачи")
async def get_failed_tasks(
    request: Request,
    agent: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Получает список неудачных задач для анализа.
    
    Args:
        agent: Опциональный фильтр по агенту
        limit: Максимальное количество записей
    
    Returns:
        Список failed задач с информацией об ошибках
    """
    try:
        engine = getattr(request.app.state, "engine", None)
        if not engine or not engine.memory:
            return {
                "success": True,
                "failed_tasks": [],
                "message": "Memory system not initialized"
            }
        
        # Query failed tasks directly
        query = "SELECT task, agent, error_type, error_message, occurrence_count, created_at FROM failed_tasks"
        params = []
        if agent:
            query += " WHERE agent = ?"
            params.append(agent)
        query += " ORDER BY occurrence_count DESC, created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = await engine.memory.db.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        
        failed_tasks = [
            {
                "task": row[0][:200] + "..." if len(row[0]) > 200 else row[0],
                "agent": row[1],
                "error_type": row[2],
                "error_message": row[3],
                "occurrence_count": row[4],
                "created_at": row[5]
            }
            for row in rows
        ]
        
        return {
            "success": True,
            "count": len(failed_tasks),
            "failed_tasks": failed_tasks
        }
        
    except Exception as e:
        logger.error(f"Failed to get failed tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

