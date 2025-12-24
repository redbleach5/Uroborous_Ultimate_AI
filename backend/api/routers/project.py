"""
Project router - Project indexing and management
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any

router = APIRouter()


@router.post("/project/index")
async def index_project(request: Request, index_request: Dict[str, Any]):
    """Индексировать проект для RAG"""
    from ...core.validators import validate_project_index_input
    
    engine = request.app.state.engine
    
    if not engine or not engine.vector_store:
        raise HTTPException(status_code=503, detail="Векторное хранилище недоступно")
    
    try:
        # Validate input
        validated = validate_project_index_input(index_request)
        
        from ..project.indexer import ProjectIndexer
        
        indexer = ProjectIndexer(engine.vector_store)
        result = await indexer.index_project(
            project_path=validated.project_path,
            extensions=set(validated.extensions) if validated.extensions else None,
            max_file_size=validated.max_file_size
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

