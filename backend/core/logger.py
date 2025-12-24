"""
Unified logging system for AILLM
Все модули должны использовать этот модуль для логирования
"""

from loguru import logger
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import json


# Глобальная переменная для хранения конфигурации логирования
_logging_config: Optional[Dict[str, Any]] = None
_logger_initialized: bool = False


def get_logger(name: str = None):
    """
    Получить логгер для модуля
    
    Args:
        name: Имя модуля (опционально, будет автоматически определено из стека вызовов)
    
    Returns:
        loguru logger instance с правильной конфигурацией
    """
    if not _logger_initialized:
        _initialize_logger()
    
    if name:
        return logger.bind(name=name)
    return logger


def configure_logging(config: Dict[str, Any]) -> None:
    """
    Настроить логирование из конфигурации
    
    Args:
        config: Словарь с настройками логирования:
            - level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
            - format: формат (json, text)
            - file: путь к файлу логов
            - max_size_mb: максимальный размер файла в MB
            - backup_count: количество резервных копий
    """
    global _logging_config, _logger_initialized
    _logging_config = config
    _logger_initialized = False
    _initialize_logger()


def _initialize_logger() -> None:
    """Инициализировать логгер с текущей конфигурацией"""
    global _logger_initialized, _logging_config
    
    # Удаляем все существующие обработчики
    logger.remove()
    
    # Если конфигурация не установлена, используем значения по умолчанию
    if _logging_config is None:
        _logging_config = {
            "level": "INFO",
            "format": "text",
            "file": "logs/app.log",
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
    
    # Форматы логирования
    if log_format == "json":
        console_format = "{message}"
        file_format = "{message}"
    else:
        console_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        file_format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
    
    # Обработчик консоли
    logger.add(
        sys.stdout,
        format=console_format,
        level=level,
        colorize=(log_format != "json"),
        serialize=(log_format == "json")
    )
    
    # Обработчик файла для всех логов
    logger.add(
        log_file,
        format=file_format,
        level="DEBUG",  # В файл пишем все уровни
        rotation=f"{max_size_mb} MB",
        retention=backup_count,  # Количество файлов (число, не строка)
        serialize=(log_format == "json"),
        encoding="utf-8"
    )
    
    # Отдельный файл для ошибок
    error_log_file = str(log_path.parent / "error.log")
    logger.add(
        error_log_file,
        format=file_format,
        level="ERROR",
        rotation=f"{max_size_mb // 2} MB",
        retention=backup_count,  # Количество файлов (число, не строка)
        serialize=(log_format == "json"),
        encoding="utf-8"
    )
    
    _logger_initialized = True


class StructuredLogger:
    """Структурированное логирование с контекстом"""
    
    def __init__(self, name: str = "AILLM"):
        self.name = name
        self._logger = get_logger(name)
    
    def log_agent_action(
        self,
        agent_name: str,
        action: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None
    ):
        """Логирование действия агента со структурированными данными"""
        log_data = {
            "agent": agent_name,
            "action": action,
            "task": task,
            "timestamp": datetime.utcnow().isoformat(),
            "context": context or {},
            "duration_ms": duration * 1000 if duration else None
        }
        
        if result:
            log_data["result"] = {
                "success": result.get("success", False),
                "error": result.get("error")
            }
        
        self._logger.info(f"[AGENT] {agent_name} - {action}", extra={"data": log_data})
    
    def log_tool_execution(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Логирование выполнения инструмента"""
        log_data = {
            "tool": tool_name,
            "input": input_data,
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": duration * 1000 if duration else None
        }
        
        if result:
            log_data["result"] = result
        if error:
            log_data["error"] = error
        
        self._logger.info(f"[TOOL] {tool_name}", extra={"data": log_data})
    
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
        log_data = {
            "provider": provider,
            "model": model,
            "messages_count": len(messages),
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": duration * 1000 if duration else None,
            "tokens": tokens
        }
        
        if response:
            log_data["response_length"] = len(response)
        if error:
            log_data["error"] = error
        
        self._logger.info(f"[LLM] {provider}/{model}", extra={"data": log_data})
    
    def log_task_execution(
        self,
        task: str,
        agent_type: Optional[str],
        result: Dict[str, Any],
        duration: Optional[float] = None
    ):
        """Логирование выполнения задачи"""
        log_data = {
            "task": task,
            "agent_type": agent_type,
            "timestamp": datetime.utcnow().isoformat(),
            "success": result.get("success", False),
            "duration_ms": duration * 1000 if duration else None
        }
        
        if result.get("error"):
            log_data["error"] = result["error"]
        
        self._logger.info(f"[TASK] {task[:50]}...", extra={"data": log_data})


# Глобальный экземпляр структурированного логгера
structured_logger = StructuredLogger()


# Инициализируем логирование при импорте модуля (будет переконфигурировано при загрузке конфигурации)
if not _logger_initialized:
    _initialize_logger()
