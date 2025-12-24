#!/bin/bash
# Скрипт для установки git hooks

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
PRE_COMMIT_HOOK="$HOOKS_DIR/pre-commit"

echo "🔧 Установка git hooks..."

# Проверяем что мы в git репозитории
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "❌ Ошибка: не найден .git директория. Убедитесь что это git репозиторий."
    exit 1
fi

# Создаем директорию hooks если её нет
mkdir -p "$HOOKS_DIR"

# Копируем pre-commit hook
if [ -f "$PROJECT_ROOT/.git/hooks/pre-commit" ]; then
    # Сохраняем существующий hook если есть
    if ! grep -q "validate_project.py" "$PRE_COMMIT_HOOK" 2>/dev/null; then
        echo "⚠️  Существующий pre-commit hook найден. Создаю резервную копию..."
        cp "$PRE_COMMIT_HOOK" "$PRE_COMMIT_HOOK.backup"
    fi
fi

# Создаем новый pre-commit hook
cat > "$PRE_COMMIT_HOOK" << 'EOF'
#!/bin/bash
# Pre-commit hook для автоматической валидации проекта

# Определяем корень проекта
PROJECT_ROOT="$(git rev-parse --show-toplevel)"

# Переходим в корень проекта
cd "$PROJECT_ROOT"

echo "🔍 Запуск pre-commit проверок..."

# Запускаем валидатор проекта (без auto-fix в hook для безопасности)
python3 scripts/validate_project.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Pre-commit проверки не пройдены!"
    echo "Исправьте ошибки перед коммитом."
    exit 1
fi

# Проверка синтаксиса Python файлов в staged изменениях
echo ""
echo "🔍 Проверка синтаксиса измененных Python файлов..."

STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

if [ -n "$STAGED_PY_FILES" ]; then
    python3 scripts/check_syntax.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Обнаружены синтаксические ошибки в Python файлах!"
        exit 1
    fi
fi

echo ""
echo "✅ Все проверки пройдены успешно!"
exit 0
EOF

# Делаем hook исполняемым
chmod +x "$PRE_COMMIT_HOOK"

echo "✅ Git hooks успешно установлены!"
echo ""
echo "Теперь при каждом коммите будут автоматически выполняться:"
echo "  - Валидация проекта (структура, импорты, конфигурация)"
echo "  - Проверка синтаксиса Python файлов"
echo ""
echo "Для пропуска проверок (не рекомендуется): git commit --no-verify"

