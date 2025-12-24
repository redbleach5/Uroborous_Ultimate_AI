"""
Pydantic utilities for compatibility between v1 and v2
"""

from typing import Any, Dict


def pydantic_to_dict(obj: Any) -> Dict[str, Any]:
    """
    Convert Pydantic model to dict, compatible with v1 and v2
    
    Args:
        obj: Pydantic model instance or dict
        
    Returns:
        Dictionary representation of the object
    """
    if hasattr(obj, 'model_dump'):
        # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        # Pydantic v1
        return obj.dict()
    elif isinstance(obj, dict):
        return obj
    else:
        return {}

