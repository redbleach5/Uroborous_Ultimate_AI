"""
Rate Limiter - Middleware для ограничения частоты запросов
"""

import time
from typing import Dict, Optional, Tuple
from collections import defaultdict
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from .logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Rate limiter для ограничения частоты запросов
    
    Использует sliding window алгоритм для более точного ограничения
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000
    ):
        """
        Инициализация rate limiter
        
        Args:
            requests_per_minute: Максимальное количество запросов в минуту
            requests_per_hour: Максимальное количество запросов в час
            requests_per_day: Максимальное количество запросов в день
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests_per_day = requests_per_day
        
        # Хранилище запросов: {identifier: [timestamps]}
        self.requests: Dict[str, list] = defaultdict(list)
        
        # Время последней очистки
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Очистка каждые 5 минут
    
    def _get_identifier(self, request: Request) -> str:
        """
        Получает идентификатор клиента для rate limiting
        
        Приоритет:
        1. API ключ из заголовка (если есть)
        2. IP адрес
        """
        # Проверяем API ключ
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"
        
        # Используем IP адрес
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"
    
    def _cleanup_old_requests(self):
        """Очищает старые записи для экономии памяти"""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
        
        # Удаляем записи старше 24 часов
        cutoff_time = current_time - 86400  # 24 часа
        
        for identifier in list(self.requests.keys()):
            self.requests[identifier] = [
                ts for ts in self.requests[identifier]
                if ts > cutoff_time
            ]
            # Удаляем пустые списки
            if not self.requests[identifier]:
                del self.requests[identifier]
        
        self.last_cleanup = current_time
    
    def is_allowed(self, request: Request) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, разрешен ли запрос
        
        Returns:
            (is_allowed, error_message)
        """
        self._cleanup_old_requests()
        
        identifier = self._get_identifier(request)
        current_time = time.time()
        
        # Получаем историю запросов
        request_times = self.requests[identifier]
        
        # Удаляем запросы старше 24 часов
        request_times = [ts for ts in request_times if ts > current_time - 86400]
        self.requests[identifier] = request_times
        
        # Проверяем лимиты
        # 1. Минутный лимит
        minute_ago = current_time - 60
        recent_requests = [ts for ts in request_times if ts > minute_ago]
        if len(recent_requests) >= self.requests_per_minute:
            return False, f"Rate limit exceeded: {self.requests_per_minute} requests per minute"
        
        # 2. Часовой лимит
        hour_ago = current_time - 3600
        hour_requests = [ts for ts in request_times if ts > hour_ago]
        if len(hour_requests) >= self.requests_per_hour:
            return False, f"Rate limit exceeded: {self.requests_per_hour} requests per hour"
        
        # 3. Дневной лимит
        day_ago = current_time - 86400
        day_requests = [ts for ts in request_times if ts > day_ago]
        if len(day_requests) >= self.requests_per_day:
            return False, f"Rate limit exceeded: {self.requests_per_day} requests per day"
        
        # Запрос разрешен - добавляем timestamp
        request_times.append(current_time)
        self.requests[identifier] = request_times
        
        return True, None
    
    def get_remaining_requests(self, request: Request) -> Dict[str, int]:
        """
        Возвращает количество оставшихся запросов для каждого периода
        """
        identifier = self._get_identifier(request)
        current_time = time.time()
        request_times = self.requests.get(identifier, [])
        
        # Удаляем старые запросы
        request_times = [ts for ts in request_times if ts > current_time - 86400]
        
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        day_ago = current_time - 86400
        
        return {
            "per_minute": max(0, self.requests_per_minute - len([ts for ts in request_times if ts > minute_ago])),
            "per_hour": max(0, self.requests_per_hour - len([ts for ts in request_times if ts > hour_ago])),
            "per_day": max(0, self.requests_per_day - len([ts for ts in request_times if ts > day_ago]))
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware для rate limiting
    """
    
    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()
    
    async def dispatch(self, request: Request, call_next):
        # Пропускаем health check и другие системные endpoints
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Проверяем rate limit
        is_allowed, error_message = self.rate_limiter.is_allowed(request)
        
        if not is_allowed:
            remaining = self.rate_limiter.get_remaining_requests(request)
            logger.warning(
                f"Rate limit exceeded for {self.rate_limiter._get_identifier(request)}: {error_message}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": error_message,
                    "remaining": remaining
                }
            )
        
        # Выполняем запрос
        response = await call_next(request)
        
        # Добавляем заголовки с информацией о rate limit
        remaining = self.rate_limiter.get_remaining_requests(request)
        response.headers["X-RateLimit-Limit-Minute"] = str(self.rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Limit-Hour"] = str(self.rate_limiter.requests_per_hour)
        response.headers["X-RateLimit-Limit-Day"] = str(self.rate_limiter.requests_per_day)
        response.headers["X-RateLimit-Remaining-Minute"] = str(remaining["per_minute"])
        response.headers["X-RateLimit-Remaining-Hour"] = str(remaining["per_hour"])
        response.headers["X-RateLimit-Remaining-Day"] = str(remaining["per_day"])
        
        return response

