"""
FastAPI application entry point
"""

from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from .config import get_config
from .core.engine import IDAEngine
from .core.logger import get_logger, configure_logging, create_logging_middleware
from .api.routers import tasks, code, tools, preview, config as config_router, monitoring, project, multimodal, metrics, batch, feedback, learning, chat, models, secret, code_intelligence
from .api.docs import custom_openapi
from .core.preview_manager import PreviewManager
from .core.rate_limiter import RateLimitMiddleware, RateLimiter
from starlette.middleware.base import BaseHTTPMiddleware

# Инициализируем логгер
logger = get_logger(__name__)


# Global engine and preview manager instances
engine: Optional[IDAEngine] = None
preview_manager: Optional[PreviewManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    global engine, preview_manager
    
    # Startup
    logger.info("Starting AILLM API server...")
    config = get_config()
    
    # Настраиваем логирование из конфигурации
    if config.logging:
        from backend.core.pydantic_utils import pydantic_to_dict
        logging_config = pydantic_to_dict(config.logging)
        configure_logging(logging_config)
        logger.info("Logging configured from settings")
    
    engine = IDAEngine(config)
    await engine.initialize()
    
    preview_manager = PreviewManager(port_pool=set(range(9000, 9051)))
    
    # Store engine in app state
    app.state.engine = engine
    app.state.preview_manager = preview_manager
    
    yield
    
    # Shutdown
    logger.info("Shutting down AILLM API server...")
    if engine:
        await engine.shutdown()
    engine = None
    preview_manager = None


# Create FastAPI app
app = FastAPI(
    title="AILLM API",
    description="Autonomous Intelligent LLM Agents for Software Development",
    version="0.1.0",
    lifespan=lifespan
)

# Custom OpenAPI schema
app.openapi = lambda: custom_openapi(app)

# CORS middleware
config = get_config()
if config.api.cors.get("enabled", True):
    cors_origins = config.api.cors.get("origins", ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"])
    # Security: if credentials=True, origins cannot be "*" - use specific origins
    if cors_origins == ["*"] or "*" in cors_origins:
        # For development, use common localhost ports; in production should be configured explicitly
        cors_origins = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://localhost:8000"]
        logger.warning("CORS origins set to '*' with credentials - using localhost defaults for security")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Rate limiting middleware
rate_limit_config = getattr(config.api, "rate_limit", {})
if isinstance(rate_limit_config, dict):
    enabled = rate_limit_config.get("enabled", True)
    requests_per_minute = rate_limit_config.get("requests_per_minute", 60)
    requests_per_hour = rate_limit_config.get("requests_per_hour", 1000)
    requests_per_day = rate_limit_config.get("requests_per_day", 10000)
else:
    enabled = getattr(rate_limit_config, "enabled", True) if hasattr(rate_limit_config, "enabled") else True
    requests_per_minute = getattr(rate_limit_config, "requests_per_minute", 60) if hasattr(rate_limit_config, "requests_per_minute") else 60
    requests_per_hour = getattr(rate_limit_config, "requests_per_hour", 1000) if hasattr(rate_limit_config, "requests_per_hour") else 1000
    requests_per_day = getattr(rate_limit_config, "requests_per_day", 10000) if hasattr(rate_limit_config, "requests_per_day") else 10000

if enabled:
    rate_limiter = RateLimiter(
        requests_per_minute=requests_per_minute,
        requests_per_hour=requests_per_hour,
        requests_per_day=requests_per_day
    )
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    logger.info(f"Rate limiting enabled: {requests_per_minute}/min, {requests_per_hour}/hour, {requests_per_day}/day")

# Logging middleware with correlation ID (добавляется последним чтобы выполнялся первым)
app.add_middleware(BaseHTTPMiddleware, dispatch=create_logging_middleware())

# Include routers
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(code.router, prefix="/api/v1", tags=["code"])
app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
app.include_router(preview.router, prefix="/api/v1", tags=["preview"])
app.include_router(config_router.router, prefix="/api/v1", tags=["config"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
app.include_router(project.router, prefix="/api/v1", tags=["project"])
app.include_router(multimodal.router, prefix="/api/v1", tags=["multimodal"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(batch.router, prefix="/api/v1", tags=["batch"])
app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])
app.include_router(learning.router, prefix="/api/v1", tags=["learning"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(models.router, prefix="/api/v1", tags=["models"])
app.include_router(code_intelligence.router, prefix="/api/v1", tags=["code-intelligence"])
app.include_router(secret.router, prefix="/api/secret")  # 🥚 Скрытый роутер


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "AILLM API",
        "version": "0.1.0",
        "status": "работает",
        "description": "Автономные интеллектуальные LLM агенты для разработки ПО"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    global engine
    if engine:
        status = engine.get_status()
        return {"status": "работает", "engine": status}
    return {"status": "инициализация"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    logger.info("WebSocket client connected")
    
    async def send_progress(stage: str, progress: float, message: str, data: dict = None):
        """Callback для отправки прогресса клиенту"""
        try:
            await websocket.send_json({
                "type": "progress",
                "stage": stage,
                "progress": progress,
                "message": message,
                "data": data or {}
            })
        except Exception as e:
            logger.warning(f"Failed to send progress: {e}")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            message_type = data.get("type")
            
            if message_type == "ping":
                # Heartbeat для поддержания соединения
                await websocket.send_json({"type": "pong"})
            
            elif message_type == "task":
                # Execute task with progress updates
                task = data.get("task")
                agent_type = data.get("agent_type")
                context = data.get("context", {})
                model = data.get("model")
                provider = data.get("provider")
                
                if engine:
                    # Отправляем начало
                    await send_progress("started", 0, "Начинаем выполнение задачи...")
                    
                    try:
                        # Добавляем callback для прогресса в контекст
                        context["_progress_callback"] = send_progress
                        context["model"] = model
                        context["provider"] = provider
                        
                        await send_progress("processing", 20, "Анализируем задачу...")
                        
                        result = await engine.execute_task(task, agent_type, context)
                        
                        await send_progress("completed", 100, "Задача выполнена!")
                        
                        await websocket.send_json({
                            "type": "result",
                            "data": result,
                            "success": True
                        })
                    except Exception as task_error:
                        logger.error(f"Task execution error: {task_error}")
                        await send_progress("error", 0, str(task_error))
                        await websocket.send_json({
                            "type": "result",
                            "data": {"error": str(task_error)},
                            "success": False
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Движок не инициализирован"
                    })
            
            elif message_type == "chat":
                # Chat with progress
                message = data.get("message")
                history = data.get("history", [])
                mode = data.get("mode", "general")
                model = data.get("model")
                provider = data.get("provider")
                
                if engine and engine.llm_manager:
                    await send_progress("started", 0, "Обрабатываем сообщение...")
                    
                    try:
                        from backend.api.routers.chat import ChatRequest, chat
                        from unittest.mock import Mock
                        
                        # Создаём mock request с необходимыми атрибутами
                        mock_request = Mock()
                        mock_request.app.state.engine = engine
                        
                        chat_request = ChatRequest(
                            message=message,
                            history=[{"role": h["role"], "content": h["content"]} for h in history] if history else None,
                            mode=mode,
                            model=model,
                            provider=provider
                        )
                        
                        await send_progress("processing", 50, "Генерируем ответ...")
                        
                        response = await chat(mock_request, chat_request)
                        
                        await send_progress("completed", 100, "Готово!")
                        
                        await websocket.send_json({
                            "type": "chat_response",
                            "data": {
                                "success": response.success,
                                "message": response.message,
                                "error": response.error,
                                "warning": response.warning,
                                "metadata": response.metadata
                            }
                        })
                    except Exception as chat_error:
                        logger.error(f"Chat error via WebSocket: {chat_error}")
                        await websocket.send_json({
                            "type": "chat_response",
                            "data": {
                                "success": False,
                                "message": "",
                                "error": str(chat_error)
                            }
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "LLM провайдер не доступен"
                    })
            
            elif message_type == "status":
                # Get status
                if engine:
                    status = engine.get_status()
                    await websocket.send_json({
                        "type": "status",
                        "data": status
                    })
            
            elif message_type == "subscribe":
                # Подписка на обновления статуса
                channel = data.get("channel", "status")
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": channel
                })
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            pass  # Connection already closed


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "backend.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        workers=config.api.workers
    )

