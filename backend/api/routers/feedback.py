"""
Feedback API - Сбор обратной связи для обучения системы
Позволяет оценивать качество решений и улучшать работу агентов.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiosqlite
from pathlib import Path

from ...core.logger import get_logger
from ...core.model_performance_tracker import get_performance_tracker

logger = get_logger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

# Database path
FEEDBACK_DB_PATH = Path("memory/feedback.db")


class SolutionFeedback(BaseModel):
    """Обратная связь о качестве решения"""
    solution_id: Optional[str] = None  # ID решения (если есть)
    task: str = Field(..., description="Исходная задача")
    solution: str = Field(..., description="Полученное решение")
    rating: int = Field(..., ge=1, le=5, description="Оценка от 1 до 5")
    is_helpful: bool = Field(..., description="Было ли решение полезным")
    comments: Optional[str] = None
    agent: Optional[str] = None  # Какой агент создал решение
    model: Optional[str] = None  # Какая модель использовалась
    provider: Optional[str] = None  # Какой провайдер


class ModelFeedback(BaseModel):
    """Обратная связь о качестве работы модели"""
    provider: str
    model: str
    task_type: str = Field(..., description="Тип задачи (code, chat, analysis)")
    rating: int = Field(..., ge=1, le=5)
    response_quality: int = Field(..., ge=1, le=5, description="Качество ответа")
    speed_satisfaction: int = Field(..., ge=1, le=5, description="Удовлетворенность скоростью")
    comments: Optional[str] = None


class FeedbackStats(BaseModel):
    """Статистика обратной связи"""
    total_feedbacks: int
    avg_rating: float
    helpful_percentage: float
    by_agent: Dict[str, Dict[str, Any]]
    by_model: Dict[str, Dict[str, Any]]
    recent_trends: List[Dict[str, Any]]


async def get_feedback_db() -> aiosqlite.Connection:
    """Получить соединение с базой feedback"""
    FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(FEEDBACK_DB_PATH))
    await db.execute("PRAGMA journal_mode=WAL")
    
    # Создаем таблицы
    await db.execute("""
        CREATE TABLE IF NOT EXISTS solution_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            solution_id TEXT,
            task TEXT NOT NULL,
            solution TEXT NOT NULL,
            rating INTEGER NOT NULL,
            is_helpful INTEGER NOT NULL,
            comments TEXT,
            agent TEXT,
            model TEXT,
            provider TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await db.execute("""
        CREATE TABLE IF NOT EXISTS model_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            task_type TEXT NOT NULL,
            rating INTEGER NOT NULL,
            response_quality INTEGER NOT NULL,
            speed_satisfaction INTEGER NOT NULL,
            comments TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_solution_feedback_agent 
        ON solution_feedback(agent)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_solution_feedback_model 
        ON solution_feedback(provider, model)
    """)
    
    await db.commit()
    return db


