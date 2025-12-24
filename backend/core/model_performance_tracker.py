"""
Model Performance Tracker - Отслеживание производительности моделей
Критично для оптимизации работы с 30+ моделями 60B+ параметров

Поддерживает персистентность метрик в SQLite для обучения на опыте.
"""

import time
import asyncio
import json
import aiosqlite
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
from .logger import get_logger
logger = get_logger(__name__)
import statistics


@dataclass
class ModelMetrics:
    """Метрики производительности модели"""
    model_name: str
    provider: str
    
    # Статистика запросов
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Время выполнения
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    duration_history: List[float] = field(default_factory=list)
    
    # Токены
    total_tokens: int = 0
    avg_tokens_per_sec: float = 0.0
    tokens_per_sec_history: List[float] = field(default_factory=list)
    
    # Ошибки
    error_types: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Последнее использование
    last_used: Optional[datetime] = None
    
    # Рейтинг (вычисляется динамически)
    performance_score: float = 0.0
    
    def update(self, duration: float, tokens: int, success: bool, error_type: Optional[str] = None):
        """Обновить метрики"""
        self.total_requests += 1
        self.last_used = datetime.now()
        
        if success:
            self.successful_requests += 1
            self.total_duration += duration
            self.total_tokens += tokens
            
            # Обновляем историю (храним последние 100 записей)
            self.duration_history.append(duration)
            if len(self.duration_history) > 100:
                self.duration_history.pop(0)
            
            if duration > 0:
                tokens_per_sec = tokens / duration
                self.tokens_per_sec_history.append(tokens_per_sec)
                if len(self.tokens_per_sec_history) > 100:
                    self.tokens_per_sec_history.pop(0)
            
            # Обновляем min/max
            if duration < self.min_duration:
                self.min_duration = duration
            if duration > self.max_duration:
                self.max_duration = duration
            
            # Пересчитываем средние
            if self.successful_requests > 0:
                self.avg_duration = self.total_duration / self.successful_requests
                if self.tokens_per_sec_history:
                    self.avg_tokens_per_sec = statistics.mean(self.tokens_per_sec_history)
        else:
            self.failed_requests += 1
            if error_type:
                self.error_types[error_type] += 1
        
        # Пересчитываем performance score
        self._calculate_score()
    
    def _calculate_score(self):
        """Вычисляет общий рейтинг производительности модели"""
        if self.total_requests == 0:
            self.performance_score = 0.0
            return
        
        # Success rate (0-50 баллов)
        success_rate = self.successful_requests / self.total_requests
        score = success_rate * 50
        
        # Скорость (0-30 баллов)
        if self.avg_tokens_per_sec > 0:
            # Нормализуем: 100 токенов/сек = 30 баллов
            speed_score = min(self.avg_tokens_per_sec / 100 * 30, 30)
            score += speed_score
        
        # Стабильность (0-20 баллов) - на основе стандартного отклонения
        if len(self.duration_history) > 1:
            try:
                std_dev = statistics.stdev(self.duration_history)
                avg = statistics.mean(self.duration_history)
                if avg > 0:
                    # Коэффициент вариации (меньше = стабильнее)
                    cv = std_dev / avg
                    stability_score = max(0, 20 - cv * 20)  # До 20 баллов
                    score += stability_score
            except Exception as e:
                logger.debug(f"Failed to calculate stability score: {e}")
                # Continue without stability score
        
        self.performance_score = score
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику в виде словаря"""
        return {
            "model_name": self.model_name,
            "provider": self.provider,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0,
            "avg_duration": self.avg_duration,
            "min_duration": self.min_duration if self.min_duration != float('inf') else 0.0,
            "max_duration": self.max_duration,
            "avg_tokens_per_sec": self.avg_tokens_per_sec,
            "total_tokens": self.total_tokens,
            "performance_score": self.performance_score,
            "error_types": dict(self.error_types),
            "last_used": self.last_used.isoformat() if self.last_used else None
        }


class ModelPerformanceTracker:
    """
    Трекер производительности моделей с персистентностью в SQLite.
    
    Автоматически сохраняет и загружает метрики между сессиями,
    позволяя системе учиться на опыте использования моделей.
    """
    
    def __init__(self, db_path: str = "memory/model_metrics.db"):
        self.metrics: Dict[str, ModelMetrics] = {}
        self._lock = asyncio.Lock()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db: Optional[aiosqlite.Connection] = None
        self._initialized = False
        self._save_interval = 10  # Сохранять каждые N запросов
        self._request_count = 0
    
    async def initialize(self) -> None:
        """Инициализация базы данных и загрузка метрик"""
        if self._initialized:
            return
        
        try:
            self.db = await aiosqlite.connect(str(self.db_path))
            await self.db.execute("PRAGMA journal_mode=WAL")
            
            # Создаем таблицу для метрик моделей
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS model_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    total_requests INTEGER DEFAULT 0,
                    successful_requests INTEGER DEFAULT 0,
                    failed_requests INTEGER DEFAULT 0,
                    total_duration REAL DEFAULT 0.0,
                    avg_duration REAL DEFAULT 0.0,
                    min_duration REAL DEFAULT 0.0,
                    max_duration REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    avg_tokens_per_sec REAL DEFAULT 0.0,
                    performance_score REAL DEFAULT 0.0,
                    error_types TEXT DEFAULT '{}',
                    duration_history TEXT DEFAULT '[]',
                    tokens_per_sec_history TEXT DEFAULT '[]',
                    last_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, model_name)
                )
            """)
            
            # Создаем таблицу для истории запросов (для детального анализа)
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS request_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    duration REAL,
                    tokens INTEGER,
                    success INTEGER,
                    error_type TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индексы для быстрого поиска
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_provider_model 
                ON model_metrics(provider, model_name)
            """)
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp 
                ON request_history(timestamp)
            """)
            
            await self.db.commit()
            
            # Загружаем существующие метрики
            await self._load_metrics()
            
            self._initialized = True
            logger.info(f"Performance tracker initialized with {len(self.metrics)} models loaded")
            
        except Exception as e:
            logger.error(f"Failed to initialize performance tracker: {e}")
            # Продолжаем работу в memory-only режиме
            self._initialized = True
    
    async def _load_metrics(self) -> None:
        """Загрузка метрик из базы данных"""
        if not self.db:
            return
        
        try:
            async with self.db.execute(
                "SELECT * FROM model_metrics"
            ) as cursor:
                async for row in cursor:
                    (id_, provider, model_name, total_requests, successful_requests,
                     failed_requests, total_duration, avg_duration, min_duration,
                     max_duration, total_tokens, avg_tokens_per_sec, performance_score,
                     error_types_json, duration_history_json, tokens_per_sec_history_json,
                     last_used, created_at, updated_at) = row
                    
                    key = f"{provider}:{model_name}"
                    
                    # Парсим JSON данные
                    try:
                        error_types = defaultdict(int, json.loads(error_types_json or "{}"))
                    except:
                        error_types = defaultdict(int)
                    
                    try:
                        duration_history = json.loads(duration_history_json or "[]")
                    except:
                        duration_history = []
                    
                    try:
                        tokens_per_sec_history = json.loads(tokens_per_sec_history_json or "[]")
                    except:
                        tokens_per_sec_history = []
                    
                    # Парсим last_used
                    last_used_dt = None
                    if last_used:
                        try:
                            last_used_dt = datetime.fromisoformat(last_used)
                        except:
                            pass
                    
                    self.metrics[key] = ModelMetrics(
                        model_name=model_name,
                        provider=provider,
                        total_requests=total_requests,
                        successful_requests=successful_requests,
                        failed_requests=failed_requests,
                        total_duration=total_duration,
                        avg_duration=avg_duration,
                        min_duration=min_duration if min_duration > 0 else float('inf'),
                        max_duration=max_duration,
                        total_tokens=total_tokens,
                        avg_tokens_per_sec=avg_tokens_per_sec,
                        performance_score=performance_score,
                        error_types=error_types,
                        duration_history=duration_history,
                        tokens_per_sec_history=tokens_per_sec_history,
                        last_used=last_used_dt
                    )
                    
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
    
    async def _save_metrics(self, metrics: ModelMetrics) -> None:
        """Сохранение метрик в базу данных"""
        if not self.db:
            return
        
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO model_metrics 
                (provider, model_name, total_requests, successful_requests, failed_requests,
                 total_duration, avg_duration, min_duration, max_duration, total_tokens,
                 avg_tokens_per_sec, performance_score, error_types, duration_history,
                 tokens_per_sec_history, last_used, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                metrics.provider,
                metrics.model_name,
                metrics.total_requests,
                metrics.successful_requests,
                metrics.failed_requests,
                metrics.total_duration,
                metrics.avg_duration,
                metrics.min_duration if metrics.min_duration != float('inf') else 0.0,
                metrics.max_duration,
                metrics.total_tokens,
                metrics.avg_tokens_per_sec,
                metrics.performance_score,
                json.dumps(dict(metrics.error_types)),
                json.dumps(metrics.duration_history[-100:]),  # Храним последние 100
                json.dumps(metrics.tokens_per_sec_history[-100:]),
                metrics.last_used.isoformat() if metrics.last_used else None
            ))
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    async def _save_request_history(
        self,
        provider: str,
        model: str,
        duration: float,
        tokens: int,
        success: bool,
        error_type: Optional[str]
    ) -> None:
        """Сохранение истории запросов для анализа"""
        if not self.db:
            return
        
        try:
            await self.db.execute("""
                INSERT INTO request_history 
                (provider, model_name, duration, tokens, success, error_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (provider, model, duration, tokens, 1 if success else 0, error_type))
            
            # Очистка старых записей (храним последние 10000)
            await self.db.execute("""
                DELETE FROM request_history 
                WHERE id NOT IN (
                    SELECT id FROM request_history 
                    ORDER BY timestamp DESC 
                    LIMIT 10000
                )
            """)
            await self.db.commit()
        except Exception as e:
            logger.debug(f"Failed to save request history: {e}")
    
    async def shutdown(self) -> None:
        """Закрытие соединения с базой данных"""
        if self.db:
            # Сохраняем все метрики перед закрытием
            for metrics in self.metrics.values():
                await self._save_metrics(metrics)
            await self.db.close()
            self.db = None
            logger.info("Performance tracker shutdown complete")
    
    def get_metrics(self, provider: str, model: str) -> ModelMetrics:
        """Получить или создать метрики для модели"""
        key = f"{provider}:{model}"
        if key not in self.metrics:
            self.metrics[key] = ModelMetrics(
                model_name=model,
                provider=provider
            )
        return self.metrics[key]
    
    def record_request(
        self,
        provider: str,
        model: str,
        duration: float,
        tokens: int,
        success: bool,
        error_type: Optional[str] = None
    ):
        """Записать метрики запроса (синхронная версия для совместимости)"""
        metrics = self.get_metrics(provider, model)
        metrics.update(duration, tokens, success, error_type)
        
        # Планируем асинхронное сохранение
        self._request_count += 1
        if self._request_count >= self._save_interval:
            self._request_count = 0
            # Создаем задачу для асинхронного сохранения
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._async_save(provider, model, duration, tokens, success, error_type))
            except RuntimeError:
                # Если нет event loop, сохраним позже
                pass
    
    async def record_request_async(
        self,
        provider: str,
        model: str,
        duration: float,
        tokens: int,
        success: bool,
        error_type: Optional[str] = None
    ):
        """Записать метрики запроса (асинхронная версия с персистентностью)"""
        # Инициализируем если нужно
        if not self._initialized:
            await self.initialize()
        
        metrics = self.get_metrics(provider, model)
        metrics.update(duration, tokens, success, error_type)
        
        # Сохраняем в базу данных
        await self._save_metrics(metrics)
        await self._save_request_history(provider, model, duration, tokens, success, error_type)
    
    async def _async_save(
        self,
        provider: str,
        model: str,
        duration: float,
        tokens: int,
        success: bool,
        error_type: Optional[str]
    ):
        """Асинхронное сохранение метрик"""
        if not self._initialized:
            await self.initialize()
        
        metrics = self.get_metrics(provider, model)
        await self._save_metrics(metrics)
        await self._save_request_history(provider, model, duration, tokens, success, error_type)
    
    def get_best_models(
        self,
        provider: Optional[str] = None,
        min_requests: int = 5,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Получить лучшие модели по производительности"""
        candidates = []
        
        for key, metrics in self.metrics.items():
            if metrics.total_requests < min_requests:
                continue
            
            if provider and metrics.provider != provider:
                continue
            
            candidates.append(metrics)
        
        # Сортируем по performance_score
        candidates.sort(key=lambda m: m.performance_score, reverse=True)
        
        return [m.get_stats() for m in candidates[:limit]]
    
    def get_model_recommendation(
        self,
        task_complexity: str,
        provider: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Получить рекомендацию модели для задачи"""
        # Фильтруем модели по сложности задачи
        candidates = []
        
        for metrics in self.metrics.values():
            if provider and metrics.provider != provider:
                continue
            
            if metrics.total_requests < 3:  # Минимум 3 запроса для рекомендации
                continue
            
            # Для простых задач предпочитаем быстрые модели
            if task_complexity == "low":
                if metrics.avg_tokens_per_sec > 30:  # Быстрые модели
                    candidates.append(metrics)
            # Для сложных задач предпочитаем надежные модели
            elif task_complexity == "high":
                if metrics.successful_requests / max(metrics.total_requests, 1) > 0.9:  # Высокий success rate
                    candidates.append(metrics)
            else:  # medium
                candidates.append(metrics)
        
        if not candidates:
            return None
        
        # Выбираем лучшую по performance_score
        best = max(candidates, key=lambda m: m.performance_score)
        return best.get_stats()
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Получить статистику всех моделей"""
        return {
            "total_models": len(self.metrics),
            "models": [m.get_stats() for m in self.metrics.values()],
            "summary": {
                "total_requests": sum(m.total_requests for m in self.metrics.values()),
                "total_successful": sum(m.successful_requests for m in self.metrics.values()),
                "total_failed": sum(m.failed_requests for m in self.metrics.values()),
                "avg_performance_score": statistics.mean([m.performance_score for m in self.metrics.values()]) if self.metrics else 0.0
            }
        }
    
    async def get_learning_insights(self) -> Dict[str, Any]:
        """
        Получить инсайты для обучения системы.
        Анализирует накопленные данные и предоставляет рекомендации.
        """
        if not self.metrics:
            return {"status": "no_data", "recommendations": []}
        
        insights = {
            "status": "ok",
            "total_experience": sum(m.total_requests for m in self.metrics.values()),
            "models_analyzed": len(self.metrics),
            "recommendations": [],
            "top_performers": [],
            "underperformers": [],
            "error_patterns": {}
        }
        
        # Топ-3 лучших модели
        sorted_models = sorted(
            self.metrics.values(),
            key=lambda m: m.performance_score,
            reverse=True
        )
        
        insights["top_performers"] = [
            {
                "model": m.model_name,
                "provider": m.provider,
                "score": m.performance_score,
                "success_rate": m.successful_requests / max(m.total_requests, 1),
                "avg_speed": m.avg_tokens_per_sec
            }
            for m in sorted_models[:3] if m.total_requests >= 3
        ]
        
        # Модели с проблемами
        for m in self.metrics.values():
            if m.total_requests >= 5:
                success_rate = m.successful_requests / m.total_requests
                if success_rate < 0.8:
                    insights["underperformers"].append({
                        "model": m.model_name,
                        "provider": m.provider,
                        "success_rate": success_rate,
                        "common_errors": dict(m.error_types)
                    })
        
        # Паттерны ошибок
        all_errors: Dict[str, int] = defaultdict(int)
        for m in self.metrics.values():
            for error_type, count in m.error_types.items():
                all_errors[error_type] += count
        insights["error_patterns"] = dict(all_errors)
        
        # Рекомендации
        if insights["top_performers"]:
            best = insights["top_performers"][0]
            insights["recommendations"].append(
                f"Предпочитайте модель {best['model']} ({best['provider']}) - "
                f"лучший performance score {best['score']:.1f}"
            )
        
        if insights["underperformers"]:
            for up in insights["underperformers"]:
                insights["recommendations"].append(
                    f"Избегайте {up['model']} ({up['provider']}) - "
                    f"низкий success rate {up['success_rate']:.1%}"
                )
        
        if all_errors:
            top_error = max(all_errors.items(), key=lambda x: x[1])
            insights["recommendations"].append(
                f"Частая ошибка: {top_error[0]} ({top_error[1]} раз) - "
                f"рассмотрите обработку этого сценария"
            )
        
        return insights


# Singleton instance
_performance_tracker: Optional[ModelPerformanceTracker] = None


def get_performance_tracker() -> ModelPerformanceTracker:
    """Получить singleton экземпляр трекера"""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = ModelPerformanceTracker()
    return _performance_tracker


async def initialize_performance_tracker() -> ModelPerformanceTracker:
    """Инициализировать и вернуть трекер с загруженными данными"""
    tracker = get_performance_tracker()
    await tracker.initialize()
    return tracker

