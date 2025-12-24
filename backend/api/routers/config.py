"""
Config router
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
from pathlib import Path
import yaml

router = APIRouter()


@router.get("/config")
async def get_config():
    """Получить текущую конфигурацию (полная версия для настроек)"""
    try:
        from backend.config import get_config as load_config, get_system_resources
        
        config = load_config()
        system_resources = get_system_resources()
        
        # Возвращаем полную конфигурацию (без API ключей для безопасности)
        from backend.core.pydantic_utils import pydantic_to_dict
        
        def safe_dict(obj):
            """Безопасное преобразование в dict без API ключей"""
            # Используем универсальную функцию для совместимости с Pydantic v1 и v2
            d = pydantic_to_dict(obj)
            
            # Удаляем API ключи
            if isinstance(d, dict):
                d.pop('api_key', None)
                # Рекурсивно обрабатываем вложенные словари
                for key, value in d.items():
                    if isinstance(value, dict):
                        d[key] = safe_dict(value)
                    elif isinstance(value, list):
                        # Обрабатываем элементы списка
                        processed_list = []
                        for item in value:
                            if item is None:
                                continue  # Пропускаем None
                            elif hasattr(item, 'model_dump') or hasattr(item, 'dict'):
                                # Объект Pydantic - используем safe_dict для обработки
                                processed_list.append(safe_dict(item))
                            elif isinstance(item, dict):
                                # Обычный словарь
                                processed_list.append(safe_dict(item))
                            else:
                                # Примитивный тип
                                processed_list.append(item)
                        d[key] = processed_list
            
            return d
        
        # Получаем полную конфигурацию со всеми дефолтами
        full_config = {
            "llm": {
                "default_provider": config.llm.default_provider,
                "providers": {
                    name: safe_dict(provider)
                    for name, provider in config.llm.providers.items()
                }
            },
            "rag": safe_dict(config.rag) if config.rag else {},
            "context": safe_dict(config.context) if config.context else {},
            "orchestrator": safe_dict(config.orchestrator) if config.orchestrator else {},
            "agents": safe_dict(config.agents) if config.agents else {},
            "memory": safe_dict(config.memory) if config.memory else {},
            "api": safe_dict(config.api) if config.api else {},
            "logging": safe_dict(config.logging) if config.logging else {},
            "performance": safe_dict(config.performance) if config.performance else {},
            "tools": safe_dict(config.tools) if config.tools else {},
            "multimodal": safe_dict(config.multimodal) if hasattr(config, 'multimodal') and config.multimodal else {},
            "automl": safe_dict(config.automl) if hasattr(config, 'automl') and config.automl else {},
            "data": safe_dict(config.data) if hasattr(config, 'data') and config.data else {},
            "workflow": safe_dict(config.workflow) if hasattr(config, 'workflow') and config.workflow else {},
            "frontend": safe_dict(config.frontend) if hasattr(config, 'frontend') and config.frontend else {},
            "system": {
                "resources": system_resources,
                "adaptive_defaults_applied": True,
            },
        }
        
        return full_config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфигурации: {str(e)}")


def deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Рекурсивно мерджит update в base словарь
    
    Args:
        base: Базовый словарь (будет изменен)
        update: Словарь с обновлениями
        
    Returns:
        Мердженный словарь
    """
    result = base.copy() if base else {}
    
    for key, value in update.items():
        if value is None:
            # Пропускаем None значения
            continue
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Рекурсивно мерджим вложенные словари
            result[key] = deep_merge(result[key], value)
        elif isinstance(value, list):
            # Для списков просто заменяем (не мерджим списки, чтобы избежать проблем)
            # Но фильтруем пустые объекты из списка
            filtered_list = [item for item in value if item is not None and item != {}]
            result[key] = filtered_list if filtered_list else value  # Сохраняем оригинал если все удалили
        else:
            # Перезаписываем значение (или добавляем новое)
            result[key] = value
    
    return result


