"""
API Documentation helpers
"""

from fastapi import APIRouter
from fastapi.openapi.utils import get_openapi

router = APIRouter()


def custom_openapi(app):
    """Custom OpenAPI schema"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="AILLM API",
        version="0.1.0",
        description="""
## AILLM - Autonomous Intelligent LLM Agents API

Комплексная система автономных агентов для разработки ПО на основе LLM.

### Возможности

- 🤖 7 автономных агентов для различных задач
- 🧠 Интеллектуальное планирование и декомпозиция задач
- 🔍 RAG система для семантического поиска
- 🔌 Поддержка множественных LLM провайдеров
- 🛠️ Богатый набор инструментов
- 🔒 Система безопасности
- 📊 Мониторинг в реальном времени
- 🖼️ Мультимодальная обработка

### Агенты

1. **CodeWriterAgent** - Генерация и рефакторинг кода
2. **ReactAgent** - Интерактивное решение задач (ReAct)
3. **ResearchAgent** - Исследование кодовой базы
4. **DataAnalysisAgent** - Анализ данных и ML
5. **WorkflowAgent** - Управление workflows
6. **IntegrationAgent** - Интеграция с внешними сервисами
7. **MonitoringAgent** - Мониторинг системы

### Инструменты

- File operations (read, write, list)
- Shell commands (with safety checks)
- Git operations (status, commit, branch, diff, log)
- Web search and API calls
- Database queries

### Мультимодальная обработка

- Image processing (OCR, analysis)
- Audio transcription (Whisper)
- Video processing (frame extraction)

### Примеры использования

#### Выполнение задачи
```python
POST /api/v1/tasks/execute
{
  "task": "Create a Python function",
  "agent_type": "code_writer",
  "context": {}
}
```

#### Генерация кода
```python
POST /api/v1/code/generate
{
  "task": "Create a todo list class",
  "file_path": "todo.py"
}
```

#### Индексация проекта
```python
POST /api/v1/project/index
{
  "project_path": "/path/to/project"
}
```
        """,
        routes=app.routes,
    )
    
    # Add custom tags
    openapi_schema["tags"] = [
        {
            "name": "tasks",
            "description": "Task execution and management"
        },
        {
            "name": "code",
            "description": "Code generation and manipulation"
        },
        {
            "name": "tools",
            "description": "Tool management and execution"
        },
        {
            "name": "config",
            "description": "Configuration management"
        },
        {
            "name": "monitoring",
            "description": "System monitoring and metrics"
        },
        {
            "name": "project",
            "description": "Project indexing and management"
        },
        {
            "name": "multimodal",
            "description": "Multimodal processing (images, audio, video)"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

