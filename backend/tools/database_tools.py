"""
Database tools
"""

from typing import Dict, Any, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseTool, ToolOutput

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from sqlalchemy.exc import SQLAlchemyError
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class DatabaseQueryTool(BaseTool):
    """Tool for executing database queries"""
    
    def __init__(self, safety_guard=None):
        super().__init__(
            name="database_query",
            description="Выполнение SQL запросов к базе данных",
            safety_guard=safety_guard
        )
    
    async def execute(self, input_data: Dict[str, Any]) -> ToolOutput:
        """Execute database query"""
        query = input_data.get("query")
        connection_string = input_data.get("connection_string")
        
        if not query:
            return ToolOutput(success=False, result=None, error="query required")
        
        if not connection_string:
            return ToolOutput(success=False, result=None, error="connection_string required")
        
        # Safety check - prevent dangerous operations
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE"]
        query_upper = query.upper()
        
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return ToolOutput(
                    success=False,
                    result=None,
                    error=f"Dangerous operation detected: {keyword}. Only SELECT queries are allowed."
                )
        
        if not SQLALCHEMY_AVAILABLE:
            return ToolOutput(
                success=False,
                result=None,
                error="SQLAlchemy is not installed. Install it with: pip install sqlalchemy"
            )
        
        try:
            # Create engine with connection pooling
            # Use NullPool to avoid connection leaks
            engine = create_engine(
                connection_string,
                poolclass=NullPool,
                echo=False,
                connect_args={"check_same_thread": False} if "sqlite" in connection_string.lower() else {}
            )
            
            # Execute query
            with engine.connect() as connection:
                # Use text() for raw SQL queries
                result = connection.execute(text(query))
                
                # Fetch results
                if result.returns_rows:
                    rows = [dict(row._mapping) for row in result]
                    columns = list(result.keys()) if hasattr(result, 'keys') else []
                    
                    return ToolOutput(
                        success=True,
                        result={
                            "query": query,
                            "rows": rows,
                            "row_count": len(rows),
                            "columns": columns
                        }
                    )
                else:
                    # For INSERT, UPDATE, DELETE, etc.
                    return ToolOutput(
                        success=True,
                        result={
                            "query": query,
                            "rows_affected": result.rowcount,
                            "message": "Query executed successfully"
                        }
                    )
        
        except SQLAlchemyError as e:
            logger.error(f"DatabaseQueryTool SQL error: {e}")
            return ToolOutput(
                success=False,
                result=None,
                error=f"Database error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"DatabaseQueryTool error: {e}")
            return ToolOutput(
                success=False,
                result=None,
                error=f"Unexpected error: {str(e)}"
            )