@router.post("/solution", summary="Отправить feedback о решении")
async def submit_solution_feedback(
    feedback: SolutionFeedback,
    request: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Отправить обратную связь о качестве решения.
    Это помогает системе учиться и улучшать качество ответов.
    
    Feedback используется для:
    - Обновления quality_score в Long-Term Memory
    - Корректировки performance_score моделей
    - Генерации рекомендаций по улучшению
    """
    try:
        db = await get_feedback_db()
        
        await db.execute("""
            INSERT INTO solution_feedback 
            (solution_id, task, solution, rating, is_helpful, comments, agent, model, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feedback.solution_id,
            feedback.task[:1000],  # Ограничиваем размер
            feedback.solution[:5000],
            feedback.rating,
            1 if feedback.is_helpful else 0,
            feedback.comments,
            feedback.agent,
            feedback.model,
            feedback.provider
        ))
        await db.commit()
        await db.close()
        
        memory_updated = False
        
        # Обновляем качество в Long-Term Memory если есть solution_id
        if feedback.solution_id:
            try:
                # Получаем engine из app state
                from fastapi import Request
                if hasattr(request, 'app') and hasattr(request.app, 'state'):
                    engine = getattr(request.app.state, 'engine', None)
                    if engine and hasattr(engine, 'memory') and engine.memory:
                        memory_id = int(feedback.solution_id)
                        await engine.memory.update_solution_feedback(
                            memory_id=memory_id,
                            rating=feedback.rating,
                            is_helpful=feedback.is_helpful
                        )
                        memory_updated = True
            except (ValueError, AttributeError) as e:
                logger.debug(f"Could not update long-term memory: {e}")
        
        # Обновляем метрики модели если указана
        if feedback.model and feedback.provider:
            tracker = get_performance_tracker()
            # Влияем на performance score через feedback
            # Высокий рейтинг = положительный эффект
            quality_boost = (feedback.rating - 3) * 0.1  # -0.2 to +0.2
            metrics = tracker.get_metrics(feedback.provider, feedback.model)
            metrics.performance_score = max(0, min(100, 
                metrics.performance_score + quality_boost * 10
            ))
        
        logger.info(f"Received solution feedback: rating={feedback.rating}, helpful={feedback.is_helpful}, memory_updated={memory_updated}")
        
        return {
            "success": True,
            "message": "Спасибо за обратную связь! Это поможет улучшить систему.",
            "rating_applied": True,
            "memory_updated": memory_updated
        }
        
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model", summary="Отправить feedback о модели")
async def submit_model_feedback(feedback: ModelFeedback) -> Dict[str, Any]:
    """
    Отправить обратную связь о качестве работы модели.
    """
    try:
        db = await get_feedback_db()
        
        await db.execute("""
            INSERT INTO model_feedback 
            (provider, model, task_type, rating, response_quality, speed_satisfaction, comments)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            feedback.provider,
            feedback.model,
            feedback.task_type,
            feedback.rating,
            feedback.response_quality,
            feedback.speed_satisfaction,
            feedback.comments
        ))
        await db.commit()
        await db.close()
        
        # Обновляем метрики модели
        tracker = get_performance_tracker()
        metrics = tracker.get_metrics(feedback.provider, feedback.model)
        
        # Комплексная корректировка score на основе feedback
        avg_satisfaction = (feedback.rating + feedback.response_quality + feedback.speed_satisfaction) / 3
        adjustment = (avg_satisfaction - 3) * 2  # -4 to +4
        metrics.performance_score = max(0, min(100, 
            metrics.performance_score + adjustment
        ))
        
        logger.info(f"Received model feedback: {feedback.provider}/{feedback.model}, rating={feedback.rating}")
        
        return {
            "success": True,
            "message": "Feedback о модели сохранен",
            "score_adjustment": adjustment
        }
        
    except Exception as e:
        logger.error(f"Failed to save model feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="Получить статистику feedback")
async def get_feedback_stats() -> Dict[str, Any]:
    """
    Получить агрегированную статистику обратной связи.
    Полезно для анализа качества работы системы.
    """
    try:
        db = await get_feedback_db()
        
        stats = {
            "solution_feedback": {},
            "model_feedback": {},
            "learning_insights": {}
        }
        
        # Статистика по решениям
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(rating) as avg_rating,
                SUM(is_helpful) * 100.0 / COUNT(*) as helpful_pct
            FROM solution_feedback
        """) as cursor:
            row = await cursor.fetchone()
            if row:
                stats["solution_feedback"]["total"] = row[0]
                stats["solution_feedback"]["avg_rating"] = round(row[1] or 0, 2)
                stats["solution_feedback"]["helpful_percentage"] = round(row[2] or 0, 1)
        
        # Статистика по агентам
        async with db.execute("""
            SELECT 
                agent,
                COUNT(*) as count,
                AVG(rating) as avg_rating,
                SUM(is_helpful) * 100.0 / COUNT(*) as helpful_pct
            FROM solution_feedback
            WHERE agent IS NOT NULL
            GROUP BY agent
        """) as cursor:
            agent_stats = {}
            async for row in cursor:
                agent_stats[row[0]] = {
                    "count": row[1],
                    "avg_rating": round(row[2] or 0, 2),
                    "helpful_percentage": round(row[3] or 0, 1)
                }
            stats["solution_feedback"]["by_agent"] = agent_stats
        
        # Статистика по моделям
        async with db.execute("""
            SELECT 
                provider || '/' || model as model_key,
                COUNT(*) as count,
                AVG(rating) as avg_rating,
                AVG(response_quality) as avg_quality,
                AVG(speed_satisfaction) as avg_speed
            FROM model_feedback
            GROUP BY provider, model
        """) as cursor:
            model_stats = {}
            async for row in cursor:
                model_stats[row[0]] = {
                    "count": row[1],
                    "avg_rating": round(row[2] or 0, 2),
                    "avg_quality": round(row[3] or 0, 2),
                    "avg_speed": round(row[4] or 0, 2)
                }
            stats["model_feedback"]["by_model"] = model_stats
        
        # Тренды последних 7 дней
        async with db.execute("""
            SELECT 
                DATE(created_at) as day,
                COUNT(*) as count,
                AVG(rating) as avg_rating
            FROM solution_feedback
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """) as cursor:
            trends = []
            async for row in cursor:
                trends.append({
                    "date": row[0],
                    "count": row[1],
                    "avg_rating": round(row[2] or 0, 2)
                })
            stats["solution_feedback"]["recent_trends"] = trends
        
        # Инсайты для обучения
        tracker = get_performance_tracker()
        stats["learning_insights"] = await tracker.get_learning_insights()
        
        await db.close()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations", summary="Получить рекомендации на основе feedback")
