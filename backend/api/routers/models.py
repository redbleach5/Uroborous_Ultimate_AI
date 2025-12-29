"""
Models router - API для управления моделями LLM
Выбор, автоопределение, рейтинг моделей
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from backend.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ModelInfo(BaseModel):
    """Информация о модели"""
    name: str
    provider: str  # ollama, openai, anthropic
    size: Optional[str] = None  # 1b, 7b, 13b, 70b и т.д.
    capabilities: List[str] = []  # chat, code, vision, reasoning
    quality_score: float = 0.7  # 0.0 - 1.0
    speed_score: float = 0.5  # токенов/сек относительно
    is_available: bool = True
    is_recommended: bool = False
    description: Optional[str] = None


class ModelsResponse(BaseModel):
    """Ответ со списком моделей"""
    success: bool
    models: List[ModelInfo]
    current_model: Optional[str] = None
    auto_select_enabled: bool = True
    resource_level: str = "low"


class ModelSelectRequest(BaseModel):
    """Запрос на выбор модели"""
    model: Optional[str] = None  # None = автовыбор
    provider: Optional[str] = "ollama"
    auto_select: bool = True  # Включить автовыбор


class ModelSelectResponse(BaseModel):
    """Ответ на выбор модели"""
    success: bool
    selected_model: str
    provider: str
    auto_selected: bool
    reason: str


# Информация о популярных моделях
MODEL_INFO_DB: Dict[str, Dict[str, Any]] = {
    # Маленькие модели (1-3B) - быстрые
    "gemma3:1b": {
        "size": "1b",
        "capabilities": ["chat", "code"],
        "quality_score": 0.55,
        "speed_score": 0.95,
        "description": "Быстрая модель для простых задач"
    },
    "gemma2:2b": {
        "size": "2b",
        "capabilities": ["chat", "code"],
        "quality_score": 0.6,
        "speed_score": 0.9,
        "description": "Баланс скорости и качества"
    },
    "phi3:mini": {
        "size": "3.8b",
        "capabilities": ["chat", "code", "reasoning"],
        "quality_score": 0.65,
        "speed_score": 0.85,
        "description": "Компактная модель Microsoft"
    },
    "tinyllama": {
        "size": "1.1b",
        "capabilities": ["chat"],
        "quality_score": 0.5,
        "speed_score": 0.98,
        "description": "Сверхбыстрая для простых задач"
    },
    
    # Средние модели (7-8B) - баланс
    "llama3:8b": {
        "size": "8b",
        "capabilities": ["chat", "code", "reasoning"],
        "quality_score": 0.8,
        "speed_score": 0.7,
        "description": "Отличная модель для большинства задач"
    },
    "llama3.1:8b": {
        "size": "8b",
        "capabilities": ["chat", "code", "reasoning"],
        "quality_score": 0.82,
        "speed_score": 0.7,
        "description": "Улучшенная версия Llama 3"
    },
    "mistral:7b": {
        "size": "7b",
        "capabilities": ["chat", "code", "reasoning"],
        "quality_score": 0.78,
        "speed_score": 0.75,
        "description": "Быстрая и качественная"
    },
    "gemma2:9b": {
        "size": "9b",
        "capabilities": ["chat", "code"],
        "quality_score": 0.75,
        "speed_score": 0.7,
        "description": "Google Gemma 2"
    },
    "codellama:7b": {
        "size": "7b",
        "capabilities": ["code"],
        "quality_score": 0.8,
        "speed_score": 0.75,
        "description": "Специализирована на коде"
    },
    "deepseek-coder:6.7b": {
        "size": "6.7b",
        "capabilities": ["code"],
        "quality_score": 0.82,
        "speed_score": 0.75,
        "description": "Отличная для программирования"
    },
    "qwen2.5-coder:7b": {
        "size": "7b",
        "capabilities": ["code", "chat"],
        "quality_score": 0.85,
        "speed_score": 0.72,
        "description": "Топ модель для кода от Alibaba"
    },
    
    # Большие модели (13-14B)
    "llama3:13b": {
        "size": "13b",
        "capabilities": ["chat", "code", "reasoning"],
        "quality_score": 0.88,
        "speed_score": 0.5,
        "description": "Мощная универсальная модель"
    },
    "codellama:13b": {
        "size": "13b",
        "capabilities": ["code"],
        "quality_score": 0.88,
        "speed_score": 0.5,
        "description": "Продвинутая модель для кода"
    },
    
    # Очень большие модели (30B+)
    "llama3:70b": {
        "size": "70b",
        "capabilities": ["chat", "code", "reasoning", "analysis"],
        "quality_score": 0.95,
        "speed_score": 0.2,
        "description": "Максимальное качество"
    },
    "qwen2.5:72b": {
        "size": "72b",
        "capabilities": ["chat", "code", "reasoning", "analysis"],
        "quality_score": 0.96,
        "speed_score": 0.18,
        "description": "Топовая модель Alibaba"
    },
    "deepseek-coder:33b": {
        "size": "33b",
        "capabilities": ["code"],
        "quality_score": 0.92,
        "speed_score": 0.3,
        "description": "Премиум модель для кода"
    },
    
    # Vision модели
    "llava:7b": {
        "size": "7b",
        "capabilities": ["chat", "vision"],
        "quality_score": 0.75,
        "speed_score": 0.6,
        "description": "Модель с поддержкой изображений"
    },
    "llava:13b": {
        "size": "13b",
        "capabilities": ["chat", "vision"],
        "quality_score": 0.82,
        "speed_score": 0.4,
        "description": "Улучшенная vision модель"
    },
}


def _extract_model_size(model_name: str) -> Optional[str]:
    """Извлекает размер модели из названия"""
    import re
    
    # Паттерны для размера: 1b, 7b, 13b, 70b, 1.5b и т.д.
    patterns = [
        r'(\d+\.?\d*)[bB]',  # 7b, 70b, 1.5b
        r':(\d+)[bB]',  # :7b
    ]
    
    for pattern in patterns:
        match = re.search(pattern, model_name)
        if match:
            return f"{match.group(1)}b"
    
    return None


def _get_model_info(model_name: str, provider: str = "ollama") -> ModelInfo:
    """Получает информацию о модели"""
    # Нормализуем имя (убираем :latest и т.п.)
    model_name.split(":")[0] if ":" in model_name else model_name
    full_name = model_name.lower()
    
    # Ищем в базе данных
    info = None
    for key, data in MODEL_INFO_DB.items():
        if key.lower() in full_name or full_name in key.lower():
            info = data
            break
    
    if info:
        return ModelInfo(
            name=model_name,
            provider=provider,
            size=info.get("size"),
            capabilities=info.get("capabilities", ["chat"]),
            quality_score=info.get("quality_score", 0.7),
            speed_score=info.get("speed_score", 0.5),
            is_available=True,
            description=info.get("description")
        )
    
    # Если модель не в базе, пытаемся определить характеристики
    size = _extract_model_size(model_name)
    
    # Оцениваем качество по размеру
    quality_score = 0.7
    speed_score = 0.5
    capabilities = ["chat"]
    
    if size:
        size_num = float(size.replace("b", ""))
        if size_num <= 3:
            quality_score = 0.55
            speed_score = 0.9
        elif size_num <= 8:
            quality_score = 0.75
            speed_score = 0.7
        elif size_num <= 15:
            quality_score = 0.85
            speed_score = 0.5
        elif size_num <= 35:
            quality_score = 0.9
            speed_score = 0.3
        else:
            quality_score = 0.95
            speed_score = 0.2
    
    # Определяем capabilities по названию
    name_lower = model_name.lower()
    if "code" in name_lower or "coder" in name_lower:
        capabilities = ["code", "chat"]
    if "vision" in name_lower or "llava" in name_lower:
        capabilities.append("vision")
    
    return ModelInfo(
        name=model_name,
        provider=provider,
        size=size,
        capabilities=capabilities,
        quality_score=quality_score,
        speed_score=speed_score,
        is_available=True,
        description=f"Модель {model_name}"
    )


@router.get("/models", response_model=ModelsResponse)
async def get_available_models(request: Request):
    """Получить список доступных моделей"""
    try:
        engine = request.app.state.engine
        if not engine or not engine.llm_manager:
            return ModelsResponse(
                success=False,
                models=[],
                current_model=None,
                auto_select_enabled=True,
                resource_level="unknown"
            )
        
        models_list: List[ModelInfo] = []
        current_model = None
        resource_level = "low"
        
        # Получаем Ollama модели
        ollama_provider = engine.llm_manager.providers.get("ollama")
        if ollama_provider:
            try:
                available = await ollama_provider.list_models()
                current_model = ollama_provider.default_model
                
                for model_name in available:
                    info = _get_model_info(model_name, "ollama")
                    models_list.append(info)
                
                # Определяем resource_level
                if any(m.size and float(m.size.replace("b", "")) >= 30 for m in models_list if m.size):
                    resource_level = "high"
                elif any(m.size and float(m.size.replace("b", "")) >= 13 for m in models_list if m.size):
                    resource_level = "medium"
                elif any(m.size and float(m.size.replace("b", "")) >= 7 for m in models_list if m.size):
                    resource_level = "low"
                else:
                    resource_level = "minimal"
                    
            except Exception as e:
                logger.warning(f"Failed to get Ollama models: {e}")
        
        # TODO: Добавить модели OpenAI/Anthropic если доступны
        openai_provider = engine.llm_manager.providers.get("openai")
        if openai_provider:
            # Добавляем известные модели OpenAI
            openai_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
            for model_name in openai_models:
                models_list.append(ModelInfo(
                    name=model_name,
                    provider="openai",
                    capabilities=["chat", "code", "reasoning"],
                    quality_score=0.95 if "gpt-4" in model_name else 0.8,
                    speed_score=0.6,
                    is_available=True,
                    description=f"OpenAI {model_name}"
                ))
        
        anthropic_provider = engine.llm_manager.providers.get("anthropic")
        if anthropic_provider:
            anthropic_models = ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
            for model_name in anthropic_models:
                models_list.append(ModelInfo(
                    name=model_name,
                    provider="anthropic",
                    capabilities=["chat", "code", "reasoning", "analysis"],
                    quality_score=0.97 if "sonnet" in model_name else 0.85,
                    speed_score=0.5 if "sonnet" in model_name else 0.8,
                    is_available=True,
                    description=f"Anthropic {model_name}"
                ))
        
        # Сортируем по качеству (по убыванию)
        models_list.sort(key=lambda m: m.quality_score, reverse=True)
        
        # Помечаем рекомендуемые модели
        # Рекомендуем лучшие для каждого размера
        recommended_sizes = set()
        for model in models_list:
            if model.size and model.size not in recommended_sizes:
                model.is_recommended = True
                recommended_sizes.add(model.size)
                if len(recommended_sizes) >= 3:
                    break
        
        return ModelsResponse(
            success=True,
            models=models_list,
            current_model=current_model,
            auto_select_enabled=True,
            resource_level=resource_level
        )
        
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        return ModelsResponse(
            success=False,
            models=[],
            current_model=None,
            auto_select_enabled=True,
            resource_level="unknown"
        )


@router.post("/models/select", response_model=ModelSelectResponse)
async def select_model(req: ModelSelectRequest, request: Request):
    """Выбрать модель для использования"""
    try:
        engine = request.app.state.engine
        if not engine or not engine.llm_manager:
            raise HTTPException(status_code=503, detail="Engine не инициализирован")
        
        ollama_provider = engine.llm_manager.providers.get("ollama")
        if not ollama_provider:
            raise HTTPException(status_code=503, detail="Ollama provider не доступен")
        
        if req.auto_select or not req.model:
            # Автоматический выбор - используем ResourceAwareSelector
            # Пока просто возвращаем текущую модель
            return ModelSelectResponse(
                success=True,
                selected_model=ollama_provider.default_model,
                provider="ollama",
                auto_selected=True,
                reason="Автоматический выбор на основе доступных ресурсов"
            )
        
        # Ручной выбор
        available = await ollama_provider.list_models()
        
        if req.model not in available:
            raise HTTPException(
                status_code=400, 
                detail=f"Модель '{req.model}' не доступна. Доступные: {', '.join(available[:10])}"
            )
        
        # Устанавливаем выбранную модель как default
        ollama_provider.default_model = req.model
        
        logger.info(f"Model manually selected: {req.model}")
        
        return ModelSelectResponse(
            success=True,
            selected_model=req.model,
            provider=req.provider or "ollama",
            auto_selected=False,
            reason=f"Модель '{req.model}' выбрана вручную"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error selecting model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/recommend")
async def recommend_model(
    request: Request,
    task_type: Optional[str] = None,  # code, chat, research, analysis
    complexity: Optional[str] = None,  # low, medium, high
    speed_priority: bool = False
):
    """Рекомендовать модель для задачи"""
    try:
        engine = request.app.state.engine
        if not engine or not engine.llm_manager:
            raise HTTPException(status_code=503, detail="Engine не инициализирован")
        
        # Получаем доступные модели
        ollama_provider = engine.llm_manager.providers.get("ollama")
        if not ollama_provider:
            raise HTTPException(status_code=503, detail="Нет доступных провайдеров")
        
        available = await ollama_provider.list_models()
        if not available:
            raise HTTPException(status_code=503, detail="Нет доступных моделей")
        
        # Получаем информацию о моделях
        models_info = [_get_model_info(m, "ollama") for m in available]
        
        # Фильтруем по capabilities
        if task_type == "code":
            # Предпочитаем модели с capability "code"
            models_info.sort(key=lambda m: ("code" in m.capabilities, m.quality_score), reverse=True)
        elif task_type == "vision":
            models_info = [m for m in models_info if "vision" in m.capabilities]
        
        # Балансируем качество и скорость
        if speed_priority:
            # Предпочитаем быстрые модели
            models_info.sort(key=lambda m: m.speed_score, reverse=True)
        elif complexity == "high":
            # Для сложных задач - качество важнее
            models_info.sort(key=lambda m: m.quality_score, reverse=True)
        elif complexity == "low":
            # Для простых - баланс (качество * скорость)
            models_info.sort(key=lambda m: m.quality_score * m.speed_score, reverse=True)
        
        if not models_info:
            # Fallback
            return {
                "success": True,
                "recommended": available[0],
                "alternatives": available[1:3] if len(available) > 1 else [],
                "reason": "Fallback: первая доступная модель"
            }
        
        recommended = models_info[0]
        alternatives = [m.name for m in models_info[1:4]]
        
        return {
            "success": True,
            "recommended": recommended.name,
            "recommended_info": recommended.dict(),
            "alternatives": alternatives,
            "reason": f"Лучшая модель для {task_type or 'общих задач'} "
                     f"(качество: {recommended.quality_score:.0%}, скорость: {recommended.speed_score:.0%})"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recommending model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

