#!/usr/bin/env python3
"""
Комплексный валидатор проекта AILLM
Проверяет структуру, пути, импорты, конфигурацию и общую согласованность проекта
Поддерживает автоматическое исправление простых проблем
"""

import ast
import os
import sys
import re
import shutil
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any, Optional
from collections import defaultdict

# Опциональные импорты
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Определяем корень проекта
PROJECT_ROOT = Path(__file__).parent.parent

# Цвета для вывода
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
CYAN = '\033[0;36m'
NC = '\033[0m'  # No Color


class ValidationError:
    """Ошибка валидации"""
    def __init__(self, file: Path, message: str, line: Optional[int] = None, severity: str = "error", auto_fixable: bool = False, fix_action: Optional[callable] = None):
        self.file = file
        self.message = message
        self.line = line
        self.severity = severity  # error, warning, info
        self.auto_fixable = auto_fixable
        self.fix_action = fix_action
        self.fixed = False
    
    def __str__(self):
        location = f"{self.file}"
        if self.line:
            location += f":{self.line}"
        severity_color = RED if self.severity == "error" else YELLOW if self.severity == "warning" else BLUE
        fixable_mark = f"{CYAN}[AUTO-FIX]{NC} " if self.auto_fixable else ""
        return f"{severity_color}[{self.severity.upper()}]{NC} {fixable_mark}{location}: {self.message}"


