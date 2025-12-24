#!/usr/bin/env python3
"""
Скрипт для очистки проекта AILLM от мусорных файлов
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

# Определяем корень проекта (на уровень выше scripts/)
PROJECT_ROOT = Path(__file__).parent.parent

# Цвета для вывода
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'  # No Color

# Счетчики
DELETED = 0
SKIPPED = 0


def safe_delete(path: Path) -> bool:
    """Безопасное удаление файла или директории"""
    global DELETED, SKIPPED
    if path.exists():
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"{YELLOW}Удаляем:{NC} {path.relative_to(PROJECT_ROOT)}")
            DELETED += 1
            return True
        except Exception as e:
            print(f"{RED}Ошибка при удалении {path}:{NC} {e}")
            return False
    else:
        SKIPPED += 1
        return False


def find_files(pattern: str, root: Path = None, exclude_dirs: List[str] = None) -> List[Path]:
    """Найти файлы по паттерну"""
    if root is None:
        root = PROJECT_ROOT
    if exclude_dirs is None:
        exclude_dirs = ['.venv', '.git', 'node_modules']
    
    files = []
    for path in root.rglob(pattern):
        # Пропускаем исключенные директории
        if any(excluded in str(path) for excluded in exclude_dirs):
            continue
        if path.is_file():
            files.append(path)
    return files


def find_dirs(name: str, root: Path = None, exclude_dirs: List[str] = None) -> List[Path]:
    """Найти директории по имени"""
    if root is None:
        root = PROJECT_ROOT
    if exclude_dirs is None:
        exclude_dirs = ['.venv', '.git', 'node_modules']
    
    dirs = []
    for path in root.rglob(name):
        # Пропускаем исключенные директории
        if any(excluded in str(path) for excluded in exclude_dirs):
            continue
        if path.is_dir():
            dirs.append(path)
    return dirs


def delete_logs_in_dir(directory: Path, extensions: List[str] = None, preserve_files: List[str] = None) -> int:
    """Удалить все логи в директории
    
    Args:
        directory: Директория для очистки
        extensions: Список расширений файлов для удаления
        preserve_files: Список имен файлов, которые нужно сохранить
    """
    if extensions is None:
        extensions = ['.log']
    if preserve_files is None:
        preserve_files = ['README.md']
    
    if not directory.exists() or not directory.is_dir():
        return 0
    
    deleted_count = 0
    for ext in extensions:
        for log_file in directory.glob(f'*{ext}'):
            if log_file.is_file() and log_file.name not in preserve_files:
                try:
                    log_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"{RED}Ошибка при удалении {log_file}:{NC} {e}")
    
    return deleted_count


def update_gitignore():
    """Обновить .gitignore если нужно"""
    gitignore_path = PROJECT_ROOT / '.gitignore'
    if not gitignore_path.exists():
        return False
    
    try:
        content = gitignore_path.read_text()
        updated = False
        
        # Проверяем и добавляем правила для LOGS_DEBUG если нужно
        if 'LOGS_DEBUG' not in content:
            with gitignore_path.open('a') as f:
                f.write('\n# Debug logs from Intelligent Monitor\n')
                f.write('LOGS_DEBUG/*.log\n')
                f.write('LOGS_DEBUG/*.json\n')
                f.write('!LOGS_DEBUG/README.md\n')
            print(f"{YELLOW}Добавлены правила для LOGS_DEBUG в .gitignore{NC}")
            updated = True
        
        # Проверяем правила для PID файлов
        if '*.pid' not in content:
            with gitignore_path.open('a') as f:
                f.write('\n# PID files\n')
                f.write('*.pid\n')
            print(f"{YELLOW}Добавлены правила для PID файлов в .gitignore{NC}")
            updated = True
        
        return updated
    except Exception as e:
        print(f"{RED}Ошибка при обновлении .gitignore:{NC} {e}")
    
    return False


def get_dir_size(path: Path) -> str:
    """Получить размер директории"""
    try:
        result = subprocess.run(
            ['du', '-sh', str(path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.split()[0]
    except Exception:
        pass
    return "N/A"


def main():
    global DELETED, SKIPPED
    
    print("🧹 Начинаем очистку проекта AILLM...")
    print(f"📁 Корень проекта: {PROJECT_ROOT}")
    
    root = PROJECT_ROOT
    
    # 1. Удаляем __pycache__ директории (кроме .venv)
    print(f"\n{GREEN}1. Очистка Python кэша...{NC}")
    pycache_dirs = find_dirs('__pycache__', exclude_dirs=['.venv'])
    for pycache_dir in pycache_dirs:
        safe_delete(pycache_dir)
    
    # Удаляем .pyc, .pyo, .pyd файлы
    for pattern in ['*.pyc', '*.pyo', '*.pyd', '*.py[cod]', '*$py.class']:
        for file_path in find_files(pattern, exclude_dirs=['.venv']):
            safe_delete(file_path)
    
    # 2. Удаляем временные файлы Python
    print(f"\n{GREEN}2. Очистка временных файлов Python...{NC}")
    for pattern in ['*.egg-info']:
        for dir_path in find_dirs(pattern, exclude_dirs=['.venv']):
            safe_delete(dir_path)
    
    for cache_dir_name in ['.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov']:
        for cache_dir in find_dirs(cache_dir_name):
            safe_delete(cache_dir)
    
    for coverage_file in find_files('.coverage'):
        safe_delete(coverage_file)
    
    # 3. Удаляем файлы установки Python
    print(f"\n{GREEN}3. Удаление файлов установки Python...{NC}")
    python_install_files = [
        'python312.pkg',
        'python312_expanded',
        'python312_extracted',
        'INSTALL_PYTHON312.md',
        'install_python312.sh',
        'install_python312_manual.sh',
        'install_python312_pyenv.sh',
        'setup_python312.sh',
        'setup_python312_final.sh',
        'recreate_venv_312.sh'
    ]
    for file_name in python_install_files:
        safe_delete(root / file_name)
    
    # 4. Удаляем тестовые файлы змейки
    print(f"\n{GREEN}4. Удаление тестовых файлов...{NC}")
    test_files = ['test_snake_direct.py', 'test_snake_generation.py']
    for file_name in test_files:
        safe_delete(root / file_name)
    
    # 5. Удаляем OS файлы
    print(f"\n{GREEN}5. Очистка OS файлов...{NC}")
    os_files = ['.DS_Store', 'Thumbs.db']
    for os_file in os_files:
        for file_path in find_files(os_file):
            safe_delete(file_path)
    
    for pattern in ['*.swp', '*.swo', '*~']:
        for file_path in find_files(pattern):
            safe_delete(file_path)
    
    # 6. Удаление всех логов проекта
    print(f"\n{GREEN}6. Удаление всех логов проекта...{NC}")
    
    # Удаляем логи из ./logs/ (логи из централизованной системы логирования)
    logs_dir = root / 'logs'
    if logs_dir.exists():
        log_count = delete_logs_in_dir(logs_dir, ['.log'])
        if log_count > 0:
            print(f"{YELLOW}Очищена директория: ./logs (удалено файлов: {log_count}){NC}")
            DELETED += log_count
        else:
            print(f"{YELLOW}Директория ./logs пуста{NC}")
    
    # Удаляем логи из ./frontend/logs/
    frontend_logs_dir = root / 'frontend' / 'logs'
    if frontend_logs_dir.exists():
        log_count = delete_logs_in_dir(frontend_logs_dir, ['.log'])
        if log_count > 0:
            print(f"{YELLOW}Очищена директория: ./frontend/logs (удалено файлов: {log_count}){NC}")
            DELETED += log_count
        else:
            print(f"{YELLOW}Директория ./frontend/logs пуста{NC}")
    
    # Удаляем логи из ./LOGS_DEBUG/, но сохраняем README.md и monitor_state.json
    logs_debug_dir = root / 'LOGS_DEBUG'
    if logs_debug_dir.exists():
        deleted_count = 0
        for log_file in logs_debug_dir.glob('*.log'):
            if log_file.is_file() and log_file.name != 'README.md':
                try:
                    log_file.unlink()
                    deleted_count += 1
                    DELETED += 1
                except Exception as e:
                    print(f"{RED}Ошибка при удалении {log_file}:{NC} {e}")
        # Удаляем JSON файлы кроме monitor_state.json (если нужно сохранить состояние)
        for json_file in logs_debug_dir.glob('*.json'):
            if json_file.is_file() and json_file.name not in ['README.md', 'monitor_state.json']:
                try:
                    json_file.unlink()
                    deleted_count += 1
                    DELETED += 1
                except Exception as e:
                    print(f"{RED}Ошибка при удалении {json_file}:{NC} {e}")
        if deleted_count > 0:
            print(f"{YELLOW}Очищена директория: ./LOGS_DEBUG (удалено файлов: {deleted_count}){NC}")
        else:
            print(f"{YELLOW}Директория ./LOGS_DEBUG уже чиста{NC}")
    
    # Удаляем любые другие .log файлы в корне проекта (backend.log, frontend.log и т.д.)
    for log_file in root.glob('*.log'):
        if log_file.is_file() and '.venv' not in str(log_file):
            safe_delete(log_file)
    
    # 7. Удаляем PID файлы процессов
    print(f"\n{GREEN}7. Удаление PID файлов...{NC}")
    pid_files = ['backend.pid', 'frontend.pid']
    for pid_file in pid_files:
        pid_path = root / pid_file
        if pid_path.exists():
            try:
                # Проверяем, запущен ли процесс
                try:
                    with pid_path.open('r') as f:
                        pid = int(f.read().strip())
                    # Проверяем существование процесса (только на Unix системах)
                    import os
                    if hasattr(os, 'kill'):
                        os.kill(pid, 0)  # Проверка без сигнала
                        print(f"{YELLOW}⚠️  Процесс с PID {pid} еще запущен, пропускаем {pid_file}{NC}")
                        SKIPPED += 1
                        continue
                except (ValueError, OSError, ProcessLookupError):
                    # Процесс не запущен, можно удалить
                    pass
                pid_path.unlink()
                print(f"{YELLOW}Удален PID файл: {pid_file}{NC}")
                DELETED += 1
            except Exception as e:
                print(f"{RED}Ошибка при удалении {pid_file}:{NC} {e}")
    
    # 8. Удаляем резервные копии конфигурации (опционально)
    print(f"\n{GREEN}8. Проверка резервных копий конфигурации...{NC}")
    config_backup_files = []
    # Проверяем backup файлы в backend/config/
    config_backup = root / 'backend' / 'config' / 'config.yaml.bak'
    if config_backup.exists():
        config_backup_files.append(config_backup)
    # Проверяем backup файлы в config/
    config_backup2 = root / 'config' / 'config.yaml.bak'
    if config_backup2.exists():
        config_backup_files.append(config_backup2)
    
    if config_backup_files:
        print(f"{YELLOW}Найдены резервные копии конфигурации (можно удалить вручную):{NC}")
        for backup_file in config_backup_files:
            print(f"  - {backup_file.relative_to(root)}")
        # Не удаляем автоматически - пользователь может хотеть их сохранить
        # Раскомментируйте следующие строки, если хотите автоматическое удаление:
        # for backup_file in config_backup_files:
        #     safe_delete(backup_file)
    else:
        print(f"{YELLOW}Резервные копии конфигурации не найдены{NC}")
    
    # 9. Очистка кэша node_modules (если есть)
    print(f"\n{GREEN}9. Очистка кэша node_modules...{NC}")
    node_cache_dir = root / 'frontend' / 'node_modules' / '.cache'
    if node_cache_dir.exists():
        try:
            shutil.rmtree(node_cache_dir)
            print(f"{YELLOW}Очищен кэш: {node_cache_dir.relative_to(root)}{NC}")
            DELETED += 1
        except Exception as e:
            print(f"{RED}Ошибка при удалении {node_cache_dir}:{NC} {e}")
    else:
        print(f"{YELLOW}Кэш node_modules не найден{NC}")
    
    # 10. Очистка временных файлов и wrapper'ов (если есть)
    print(f"\n{GREEN}10. Проверка временных файлов...{NC}")
    # Удаляем временный wrapper для обратной совместимости (если был создан)
    loguru_wrapper = root / 'backend' / '_loguru_wrapper.py'
    if loguru_wrapper.exists():
        print(f"{YELLOW}Найден временный файл _loguru_wrapper.py (можно удалить){NC}")
        # Раскомментируйте для автоматического удаления:
        # safe_delete(loguru_wrapper)
    
    # 11. Обновляем .gitignore если нужно
    print(f"\n{GREEN}11. Проверка .gitignore...{NC}")
    update_gitignore()
    
    # 12. Показываем статистику
    print(f"\n{GREEN}✅ Очистка завершена!{NC}")
    print(f"{GREEN}Удалено файлов/директорий: {DELETED}{NC}")
    print(f"{YELLOW}Пропущено (не найдено или защищено): {SKIPPED}{NC}")
    
    # Показываем размер освобожденного места
    print(f"\n{GREEN}Размер проекта после очистки:{NC}")
    size = get_dir_size(root)
    print(size)
    
    print(f"\n{GREEN}✨ Проект очищен!{NC}")
    print(f"{YELLOW}💡 Примечание: Резервные копии конфигурации и PID файлы запущенных процессов не удалены автоматически{NC}")


if __name__ == '__main__':
    main()

