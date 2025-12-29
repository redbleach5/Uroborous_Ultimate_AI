"""
Code Intelligence API - эндпоинты для анализа кода и семантического поиска.

Предоставляет:
- Анализ структуры проекта (AST-based)
- Семантический поиск по коду
- Инкрементальное индексирование
- Валидация кода
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time

from ...core.logger import get_logger
from ...project.code_intelligence import get_code_intelligence, EntityType
from ...project.incremental_indexer import get_incremental_indexer
from ...core.code_validator import get_code_validator

logger = get_logger(__name__)

router = APIRouter(prefix="/code-intelligence", tags=["Code Intelligence"])


# ============== Request/Response Models ==============

class AnalyzeProjectRequest(BaseModel):
    """Запрос на анализ проекта."""
    project_path: str = Field(..., description="Путь к проекту")
    max_files: int = Field(500, description="Максимальное количество файлов")


class AnalyzeFileRequest(BaseModel):
    """Запрос на анализ файла."""
    file_path: str = Field(..., description="Путь к файлу")
    content: Optional[str] = Field(None, description="Содержимое файла (опционально)")


class SearchCodeRequest(BaseModel):
    """Запрос на поиск по коду."""
    query: str = Field(..., description="Поисковый запрос")
    project_path: str = Field(..., description="Путь к проекту")
    top_k: int = Field(10, description="Количество результатов")
    entity_types: Optional[List[str]] = Field(None, description="Фильтр по типам сущностей")
    min_score: float = Field(0.3, description="Минимальный score")


class IndexProjectRequest(BaseModel):
    """Запрос на индексирование проекта."""
    project_path: str = Field(..., description="Путь к проекту")
    force_full: bool = Field(False, description="Принудительная полная переиндексация")
    max_files: int = Field(1000, description="Максимальное количество файлов")


class ValidateCodeRequest(BaseModel):
    """Запрос на валидацию кода."""
    code: str = Field(..., description="Код для валидации")
    language: Optional[str] = Field(None, description="Язык (auto-detect если не указан)")
    fix_errors: bool = Field(True, description="Попытаться исправить ошибки")
    task_context: Optional[str] = Field(None, description="Контекст задачи для LLM")


class FindEntityRequest(BaseModel):
    """Запрос на поиск сущности."""
    project_path: str = Field(..., description="Путь к проекту")
    entity_name: str = Field(..., description="Имя сущности")
    entity_type: Optional[str] = Field(None, description="Тип сущности")


# ============== Endpoints ==============

@router.post("/analyze/project")
async def analyze_project(request: AnalyzeProjectRequest) -> Dict[str, Any]:
    """
    Анализирует структуру проекта.
    
    Возвращает:
    - Список файлов и сущностей (функции, классы, методы)
    - Граф зависимостей
    - Статистику сложности
    - Наиболее используемые функции
    """
    start_time = time.time()
    
    try:
        code_intelligence = get_code_intelligence()
        result = await code_intelligence.analyze_project(
            project_path=request.project_path,
            max_files=request.max_files
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        result["elapsed_seconds"] = round(time.time() - start_time, 2)
        return result
        
    except Exception as e:
        logger.error(f"Project analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/file")
async def analyze_file(request: AnalyzeFileRequest) -> Dict[str, Any]:
    """
    Анализирует отдельный файл.
    
    Возвращает:
    - Список сущностей в файле
    - Импорты и зависимости
    - Сложность кода
    """
    try:
        code_intelligence = get_code_intelligence()
        result = await code_intelligence.analyze_file(
            file_path=request.file_path,
            content=request.content
        )
        
        if result is None:
            return {"error": "Unsupported file type or file not found", "success": False}
        
        return {
            "success": True,
            "file_path": request.file_path,
            "module_info": result.to_dict()
        }
        
    except Exception as e:
        logger.error(f"File analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index")
async def index_project(
    request: IndexProjectRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Индексирует проект для семантического поиска.
    
    Использует инкрементальное индексирование —
    обновляет только изменённые файлы.
    """
    try:
        indexer = get_incremental_indexer()
        
        # Для больших проектов запускаем в фоне
        if request.max_files > 200 and not request.force_full:
            background_tasks.add_task(
                indexer.update_index,
                request.project_path,
                request.force_full,
                request.max_files
            )
            return {
                "status": "started",
                "message": "Indexing started in background",
                "project_path": request.project_path
            }
        
        # Для небольших проектов индексируем сразу
        stats = await indexer.update_index(
            project_path=request.project_path,
            force_full=request.force_full,
            max_files=request.max_files
        )
        
        return {
            "status": "completed",
            "stats": stats.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/status/{project_path:path}")
async def get_index_status(project_path: str) -> Dict[str, Any]:
    """Получает статус индекса проекта."""
    try:
        indexer = get_incremental_indexer()
        return indexer.get_project_status(project_path)
    except Exception as e:
        logger.error(f"Failed to get index status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/projects")
async def list_indexed_projects() -> Dict[str, Any]:
    """Возвращает список проиндексированных проектов."""
    try:
        indexer = get_incremental_indexer()
        projects = indexer.list_indexed_projects()
        return {"projects": projects}
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_code(request: ValidateCodeRequest) -> Dict[str, Any]:
    """
    Валидирует код.
    
    Использует:
    - AST для синтаксической проверки
    - ruff для расширенного анализа Python
    - LLM для автоматического исправления
    """
    try:
        validator = get_code_validator()
        result = await validator.validate(
            code=request.code,
            language=request.language,
            fix_errors=request.fix_errors,
            task_context=request.task_context
        )
        
        return {
            "success": True,
            "validation": result.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/find-entity")
async def find_entity(request: FindEntityRequest) -> Dict[str, Any]:
    """
    Находит сущность по имени.
    
    Поддерживает частичное совпадение имён.
    """
    try:
        code_intelligence = get_code_intelligence()
        
        entity_type = None
        if request.entity_type:
            try:
                entity_type = EntityType(request.entity_type)
            except ValueError:
                pass
        
        entities = await code_intelligence.find_entity(
            project_path=request.project_path,
            entity_name=request.entity_name,
            entity_type=entity_type
        )
        
        return {
            "success": True,
            "count": len(entities),
            "entities": [e.to_dict() for e in entities]
        }
        
    except Exception as e:
        logger.error(f"Entity search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity-types")
async def get_entity_types() -> Dict[str, Any]:
    """Возвращает доступные типы сущностей."""
    return {
        "entity_types": [e.value for e in EntityType]
    }


@router.delete("/index/clear")
async def clear_index() -> Dict[str, Any]:
    """Очищает весь индекс."""
    try:
        indexer = get_incremental_indexer()
        indexer.clear_all()
        return {"status": "cleared", "message": "All index data cleared"}
    except Exception as e:
        logger.error(f"Failed to clear index: {e}")
        raise HTTPException(status_code=500, detail=str(e))

