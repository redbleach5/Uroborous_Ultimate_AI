"""
Configuration management for AILLM
"""

import os
import multiprocessing
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from .core.logger import get_logger

logger = get_logger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider"""
    enabled: bool = True
    api_key: Optional[str] = None
    default_model: str = "gpt-4"
    base_url: Optional[str] = None
    timeout: int = 60
    max_retries: int = 3
    cache_enabled: bool = True
    auto_detect_models: bool = False
    recommended_models: Optional[Dict[str, list]] = None


class LLMConfig(BaseModel):
    """LLM providers configuration"""
    default_provider: str = "openai"
    providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)


class RAGConfig(BaseModel):
    """RAG system configuration"""
    enabled: bool = True
    vector_store: Dict[str, Any] = Field(default_factory=dict)
    embeddings: Dict[str, Any] = Field(default_factory=dict)
    search: Dict[str, Any] = Field(default_factory=dict)


class ContextConfig(BaseModel):
    """Context manager configuration"""
    max_tokens: int = 8000
    hierarchical: bool = True
    query_expansion: bool = True
    multi_query: bool = True


class AgentConfig(BaseModel):
    """Configuration for a single agent"""
    enabled: bool = True
    default_model: Optional[str] = None
    temperature: float = 0.7
    max_iterations: int = 10
    use_thinking_mode: bool = False  # Enable thinking/reasoning mode for models that support it


class AgentsConfig(BaseModel):
    """Agents configuration"""
    code_writer: AgentConfig = Field(default_factory=AgentConfig)
    react: AgentConfig = Field(default_factory=lambda: AgentConfig(max_iterations=20, use_thinking_mode=True))
    research: AgentConfig = Field(default_factory=lambda: AgentConfig(temperature=0.3, use_thinking_mode=True))
    data_analysis: AgentConfig = Field(default_factory=lambda: AgentConfig(temperature=0.2, use_thinking_mode=True))
    workflow: AgentConfig = Field(default_factory=lambda: AgentConfig(temperature=0.3))
    integration: AgentConfig = Field(default_factory=lambda: AgentConfig(temperature=0.4))
    monitoring: AgentConfig = Field(default_factory=lambda: AgentConfig(temperature=0.2))


class OrchestratorConfig(BaseModel):
    """Orchestrator configuration"""
    enabled: bool = True
    max_parallel_tasks: int = 5
    task_timeout: int = 3600
    auto_recovery: bool = True
    planning: Dict[str, Any] = Field(default_factory=dict)


class ToolsConfig(BaseModel):
    """Tools configuration"""
    enabled: bool = True
    categories: Dict[str, bool] = Field(default_factory=dict)
    safety: Dict[str, Any] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """Long term memory configuration"""
    enabled: bool = True
    storage_path: str = "memory/memories.db"
    max_memories: int = 10000
    similarity_threshold: float = 0.7
    auto_cleanup: bool = True
    cleanup_interval_days: int = 30


class APIConfig(BaseModel):
    """API server configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1
    cors: Dict[str, Any] = Field(default_factory=dict)
    websocket: Dict[str, Any] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    format: str = "text"  # text, json
    file: Optional[str] = "logs/app.log"
    max_size_mb: int = 100
    backup_count: int = 5


class PerformanceConfig(BaseModel):
    """Performance configuration"""
    cache: Dict[str, bool] = Field(default_factory=dict)
    parallel: Dict[str, Any] = Field(default_factory=dict)
    gpu: Dict[str, Any] = Field(default_factory=dict)


class FrontendConfig(BaseModel):
    """Frontend configuration"""
    enabled: bool = True
    tauri: Dict[str, Any] = Field(default_factory=dict)


class AutoMLConfig(BaseModel):
    """AutoML configuration"""
    enabled: bool = True
    frameworks: list = Field(default_factory=lambda: ["sklearn", "xgboost", "lightgbm"])
    optimization: Dict[str, Any] = Field(default_factory=dict)
    explainability: Dict[str, Any] = Field(default_factory=dict)


class MultimodalConfig(BaseModel):
    """Multimodal processing configuration"""
    enabled: bool = True
    image: Dict[str, Any] = Field(default_factory=dict)
    audio: Dict[str, Any] = Field(default_factory=dict)
    video: Dict[str, Any] = Field(default_factory=dict)


class DataConfig(BaseModel):
    """Data processing configuration"""
    processing: Dict[str, Any] = Field(default_factory=dict)
    etl: Dict[str, Any] = Field(default_factory=dict)
    analytics: Dict[str, Any] = Field(default_factory=dict)


class WorkflowConfig(BaseModel):
    """Workflow configuration"""
    enabled: bool = True
    visual_editor: bool = True
    storage_path: str = "workflows/"
    templates_path: str = "workflows/templates/"


