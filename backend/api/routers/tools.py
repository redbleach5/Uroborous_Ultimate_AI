"""
Tools router
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
from backend.core.logger import get_logger
logger = get_logger(__name__)

router = APIRouter()


@router.get("/tools")
async def list_tools(request: Request):
    """Список всех доступных инструментов"""
    engine = request.app.state.engine
    
    if not engine or not engine.tool_registry:
        raise HTTPException(status_code=503, detail="Реестр инструментов недоступен")
    
    tools = await engine.tool_registry.list_tools()
    return {"tools": tools}


@router.post("/tools/execute")
async def execute_tool(request: Request, tool_request: Dict[str, Any]):
    """Выполнить инструмент"""
    from ...core.validators import validate_tool_input
    
    engine = request.app.state.engine
    
    if not engine or not engine.tool_registry:
        raise HTTPException(status_code=503, detail="Реестр инструментов недоступен")
    
    try:
        # Validate input
        validated = validate_tool_input(tool_request)

        logger.debug(
            "Executing tool",
            tool_name=validated.tool_name,
            tool_input=validated.input,
        )

        result = await engine.tool_registry.execute_tool(validated.tool_name, validated.input)
        # Return ToolOutput directly - execution errors are valid results, not API errors
        return {
            "success": result.success,
            "result": result.result,
            "error": result.error
        }
    except ValueError as e:
        logger.warning("Tool validation failed", error=str(e), payload=tool_request)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log full stack to help diagnose 500 responses from the UI
        logger.exception("Tool execution failed", payload=tool_request)
        raise HTTPException(status_code=500, detail=str(e))

