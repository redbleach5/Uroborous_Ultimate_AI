"""
Monitoring router
"""

from fastapi import APIRouter, Request

from ...core.logger import get_logger
logger = get_logger(__name__)

router = APIRouter()


@router.get("/monitoring/metrics")
async def get_metrics(request: Request):
    """Получить метрики системы"""
    engine = request.app.state.engine
    
    if not engine:
        return {"status": "не_инициализирован"}
    
    # Basic metrics
    status = engine.get_status()
    
    return {
        "engine_status": status,
        "agents": {
            name: {"available": True}
            for name in engine.agent_registry.list_agents() if engine.agent_registry
        },
        "llm_providers": {
            name: {"available": engine.llm_manager.is_provider_available(name)}
            for name in ["openai", "anthropic", "ollama"]
            if engine.llm_manager
        }
    }


@router.get("/monitoring/health")
async def get_health_report(request: Request):
    """Получить отчет о здоровье системы от Intelligent Monitor"""
    engine = request.app.state.engine
    
    if not engine or not hasattr(engine, 'monitor') or not engine.monitor:
        return {
            "status": "monitor_not_available",
            "message": "Intelligent monitor не инициализирован"
        }
    
    try:
        health_report = engine.monitor.get_health_report()
        return health_report
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ошибка получения отчета: {str(e)}"
        }


@router.get("/monitoring/debug-logs")
async def get_debug_logs_info(request: Request):
    """Получить информацию о debug логах"""
    engine = request.app.state.engine
    
    if not engine or not hasattr(engine, 'monitor') or not engine.monitor:
        return {
            "status": "monitor_not_available",
            "message": "Intelligent monitor не инициализирован"
        }
    
    
    debug_dir = engine.monitor.debug_logs_dir
    
    try:
        log_files = {}
        if debug_dir.exists():
            for log_file in debug_dir.glob("*.log"):
                stat = log_file.stat()
                log_files[log_file.name] = {
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified": stat.st_mtime,
                }
        
        return {
            "debug_logs_directory": str(debug_dir),
            "directory_exists": debug_dir.exists(),
            "log_files": log_files,
            "monitoring_active": engine.monitor._monitoring_active,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ошибка получения информации о логах: {str(e)}"
        }


@router.get("/monitoring/check-availability")
async def check_availability(request: Request):
    """Проверить доступность сервера и моделей LLM провайдеров"""
    import httpx
    from backend.config import get_config
    
    engine = request.app.state.engine
    
    if not engine:
        return {
            "server_available": False,
            "message": "Engine не инициализирован",
            "providers": {}
        }
    
    result = {
        "server_available": True,
        "message": "Сервер доступен",
        "providers": {}
    }
    
    # Проверяем доступность LLM провайдеров и их моделей
    if engine.llm_manager:
        try:
            # Для Ollama делаем прямую проверку через API
            config = get_config()
            if config.llm and config.llm.providers and "ollama" in config.llm.providers:
                ollama_config = config.llm.providers["ollama"]
                base_url = ollama_config.base_url if ollama_config.base_url else "http://localhost:11434"
                
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"{base_url}/api/tags")
                        if response.status_code == 200:
                            data = response.json()
                            models = [model["name"] for model in data.get("models", [])]
                            result["providers"]["ollama"] = {
                                "available": True,
                                "models_available": len(models),
                                "models": models,
                                "status": "ok" if models else "no_models"
                            }
                        else:
                            result["providers"]["ollama"] = {
                                "available": False,
                                "models_available": 0,
                                "models": [],
                                "status": "error",
                                "error": f"HTTP {response.status_code}"
                            }
                except Exception as e:
                    logger.warning(f"Error checking Ollama directly: {e}")
                    result["providers"]["ollama"] = {
                        "available": False,
                        "models_available": 0,
                        "models": [],
                        "status": "error",
                        "error": str(e)
                    }
            
            # Для остальных провайдеров используем стандартный метод
            all_providers = await engine.llm_manager.list_available_models()
            
            for provider_name, models in all_providers.items():
                # Пропускаем Ollama, так как уже проверили напрямую
                if provider_name == "ollama":
                    continue
                    
                try:
                    provider_available = engine.llm_manager.is_provider_available(provider_name)
                    result["providers"][provider_name] = {
                        "available": provider_available,
                        "models_available": len(models) if models else 0,
                        "models": models if models else [],
                        "status": "ok" if provider_available and models else ("unavailable" if not provider_available else "no_models")
                    }
                except Exception as e:
                    logger.warning(f"Error checking provider {provider_name}: {e}")
                    result["providers"][provider_name] = {
                        "available": False,
                        "models_available": 0,
                        "models": [],
                        "status": "error",
                        "error": str(e)
                    }
        except Exception as e:
            logger.error(f"Error checking LLM providers availability: {e}")
            result["message"] = f"Ошибка проверки провайдеров: {str(e)}"
    else:
        result["message"] = "LLM Manager не инициализирован"
    
    return result


@router.get("/monitoring/ollama/check")
async def check_ollama_server(request: Request):
    """Проверить доступность Ollama сервера и получить список моделей"""
    import httpx
    from backend.config import get_config
    
    engine = request.app.state.engine
    
    if not engine:
        return {
            "available": False,
            "message": "Engine не инициализирован",
            "models": [],
            "base_url": None
        }
    
    # Получаем конфигурацию Ollama
    config = get_config()
    ollama_config = None
    if engine.llm_manager and "ollama" in engine.llm_manager.providers:
        ollama_provider = engine.llm_manager.providers["ollama"]
        base_url = ollama_provider.base_url
    elif config.llm and config.llm.providers and "ollama" in config.llm.providers:
        ollama_config = config.llm.providers["ollama"]
        base_url = ollama_config.base_url if ollama_config.base_url else "http://localhost:11434"
    else:
        base_url = "http://localhost:11434"
    
    result = {
        "available": False,
        "message": "",
        "models": [],
        "base_url": base_url,
        "error": None
    }
    
    try:
        # Проверяем доступность Ollama сервера
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                
                result["available"] = True
                result["message"] = f"Ollama сервер доступен. Найдено моделей: {len(models)}"
                result["models"] = models
            else:
                result["message"] = f"Ollama сервер вернул ошибку: {response.status_code}"
                result["error"] = f"HTTP {response.status_code}"
                
    except httpx.TimeoutException:
        result["message"] = f"Таймаут подключения к Ollama серверу ({base_url})"
        result["error"] = "timeout"
    except httpx.ConnectError:
        result["message"] = f"Не удалось подключиться к Ollama серверу ({base_url}). Убедитесь, что Ollama запущен."
        result["error"] = "connection_error"
    except Exception as e:
        logger.error(f"Error checking Ollama server: {e}")
        result["message"] = f"Ошибка при проверке Ollama: {str(e)}"
        result["error"] = str(e)
    
    return result