class Config(BaseSettings):
    """Main configuration class"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    automl: AutoMLConfig = Field(default_factory=AutoMLConfig)
    multimodal: MultimodalConfig = Field(default_factory=MultimodalConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields instead of raising errors


def get_system_resources() -> Dict[str, Any]:
    """Получить информацию о системных ресурсах для адаптивной настройки"""
    resources = {
        "cpu_cores": multiprocessing.cpu_count(),
        "memory_gb": 8,  # Default fallback
        "gpu_available": False,
        "gpu_count": 0,
    }
    
    # Получаем информацию о памяти
    if PSUTIL_AVAILABLE:
        try:
            memory = psutil.virtual_memory()
            resources["memory_gb"] = memory.total / (1024 ** 3)
        except Exception as e:
            logger.debug(f"Failed to get memory info: {e}")
            resources["memory_gb"] = None
    
    # Проверяем наличие GPU
    if TORCH_AVAILABLE:
        try:
            resources["gpu_available"] = torch.cuda.is_available()
            if resources["gpu_available"]:
                resources["gpu_count"] = torch.cuda.device_count()
        except Exception as e:
            logger.debug(f"Failed to get GPU info: {e}")
            resources["gpu_available"] = False
            resources["gpu_count"] = 0
    
    return resources


def get_adaptive_defaults() -> Dict[str, Any]:
    """Генерирует адаптивные дефолтные значения на основе системных ресурсов"""
    resources = get_system_resources()
    cpu_cores = resources["cpu_cores"]
    memory_gb = resources["memory_gb"]
    gpu_available = resources["gpu_available"]
    
    # Адаптивные значения на основе ресурсов
    defaults = {
        "llm": {
            "default_provider": "ollama",  # По умолчанию локальный
            "providers": {
                "openai": {
                    "enabled": True,
                    "default_model": "gpt-4-turbo-preview",
                    "base_url": "https://api.openai.com/v1",
                    "timeout": 60,
                    "max_retries": 3,
                    "cache_enabled": True,
                },
                "anthropic": {
                    "enabled": True,
                    "default_model": "claude-3-opus-20240229",
                    "timeout": 60,
                    "max_retries": 3,
                    "cache_enabled": True,
                },
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "default_model": "llama2",
                    "timeout": 300,
                    "max_retries": 2,
                    "cache_enabled": True,
                    "auto_detect_models": True,
                    "recommended_models": {
                        "code": ["codellama", "deepseek-coder", "mistral"],
                        "chat": ["llama2", "mistral", "neural-chat"],
                        "analysis": ["llama2", "mistral"],
                    },
                },
            },
        },
        "rag": {
            "enabled": True,
            "vector_store": {
                "type": "faiss",
                "dimension": 384,
                "index_path": "vector_store/index.faiss",
                "metadata_path": "vector_store/metadata.pkl",
            },
            "embeddings": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "device": "cuda" if gpu_available else "cpu",
                "batch_size": min(64, max(16, int(memory_gb / 2))),  # Адаптивный batch size
                "cache_dir": "embeddings_cache",
            },
            "search": {
                "top_k": 10,
                "use_bm25": True,
                "use_reranking": True,
                "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                "query_expansion": True,
                "multi_query": True,
            },
        },
        "context": {
            "max_tokens": min(16000, max(4000, int(memory_gb * 500))),  # Адаптивный размер контекста
            "hierarchical": True,
            "query_expansion": True,
            "multi_query": True,
        },
        "agents": {
            "code_writer": {
                "enabled": True,
                "default_model": None,  # None = auto-select from Ollama recommended models
                "temperature": 0.7,
                "max_iterations": 10,
                "use_thinking_mode": False,  # Can enable for complex code generation
            },
            "react": {
                "enabled": True,
                "default_model": None,  # None = auto-select from Ollama recommended models
                "temperature": 0.5,
                "max_iterations": 20,
                "max_tool_calls": 10,
                "use_thinking_mode": True,  # Enable thinking for complex reasoning
            },
            "research": {
                "enabled": True,
                "default_model": None,  # None = auto-select from Ollama recommended models
                "temperature": 0.3,
                "max_iterations": 15,
                "use_thinking_mode": True,  # Enable thinking for research tasks
            },
            "data_analysis": {
                "enabled": True,
                "default_model": None,  # None = auto-select from Ollama recommended models
                "temperature": 0.2,
                "max_iterations": 25,
                "use_thinking_mode": True,  # Enable thinking for data analysis
            },
            "workflow": {
                "enabled": True,
                "default_model": None,
                "temperature": 0.3,
            },
            "integration": {
                "enabled": True,
                "default_model": None,
                "temperature": 0.4,
            },
            "monitoring": {
                "enabled": True,
                "default_model": None,
                "temperature": 0.2,
            },
        },
        "orchestrator": {
            "enabled": True,
            "max_parallel_tasks": min(10, max(2, cpu_cores - 1)),  # Адаптивное количество параллельных задач
            "task_timeout": 3600,
            "auto_recovery": True,
            "planning": {
                "strategy": "llm",
                "use_memory": True,
                "max_depth": 5,
            },
        },
        "tools": {
            "enabled": True,
            "categories": {
                "file": True,
                "shell": True,
                "git": True,
                "web": True,
                "database": True,
                "api": True,
            },
            "safety": {
                "enabled": True,
                "sandbox": False,
                "allowed_commands": [],
                "blocked_patterns": [
                    "rm -rf /",
                    "format c:",
                    "del /f /s /q",
                ],
            },
        },
        "memory": {
            "enabled": True,
            "storage_path": "memory/memories.db",
            "max_memories": min(50000, max(5000, int(memory_gb * 1000))),  # Адаптивный размер памяти
            "similarity_threshold": 0.7,
            "auto_cleanup": True,
            "cleanup_interval_days": 30,
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False,
            "workers": min(4, max(1, cpu_cores // 2)),  # Адаптивное количество воркеров
            "cors": {
                "enabled": True,
                "origins": ["*"],
            },
            "websocket": {
                "enabled": True,
                "ping_interval": 20,
                "ping_timeout": 10,
            },
        },
        "logging": {
            "level": "INFO",
            "format": "json",
            "file": "logs/aillm.log",
            "max_size_mb": 100,
            "backup_count": 5,
        },
        "performance": {
            "cache": {
                "llm_responses": True,
                "embeddings": True,
                "search_results": True,
            },
            "parallel": {
                "enabled": True,
                "max_workers": min(8, max(2, cpu_cores)),  # Адаптивное количество воркеров
            },
            "gpu": {
                "enabled": gpu_available,
                "device": "cuda:0" if gpu_available else "cpu",
            },
        },
        "multimodal": {
            "enabled": True,
            "image": {
                "enabled": True,
                "ocr": True,
                "ocr_engine": "tesseract",
                "max_size_mb": 10,
            },
            "audio": {
                "enabled": True,
                "transcription": True,
                "model": "whisper-base",
            },
            "video": {
                "enabled": True,
                "max_duration_seconds": 300,
                "extract_frames": True,
            },
        },
        "automl": {
            "enabled": True,
            "frameworks": ["sklearn", "xgboost", "lightgbm"],
            "optimization": {
                "enabled": True,
                "framework": "optuna",
                "n_trials": 100,
                "timeout": 3600,
            },
            "explainability": {
                "enabled": True,
                "methods": ["shap", "lime"],
            },
        },
        "data": {
            "processing": {
                "enabled": True,
                "frameworks": ["pandas", "dask"],
            },
            "etl": {
                "enabled": True,
                "streaming": True,
            },
            "analytics": {
                "enabled": True,
                "auto_eda": True,
                "visualization": True,
            },
        },
        "workflow": {
            "enabled": True,
            "visual_editor": True,
            "storage_path": "workflows/",
            "templates_path": "workflows/templates/",
        },
        "frontend": {
            "enabled": True,
            "tauri": {
                "enabled": True,
                "window_title": "AILLM",
                "window_size": [1200, 800],
                "min_size": [800, 600],
            },
        },
    }
    
    return defaults


def merge_config_with_defaults(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Объединяет конфигурацию из файла с адаптивными дефолтами"""
    defaults = get_adaptive_defaults()
    
    def deep_merge(base: Dict, override: Dict) -> Dict:
        """Рекурсивно объединяет словари"""
        result = base.copy() if base else {}
        for key, value in override.items():
            if value is None:
                # Пропускаем None значения
                continue
            elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            elif isinstance(value, list):
                # Для списков просто заменяем (не мерджим списки)
                result[key] = value
            else:
                result[key] = value
        return result
    
    # Объединяем дефолты с конфигурацией из файла
    merged = deep_merge(defaults, config_dict or {})
    return merged


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file
    
    Args:
        config_path: Path to config file. If None, uses default location.
        
    Returns:
        Config object
    """
    if config_path is None:
        # Try to find config file
        base_dir = Path(__file__).parent.parent  # корень проекта
        # Проверяем оба возможных пути
        backend_config_path = base_dir / "backend" / "config" / "config.yaml"
        root_config_path = base_dir / "config" / "config.yaml"
        
        if backend_config_path.exists():
            config_path = backend_config_path
        elif root_config_path.exists():
            config_path = root_config_path
        else:
            # Используем backend/config/config.yaml как стандартный путь
            config_path = backend_config_path
        
        # Если файл не существует, пробуем example config
        if not Path(config_path).exists():
            example_path = base_dir / "config" / "config.example.yaml"
            if example_path.exists():
                config_path = example_path
    
    config_dict = {}
    
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}
    
    # Объединяем с адаптивными дефолтами
    config_dict = merge_config_with_defaults(config_dict)
    
    # Load environment variables for API keys
    if "llm" in config_dict and "providers" in config_dict["llm"]:
        for provider_name, provider_config in config_dict["llm"]["providers"].items():
            env_key = f"{provider_name.upper()}_API_KEY"
            api_key = os.getenv(env_key)
            if api_key:
                provider_config["api_key"] = api_key
    
    # Create config object
    config = Config(**config_dict)
    
    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """Reload configuration"""
    global _config
    _config = load_config(config_path)
    return _config