async def get_recommendations() -> Dict[str, Any]:
    """
    Получить рекомендации по улучшению системы на основе накопленного feedback.
    """
    try:
        db = await get_feedback_db()
        recommendations = []
        
        # Анализ слабых агентов
        async with db.execute("""
            SELECT agent, AVG(rating) as avg_rating, COUNT(*) as count
            FROM solution_feedback
            WHERE agent IS NOT NULL
            GROUP BY agent
            HAVING count >= 5 AND avg_rating < 3.5
        """) as cursor:
            async for row in cursor:
                recommendations.append({
                    "type": "agent_improvement",
                    "agent": row[0],
                    "avg_rating": round(row[1], 2),
                    "sample_size": row[2],
                    "suggestion": f"Агент {row[0]} имеет низкий рейтинг ({row[1]:.2f}). "
                                  f"Рассмотрите улучшение промптов или смену модели."
                })
        
        # Анализ слабых моделей
        async with db.execute("""
            SELECT provider, model, AVG(rating) as avg_rating, 
                   AVG(response_quality) as quality, COUNT(*) as count
            FROM model_feedback
            GROUP BY provider, model
            HAVING count >= 3 AND avg_rating < 3.0
        """) as cursor:
            async for row in cursor:
                recommendations.append({
                    "type": "model_concern",
                    "provider": row[0],
                    "model": row[1],
                    "avg_rating": round(row[2], 2),
                    "quality": round(row[3], 2),
                    "sample_size": row[4],
                    "suggestion": f"Модель {row[0]}/{row[1]} показывает низкое качество. "
                                  f"Рассмотрите альтернативные модели."
                })
        
        # Общие рекомендации
        async with db.execute("""
            SELECT AVG(rating), AVG(is_helpful) 
            FROM solution_feedback
        """) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                avg_rating = row[0]
                helpful_rate = row[1] * 100
                
                if avg_rating < 3.5:
                    recommendations.append({
                        "type": "general",
                        "suggestion": f"Общий рейтинг решений ({avg_rating:.2f}) ниже целевого (3.5). "
                                      f"Рассмотрите улучшение системных промптов."
                    })
                
                if helpful_rate < 70:
                    recommendations.append({
                        "type": "general",
                        "suggestion": f"Только {helpful_rate:.1f}% решений считаются полезными. "
                                      f"Улучшите понимание контекста задач."
                    })
        
        await db.close()
        
        # Добавляем инсайты от performance tracker
        tracker = get_performance_tracker()
        insights = await tracker.get_learning_insights()
        
        for rec in insights.get("recommendations", []):
            recommendations.append({
                "type": "performance",
                "suggestion": rec
            })
        
        return {
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
            "total_recommendations": len(recommendations)
        }
        
    except Exception as e:
        logger.error(f"Failed to generate recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

