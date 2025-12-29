"""
Unified logging system for AILLM

Все модули должны использовать этот модуль для логирования:
    from backend.core.logger import get_logger
    logger = get_logger(__name__)

Особенности:
- Единый формат для всех компонентов
- Поддержка correlation ID для трассировки запросов
- Настраиваемые уровни по компонентам
- Интеграция с Uvicorn
"""

from loguru import logger
from pathlib import Path
from typing import Dict, Any, Optional, Set
import sys
import contextvars
import logging


# Context variable for correlation ID (shared with error_handler)
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    'correlation_id', default=''
)


def get_correlation_id() -> str:
    """Get current correlation ID for request tracing"""
    return _correlation_id.get() or ''


def set_correlation_id(cid: str) -> None:
    """Set correlation ID for current context"""
    _correlation_id.set(cid)


# Глобальная переменная для хранения конфигурации логирования
_logging_config: Optional[Dict[str, Any]] = None
_logger_initialized: bool = False

# Уровни логирования по компонентам (можно настраивать)
_component_levels: Dict[str, str] = {}

# Компоненты с подавленным DEBUG (слишком шумные)
_quiet_components: Set[str] = {
    "backend.tools.registry",
    "backend.core.intelligent_monitor",
    "backend.core.distributed_model_router",
    "backend.agents.communicator",
    "httpx",
    "httpcore",
}


def set_component_level(component: str, level: str) -> None:
    """Set log level for specific component"""
    _component_levels[component] = level.upper()


def get_logger(name: str = None):
    """
    Получить логгер для модуля
    
    Args:
        name: Имя модуля (обычно __name__)
    
    Returns:
        loguru logger instance с правильной конфигурацией
    
    Example:
        from backend.core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Message")
    """
    if not _logger_initialized:
        _initialize_logger()
    
    if name:
        return logger.bind(module=name)
    return logger


def configure_logging(config: Dict[str, Any]) -> None:
    """
    Настроить логирование из конфигурации
    
    Args:
        config: Словарь с настройками логирования:
            - level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
            - format: формат (json, text) - рекомендуется text для консоли
            - file: путь к файлу логов
            - max_size_mb: максимальный размер файла в MB
            - backup_count: количество резервных копий
            - component_levels: dict с уровнями для конкретных компонентов
            - quiet_components: list компонентов с подавленным DEBUG
    """
    global _logging_config, _logger_initialized, _component_levels, _quiet_components
    _logging_config = config
    
    # Настройка уровней по компонентам
    if "component_levels" in config:
        _component_levels.update(config["component_levels"])
    
    # Добавляем quiet компоненты
    if "quiet_components" in config:
        _quiet_components.update(config["quiet_components"])
    
    _logger_initialized = False
    _initialize_logger()


def _format_record(record: dict) -> str:
    """
    Форматирует запись лога с correlation ID.
    Используется для кастомного формата.
    """
    # Получаем correlation ID
    cid = get_correlation_id()
    cid_part = f"[{cid}] " if cid else ""
    
    # Получаем имя модуля (короткое)
    module = record.get("extra", {}).get("module", record.get("name", ""))
    if module and module.startswith("backend."):
        module = module[8:]  # Убираем "backend."
    
    # Формируем сообщение
    return (
        f"<green>{{time:HH:mm:ss}}</green> | "
        f"<level>{{level: <7}}</level> | "
        f"<cyan>{module or '{{name}}'}</cyan> | "
        f"{cid_part}<level>{{message}}</level>\n"
    )


def _filter_by_component(record: dict) -> bool:
    """
    Фильтр для подавления DEBUG логов от шумных компонентов.
    """
    module = record.get("extra", {}).get("module", record.get("name", ""))
    level = record["level"].name
    
    # Проверяем quiet компоненты
    for quiet in _quiet_components:
        if module and quiet in module:
            if level == "DEBUG":
                return False  # Подавляем DEBUG
    
    # Проверяем кастомные уровни
    for component, min_level in _component_levels.items():
        if module and component in module:
            level_no = record["level"].no
            min_level_no = logger.level(min_level).no
            return level_no >= min_level_no
    
    return True


