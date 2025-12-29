"""
Code Intelligence - AST-based анализ кода для глубокого понимания структуры.

Обеспечивает:
- Извлечение функций, классов, методов
- Построение графа зависимостей
- Анализ сложности кода
- Понимание связей между компонентами
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from enum import Enum

from ..core.logger import get_logger

logger = get_logger(__name__)


class EntityType(Enum):
    """Тип сущности кода."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ASYNC_FUNCTION = "async_function"
    ASYNC_METHOD = "async_method"
    MODULE = "module"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"


@dataclass
class CodeEntity:
    """Сущность кода (функция, класс, метод и т.д.)."""
    type: EntityType
    name: str
    qualified_name: str  # module.class.method
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    signature: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # Вызываемые функции/классы
    imports: List[str] = field(default_factory=list)  # Используемые импорты
    complexity: int = 1  # Cyclomatic complexity
    decorators: List[str] = field(default_factory=list)
    parent: Optional[str] = None  # Родительский класс/модуль
    children: List[str] = field(default_factory=list)  # Методы класса и т.д.
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь."""
        return {
            "type": self.type.value,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "docstring": self.docstring,
            "signature": self.signature,
            "dependencies": self.dependencies,
            "imports": self.imports,
            "complexity": self.complexity,
            "decorators": self.decorators,
            "parent": self.parent,
            "children": self.children,
        }
    
    def get_semantic_text(self) -> str:
        """Получить семантическое описание для эмбеддинга."""
        parts = [
            f"Type: {self.type.value}",
            f"Name: {self.name}",
            f"Full path: {self.qualified_name}",
        ]
        
        if self.signature:
            parts.append(f"Signature: {self.signature}")
        
        if self.docstring:
            parts.append(f"Purpose: {self.docstring[:500]}")
        
        if self.dependencies:
            parts.append(f"Calls: {', '.join(self.dependencies[:20])}")
        
        if self.decorators:
            parts.append(f"Decorators: {', '.join(self.decorators)}")
        
        parts.append(f"File: {self.file_path}")
        parts.append(f"Lines: {self.start_line}-{self.end_line}")
        parts.append(f"Complexity: {self.complexity}")
        
        return "\n".join(parts)


@dataclass
class ModuleInfo:
    """Информация о модуле."""
    file_path: str
    module_name: str
    imports: List[Dict[str, str]] = field(default_factory=list)
    entities: List[CodeEntity] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)  # Зависимости от других модулей
    total_lines: int = 0
    total_complexity: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "module_name": self.module_name,
            "imports": self.imports,
            "entities": [e.to_dict() for e in self.entities],
            "dependencies": list(self.dependencies),
            "total_lines": self.total_lines,
            "total_complexity": self.total_complexity,
        }


class PythonAnalyzer(ast.NodeVisitor):
    """AST-анализатор для Python кода."""
    
    def __init__(self, file_path: str, module_name: str):
        self.file_path = file_path
        self.module_name = module_name
        self.entities: List[CodeEntity] = []
        self.imports: List[Dict[str, str]] = []
        self.current_class: Optional[str] = None
        self._source_lines: List[str] = []
    
    def analyze(self, source: str) -> ModuleInfo:
        """Анализирует исходный код и возвращает информацию о модуле."""
        self._source_lines = source.split("\n")
        
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {self.file_path}: {e}")
            return ModuleInfo(
                file_path=self.file_path,
                module_name=self.module_name,
                total_lines=len(self._source_lines)
            )
        
        self.visit(tree)
        
        # Вычисляем зависимости модуля
        dependencies = set()
        for imp in self.imports:
            module = imp.get("module", "")
            if module and "." in module:
                dependencies.add(module.split(".")[0])
            elif module:
                dependencies.add(module)
        
        total_complexity = sum(e.complexity for e in self.entities)
        
        return ModuleInfo(
            file_path=self.file_path,
            module_name=self.module_name,
            imports=self.imports,
            entities=self.entities,
            dependencies=dependencies,
            total_lines=len(self._source_lines),
            total_complexity=total_complexity
        )
    
    def visit_Import(self, node: ast.Import) -> None:
        """Обработка import statements."""
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "module": alias.name,
                "alias": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Обработка from ... import statements."""
        module = node.module or ""
        for alias in node.names:
            self.imports.append({
                "type": "from_import",
                "module": module,
                "name": alias.name,
                "alias": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Обработка определения функции."""
        self._process_function(node, is_async=False)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Обработка определения async функции."""
        self._process_function(node, is_async=True)
        self.generic_visit(node)
    
    def _process_function(self, node, is_async: bool) -> None:
        """Общая обработка функций и методов."""
        # Определяем тип сущности
        if self.current_class:
            entity_type = EntityType.ASYNC_METHOD if is_async else EntityType.METHOD
            qualified_name = f"{self.module_name}.{self.current_class}.{node.name}"
            parent = f"{self.module_name}.{self.current_class}"
        else:
            entity_type = EntityType.ASYNC_FUNCTION if is_async else EntityType.FUNCTION
            qualified_name = f"{self.module_name}.{node.name}"
            parent = self.module_name
        
        # Извлекаем сигнатуру
        signature = self._extract_signature(node)
        
        # Извлекаем docstring
        docstring = ast.get_docstring(node)
        
        # Извлекаем зависимости (вызовы функций)
        dependencies = self._extract_dependencies(node)
        
        # Извлекаем используемые импорты
        imports = self._extract_used_imports(node)
        
        # Вычисляем сложность
        complexity = self._calculate_complexity(node)
        
        # Извлекаем декораторы
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        entity = CodeEntity(
            type=entity_type,
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=signature,
            dependencies=dependencies,
            imports=imports,
            complexity=complexity,
            decorators=decorators,
            parent=parent
        )
        
        self.entities.append(entity)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Обработка определения класса."""
        qualified_name = f"{self.module_name}.{node.name}"
        
        # Извлекаем docstring
        docstring = ast.get_docstring(node)
        
        # Извлекаем базовые классы
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{self._get_attribute_name(base)}")
        
        # Извлекаем декораторы
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        # Сохраняем текущий класс для обработки методов
        old_class = self.current_class
        self.current_class = node.name
        
        # Обрабатываем содержимое класса
        method_names = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_names.append(item.name)
        
        entity = CodeEntity(
            type=EntityType.CLASS,
            name=node.name,
            qualified_name=qualified_name,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}",
            dependencies=bases,
            decorators=decorators,
            parent=self.module_name,
            children=method_names
        )
        
        self.entities.append(entity)
        
        # Рекурсивно обрабатываем методы
        self.generic_visit(node)
        
        # Восстанавливаем контекст
        self.current_class = old_class
    
    def _extract_signature(self, node) -> str:
        """Извлекает сигнатуру функции."""
        args = []
        
        # Обычные аргументы
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_annotation_str(arg.annotation)}"
            args.append(arg_str)
        
        # *args
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        
        # **kwargs
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        # Возвращаемый тип
        return_annotation = ""
        if node.returns:
            return_annotation = f" -> {self._get_annotation_str(node.returns)}"
        
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)}){return_annotation}"
    
    def _extract_dependencies(self, node) -> List[str]:
        """Извлекает вызовы функций/методов из узла."""
        calls = []
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        
        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_calls = []
        for call in calls:
            if call not in seen:
                seen.add(call)
                unique_calls.append(call)
        
        return unique_calls
    
    def _extract_used_imports(self, node) -> List[str]:
        """Извлекает импорты, используемые в функции."""
        used_names = set()
        
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                used_names.add(child.id)
        
        used_imports = []
        for imp in self.imports:
            name = imp.get("alias") or imp.get("name") or imp.get("module", "").split(".")[-1]
            if name in used_names:
                used_imports.append(imp.get("module", "") or imp.get("name", ""))
        
        return used_imports
    
    def _calculate_complexity(self, node) -> int:
        """Вычисляет цикломатическую сложность."""
        complexity = 1  # Базовая сложность
        
        for child in ast.walk(node):
            # Условные конструкции
            if isinstance(child, (ast.If, ast.IfExp)):
                complexity += 1
            # Циклы
            elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
                complexity += 1
            # Обработка исключений
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            # Логические операторы
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            # Comprehensions
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        
        return complexity
    
    def _get_decorator_name(self, node) -> str:
        """Получает имя декоратора."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return str(node)
    
    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """Получает полное имя атрибута."""
        parts = [node.attr]
        current = node.value
        
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        
        if isinstance(current, ast.Name):
            parts.append(current.id)
        
        return ".".join(reversed(parts))
    
    def _get_annotation_str(self, node) -> str:
        """Преобразует аннотацию типа в строку."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Subscript):
            value = self._get_annotation_str(node.value)
            if isinstance(node.slice, ast.Tuple):
                slice_str = ", ".join(self._get_annotation_str(e) for e in node.slice.elts)
            else:
                slice_str = self._get_annotation_str(node.slice)
            return f"{value}[{slice_str}]"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Union type (X | Y)
            left = self._get_annotation_str(node.left)
            right = self._get_annotation_str(node.right)
            return f"{left} | {right}"
        return "Any"


class JavaScriptAnalyzer:
    """Анализатор для JavaScript/TypeScript кода (regex-based)."""
    
    FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)',
        re.MULTILINE
    )
    
    ARROW_FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
        re.MULTILINE
    )
    
    CLASS_PATTERN = re.compile(
        r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?',
        re.MULTILINE
    )
    
    METHOD_PATTERN = re.compile(
        r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*{',
        re.MULTILINE
    )
    
    IMPORT_PATTERN = re.compile(
        r"import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE
    )
    
    def __init__(self, file_path: str, module_name: str):
        self.file_path = file_path
        self.module_name = module_name
    
    def analyze(self, source: str) -> ModuleInfo:
        """Анализирует JavaScript/TypeScript код."""
        lines = source.split("\n")
        entities = []
        imports = []
        
        # Извлекаем импорты
        for match in self.IMPORT_PATTERN.finditer(source):
            imports.append({
                "type": "import",
                "module": match.group(1),
                "line": source[:match.start()].count("\n") + 1
            })
        
        # Извлекаем функции
        for match in self.FUNCTION_PATTERN.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            entities.append(CodeEntity(
                type=EntityType.FUNCTION,
                name=match.group(1),
                qualified_name=f"{self.module_name}.{match.group(1)}",
                file_path=self.file_path,
                start_line=line_num,
                end_line=self._find_block_end(lines, line_num - 1),
                signature=match.group(0).strip()
            ))
        
        # Извлекаем arrow functions
        for match in self.ARROW_FUNCTION_PATTERN.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            entities.append(CodeEntity(
                type=EntityType.FUNCTION,
                name=match.group(1),
                qualified_name=f"{self.module_name}.{match.group(1)}",
                file_path=self.file_path,
                start_line=line_num,
                end_line=self._find_block_end(lines, line_num - 1),
                signature=match.group(0).strip()
            ))
        
        # Извлекаем классы
        for match in self.CLASS_PATTERN.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            class_name = match.group(1)
            base_class = match.group(2)
            
            entities.append(CodeEntity(
                type=EntityType.CLASS,
                name=class_name,
                qualified_name=f"{self.module_name}.{class_name}",
                file_path=self.file_path,
                start_line=line_num,
                end_line=self._find_block_end(lines, line_num - 1),
                signature=match.group(0).strip(),
                dependencies=[base_class] if base_class else []
            ))
        
        dependencies = set(imp["module"].split("/")[0] for imp in imports if "/" in imp["module"])
        
        return ModuleInfo(
            file_path=self.file_path,
            module_name=self.module_name,
            imports=imports,
            entities=entities,
            dependencies=dependencies,
            total_lines=len(lines)
        )
    
    def _find_block_end(self, lines: List[str], start_line: int) -> int:
        """Находит конец блока кода по скобкам."""
        brace_count = 0
        started = False
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        return i + 1
        
        return len(lines)


class CodeIntelligence:
    """
    Центральный класс для анализа кода.
    
    Обеспечивает:
    - Анализ Python и JavaScript/TypeScript файлов
    - Построение графа зависимостей
    - Поиск по сущностям кода
    - Семантическое понимание структуры проекта
    """
    
    PYTHON_EXTENSIONS = {".py", ".pyw"}
    JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
    
    IGNORE_DIRS = {
        "__pycache__", "node_modules", ".git", ".venv", "venv", "env",
        "dist", "build", ".pytest_cache", ".mypy_cache", "coverage",
        ".next", ".nuxt", "target", "vendor"
    }
    
    def __init__(self):
        self._cache: Dict[str, ModuleInfo] = {}
    
    async def analyze_file(self, file_path: str, content: Optional[str] = None) -> Optional[ModuleInfo]:
        """
        Анализирует отдельный файл.
        
        Args:
            file_path: Путь к файлу
            content: Содержимое файла (если None, читается с диска)
            
        Returns:
            ModuleInfo или None если файл не поддерживается
        """
        path = Path(file_path)
        extension = path.suffix.lower()
        
        if extension not in self.PYTHON_EXTENSIONS and extension not in self.JS_EXTENSIONS:
            return None
        
        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, IOError) as e:
                logger.warning(f"Cannot read file {file_path}: {e}")
                return None
        
        module_name = path.stem
        
        try:
            if extension in self.PYTHON_EXTENSIONS:
                analyzer = PythonAnalyzer(str(path), module_name)
            else:
                analyzer = JavaScriptAnalyzer(str(path), module_name)
            
            return analyzer.analyze(content)
            
        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}")
            return None
    
    async def analyze_project(
        self,
        project_path: str,
        max_files: int = 1000
    ) -> Dict[str, Any]:
        """
        Анализирует весь проект.
        
        Args:
            project_path: Путь к корню проекта
            max_files: Максимальное количество файлов для анализа
            
        Returns:
            Словарь с информацией о проекте
        """
        project_path = Path(project_path)
        
        if not project_path.exists():
            return {"error": f"Project path does not exist: {project_path}"}
        
        modules: Dict[str, ModuleInfo] = {}
        all_entities: List[CodeEntity] = []
        total_lines = 0
        total_complexity = 0
        files_analyzed = 0
        
        # Рекурсивно обходим проект
        for path in self._walk_project(project_path, max_files):
            module_info = await self.analyze_file(str(path))
            
            if module_info:
                rel_path = str(path.relative_to(project_path))
                modules[rel_path] = module_info
                all_entities.extend(module_info.entities)
                total_lines += module_info.total_lines
                total_complexity += module_info.total_complexity
                files_analyzed += 1
                
                # Кэшируем результат
                self._cache[str(path)] = module_info
        
        # Строим граф зависимостей
        dependency_graph = self._build_dependency_graph(modules)
        
        # Статистика по типам сущностей
        entity_stats = self._calculate_entity_stats(all_entities)
        
        # Находим наиболее сложные сущности
        complex_entities = sorted(
            all_entities,
            key=lambda e: e.complexity,
            reverse=True
        )[:20]
        
        # Находим наиболее используемые функции
        dependency_counts = {}
        for entity in all_entities:
            for dep in entity.dependencies:
                dependency_counts[dep] = dependency_counts.get(dep, 0) + 1
        
        most_used = sorted(
            dependency_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        
        return {
            "project_path": str(project_path),
            "files_analyzed": files_analyzed,
            "total_lines": total_lines,
            "total_complexity": total_complexity,
            "average_complexity": total_complexity / max(len(all_entities), 1),
            "total_entities": len(all_entities),
            "entity_stats": entity_stats,
            "dependency_graph": dependency_graph,
            "complex_entities": [e.to_dict() for e in complex_entities],
            "most_used_functions": most_used,
            "modules": {k: v.to_dict() for k, v in modules.items()}
        }
    
    def _walk_project(self, project_path: Path, max_files: int) -> List[Path]:
        """Обходит проект, игнорируя ненужные директории."""
        files = []
        
        for root, dirs, filenames in project_path.walk():
            # Фильтруем игнорируемые директории
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
            
            for filename in filenames:
                if len(files) >= max_files:
                    return files
                
                file_path = root / filename
                extension = file_path.suffix.lower()
                
                if extension in self.PYTHON_EXTENSIONS or extension in self.JS_EXTENSIONS:
                    files.append(file_path)
        
        return files
    
    def _build_dependency_graph(self, modules: Dict[str, ModuleInfo]) -> Dict[str, List[str]]:
        """Строит граф зависимостей между модулями."""
        graph = {}
        
        for file_path, module in modules.items():
            graph[file_path] = list(module.dependencies)
        
        return graph
    
    def _calculate_entity_stats(self, entities: List[CodeEntity]) -> Dict[str, int]:
        """Подсчитывает статистику по типам сущностей."""
        stats = {}
        
        for entity in entities:
            type_name = entity.type.value
            stats[type_name] = stats.get(type_name, 0) + 1
        
        return stats
    
    async def find_entity(
        self,
        project_path: str,
        entity_name: str,
        entity_type: Optional[EntityType] = None
    ) -> List[CodeEntity]:
        """
        Находит сущности по имени.
        
        Args:
            project_path: Путь к проекту
            entity_name: Имя сущности (поддерживает частичное совпадение)
            entity_type: Тип сущности (опционально)
            
        Returns:
            Список найденных сущностей
        """
        results = []
        entity_name_lower = entity_name.lower()
        
        # Анализируем проект если не в кэше
        if not self._cache:
            await self.analyze_project(project_path)
        
        for module_info in self._cache.values():
            for entity in module_info.entities:
                # Проверяем совпадение имени
                if entity_name_lower in entity.name.lower():
                    # Проверяем тип если указан
                    if entity_type is None or entity.type == entity_type:
                        results.append(entity)
        
        return results
    
    async def get_entity_context(
        self,
        entity: CodeEntity,
        include_dependencies: bool = True,
        include_dependents: bool = True
    ) -> Dict[str, Any]:
        """
        Получает контекст для сущности (зависимости и зависимые).
        
        Args:
            entity: Сущность кода
            include_dependencies: Включить зависимости
            include_dependents: Включить зависимые сущности
            
        Returns:
            Контекст с информацией о связях
        """
        context = {
            "entity": entity.to_dict(),
            "dependencies": [],
            "dependents": []
        }
        
        if include_dependencies:
            # Находим определения зависимостей
            for dep_name in entity.dependencies:
                for module_info in self._cache.values():
                    for other in module_info.entities:
                        if other.name == dep_name:
                            context["dependencies"].append(other.to_dict())
        
        if include_dependents:
            # Находим сущности, которые используют данную
            for module_info in self._cache.values():
                for other in module_info.entities:
                    if entity.name in other.dependencies:
                        context["dependents"].append(other.to_dict())
        
        return context
    
    def clear_cache(self) -> None:
        """Очищает кэш анализа."""
        self._cache.clear()


# Глобальный экземпляр для использования в других модулях
_code_intelligence: Optional[CodeIntelligence] = None


def get_code_intelligence() -> CodeIntelligence:
    """Получить глобальный экземпляр CodeIntelligence."""
    global _code_intelligence
    if _code_intelligence is None:
        _code_intelligence = CodeIntelligence()
    return _code_intelligence

