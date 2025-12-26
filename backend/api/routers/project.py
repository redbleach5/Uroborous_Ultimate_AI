"""
Project router - Project management, file browsing and analysis
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from pathlib import Path
import os
import mimetypes
import asyncio
import json

from ...core.logger import get_logger
from ...core.progress_tracker import get_progress_manager, ProgressTracker

logger = get_logger(__name__)

router = APIRouter()


class FileInfo(BaseModel):
    """Информация о файле"""
    name: str
    path: str
    is_dir: bool
    size: int = 0
    extension: Optional[str] = None
    children: Optional[List["FileInfo"]] = None


class ProjectOpenRequest(BaseModel):
    """Запрос на открытие проекта"""
    project_path: str = Field(..., description="Путь к папке проекта")
    max_depth: int = Field(default=5, description="Максимальная глубина сканирования")
    include_hidden: bool = Field(default=False, description="Включать скрытые файлы")


class FileReadRequest(BaseModel):
    """Запрос на чтение файла"""
    file_path: str = Field(..., description="Путь к файлу")


class ProjectAnalysisRequest(BaseModel):
    """Запрос на анализ проекта"""
    project_path: str = Field(..., description="Путь к проекту")
    analysis_type: str = Field(default="overview", description="Тип анализа: overview, structure, dependencies, issues")
    specific_question: Optional[str] = Field(default=None, description="Конкретный вопрос о проекте")


# Список игнорируемых директорий и файлов
IGNORED_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 
    '.idea', '.vscode', 'dist', 'build', '.next', '.cache',
    'coverage', '.pytest_cache', '.mypy_cache', 'eggs', '*.egg-info'
}

IGNORED_FILES = {
    '.DS_Store', 'Thumbs.db', '.gitignore', '.env', '.env.local'
}

# Расширения бинарных файлов (не читаем)
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.exe', '.dll', '.so', '.dylib',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.ttf', '.woff', '.woff2', '.eot',
    '.pyc', '.pyo', '.class', '.o'
}

# Расширения кода
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte',
    '.html', '.css', '.scss', '.sass', '.less',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg',
    '.md', '.txt', '.rst', '.log',
    '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs',
    '.rb', '.php', '.swift', '.kt', '.scala',
    '.sql', '.sh', '.bash', '.zsh', '.ps1',
    '.xml', '.svg'
}


def should_ignore(name: str, is_dir: bool) -> bool:
    """Проверяет, следует ли игнорировать файл/директорию"""
    if is_dir:
        return name in IGNORED_DIRS or name.startswith('.')
    return name in IGNORED_FILES


def get_file_info(path: Path, base_path: Path, max_depth: int, current_depth: int = 0, include_hidden: bool = False) -> Optional[FileInfo]:
    """Рекурсивно получает информацию о файле/директории"""
    try:
        name = path.name
        is_dir = path.is_dir()
        
        # Проверяем, нужно ли игнорировать
        if not include_hidden and should_ignore(name, is_dir):
            return None
        
        relative_path = str(path.relative_to(base_path))
        
        if is_dir:
            children = None
            if current_depth < max_depth:
                children = []
                try:
                    for child in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                        child_info = get_file_info(child, base_path, max_depth, current_depth + 1, include_hidden)
                        if child_info:
                            children.append(child_info)
                except PermissionError:
                    pass
            
            return FileInfo(
                name=name,
                path=relative_path,
                is_dir=True,
                children=children
            )
        else:
            extension = path.suffix.lower() if path.suffix else None
            try:
                size = path.stat().st_size
            except (OSError, PermissionError):
                size = 0
            
            return FileInfo(
                name=name,
                path=relative_path,
                is_dir=False,
                size=size,
                extension=extension
            )
    except Exception as e:
        logger.debug(f"Error getting file info for {path}: {e}")
        return None


class BrowseRequest(BaseModel):
    """Запрос на просмотр директории"""
    path: str = Field(default="~", description="Путь для просмотра")


@router.post("/project/browse")
async def browse_directory(request: BrowseRequest) -> Dict[str, Any]:
    """
    Просмотреть содержимое директории для навигации.
    Возвращает только папки для выбора проекта.
    """
    path = Path(request.path).expanduser().resolve()
    
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Путь не найден: {request.path}")
    
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Указанный путь не является директорией")
    
    try:
        directories = []
        files_count = 0
        
        for item in sorted(path.iterdir(), key=lambda x: x.name.lower()):
            try:
                if item.name.startswith('.'):
                    continue
                if item.is_dir():
                    # Check if it's a potential project (has code files)
                    has_code = False
                    try:
                        for sub in item.iterdir():
                            if sub.suffix.lower() in CODE_EXTENSIONS or sub.name in ['package.json', 'requirements.txt', 'Cargo.toml', 'go.mod']:
                                has_code = True
                                break
                    except PermissionError:
                        pass
                    
                    directories.append({
                        "name": item.name,
                        "path": str(item),
                        "has_code": has_code
                    })
                else:
                    files_count += 1
            except PermissionError:
                continue
        
        return {
            "success": True,
            "current_path": str(path),
            "parent_path": str(path.parent) if path.parent != path else None,
            "directories": directories[:50],  # Limit
            "files_count": files_count
        }
        
    except PermissionError:
        raise HTTPException(status_code=403, detail="Нет доступа к директории")
    except Exception as e:
        logger.error(f"Error browsing directory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/open")
async def open_project(request: ProjectOpenRequest) -> Dict[str, Any]:
    """
    Открыть проект и получить его структуру файлов.
    
    Возвращает дерево файлов проекта для отображения в UI.
    """
    project_path = Path(request.project_path).expanduser().resolve()
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Путь не найден: {request.project_path}")
    
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail="Указанный путь не является директорией")
    
    try:
        # Получаем структуру файлов
        root_info = get_file_info(
            project_path, 
            project_path, 
            request.max_depth,
            include_hidden=request.include_hidden
        )
        
        if not root_info:
            raise HTTPException(status_code=500, detail="Не удалось прочитать структуру проекта")
        
        # Считаем статистику
        def count_files(info: FileInfo) -> Dict[str, int]:
            stats = {"files": 0, "dirs": 0, "code_files": 0}
            if info.is_dir:
                stats["dirs"] += 1
                if info.children:
                    for child in info.children:
                        child_stats = count_files(child)
                        stats["files"] += child_stats["files"]
                        stats["dirs"] += child_stats["dirs"]
                        stats["code_files"] += child_stats["code_files"]
            else:
                stats["files"] += 1
                if info.extension and info.extension in CODE_EXTENSIONS:
                    stats["code_files"] += 1
            return stats
        
        stats = count_files(root_info)
        
        return {
            "success": True,
            "project_name": project_path.name,
            "project_path": str(project_path),
            "tree": root_info.model_dump(),
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error opening project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/read-file")
async def read_file(request: FileReadRequest, req: Request) -> Dict[str, Any]:
    """
    Прочитать содержимое файла.
    """
    # Получаем базовый путь проекта из состояния или используем абсолютный путь
    file_path = Path(request.file_path).expanduser().resolve()
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Файл не найден: {request.file_path}")
    
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Указанный путь не является файлом")
    
    extension = file_path.suffix.lower()
    
    # Проверяем, не бинарный ли это файл
    if extension in BINARY_EXTENSIONS:
        return {
            "success": True,
            "path": str(file_path),
            "name": file_path.name,
            "is_binary": True,
            "content": None,
            "size": file_path.stat().st_size,
            "extension": extension
        }
    
    try:
        # Определяем кодировку
        content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding='latin-1')
        except (OSError, PermissionError, UnicodeDecodeError):
            return {
                "success": True,
                "path": str(file_path),
                "name": file_path.name,
                "is_binary": True,
                "content": None,
                "size": file_path.stat().st_size,
                "extension": extension
            }
    
    # Определяем язык для подсветки
    language_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.md': 'markdown',
        '.sql': 'sql',
        '.sh': 'shell',
        '.bash': 'shell',
        '.xml': 'xml',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
    }
    
    language = language_map.get(extension, 'plaintext')
    
    return {
        "success": True,
        "path": str(file_path),
        "name": file_path.name,
        "is_binary": False,
        "content": content,
        "size": len(content),
        "extension": extension,
        "language": language,
        "lines": content.count('\n') + 1
    }


@router.post("/project/analyze")
async def analyze_project(request: ProjectAnalysisRequest, req: Request) -> Dict[str, Any]:
    """
    Комплексный анализ проекта с помощью AI.
    
    Использует SmartProjectAnalyzer для:
    - Адаптивного профилирования проекта
    - Выбора оптимальной стратегии анализа
    - Задействования git, RAG и нескольких агентов
    """
    engine = req.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Engine недоступен")
    
    project_path = Path(request.project_path).expanduser().resolve()
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Проект не найден: {request.project_path}")
    
    try:
        from ..project.smart_analyzer import SmartProjectAnalyzer
        
        analyzer = SmartProjectAnalyzer(engine)
        result = await analyzer.analyze(
            project_path=str(project_path),
            analysis_type=request.analysis_type,
            specific_question=request.specific_question,
            use_git=True,
            use_rag=True
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Ошибка анализа"))
        
        return result
        
    except ImportError:
        # Fallback на простой анализ если SmartAnalyzer недоступен
        logger.warning("SmartProjectAnalyzer not available, using simple analysis")
        return await _simple_analyze_project(engine, project_path, request)
    except Exception as e:
        logger.error(f"Error analyzing project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/analyze-stream")
async def analyze_project_stream(request: ProjectAnalysisRequest, req: Request):
    """
    Анализ проекта с потоковой передачей прогресса через SSE.
    
    Отправляет события прогресса в реальном времени:
    - stage: текущий этап
    - message: описание
    - progress: 0.0-1.0
    - details: дополнительные данные
    """
    engine = req.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Engine недоступен")
    
    project_path = Path(request.project_path).expanduser().resolve()
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Проект не найден: {request.project_path}")
    
    async def generate_events():
        """Генератор SSE событий."""
        progress_manager = get_progress_manager()
        tracker = await progress_manager.create_tracker("project_analysis")
        
        try:
            # Начало
            yield _sse_event("starting", "Начинаем анализ...", 0.0, {"project": project_path.name})
            
            from ..project.smart_analyzer import SmartProjectAnalyzer
            
            analyzer = SmartProjectAnalyzer(engine)
            
            # Профилирование
            yield _sse_event("profiling", "📊 Профилируем проект...", 0.1)
            
            profile = await analyzer._profile_project(project_path, 5)
            
            yield _sse_event("profiling", f"Определена сложность: {profile.complexity.value}", 0.15, {
                "complexity": profile.complexity.value,
                "files": profile.code_files,
                "languages": list(profile.languages.keys())
            })
            
            # Стратегия
            yield _sse_event("strategy", "🎯 Выбираем стратегию анализа...", 0.2)
            strategy = analyzer._determine_strategy(profile, request.analysis_type)
            
            yield _sse_event("strategy", f"Стратегия: {strategy['name']}", 0.25, {
                "agents": strategy.get("agents", []),
                "max_files": strategy.get("max_files", 0)
            })
            
            # Сбор контекста
            yield _sse_event("scanning", "📂 Сканируем файлы проекта...", 0.3)
            
            context = await analyzer._gather_context(
                project_path, profile, strategy,
                use_git=True, use_rag=True
            )
            
            files_count = len(context.get("files_content", {}))
            yield _sse_event("scanning", f"Прочитано {files_count} файлов", 0.4, {
                "files_read": files_count,
                "has_git": context.get("git_info") is not None
            })
            
            # Git info
            if context.get("git_info"):
                yield _sse_event("git", "📜 Анализируем git историю...", 0.45)
            
            # RAG
            if context.get("rag_context"):
                yield _sse_event("rag", "🔍 Поиск в базе знаний...", 0.5)
            
            # Анализ
            yield _sse_event("analyzing", "🧠 AI анализирует проект...", 0.55, {
                "info": "Это может занять 1-2 минуты"
            })
            
            # Запускаем анализ
            analysis_results = await analyzer._run_analysis(
                profile, context, strategy, request.specific_question
            )
            
            yield _sse_event("processing", "📝 Обрабатываем результаты...", 0.9)
            
            # Финальный результат
            result = {
                "success": True,
                "project_name": profile.name,
                "project_path": str(project_path),
                "complexity": profile.complexity.value,
                "profile": {
                    "total_files": profile.total_files,
                    "code_files": profile.code_files,
                    "total_lines": profile.total_lines,
                    "languages": profile.languages,
                    "frameworks": profile.frameworks
                },
                "strategy_used": strategy['name'],
                "files_analyzed": files_count,
                "total_lines": profile.total_lines,
                "analysis": analysis_results.get("final_answer") or analysis_results.get("analysis"),
                "result": analysis_results
            }
            
            yield _sse_event("completed", "✅ Анализ завершён!", 1.0, {"result": result})
            
        except Exception as e:
            logger.error(f"Stream analysis error: {e}")
            yield _sse_event("error", f"❌ Ошибка: {str(e)}", -1)
        
        finally:
            await progress_manager.remove_tracker(tracker.operation_id)
    
    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _sse_event(stage: str, message: str, progress: float, details: Optional[Dict] = None) -> str:
    """Форматирует SSE событие."""
    event = {
        "stage": stage,
        "message": message,
        "progress": round(progress, 2),
        "details": details or {}
    }
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _simple_analyze_project(engine, project_path: Path, request: ProjectAnalysisRequest) -> Dict[str, Any]:
    """Простой анализ проекта (fallback)."""
    context_parts = []
    files_analyzed = []
    total_lines = 0
    
    # Читаем важные файлы
    for file_name in ['README.md', 'package.json', 'requirements.txt', 'pyproject.toml']:
        file_path = project_path / file_name
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')[:5000]
                context_parts.append(f"=== {file_name} ===\n{content}\n")
                files_analyzed.append(file_name)
            except (OSError, PermissionError, UnicodeDecodeError):
                pass
    
    # Сканируем код
    code_files = []
    for ext in CODE_EXTENSIONS:
        code_files.extend(project_path.rglob(f"*{ext}"))
    code_files = [f for f in code_files[:30] if not should_ignore(f.name, False)]
    
    for code_file in code_files[:15]:
        try:
            content = code_file.read_text(encoding='utf-8')
            lines = content.count('\n') + 1
            total_lines += lines
            truncated = content[:2000]
            rel_path = code_file.relative_to(project_path)
            context_parts.append(f"\n=== {rel_path} ===\n{truncated}")
            files_analyzed.append(str(rel_path))
        except (OSError, PermissionError, UnicodeDecodeError):
            pass
    
    task = f"""Проанализируй проект {project_path.name}:

{chr(10).join(context_parts)}

Предоставь обзор: назначение, технологии, структура, рекомендации."""
    
    result = await engine.execute_task(task=task, agent_type="research", context={})
    
    return {
        "success": True,
        "project_name": project_path.name,
        "project_path": str(project_path),
        "analysis_type": request.analysis_type,
        "files_analyzed": len(files_analyzed),
        "total_lines": total_lines,
        "result": result,
        "complexity": "unknown",
        "strategy_used": "simple_fallback"
    }


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
        
        from backend.project.indexer import ProjectIndexer
        
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


# Rebuild model for recursive FileInfo
FileInfo.model_rebuild()