def _initialize_logger() -> None:
    """Инициализировать логгер с текущей конфигурацией"""
    global _logger_initialized, _logging_config
    
    # Удаляем все существующие обработчики
    logger.remove()
    
    # Если конфигурация не установлена, используем значения по умолчанию
    # (должны совпадать с config.yaml)
    if _logging_config is None:
        _logging_config = {
            "level": "INFO",
            "format": "text",
            "file": "logs/aillm.log",  # Синхронизировано с config.yaml
            "max_size_mb": 100,
            "backup_count": 5
        }
    
    level = _logging_config.get("level", "INFO").upper()
    log_format = _logging_config.get("format", "text")
    log_file = _logging_config.get("file", "logs/app.log")
    max_size_mb = _logging_config.get("max_size_mb", 100)
    backup_count = _logging_config.get("backup_count", 5)
    
    # Создаем директорию для логов если её нет
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Единый формат для консоли - чистый и читаемый
    console_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <7}</level> | "
        "<cyan>{extra[module]}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Формат для файла - полная информация
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{extra[module]}:{function}:{line} | "
        "{message}"
    )
    
    # JSON формат для структурированного логирования
    if log_format == "json":
        console_format = "{message}"
    
    # Патчим record чтобы добавить module если его нет
    def patcher(record):
        if "module" not in record["extra"]:
            record["extra"]["module"] = record["name"] or "root"
    
    logger.configure(patcher=patcher)
    
    # Обработчик консоли с фильтрацией
    logger.add(
        sys.stdout,
        format=console_format,
        level=level,
        colorize=(log_format != "json"),
        serialize=(log_format == "json"),
        filter=_filter_by_component,
    )
    
    # Обработчик файла для всех логов (включая DEBUG)
    logger.add(
        log_file,
        format=file_format,
        level="DEBUG",
        rotation=f"{max_size_mb} MB",
        retention=backup_count,
        serialize=False,  # Файл всегда текстовый для читаемости
        encoding="utf-8",
        filter=_filter_by_component,
    )
    
    # Отдельный файл для ошибок
    error_log_file = str(log_path.parent / "error.log")
    logger.add(
        error_log_file,
        format=file_format,
        level="ERROR",
        rotation=f"{max_size_mb // 2} MB",
        retention=backup_count,
        serialize=False,
        encoding="utf-8",
    )
    
    # Интегрируем стандартный logging (для uvicorn и библиотек)
    _setup_stdlib_logging(level)
    
    _logger_initialized = True


def _setup_stdlib_logging(level: str) -> None:
    """
    Перенаправляет стандартный logging в loguru.
    Это интегрирует uvicorn, httpx и другие библиотеки.
    """
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level
            try:
                level_name = record.levelname
            except ValueError:
                level_name = record.levelno

            # Find caller from where originated the logged message
            frame, depth = sys._getframe(6), 6
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.bind(module=record.name).opt(depth=depth, exception=record.exc_info).log(
                level_name, record.getMessage()
            )
    
    # Перехватываем root logger
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Настраиваем uvicorn логгеры
    for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
    
    # Подавляем слишком подробные логи от библиотек
    for name in ["httpx", "httpcore", "asyncio"]:
        logging.getLogger(name).setLevel(logging.WARNING)


