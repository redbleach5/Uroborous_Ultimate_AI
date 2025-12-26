"""
Long Term Memory - Semantic search for similar tasks and solutions
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    aiosqlite = None
    logger.warning("aiosqlite not available, LongTermMemory will not work correctly")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

import numpy as np

from ..config import MemoryConfig
from ..core.exceptions import MemoryException


class LongTermMemory:
    """
    Long term memory for storing and retrieving solutions
    Uses semantic search to find similar tasks
    """
    
    def __init__(self, config: MemoryConfig, vector_store: Optional[Any] = None):
        """
        Initialize long term memory
        
        Args:
            config: Memory configuration
            vector_store: Optional VectorStore instance to reuse embeddings model
        """
        self.config = config
        self.storage_path = Path(config.storage_path)
        self.max_memories = config.max_memories
        self.similarity_threshold = config.similarity_threshold
        self.vector_store = vector_store  # Reuse embeddings model from vector store
        
        self.db: Optional[Any] = None  # aiosqlite.Connection
        self.embeddings_model: Optional[SentenceTransformer] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize memory system"""
        if self._initialized:
            return
        
        if not AIOSQLITE_AVAILABLE:
            raise MemoryException("aiosqlite is required for LongTermMemory. Install it with: pip install aiosqlite")
        
        logger.info("Initializing Long Term Memory...")
        
        # Create storage directory
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self.db = await aiosqlite.connect(str(self.storage_path))
        await self._create_tables()
        
        # Initialize embeddings model - reuse from vector_store if available
        # This prevents loading the model twice and avoids "threads can only be started once" errors
        if self.vector_store and hasattr(self.vector_store, 'embeddings_model') and self.vector_store.embeddings_model:
            # Reuse model from vector store to avoid loading twice
            self.embeddings_model = self.vector_store.embeddings_model
            logger.info("Reusing embeddings model from VectorStore")
        elif SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                # Set environment variables to prevent multiprocessing issues
                import os
                os.environ.setdefault('TORCH_MULTIPROCESSING', '0')
                os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
                os.environ.setdefault('OMP_NUM_THREADS', '1')
                
                # Only load if vector_store doesn't have it
                self.embeddings_model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    device="cpu"
                )
                logger.info("Loaded embeddings model for LongTermMemory")
            except Exception as e:
                logger.warning(f"Failed to load embeddings model: {e}")
                self.embeddings_model = None
        else:
            logger.warning("sentence-transformers not available, semantic search disabled")
            self.embeddings_model = None
        
        self._initialized = True
        logger.info("Long Term Memory initialized")
    
    async def _create_tables(self) -> None:
        """Create database tables with migration support"""
        # Сначала проверяем, существует ли таблица
        cursor = await self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        )
        table_exists = await cursor.fetchone() is not None
        await cursor.close()
        
        if not table_exists:
            # Создаем новую таблицу с всеми колонками
            await self.db.execute("""
                CREATE TABLE memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    solution TEXT NOT NULL,
                    agent TEXT,
                    metadata TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success_count INTEGER DEFAULT 1,
                    quality_score REAL DEFAULT 0.0,
                    feedback_count INTEGER DEFAULT 0,
                    avg_rating REAL DEFAULT 0.0,
                    is_helpful_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP
                )
            """)
            logger.info("Created memories table with all columns")
        else:
            # Миграция: добавляем новые колонки если их нет
            migrations = [
                ("quality_score", "REAL DEFAULT 0.0"),
                ("feedback_count", "INTEGER DEFAULT 0"),
                ("avg_rating", "REAL DEFAULT 0.0"),
                ("is_helpful_count", "INTEGER DEFAULT 0"),
                ("last_used", "TIMESTAMP"),
            ]
            
            for column_name, column_type in migrations:
                try:
                    await self.db.execute(f"ALTER TABLE memories ADD COLUMN {column_name} {column_type}")
                    logger.info(f"Added column {column_name} to memories table")
                except Exception as e:
                    # Колонка уже существует - это нормально
                    if "duplicate column" not in str(e).lower():
                        logger.debug(f"Column {column_name} migration skipped: {e}")
        
        # Создаем индексы
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON memories(created_at)
        """)
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_quality_score ON memories(quality_score DESC)
        """)
        
        await self.db.commit()
    
    async def save_solution(
        self,
        task: str,
        solution: str,
        agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Save a solution to memory
        
        Args:
            task: Task description
            solution: Solution content
            agent: Agent that created solution
            metadata: Additional metadata
        """
        if not self._initialized:
            await self.initialize()
        
        # Generate embedding
        embedding = None
        if self.embeddings_model and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                embedding_array = self.embeddings_model.encode([task])[0]
                embedding = embedding_array.tobytes()
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")
        
        # Save to database
        # Note: aiosqlite handles transactions automatically in isolation_level=None mode
        # For explicit transaction control, we use execute with proper error handling
        try:
            await self.db.execute("""
                INSERT INTO memories (task, solution, agent, metadata, embedding)
                VALUES (?, ?, ?, ?, ?)
            """, (
                task,
                solution,
                agent,
                json.dumps(metadata or {}),
                embedding
            ))
            await self.db.commit()
        except Exception as e:
            # Rollback is automatic in aiosqlite on error, but we call it explicitly for safety
            try:
                await self.db.rollback()
            except Exception:
                pass  # Ignore rollback errors
            logger.error(f"Failed to save solution to memory: {e}")
            raise MemoryException(f"Failed to save solution: {e}") from e
        
        # Cleanup old memories if needed
        await self._cleanup_if_needed()
    
    async def search_similar_tasks(
        self,
        task: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar tasks in memory
        
        Args:
            task: Task to search for
            top_k: Number of results to return
            
        Returns:
            List of similar tasks with solutions
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.embeddings_model or not SENTENCE_TRANSFORMERS_AVAILABLE:
            # Fallback to text search
            return await self._text_search(task, top_k)
        
        # Generate query embedding
        try:
            query_embedding = self.embeddings_model.encode([task])[0]
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return await self._text_search(task, top_k)
        
        # Search in database
        cursor = await self.db.execute("SELECT id, task, solution, agent, metadata, embedding FROM memories")
        rows = await cursor.fetchall()
        await cursor.close()
        
        if not rows:
            return []
        
        # Calculate similarities
        similarities = []
        for row in rows:
            if row[5]:  # embedding
                try:
                    stored_embedding = np.frombuffer(row[5], dtype=np.float32)
                    similarity = np.dot(query_embedding, stored_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding)
                    )
                    
                    if similarity >= self.similarity_threshold:
                        similarities.append({
                            "id": row[0],
                            "task": row[1],
                            "solution": row[2],
                            "agent": row[3],
                            "metadata": json.loads(row[4] or "{}"),
                            "similarity": float(similarity)
                        })
                except Exception as e:
                    logger.warning(f"Error calculating similarity: {e}")
                    continue
        
        # Sort by similarity
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        
        return similarities[:top_k]
    
    async def _text_search(self, task: str, top_k: int) -> List[Dict[str, Any]]:
        """Fallback text-based search"""
        cursor = await self.db.execute("""
            SELECT id, task, solution, agent, metadata
            FROM memories
            WHERE task LIKE ? OR solution LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{task}%", f"%{task}%", top_k))
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "id": row[0],
                "task": row[1],
                "solution": row[2],
                "agent": row[3],
                "metadata": json.loads(row[4] or "{}"),
                "similarity": 0.5  # Default similarity for text search
            }
            for row in rows
        ]
    
    async def _cleanup_if_needed(self) -> None:
        """Cleanup old memories if exceeding max (учитываем качество)"""
        cursor = await self.db.execute("SELECT COUNT(*) FROM memories")
        row = await cursor.fetchone()
        await cursor.close()
        count = row[0] if row else 0
        
        if count > self.max_memories:
            # Delete oldest AND lowest quality memories
            to_delete = count - self.max_memories
            try:
                # Удаляем с учетом качества: сначала низкокачественные старые
                await self.db.execute("""
                    DELETE FROM memories
                    WHERE id IN (
                        SELECT id FROM memories
                        ORDER BY quality_score ASC, created_at ASC
                        LIMIT ?
                    )
                """, (to_delete,))
                await self.db.commit()
                logger.info(f"Cleaned up {to_delete} old/low-quality memories")
            except Exception as e:
                try:
                    await self.db.rollback()
                except Exception:
                    pass  # Ignore rollback errors
                logger.error(f"Failed to cleanup old memories: {e}")
                # Don't raise here - cleanup failure shouldn't break the main operation
    
    async def update_solution_feedback(
        self,
        memory_id: int,
        rating: int,
        is_helpful: bool
    ) -> None:
        """
        Обновить качество решения на основе feedback.
        Интегрируется с feedback API для улучшения поиска.
        
        Args:
            memory_id: ID записи в памяти
            rating: Оценка от 1 до 5
            is_helpful: Было ли решение полезным
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Получаем текущие метрики
            cursor = await self.db.execute(
                "SELECT feedback_count, avg_rating, is_helpful_count FROM memories WHERE id = ?",
                (memory_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            
            if not row:
                logger.warning(f"Memory {memory_id} not found")
                return
            
            feedback_count = (row[0] or 0) + 1
            current_avg = row[1] or 0.0
            helpful_count = (row[2] or 0) + (1 if is_helpful else 0)
            
            # Рассчитываем новый средний рейтинг
            new_avg_rating = (current_avg * (feedback_count - 1) + rating) / feedback_count
            
            # Рассчитываем quality_score
            # Формула: 40% рейтинг + 40% helpful rate + 20% количество feedback
            helpful_rate = helpful_count / feedback_count if feedback_count > 0 else 0
            feedback_bonus = min(feedback_count / 10, 1.0)  # Макс 10 feedback = 100%
            
            quality_score = (
                (new_avg_rating / 5) * 40 +  # 0-40 баллов от рейтинга
                helpful_rate * 40 +           # 0-40 баллов от полезности
                feedback_bonus * 20           # 0-20 баллов от количества feedback
            )
            
            # Обновляем запись
            await self.db.execute("""
                UPDATE memories 
                SET feedback_count = ?,
                    avg_rating = ?,
                    is_helpful_count = ?,
                    quality_score = ?
                WHERE id = ?
            """, (feedback_count, new_avg_rating, helpful_count, quality_score, memory_id))
            await self.db.commit()
            
            logger.info(f"Updated memory {memory_id} quality_score to {quality_score:.2f}")
            
        except Exception as e:
            logger.error(f"Failed to update solution feedback: {e}")
    
    async def search_similar_tasks_with_quality(
        self,
        task: str,
        top_k: int = 5,
        min_quality: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Поиск похожих задач с учетом качества решений.
        Приоритет отдается качественным проверенным решениям.
        
        Args:
            task: Задача для поиска
            top_k: Количество результатов
            min_quality: Минимальный quality_score (0-100)
            
        Returns:
            Список похожих задач, отсортированный по relevance * quality
        """
        # Получаем базовые результаты поиска
        results = await self.search_similar_tasks(task, top_k * 2)  # Берем больше для фильтрации
        
        if not results:
            return []
        
        # Добавляем информацию о качестве
        enhanced_results = []
        for result in results:
            try:
                cursor = await self.db.execute(
                    "SELECT quality_score, feedback_count, avg_rating FROM memories WHERE id = ?",
                    (result["id"],)
                )
                row = await cursor.fetchone()
                await cursor.close()
                
                quality_score = row[0] if row and row[0] else 0.0
                
                if quality_score >= min_quality:
                    result["quality_score"] = quality_score
                    result["feedback_count"] = row[1] if row else 0
                    result["avg_rating"] = row[2] if row else 0.0
                    
                    # Комбинированный скор: similarity * 0.6 + quality * 0.4
                    similarity = result.get("similarity", 0.5)
                    result["combined_score"] = similarity * 0.6 + (quality_score / 100) * 0.4
                    
                    enhanced_results.append(result)
            except Exception as e:
                logger.warning(f"Failed to get quality for memory {result['id']}: {e}")
                result["quality_score"] = 0.0
                result["combined_score"] = result.get("similarity", 0.5) * 0.6
                enhanced_results.append(result)
        
        # Сортируем по combined_score
        enhanced_results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        
        # Обновляем last_used для использованных решений
        for result in enhanced_results[:top_k]:
            try:
                await self.db.execute(
                    "UPDATE memories SET last_used = CURRENT_TIMESTAMP WHERE id = ?",
                    (result["id"],)
                )
            except Exception:
                pass
        await self.db.commit()
        
        return enhanced_results[:top_k]
    
    async def get_learning_stats(self) -> Dict[str, Any]:
        """
        Получить статистику обучения памяти.
        Показывает насколько эффективно система учится.
        """
        if not self._initialized:
            await self.initialize()
        
        stats = {
            "total_memories": 0,
            "with_feedback": 0,
            "avg_quality": 0.0,
            "helpful_rate": 0.0,
            "top_agents": [],
            "top_solutions": []
        }
        
        try:
            # Общая статистика
            cursor = await self.db.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN feedback_count > 0 THEN 1 ELSE 0 END) as with_feedback,
                    AVG(quality_score) as avg_quality,
                    SUM(is_helpful_count) * 1.0 / NULLIF(SUM(feedback_count), 0) as helpful_rate
                FROM memories
            """)
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                stats["total_memories"] = row[0] or 0
                stats["with_feedback"] = row[1] or 0
                stats["avg_quality"] = round(row[2] or 0, 2)
                stats["helpful_rate"] = round((row[3] or 0) * 100, 1)
            
            # Топ агенты по качеству
            cursor = await self.db.execute("""
                SELECT agent, AVG(quality_score) as avg_quality, COUNT(*) as count
                FROM memories
                WHERE agent IS NOT NULL AND feedback_count > 0
                GROUP BY agent
                ORDER BY avg_quality DESC
                LIMIT 5
            """)
            async for row in cursor:
                stats["top_agents"].append({
                    "agent": row[0],
                    "avg_quality": round(row[1], 2),
                    "solutions": row[2]
                })
            await cursor.close()
            
            # Топ решения
            cursor = await self.db.execute("""
                SELECT id, task, quality_score, avg_rating, feedback_count
                FROM memories
                WHERE quality_score > 0
                ORDER BY quality_score DESC
                LIMIT 5
            """)
            async for row in cursor:
                stats["top_solutions"].append({
                    "id": row[0],
                    "task": row[1][:100] + "..." if len(row[1]) > 100 else row[1],
                    "quality_score": round(row[2], 2),
                    "avg_rating": round(row[3], 2),
                    "feedback_count": row[4]
                })
            await cursor.close()
            
        except Exception as e:
            logger.error(f"Failed to get learning stats: {e}")
        
        return stats
    
    async def update_config(self, new_config: MemoryConfig) -> None:
        """
        Update memory configuration dynamically.
        
        Args:
            new_config: New MemoryConfig
        """
        logger.info("Updating Long Term Memory configuration...")
        
        # Update configurable parameters that don't require restart
        if hasattr(new_config, 'max_memories'):
            self.max_memories = new_config.max_memories
        if hasattr(new_config, 'similarity_threshold'):
            self.similarity_threshold = new_config.similarity_threshold
        
        self.config = new_config
        logger.info(
            f"Long Term Memory updated: max_memories={self.max_memories}, "
            f"similarity_threshold={self.similarity_threshold}"
        )
    
    async def shutdown(self) -> None:
        """Shutdown memory system"""
        if self.db:
            await self.db.close()
        self._initialized = False