@router.put("/config")
async def update_config(config_update: Dict[str, Any], request: Request):
    """Обновить конфигурацию динамически без перезапуска"""
    try:
        from backend.config import get_config as load_current_config, reload_config, Config
        import os

        # Получаем engine из app state
        engine = request.app.state.engine
        if not engine:
            raise HTTPException(status_code=503, detail="Engine не инициализирован")

        # Путь до пользовательского конфига
        # Используем тот же путь, что и в load_config
        # В load_config: Path(__file__) = backend/config.py, parent.parent = корень проекта
        # Поэтому путь: корень проекта / config / config.yaml
        
        # Но файл может быть в backend/config/config.yaml, проверяем оба варианта
        config_file_path = Path(__file__).resolve()  # backend/api/routers/config.py
        root_dir = config_file_path.parents[2]  # корень проекта
        
        # Сначала пробуем backend/config/config.yaml (реальная структура)
        backend_config_path = root_dir / "backend" / "config" / "config.yaml"
        root_config_path = root_dir / "config" / "config.yaml"
        
        if backend_config_path.exists():
            config_path = backend_config_path
            config_dir = backend_config_path.parent
        elif root_config_path.exists():
            config_path = root_config_path
            config_dir = root_config_path.parent
        else:
            # Используем backend/config/config.yaml как стандартный путь
            config_dir = root_dir / "backend" / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.yaml"

        # Загружаем текущую конфигурацию (для мерджа с существующими настройками)
        existing_config = {}
        if config_path.exists():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    existing_config = yaml.safe_load(f) or {}
            except Exception as e:
                # Если не удалось загрузить существующий файл, начинаем с пустого
                existing_config = {}

        # Удаляем runtime-only поля из config_update перед сохранением
        config_update_clean = {k: v for k, v in config_update.items() if k != 'system'}
        
        # Очищаем пустые объекты и None значения из config_update_clean
        def clean_config(obj: Any) -> Any:
            """Рекурсивно очищает конфигурацию от пустых объектов и None"""
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    cleaned_value = clean_config(value)
                    # Пропускаем None значения и пустые словари (но сохраняем пустые списки если нужно)
                    if cleaned_value is not None and cleaned_value != {}:
                        result[key] = cleaned_value
                return result if result else None
            elif isinstance(obj, list):
                cleaned_list = [clean_config(item) for item in obj if item is not None]
                # Удаляем None и пустые словари из списка
                cleaned_list = [item for item in cleaned_list if item is not None and item != {}]
                return cleaned_list if cleaned_list else None
            else:
                return obj
        
        config_update_clean = clean_config(config_update_clean) or {}
        
        # Мерджим новую конфигурацию с существующей
        # Это сохраняет настройки, которые не были изменены в UI
        existing_config_copy = existing_config.copy() if existing_config else {}
        merged_config = deep_merge(existing_config_copy, config_update_clean)

        # Удаляем API ключи и пустые объекты из файла конфигурации
        # Это безопасно, так как API ключи загружаются из env переменных
        def remove_api_keys_and_clean(obj: Any) -> Any:
            """Рекурсивно удаляет api_key и пустые объекты из конфигурации перед сохранением"""
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    if key == 'api_key':
                        continue  # Пропускаем API ключи
                    cleaned_value = remove_api_keys_and_clean(value)
                    # Пропускаем None, но сохраняем пустые словари в некоторых случаях
                    if cleaned_value is not None:
                        result[key] = cleaned_value
                return result
            elif isinstance(obj, list):
                cleaned_list = [remove_api_keys_and_clean(item) for item in obj]
                # Удаляем None из списка, но сохраняем пустые словари если они важны
                cleaned_list = [item for item in cleaned_list if item is not None]
                return cleaned_list
            else:
                return obj

        config_to_save = remove_api_keys_and_clean(merged_config)

        # Бэкап предыдущего файла, если есть
        if config_path.exists():
            backup_path = config_dir / "config.yaml.bak"
            backup_path.write_bytes(config_path.read_bytes())

        # Сохраняем обновлённую конфигурацию
        try:
            with config_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(config_to_save, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        except Exception as e:
            from loguru import logger
            logger.error(f"Ошибка записи конфигурации в {config_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка записи конфигурации: {str(e)}")

        # Загружаем новую конфигурацию (обновляет глобальный кэш)
        # Передаем None, чтобы load_config сам нашел правильный путь
        new_config = reload_config(None)

        # Применяем изменения к engine динамически
        update_result = await engine.update_configuration(new_config)

        return {
            "success": True,
            "message": "Конфигурация сохранена и применена динамически",
            "config_path": str(config_path),
            "applied_changes": update_result.get("applied_changes", []),
            "warnings": update_result.get("warnings", []),
        }
    except Exception as e:
        from fastapi import HTTPException
        import traceback
        raise HTTPException(status_code=500, detail=f"Ошибка обновления конфигурации: {str(e)}")

