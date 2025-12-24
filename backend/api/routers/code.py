"""
Code router
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any

from ...core.validators import validate_code_input

router = APIRouter()


@router.post("/code/generate")
async def generate_code(request: Request, code_request: Dict[str, Any]):
    """Сгенерировать код"""
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    try:
        # Validate input
        validated = validate_code_input(code_request)
        
        context = {
            "file_path": validated.file_path,
            "existing_code": validated.existing_code,
            "requirements": validated.requirements
        }
        
        result = await engine.execute_task(
            task=validated.task,
            agent_type="code_writer",
            context=context
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

