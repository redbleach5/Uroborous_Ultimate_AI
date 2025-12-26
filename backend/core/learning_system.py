"""
LearningSystem - Персистентная система обучения агентов

Сохраняет и использует накопленный опыт:
1. Результаты рефлексии для каждой задачи
2. Успешные решения и паттерны
3. Типичные ошибки и способы их исправления
4. Адаптивные рекомендации для промптов
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    aiosqlite = None

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentLearningStats:
    """Статистика обучения агента"""
    agent_name: str
    total_tasks: int = 0
    successful_tasks: int = 0
    retry_count: int = 0
    avg_quality_score: float = 0.0
    avg_completeness: float = 0.0
    avg_correctness: float = 0.0
    common_issues: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    successful_patterns: List[str] = field(default_factory=list)
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": self.successful_tasks / max(self.total_tasks, 1),
            "retry_count": self.retry_count,
            "avg_retry_rate": self.retry_count / max(self.total_tasks, 1),
            "avg_quality_score": self.avg_quality_score,
            "avg_completeness": self.avg_completeness,
            "avg_correctness": self.avg_correctness,
            "common_issues": dict(self.common_issues),
            "successful_patterns": self.successful_patterns[:10],
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }


class LearningSystem:
    """
    Система обучения с персистентностью в SQLite.
    
    Сохраняет:
    - Результаты рефлексии для анализа
    - Успешные паттерны для переиспользования
    - Ошибки для предотвращения
    - Рекомендации по улучшению
    """
    
    def __init__(self, db_path: str = "memory/learning.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db: Optional[aiosqlite.Connection] = None
        self._initialized = False
        
        # Кэш статистики агентов
        self._agent_stats: Dict[str, AgentLearningStats] = {}
        
        # Кэш успешных промптов
        self._successful_prompts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # Частые проблемы и их решения
        self._issue_solutions: Dict[str, List[str]] = defaultdict(list)
    
    async def initialize(self) -> None:
        """Инициализация базы данных обучения"""
        if self._initialized:
            return
        
        if not AIOSQLITE_AVAILABLE:
            logger.warning("aiosqlite not available, learning will not persist")
            self._initialized = True
            return
        
        try:
            self.db = await aiosqlite.connect(str(self.db_path))
            await self.db.execute("PRAGMA journal_mode=WAL")
            
            # Таблица результатов рефлексии
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS reflection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task TEXT NOT NULL,
                    task_hash TEXT,
                    completeness REAL DEFAULT 0,
                    correctness REAL DEFAULT 0,
                    quality REAL DEFAULT 0,
                    overall_score REAL DEFAULT 0,
                    quality_level TEXT,
                    issues TEXT DEFAULT '[]',
                    improvements TEXT DEFAULT '[]',
                    was_corrected INTEGER DEFAULT 0,
                    correction_attempts INTEGER DEFAULT 1,
                    execution_time REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица успешных решений (для переиспользования паттернов)
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS successful_solutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task_type TEXT,
                    task_pattern TEXT,
                    solution_snippet TEXT,
                    quality_score REAL,
                    reuse_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_used TEXT
                )
            """)
            
            # Таблица адаптивных рекомендаций для промптов
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS prompt_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task_type TEXT,
                    recommendation TEXT NOT NULL,
                    effectiveness_score REAL DEFAULT 0,
                    use_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица паттернов ошибок и решений
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS error_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT,
                    error_pattern TEXT NOT NULL,
                    solution_pattern TEXT,
                    occurrence_count INTEGER DEFAULT 1,
                    resolved_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_name, error_pattern)
                )
            """)
            
            # Индексы
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_reflection_agent ON reflection_history(agent_name)"
            )
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_reflection_score ON reflection_history(overall_score DESC)"
            )
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_solutions_agent ON successful_solutions(agent_name)"
            )
            
            await self.db.commit()
            
            # Загружаем кэши
            await self._load_caches()
            
            self._initialized = True
            logger.info(f"LearningSystem initialized with {len(self._agent_stats)} agents in cache")
            
        except Exception as e:
            logger.error(f"Failed to initialize LearningSystem: {e}")
            self._initialized = True  # Продолжаем в memory-only режиме
    
    async def _load_caches(self) -> None:
        """Загрузка кэшей из базы данных"""
        if not self.db:
            return
        
        try:
            # Загружаем статистику агентов
            async with self.db.execute("""
                SELECT agent_name, 
                       COUNT(*) as total,
                       SUM(CASE WHEN overall_score >= 70 THEN 1 ELSE 0 END) as successful,
                       SUM(correction_attempts - 1) as retries,
                       AVG(overall_score) as avg_score,
                       AVG(completeness) as avg_completeness,
                       AVG(correctness) as avg_correctness,
                       MAX(created_at) as last_updated
                FROM reflection_history
                GROUP BY agent_name
            """) as cursor:
                async for row in cursor:
                    agent_name = row[0]
                    self._agent_stats[agent_name] = AgentLearningStats(
                        agent_name=agent_name,
                        total_tasks=row[1],
                        successful_tasks=row[2] or 0,
                        retry_count=row[3] or 0,
                        avg_quality_score=row[4] or 0,
                        avg_completeness=row[5] or 0,
                        avg_correctness=row[6] or 0,
                        last_updated=datetime.fromisoformat(row[7]) if row[7] else None
                    )
            
            # Загружаем частые проблемы
            async with self.db.execute("""
                SELECT agent_name, issues
                FROM reflection_history
                WHERE overall_score < 70
                ORDER BY created_at DESC
                LIMIT 500
            """) as cursor:
                async for row in cursor:
                    agent_name, issues_json = row
                    try:
                        issues = json.loads(issues_json or "[]")
                        if agent_name in self._agent_stats:
                            for issue in issues[:3]:  # Берём до 3 проблем
                                self._agent_stats[agent_name].common_issues[issue] += 1
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass
            
            # Загружаем успешные паттерны
            async with self.db.execute("""
                SELECT agent_name, task_pattern, quality_score
                FROM successful_solutions
                WHERE quality_score >= 85
                ORDER BY quality_score DESC
                LIMIT 100
            """) as cursor:
                async for row in cursor:
                    agent_name, pattern, score = row
                    self._successful_prompts[agent_name].append({
                        "pattern": pattern,
                        "score": score
                    })
                    
        except Exception as e:
            logger.error(f"Failed to load learning caches: {e}")
    
    async def record_reflection(
        self,
        agent_name: str,
        task: str,
        reflection: Dict[str, Any],
        was_corrected: bool = False,
        correction_attempts: int = 1,
        execution_time: float = 0,
        solution_snippet: Optional[str] = None
    ) -> None:
        """
        Записывает результат рефлексии для обучения.
        
        Args:
            agent_name: Имя агента
            task: Исходная задача
            reflection: Данные рефлексии
            was_corrected: Был ли результат исправлен
            correction_attempts: Количество попыток
            execution_time: Время выполнения
            solution_snippet: Фрагмент успешного решения для few-shot learning
        """
        if not self._initialized:
            await self.initialize()
        
        completeness = reflection.get("completeness", 0)
        correctness = reflection.get("correctness", 0)
        quality = reflection.get("quality", 0)
        overall_score = reflection.get("overall_score", 0)
        quality_level = reflection.get("quality_level", "unknown")
        issues = reflection.get("issues", [])
        improvements = reflection.get("improvements", [])
        
        # Обновляем кэш статистики
        if agent_name not in self._agent_stats:
            self._agent_stats[agent_name] = AgentLearningStats(agent_name=agent_name)
        
        stats = self._agent_stats[agent_name]
        stats.total_tasks += 1
        if overall_score >= 70:
            stats.successful_tasks += 1
        stats.retry_count += max(0, correction_attempts - 1)
        
        # Скользящее среднее
        n = stats.total_tasks
        stats.avg_quality_score = ((n - 1) * stats.avg_quality_score + overall_score) / n
        stats.avg_completeness = ((n - 1) * stats.avg_completeness + completeness) / n
        stats.avg_correctness = ((n - 1) * stats.avg_correctness + correctness) / n
        stats.last_updated = datetime.now()
        
        # Обновляем частые проблемы
        for issue in issues[:5]:
            stats.common_issues[issue] += 1
        
        # Сохраняем в БД
        if self.db:
            try:
                # Хэш задачи для поиска похожих
                task_hash = str(hash(task[:200]))
                
                await self.db.execute("""
                    INSERT INTO reflection_history
                    (agent_name, task, task_hash, completeness, correctness, quality,
                     overall_score, quality_level, issues, improvements, was_corrected,
                     correction_attempts, execution_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    agent_name,
                    task[:1000],  # Ограничиваем размер
                    task_hash,
                    completeness,
                    correctness,
                    quality,
                    overall_score,
                    quality_level,
                    json.dumps(issues[:10]),
                    json.dumps(improvements[:10]),
                    1 if was_corrected else 0,
                    correction_attempts,
                    execution_time
                ))
                await self.db.commit()
                
                # Если решение успешное, сохраняем паттерн с примером
                if overall_score >= 85:
                    await self._save_successful_pattern(
                        agent_name, task, overall_score, solution_snippet
                    )
                    
            except Exception as e:
                logger.error(f"Failed to record reflection: {e}")
        
        logger.debug(
            f"Learning recorded: {agent_name} score={overall_score:.1f}, "
            f"corrected={was_corrected}, attempts={correction_attempts}"
        )
    
    async def _save_successful_pattern(
        self,
        agent_name: str,
        task: str,
        quality_score: float,
        solution_snippet: Optional[str] = None
    ) -> None:
        """Сохраняет успешный паттерн задачи с примером решения"""
        if not self.db:
            return
        
        # Извлекаем паттерн из задачи (первые 100 символов как ключевые слова)
        task_pattern = task[:100].lower()
        
        try:
            # Проверяем, есть ли похожий паттерн
            async with self.db.execute("""
                SELECT id, reuse_count, quality_score as old_score FROM successful_solutions
                WHERE agent_name = ? AND task_pattern = ?
            """, (agent_name, task_pattern)) as cursor:
                existing = await cursor.fetchone()
            
            if existing:
                # Обновляем существующий только если новое решение лучше
                if quality_score > (existing[2] or 0):
                    await self.db.execute("""
                        UPDATE successful_solutions
                        SET reuse_count = reuse_count + 1,
                            quality_score = ?,
                            solution_snippet = COALESCE(?, solution_snippet),
                            last_used = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (quality_score, solution_snippet, existing[0]))
                else:
                    # Просто увеличиваем счётчик использования
                    await self.db.execute("""
                        UPDATE successful_solutions
                        SET reuse_count = reuse_count + 1,
                            last_used = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (existing[0],))
            else:
                # Создаём новый
                await self.db.execute("""
                    INSERT INTO successful_solutions
                    (agent_name, task_pattern, solution_snippet, quality_score)
                    VALUES (?, ?, ?, ?)
                """, (agent_name, task_pattern, solution_snippet, quality_score))
            
            await self.db.commit()
            
            # Обновляем кэш
            self._successful_prompts[agent_name].append({
                "pattern": task_pattern,
                "score": quality_score,
                "snippet": solution_snippet
            })
            
            logger.debug(f"Saved successful pattern for {agent_name}: score={quality_score:.1f}")
            
        except Exception as e:
            logger.debug(f"Failed to save successful pattern: {e}")
    
    async def get_agent_insights(self, agent_name: str) -> Dict[str, Any]:
        """
        Получает инсайты для агента на основе накопленного опыта.
        
        Returns:
            Рекомендации по улучшению, частые проблемы, успешные паттерны
        """
        if not self._initialized:
            await self.initialize()
        
        stats = self._agent_stats.get(agent_name)
        if not stats:
            return {
                "status": "no_data",
                "message": f"Нет данных об агенте {agent_name}",
                "recommendations": []
            }
        
        insights = {
            "status": "ok",
            "stats": stats.to_dict(),
            "recommendations": [],
            "common_issues": [],
            "successful_patterns": []
        }
        
        # Топ-5 частых проблем
        sorted_issues = sorted(
            stats.common_issues.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        insights["common_issues"] = [
            {"issue": issue, "count": count}
            for issue, count in sorted_issues
        ]
        
        # Успешные паттерны
        patterns = self._successful_prompts.get(agent_name, [])
        insights["successful_patterns"] = patterns[:5]
        
        # Генерируем рекомендации
        if stats.total_tasks > 0:
            success_rate = stats.successful_tasks / stats.total_tasks
            
            if success_rate < 0.7:
                insights["recommendations"].append(
                    f"Низкий success rate ({success_rate:.1%}). "
                    "Рассмотрите более детальные промпты."
                )
            
            if stats.retry_count / max(stats.total_tasks, 1) > 0.3:
                insights["recommendations"].append(
                    "Много повторных попыток. Уточните требования в промптах."
                )
            
            if sorted_issues:
                top_issue = sorted_issues[0]
                insights["recommendations"].append(
                    f"Частая проблема: '{top_issue[0]}' ({top_issue[1]} раз). "
                    "Добавьте явное указание в промпт."
                )
        
        return insights
    
    async def get_prompt_enhancement(
        self,
        agent_name: str,
        task: str
    ) -> Optional[str]:
        """
        Получает улучшение для промпта на основе накопленного опыта.
        Включает: предупреждения, рекомендации и примеры успешных решений.
        
        Returns:
            Дополнительные инструкции для промпта или None
        """
        if not self._initialized:
            await self.initialize()
        
        stats = self._agent_stats.get(agent_name)
        if not stats or stats.total_tasks < 3:
            return None  # Недостаточно опыта
        
        enhancements = []
        
        # 1. Добавляем предупреждения о частых проблемах
        if stats.common_issues:
            sorted_issues = sorted(
                stats.common_issues.items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            issues_text = ", ".join([issue for issue, _ in sorted_issues])
            enhancements.append(
                f"⚠️ ВАЖНО (из опыта {stats.total_tasks} задач): Избегайте проблем: {issues_text}"
            )
        
        # 2. Добавляем рекомендации по качеству на основе статистики
        if stats.avg_correctness < 80:
            enhancements.append(
                f"📊 Историческая корректность: {stats.avg_correctness:.0f}% — уделите особое внимание правильности."
            )
        
        if stats.avg_completeness < 80:
            enhancements.append(
                f"📊 Историческая полнота: {stats.avg_completeness:.0f}% — убедитесь, что решение полное."
            )
        
        # 3. Добавляем успешные паттерны как примеры (few-shot learning)
        similar = await self.get_similar_successful_solution(agent_name, task)
        if similar and similar.get("snippet"):
            enhancements.append(
                f"💡 Пример успешного решения похожей задачи (качество {similar['quality_score']:.0f}%):\n{similar['snippet'][:500]}"
            )
        
        # 4. Adaptive learning: если много исправлений, добавляем строгие требования
        retry_rate = stats.retry_count / max(stats.total_tasks, 1)
        if retry_rate > 0.3:
            enhancements.append(
                f"🔄 Часто требуются исправления ({retry_rate:.0%}). Проверьте результат ПЕРЕД ответом."
            )
        
        if not enhancements:
            return None
        
        return "--- ОБУЧЕНИЕ НА ОПЫТЕ ---\n" + "\n".join(enhancements) + "\n---"
    
    async def get_similar_successful_solution(
        self,
        agent_name: str,
        task: str
    ) -> Optional[Dict[str, Any]]:
        """
        Ищет похожее успешное решение для переиспользования.
        
        Returns:
            Информация о похожем решении или None
        """
        if not self.db or not self._initialized:
            return None
        
        task_pattern = task[:100].lower()
        
        try:
            async with self.db.execute("""
                SELECT task_pattern, solution_snippet, quality_score
                FROM successful_solutions
                WHERE agent_name = ? AND quality_score >= 85
                ORDER BY quality_score DESC
                LIMIT 5
            """, (agent_name,)) as cursor:
                async for row in cursor:
                    pattern, snippet, score = row
                    # Простое сравнение по совпадению слов
                    pattern_words = set(pattern.split())
                    task_words = set(task_pattern.split())
                    overlap = len(pattern_words & task_words)
                    
                    if overlap >= 3:  # Минимум 3 общих слова
                        return {
                            "pattern": pattern,
                            "snippet": snippet,
                            "quality_score": score,
                            "similarity": overlap / max(len(pattern_words), len(task_words))
                        }
        except Exception as e:
            logger.debug(f"Failed to find similar solution: {e}")
        
        return None
    
    async def record_error_pattern(
        self,
        agent_name: str,
        error_pattern: str,
        solution_pattern: Optional[str] = None
    ) -> None:
        """Записывает паттерн ошибки и её решение"""
        if not self.db:
            return
        
        try:
            async with self.db.execute("""
                SELECT id FROM error_patterns
                WHERE agent_name = ? AND error_pattern = ?
            """, (agent_name, error_pattern[:200])) as cursor:
                existing = await cursor.fetchone()
            
            if existing:
                await self.db.execute("""
                    UPDATE error_patterns
                    SET occurrence_count = occurrence_count + 1,
                        solution_pattern = COALESCE(?, solution_pattern),
                        resolved_count = resolved_count + CASE WHEN ? IS NOT NULL THEN 1 ELSE 0 END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (solution_pattern, solution_pattern, existing[0]))
            else:
                await self.db.execute("""
                    INSERT INTO error_patterns (agent_name, error_pattern, solution_pattern)
                    VALUES (?, ?, ?)
                """, (agent_name, error_pattern[:200], solution_pattern))
            
            await self.db.commit()
        except Exception as e:
            logger.debug(f"Failed to record error pattern: {e}")
    
    async def get_global_learning_stats(self) -> Dict[str, Any]:
        """Получает глобальную статистику обучения"""
        if not self._initialized:
            await self.initialize()
        
        total_tasks = sum(s.total_tasks for s in self._agent_stats.values())
        total_successful = sum(s.successful_tasks for s in self._agent_stats.values())
        total_retries = sum(s.retry_count for s in self._agent_stats.values())
        
        return {
            "total_tasks_learned": total_tasks,
            "total_successful": total_successful,
            "global_success_rate": total_successful / max(total_tasks, 1),
            "total_retries": total_retries,
            "agents_count": len(self._agent_stats),
            "agents": {
                name: stats.to_dict()
                for name, stats in self._agent_stats.items()
            }
        }
    
    async def shutdown(self) -> None:
        """Закрытие соединения"""
        if self.db:
            await self.db.close()
            self.db = None
            logger.info("LearningSystem shutdown complete")


# Singleton instance
_learning_system: Optional[LearningSystem] = None


def get_learning_system() -> LearningSystem:
    """Получить singleton экземпляр системы обучения"""
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem()
    return _learning_system


async def initialize_learning_system() -> LearningSystem:
    """Инициализировать и вернуть систему обучения"""
    system = get_learning_system()
    await system.initialize()
    return system