class ProjectValidator:
    """Валидатор проекта с поддержкой автоматического исправления"""
    
    def __init__(self, project_root: Path, auto_fix: bool = False, dry_run: bool = False):
        self.project_root = project_root
        self.backend_dir = project_root / "backend"
        self.frontend_dir = project_root / "frontend"
        self.config_dir = project_root / "config"
        self.scripts_dir = project_root / "scripts"
        self.docs_dir = project_root / "docs"
        self.auto_fix = auto_fix
        self.dry_run = dry_run
        self.errors: List[ValidationError] = []
        self.fixed_count = 0
        self.imports_map: Dict[str, Set[str]] = defaultdict(set)
        self.module_paths: Dict[str, Path] = {}
        self.file_dependencies: Dict[str, Set[str]] = defaultdict(set)  # Граф зависимостей
        
    def validate(self) -> bool:
        """Запустить все проверки"""
        print(f"{BLUE}🔍 Начинаем валидацию проекта...{NC}")
        if self.auto_fix:
            print(f"{CYAN}🔧 Режим автоматического исправления{' (dry-run)' if self.dry_run else ''}{NC}")
        print()
        
        print(f"{BLUE}1. Проверка структуры директорий...{NC}")
        self.validate_structure()
        
        print(f"{BLUE}2. Проверка Python файлов (синтаксис и импорты)...{NC}")
        self.validate_python_files()
        
        print(f"{BLUE}3. Проверка путей и импортов...{NC}")
        self.validate_imports()
        
        print(f"{BLUE}4. Проверка конфигурации...{NC}")
        self.validate_config()
        
        print(f"{BLUE}5. Проверка согласованности...{NC}")
        self.validate_consistency()
        
        print(f"{BLUE}6. Проверка документации...{NC}")
        self.validate_documentation()
        
        print(f"{BLUE}7. Анализ зависимостей...{NC}")
        self.analyze_dependencies()
        
        # Применяем автоматические исправления
        if self.auto_fix:
            self.apply_auto_fixes()
        
        # Выводим результаты
        self.print_results()
        
        return len([e for e in self.errors if e.severity == "error" and not e.fixed]) == 0
    
    def validate_structure(self):
        """Проверка структуры директорий"""
        required_dirs = [
            "backend",
            "frontend",
            "scripts",
            "docs",
            "config",
        ]
        
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                self.errors.append(ValidationError(
                    self.project_root,
                    f"Отсутствует обязательная директория: {dir_name}",
                    severity="error",
                    auto_fixable=True,
                    fix_action=lambda d=dir_path: d.mkdir(parents=True, exist_ok=True)
                ))
        
        # Проверка что скрипты в scripts/ (исключая разрешенные скрипты запуска в корне)
        allowed_root_scripts = {
            "start.sh",      # Скрипт запуска проекта (должен быть в корне)
            "stop.sh",       # Скрипт остановки проекта (должен быть в корне)
            "run.sh",        # Альтернативное имя скрипта запуска
            "setup.sh"       # Скрипт первоначальной настройки
        }
        scripts_in_root = list(self.project_root.glob("*.sh")) + list(self.project_root.glob("*.py"))
        for script in scripts_in_root:
            if script.name != "README.md" and script.parent == self.project_root:
                # Пропускаем разрешенные скрипты запуска и requirements.txt
                if script.suffix in [".sh", ".py"] and script.name not in ["requirements.txt"] and script.name not in allowed_root_scripts:
                    target_path = self.scripts_dir / script.name
                    self.errors.append(ValidationError(
                        script,
                        f"Скрипт должен быть в scripts/, найден в корне: {script.name}. Разрешенные скрипты в корне: {', '.join(sorted(allowed_root_scripts))}",
                        severity="warning",
                        auto_fixable=True,
                        fix_action=lambda s=script, t=target_path: self._move_file(s, t)
                    ))
    
    def _move_file(self, source: Path, target: Path):
        """Переместить файл"""
        if self.dry_run:
            print(f"  {CYAN}[DRY-RUN]{NC} Переместить {source} -> {target}")
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            print(f"  {GREEN}✓{NC} Перемещен: {source.name} -> scripts/")
        except Exception as e:
            print(f"  {RED}✗{NC} Ошибка перемещения {source}: {e}")
    
    def validate_python_files(self):
        """Проверка синтаксиса Python файлов"""
        python_files = list(self.backend_dir.rglob("*.py"))
        python_files += list(self.scripts_dir.rglob("*.py"))
        
        for file_path in python_files:
            # Пропускаем __pycache__ и .venv
            if "__pycache__" in str(file_path) or ".venv" in str(file_path):
                continue
            
            # Проверка синтаксиса
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    ast.parse(content)
            except SyntaxError as e:
                self.errors.append(ValidationError(
                    file_path,
                    f"Синтаксическая ошибка: {e.msg}",
                    line=e.lineno,
                    severity="error"
                ))
                continue
            except Exception as e:
                self.errors.append(ValidationError(
                    file_path,
                    f"Ошибка при проверке: {str(e)}",
                    severity="error"
                ))
                continue
            
            # Извлекаем импорты для дальнейшей проверки
            try:
                tree = ast.parse(content)
                self.extract_imports(file_path, tree)
                self.extract_dependencies(file_path, tree)
            except:
                pass  # Уже обработано выше
    
    def extract_imports(self, file_path: Path, tree: ast.AST):
        """Извлечь импорты из AST"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports_map[str(file_path)].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports_map[str(file_path)].add(node.module)
    
    def extract_dependencies(self, file_path: Path, tree: ast.AST):
        """Извлечь зависимости между файлами"""
        file_str = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Записываем зависимость
                self.file_dependencies[file_str].add(node.module)
    
    def validate_imports(self):
        """Проверка корректности импортов"""
        # Проверяем что все импорты backend используют правильные пути
        for file_path_str, imports in self.imports_map.items():
            file_path = Path(file_path_str)
            if not file_path.is_relative_to(self.backend_dir):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Проверяем прямое использование loguru
                if "from loguru import logger" in content:
                    # Автоматическое исправление
                    def fix_loguru_import():
                        # Определяем правильный путь импорта
                        rel_path = file_path.relative_to(self.backend_dir)
                        depth = len(rel_path.parts) - 1
                        
                        if depth == 0:
                            import_line = "from .core.logger import get_logger"
                        elif depth == 1:
                            import_line = "from ..core.logger import get_logger"
                        else:
                            dots = ".." * depth
                            import_line = f"from {dots}.core.logger import get_logger"
                        
                        # Заменяем импорт
                        new_content = re.sub(
                            r'^from loguru import logger\s*$',
                            f'{import_line}\nlogger = get_logger(__name__)',
                            content,
                            flags=re.MULTILINE
                        )
                        
                        if new_content != content:
                            if not self.dry_run:
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                            return True
                        return False
                    
                    self.errors.append(ValidationError(
                        file_path,
                        f"Используется прямой импорт loguru. Используйте: from ..core.logger import get_logger",
                        severity="error",
                        auto_fixable=True,
                        fix_action=fix_loguru_import
                    ))
            except:
                pass
    
    def validate_config(self):
        """Проверка конфигурационных файлов"""
        if not HAS_YAML:
            self.errors.append(ValidationError(
                self.project_root,
                "Модуль yaml не установлен. Установите: pip install pyyaml",
                severity="warning"
            ))
            return
        
        # Проверка config.yaml
        config_files = [
            self.project_root / "backend" / "config" / "config.yaml",
            self.project_root / "config" / "config.yaml",
        ]
        
        example_config = self.project_root / "config" / "config.example.yaml"
        
        for config_file in config_files:
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    # Базовая проверка структуры
                    if not isinstance(config, dict):
                        self.errors.append(ValidationError(
                            config_file,
                            "Конфигурация должна быть словарем",
                            severity="error"
                        ))
                except yaml.YAMLError as e:
                    self.errors.append(ValidationError(
                        config_file,
                        f"Ошибка парсинга YAML: {str(e)}",
                        severity="error"
                    ))
                except Exception as e:
                    self.errors.append(ValidationError(
                        config_file,
                        f"Ошибка чтения конфигурации: {str(e)}",
                        severity="warning"
                    ))
        
        # Проверка что есть пример конфигурации
        if not example_config.exists():
            self.errors.append(ValidationError(
                self.project_root,
                "Отсутствует config.example.yaml",
                severity="warning"
            ))
    
    def validate_consistency(self):
        """Проверка согласованности проекта"""
        # Проверка что все скрипты используют PROJECT_ROOT
        script_files = list(self.scripts_dir.glob("*.py"))
        for script_file in script_files:
            try:
                with open(script_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Проверяем что используется правильное определение корня проекта
                if "PROJECT_ROOT" not in content and "project_root" not in content:
                    if "Path(__file__)" in content or "dirname" in content:
                        # Скрипт работает с путями, должен определять PROJECT_ROOT
                        if "cleanup" in script_file.name or "check" in script_file.name or "update" in script_file.name:
                            # Автоматическое добавление PROJECT_ROOT
                            def fix_project_root():
                                lines = content.split('\n')
                                # Находим где добавить
                                insert_pos = 0
                                for i, line in enumerate(lines):
                                    if line.strip().startswith('from pathlib import Path') or line.strip().startswith('import sys'):
                                        insert_pos = i + 1
                                        break
                                
                                if 'PROJECT_ROOT' not in content:
                                    root_def = '\n# Определяем корень проекта (на уровень выше scripts/)\nPROJECT_ROOT = Path(__file__).parent.parent\n'
                                    lines.insert(insert_pos, root_def)
                                    
                                    # Заменяем все использования Path('.')
                                    new_content = '\n'.join(lines)
                                    new_content = re.sub(r"Path\('\.'\)", 'PROJECT_ROOT', new_content)
                                    new_content = re.sub(r'Path\("\.', 'PROJECT_ROOT', new_content)
                                    
                                    if not self.dry_run:
                                        with open(script_file, 'w', encoding='utf-8') as f:
                                            f.write(new_content)
                                    return True
                                return False
                            
                            self.errors.append(ValidationError(
                                script_file,
                                "Скрипт должен определять PROJECT_ROOT для корректной работы",
                                severity="warning",
                                auto_fixable=True,
                                fix_action=fix_project_root
                            ))
            except:
                pass
        
        # Проверка что все модули используют централизованное логирование
        backend_py_files = list(self.backend_dir.rglob("*.py"))
        for py_file in backend_py_files:
            if "__pycache__" in str(py_file) or py_file.name == "logger.py":
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Проверяем использование логирования
                if "logger." in content or "logger.info" in content or "logger.error" in content:
                    # Должен быть импорт get_logger
                    if "get_logger" not in content and "from loguru import logger" in content:
                        # Уже обработано в validate_imports
                        pass
            except:
                pass
    
    def validate_documentation(self):
        """Проверка документации"""
        required_docs = [
            "README.md",
            "docs/README.md",
            "scripts/README.md",
            "docs/ARCHITECTURE.md",
        ]
        
        for doc_path in required_docs:
            full_path = self.project_root / doc_path
            if not full_path.exists():
                self.errors.append(ValidationError(
                    self.project_root,
                    f"Отсутствует документация: {doc_path}",
                    severity="warning"
                ))
    
    def analyze_dependencies(self):
        """Анализ зависимостей между модулями для выявления проблем"""
        # Анализируем циклические зависимости
        visited = set()
        rec_stack = set()
        
        def has_cycle(file_path: str) -> bool:
            visited.add(file_path)
            rec_stack.add(file_path)
            
            for dep in self.file_dependencies.get(file_path, set()):
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    # Циклическая зависимость найдена
                    return True
            
            rec_stack.remove(file_path)
            return False
        
        # Проверяем каждый файл на циклические зависимости
        for file_path in self.file_dependencies.keys():
            if file_path not in visited:
                if has_cycle(file_path):
                    self.errors.append(ValidationError(
                        Path(file_path),
                        "Обнаружена потенциальная циклическая зависимость",
                        severity="warning"
                    ))
    
    def apply_auto_fixes(self):
        """Применить автоматические исправления"""
        fixable_errors = [e for e in self.errors if e.auto_fixable and not e.fixed]
        
        if not fixable_errors:
            return
        
        print(f"\n{CYAN}🔧 Применение автоматических исправлений...{NC}\n")
        
        for error in fixable_errors:
            if error.fix_action:
                try:
                    if error.fix_action():
                        error.fixed = True
                        self.fixed_count += 1
                        print(f"  {GREEN}✓{NC} Исправлено: {error.file.name if error.file.is_file() else error.file}")
                except Exception as e:
                    print(f"  {RED}✗{NC} Ошибка исправления {error.file}: {e}")
        
        if self.fixed_count > 0:
            print(f"\n{GREEN}Исправлено проблем: {self.fixed_count}{NC}\n")
    
    def print_results(self):
        """Вывести результаты валидации"""
        print("\n" + "="*70)
        
        unfixed_errors = [e for e in self.errors if e.severity == "error" and not e.fixed]
        unfixed_warnings = [e for e in self.errors if e.severity == "warning" and not e.fixed]
        fixed_count = len([e for e in self.errors if e.fixed])
        
        errors_count = len(unfixed_errors)
        warnings_count = len(unfixed_warnings)
        
        if errors_count == 0 and warnings_count == 0 and fixed_count == 0:
            print(f"{GREEN}✅ Валидация пройдена успешно!{NC}")
            return
        
        if fixed_count > 0:
            print(f"\n{CYAN}Автоматически исправлено: {fixed_count}{NC}")
        
        if errors_count > 0 or warnings_count > 0:
            print(f"\n{RED}Найдено ошибок: {errors_count}{NC}")
            print(f"{YELLOW}Найдено предупреждений: {warnings_count}{NC}")
        
        print("\n" + "="*70)
        
        # Группируем по типу
        if unfixed_errors:
            print(f"\n{RED}❌ ОШИБКИ:{NC}\n")
            for error in unfixed_errors:
                print(f"  {error}")
        
        if unfixed_warnings:
            print(f"\n{YELLOW}⚠️  ПРЕДУПРЕЖДЕНИЯ:{NC}\n")
            for warning in unfixed_warnings:
                print(f"  {warning}")
        
        print("\n" + "="*70)
        
        # Рекомендации
        if errors_count == 0 and warnings_count > 0:
            print(f"\n{CYAN}💡 Рекомендация:{NC} Запустите с --auto-fix для автоматического исправления предупреждений")
        elif errors_count > 0:
            fixable_errors = [e for e in unfixed_errors if e.auto_fixable]
            if fixable_errors:
                print(f"\n{CYAN}💡 Рекомендация:{NC} {len(fixable_errors)} ошибок можно исправить автоматически: python3 scripts/validate_project.py --auto-fix")


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Валидатор проекта AILLM')
    parser.add_argument('--auto-fix', action='store_true', help='Автоматически исправлять проблемы')
    parser.add_argument('--dry-run', action='store_true', help='Показать что будет исправлено без реальных изменений')
    args = parser.parse_args()
    
    validator = ProjectValidator(PROJECT_ROOT, auto_fix=args.auto_fix, dry_run=args.dry_run)
    success = validator.validate()
    
    if not success:
        print(f"\n{RED}Валидация завершена с ошибками.{NC}")
        if not args.auto_fix:
            fixable = len([e for e in validator.errors if e.auto_fixable and not e.fixed])
            if fixable > 0:
                print(f"{YELLOW}Запустите с --auto-fix для автоматического исправления {fixable} проблем.{NC}")
        print(f"{YELLOW}Исправьте ошибки перед коммитом.{NC}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}Валидация пройдена успешно!{NC}")
        sys.exit(0)


if __name__ == '__main__':
    main()
