"""
Progress Tracker - система отслеживания прогресса операций в реальном времени.

Позволяет:
- Отправлять события прогресса через SSE
- Отслеживать этапы выполнения
- Хранить историю прогресса для каждой операции
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid
import json

from .logger import get_logger

logger = get_logger(__name__)


class ProgressStage(Enum):
    """Стандартные этапы прогресса."""
    STARTING = "starting"
    PROFILING = "profiling"
    SCANNING = "scanning"
    READING = "reading"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    GENERATING = "generating"
    FINISHING = "finishing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ProgressEvent:
    """Событие прогресса."""
    stage: str
    message: str
    progress: float  # 0.0 - 1.0
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "message": self.message,
            "progress": round(self.progress, 2),
            "details": self.details or {},
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_sse(self) -> str:
        """Форматирует как SSE событие."""
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"


class ProgressTracker:
    """
    Трекер прогресса для одной операции.
    
    Использование:
        tracker = ProgressTracker("analyze_project")
        await tracker.update("profiling", "Анализируем структуру...", 0.1)
        await tracker.update("scanning", "Сканируем файлы...", 0.3)
        await tracker.complete("Анализ завершён")
    """
    
    def __init__(self, operation_id: str, operation_type: str = "unknown"):
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.events: List[ProgressEvent] = []
        self.listeners: List[asyncio.Queue] = []
        self.started_at = datetime.now()
        self.completed = False
        self._lock = asyncio.Lock()
    
    async def update(
        self,
        stage: str,
        message: str,
        progress: float,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Отправляет обновление прогресса всем слушателям."""
        event = ProgressEvent(
            stage=stage,
            message=message,
            progress=min(max(progress, 0.0), 1.0),
            details=details
        )
        
        async with self._lock:
            self.events.append(event)
            
            # Отправляем всем слушателям
            for queue in self.listeners:
                try:
                    await queue.put(event)
                except asyncio.QueueFull:
                    pass  # Пропускаем если очередь переполнена
        
        logger.debug(f"[Progress:{self.operation_id}] {stage}: {message} ({progress*100:.0f}%)")
    
    async def complete(self, message: str = "Завершено", details: Optional[Dict[str, Any]] = None) -> None:
        """Завершает отслеживание."""
        await self.update(ProgressStage.COMPLETED.value, message, 1.0, details)
        self.completed = True
        
        # Закрываем все очереди
        async with self._lock:
            for queue in self.listeners:
                await queue.put(None)  # Сигнал завершения
    
    async def error(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Сообщает об ошибке."""
        await self.update(ProgressStage.ERROR.value, message, -1, details)
        self.completed = True
        
        async with self._lock:
            for queue in self.listeners:
                await queue.put(None)
    
    def subscribe(self) -> asyncio.Queue:
        """Подписывается на события прогресса."""
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Отписывается от событий."""
        if queue in self.listeners:
            self.listeners.remove(queue)
    
    async def stream_events(self) -> AsyncIterator[ProgressEvent]:
        """Генератор событий для SSE."""
        queue = self.subscribe()
        try:
            # Отправляем историю
            for event in self.events:
                yield event
            
            # Слушаем новые события
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self.unsubscribe(queue)


class ProgressManager:
    """
    Менеджер прогресса для всего приложения.
    
    Синглтон для управления всеми трекерами прогресса.
    """
    
    _instance: Optional['ProgressManager'] = None
    
    def __new__(cls) -> 'ProgressManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._trackers: Dict[str, ProgressTracker] = {}
        self._lock = asyncio.Lock()
    
    async def create_tracker(self, operation_type: str) -> ProgressTracker:
        """Создаёт новый трекер."""
        operation_id = str(uuid.uuid4())[:8]
        tracker = ProgressTracker(operation_id, operation_type)
        
        async with self._lock:
            self._trackers[operation_id] = tracker
        
        logger.debug(f"[ProgressManager] Created tracker: {operation_id} for {operation_type}")
        return tracker
    
    async def get_tracker(self, operation_id: str) -> Optional[ProgressTracker]:
        """Получает трекер по ID."""
        return self._trackers.get(operation_id)
    
    async def remove_tracker(self, operation_id: str) -> None:
        """Удаляет трекер."""
        async with self._lock:
            if operation_id in self._trackers:
                del self._trackers[operation_id]
    
    async def cleanup_old_trackers(self, max_age_seconds: int = 3600) -> int:
        """Очищает старые завершённые трекеры."""
        now = datetime.now()
        removed = 0
        
        async with self._lock:
            to_remove = []
            for op_id, tracker in self._trackers.items():
                if tracker.completed:
                    age = (now - tracker.started_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(op_id)
            
            for op_id in to_remove:
                del self._trackers[op_id]
                removed += 1
        
        return removed


# Глобальный экземпляр
progress_manager = ProgressManager()


def get_progress_manager() -> ProgressManager:
    """Получает глобальный менеджер прогресса."""
    return progress_manager