class StructuredLogger:
    """
    Структурированное логирование с контекстом и correlation ID.
    
    Использует единый формат для всех типов событий:
    - AGENT: действия агентов
    - TOOL: выполнение инструментов
    - LLM: запросы к моделям
    - TASK: выполнение задач
    - API: входящие запросы
    """
    
    def __init__(self, name: str = "AILLM"):
        self.name = name
        self._logger = get_logger(name)
    
    def _get_cid(self) -> str:
        """Получить correlation ID"""
        return get_correlation_id()
    
    def _format_duration(self, duration: Optional[float]) -> str:
        """Форматирует длительность в читаемый вид"""
        if duration is None:
            return ""
        if duration < 1:
            return f"{duration * 1000:.0f}ms"
        return f"{duration:.1f}s"
    
    def log_agent_action(
        self,
        agent_name: str,
        action: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None
    ):
        """Логирование действия агента"""
        self._get_cid()
        dur_str = self._format_duration(duration)
        
        # Определяем статус
        status = "✓" if result and result.get("success") else "✗" if result else "→"
        
        # Краткое сообщение
        msg = f"[AGENT] {status} {agent_name}.{action}"
        if dur_str:
            msg += f" ({dur_str})"
        
        # Логируем
        if result and not result.get("success"):
            self._logger.warning(msg)
        else:
            self._logger.info(msg)
    
    def log_tool_execution(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Логирование выполнения инструмента"""
        dur_str = self._format_duration(duration)
        status = "✗" if error else "✓"
        
        msg = f"[TOOL] {status} {tool_name}"
        if dur_str:
            msg += f" ({dur_str})"
        if error:
            msg += f" - {error[:50]}"
        
        if error:
            self._logger.warning(msg)
        else:
            self._logger.debug(msg)  # Tools are verbose, use debug
    
    def log_llm_request(
        self,
        provider: str,
        model: str,
        messages: list,
        response: Optional[str] = None,
        duration: Optional[float] = None,
        tokens: Optional[int] = None,
        error: Optional[str] = None
    ):
        """Логирование LLM запроса"""
        dur_str = self._format_duration(duration)
        status = "✗" if error else "✓"
        
        msg = f"[LLM] {status} {provider}/{model}"
        if tokens:
            msg += f" [{tokens} tok]"
        if dur_str:
            msg += f" ({dur_str})"
        if error:
            msg += f" - {error[:50]}"
        
        if error:
            self._logger.error(msg)
        else:
            self._logger.info(msg)
    
    def log_task_execution(
        self,
        task: str,
        agent_type: Optional[str],
        result: Dict[str, Any],
        duration: Optional[float] = None
    ):
        """Логирование выполнения задачи"""
        dur_str = self._format_duration(duration)
        success = result.get("success", False)
        status = "✓" if success else "✗"
        
        # Обрезаем task до читаемой длины
        task_short = task[:60] + "..." if len(task) > 60 else task
        
        msg = f"[TASK] {status} {task_short}"
        if agent_type:
            msg = f"[TASK] {status} [{agent_type}] {task_short}"
        if dur_str:
            msg += f" ({dur_str})"
        
        if success:
            self._logger.info(msg)
        else:
            error = result.get("error", "unknown error")
            self._logger.error(f"{msg} - {error[:50]}")
    
    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: Optional[float] = None,
        user: Optional[str] = None,
    ):
        """Логирование API запроса"""
        dur_str = self._format_duration(duration)
        
        msg = f"[API] {method} {path} → {status_code}"
        if dur_str:
            msg += f" ({dur_str})"
        
        if status_code >= 500:
            self._logger.error(msg)
        elif status_code >= 400:
            self._logger.warning(msg)
        else:
            self._logger.debug(msg)  # Successful requests are verbose


# Глобальный экземпляр структурированного логгера
structured_logger = StructuredLogger()


# ==================== Middleware для FastAPI ====================

def create_logging_middleware():
    """
    Создаёт middleware для FastAPI с автоматическим correlation ID.
    
    Usage:
        from backend.core.logger import create_logging_middleware
        app.add_middleware(BaseHTTPMiddleware, dispatch=create_logging_middleware())
    """
    import time
    import uuid
    from starlette.requests import Request
    
    async def logging_middleware(request: Request, call_next):
        # Генерируем или получаем correlation ID
        cid = request.headers.get("X-Correlation-ID") or f"req-{uuid.uuid4().hex[:8]}"
        set_correlation_id(cid)
        
        # Логируем начало запроса
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Логируем завершение
            duration = time.time() - start_time
            structured_logger.log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=duration,
            )
            
            # Добавляем correlation ID в response headers
            response.headers["X-Correlation-ID"] = cid
            
            return response
        except Exception as e:
            duration = time.time() - start_time
            get_logger("api").error(f"[API] {request.method} {request.url.path} failed: {e}")
            raise
        finally:
            # Очищаем correlation ID
            set_correlation_id("")
    
    return logging_middleware


# ==================== Утилиты ====================

def log_exception(
    exc: Exception,
    context: str = "",
    level: str = "ERROR",
) -> None:
    """
    Удобная функция для логирования исключений с контекстом.
    
    Args:
        exc: Исключение
        context: Дополнительный контекст
        level: Уровень логирования
    """
    get_correlation_id()
    msg = f"Exception: {type(exc).__name__}: {exc}"
    if context:
        msg = f"{context} - {msg}"
    
    log = get_logger("exception")
    if level == "ERROR":
        log.error(msg)
    elif level == "WARNING":
        log.warning(msg)
    else:
        log.info(msg)


def with_correlation_id(cid: str = None):
    """
    Context manager для установки correlation ID.
    
    Usage:
        with with_correlation_id("my-task-123"):
            logger.info("This log will have correlation ID")
    """
    import uuid
    from contextlib import contextmanager
    
    @contextmanager
    def _context():
        old_cid = get_correlation_id()
        new_cid = cid or f"ctx-{uuid.uuid4().hex[:8]}"
        set_correlation_id(new_cid)
        try:
            yield new_cid
        finally:
            set_correlation_id(old_cid)
    
    return _context()


# Инициализируем логирование при импорте модуля (будет переконфигурировано при загрузке конфигурации)
if not _logger_initialized:
    _initialize_logger()
