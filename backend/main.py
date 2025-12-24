"""
FastAPI application entry point
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from .config import get_config
from .core.engine import IDAEngine
from .core.logger import get_logger, configure_logging
from .api.routers import tasks, code, tools, preview, config as config_router, monitoring, project, multimodal, metrics, batch, feedback
from .api.docs import custom_openapi
from .core.safety_utils import setup_signal_handlers
from .core.preview_manager import PreviewManager
from .core.rate_limiter import RateLimitMiddleware, RateLimiter

# Инициализируем логгер
logger = get_logger(__name__)


# Global engine and preview manager instances
engine: IDAEngine = None
preview_manager: PreviewManager = None


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors.get("origins", ["*"]),
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
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            message_type = data.get("type")
            
            if message_type == "task":
                # Execute task
                task = data.get("task")
                agent_type = data.get("agent_type")
                context = data.get("context", {})
                
                if engine:
                    result = await engine.execute_task(task, agent_type, context)
                    await websocket.send_json({
                        "type": "result",
                        "data": result
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Движок не инициализирован"
                    })
            
            elif message_type == "status":
                # Get status
                if engine:
                    status = engine.get_status()
                    await websocket.send_json({
                        "type": "status",
                        "data": status
                    })
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "backend.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        workers=config.api.workers
    )

