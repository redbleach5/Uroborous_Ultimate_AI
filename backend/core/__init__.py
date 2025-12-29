"""
Core module exports
"""
from .logger import get_logger, configure_logging, structured_logger
from .learning_system import LearningSystem, get_learning_system, initialize_learning_system

# Общие типы (единственный источник истины)
from .types import (
    ComplexityLevel,
    ModelTier,
    ComplexityResult,
    ModelSelection,
)

from .task_complexity_service import (
    TaskComplexityService,
    get_complexity_service,
)
from .unified_model_router import (
    UnifiedModelRouter,
    get_unified_router,
    initialize_unified_router,
    UnifiedModelSelection,
    IModelRouter,
)

# NOTE: code_validator и multi_agent_synthesis НЕ экспортируются здесь,
# т.к. они зависят от llm.providers, что создаёт циклический импорт.
# Импортируйте их напрямую:
#   from backend.core.code_validator import CodeValidator, get_code_validator
#   from backend.core.multi_agent_synthesis import MultiAgentSynthesizer, get_multi_agent_synthesizer

__all__ = [
    # Logger
    'get_logger', 
    'configure_logging', 
    'structured_logger',
    # Learning
    'LearningSystem',
    'get_learning_system',
    'initialize_learning_system',
    # Common types
    'ComplexityLevel',
    'ModelTier',
    'ComplexityResult',
    'ModelSelection',
    # Complexity Service
    'TaskComplexityService',
    'get_complexity_service',
    # Model Router
    'UnifiedModelRouter',
    'get_unified_router',
    'initialize_unified_router',
    'UnifiedModelSelection',
    'IModelRouter',
]
