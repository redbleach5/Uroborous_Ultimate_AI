#!/usr/bin/env python3
"""
Скрипт для автоматического обновления импортов логирования во всех файлах проекта
Заменяет прямые импорты loguru на использование централизованного get_logger
"""

import re
from pathlib import Path
import sys


def get_import_path(file_path: Path, backend_dir: Path) -> str:
    """Определить правильный путь импорта относительно backend"""
    try:
        rel_path = file_path.relative_to(backend_dir)
        # Количество директорий между файлом и backend (не считая сам файл)
        # Например: tools/file_tools.py -> depth = 1 (tools)
        depth = len(rel_path.parts) - 1
        
        if depth == 0:
            # Файл находится прямо в backend/ -> from .core.logger
            return 'from .core.logger import get_logger'
        elif depth == 1:
            # Файл в поддиректории первого уровня (tools/, agents/, etc.) -> from ..core.logger
            return 'from ..core.logger import get_logger'
        else:
            # Для большей вложенности используем правильное количество точек
            dots = '..' * depth
            return f'from {dots}.core.logger import get_logger'
    except ValueError:
        # Если файл не в backend, используем абсолютный путь
        return 'from backend.core.logger import get_logger'


def update_file(file_path: Path, backend_dir: Path) -> bool:
    """Обновить один файл"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # Пропускаем файлы, которые уже используют get_logger
        if 'get_logger' in content and 'core.logger' in content:
            return False
        
        # Пропускаем сам logger.py
        if 'logger.py' in str(file_path):
            return False
        
        # Паттерн для поиска импорта loguru
        loguru_import_pattern = r'^from loguru import logger\s*$'
        
        # Если есть импорт loguru, заменяем его
        if re.search(loguru_import_pattern, content, re.MULTILINE):
            # Определяем путь импорта
            import_line = get_import_path(file_path, backend_dir)
            
            # Разбиваем на строки
            lines = content.split('\n')
            
            # Находим позицию импорта loguru и заменяем его
            new_lines = []
            replaced = False
            for line in lines:
                if re.match(loguru_import_pattern, line):
                    # Заменяем импорт
                    new_lines.append(import_line)
                    new_lines.append('logger = get_logger(__name__)')
                    replaced = True
                else:
                    new_lines.append(line)
            
            if replaced:
                content = '\n'.join(new_lines)
                file_path.write_text(content, encoding='utf-8')
                return True
        
        return False
    except Exception as e:
        print(f"Ошибка при обработке {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Главная функция"""
    # Определяем корень проекта (на уровень выше scripts/)
    project_root = Path(__file__).parent.parent
    backend_dir = project_root / 'backend'
    
    if not backend_dir.exists():
        print(f"Директория {backend_dir} не найдена", file=sys.stderr)
        sys.exit(1)
    
    # Находим все Python файлы
    python_files = list(backend_dir.rglob('*.py'))
    
    print(f"Найдено {len(python_files)} Python файлов")
    
    updated_count = 0
    for file_path in python_files:
        # Пропускаем сам файл logger.py
        if 'logger.py' in str(file_path):
            continue
        
        if update_file(file_path, backend_dir):
            rel_path = file_path.relative_to(project_root)
            print(f"✓ Обновлен: {rel_path}")
            updated_count += 1
    
    print(f"\nОбновлено файлов: {updated_count}")


if __name__ == '__main__':
    main()

