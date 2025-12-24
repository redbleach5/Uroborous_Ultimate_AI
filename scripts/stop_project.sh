#!/bin/bash
# Скрипт для корректной остановки проекта
set -euo pipefail

# Определяем корень проекта (на уровень выше scripts/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "🛑 Остановка AILLM проекта..."
echo ""

stop_process() {
    local name=$1
    local pid_file=$2
    local timeout=${3:-5}
    
    if [ ! -f "$pid_file" ]; then
        echo "⚠️  $name: PID файл не найден ($pid_file)"
        return 0
    fi
    
    local pid=$(cat "$pid_file")
    
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "⚠️  $name: процесс уже остановлен (PID: $pid)"
        rm -f "$pid_file"
        return 0
    fi
    
    echo "🔄 Остановка $name (PID: $pid)..."
    kill "$pid" 2>/dev/null || true
    
    # Ждем graceful shutdown
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt $timeout ]; do
        sleep 1
        count=$((count + 1))
    done
    
    # Force kill если процесс еще жив
    if kill -0 "$pid" 2>/dev/null; then
        echo "   ⚠️  Принудительная остановка $name..."
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi
    
    if kill -0 "$pid" 2>/dev/null; then
        echo "   ❌ Не удалось остановить $name (PID: $pid)"
        return 1
    else
        echo "   ✅ $name остановлен"
        rm -f "$pid_file"
        return 0
    fi
}

# Остановка процессов
BACKEND_OK=true
FRONTEND_OK=true

stop_process "Backend" "$PROJECT_ROOT/backend.pid" 5 || BACKEND_OK=false
echo ""
stop_process "Frontend" "$PROJECT_ROOT/frontend.pid" 3 || FRONTEND_OK=false

# Дополнительная проверка и очистка "зависших" процессов по имени
echo ""
echo "🔍 Проверка оставшихся процессов..."

# Проверка backend процессов (uvicorn)
BACKEND_REMAINING=$(pgrep -f "uvicorn.*backend.main:app" 2>/dev/null || true)
if [ -n "$BACKEND_REMAINING" ]; then
    echo "⚠️  Найдены оставшиеся backend процессы, завершаю..."
    pkill -f "uvicorn.*backend.main:app" 2>/dev/null || true
    sleep 1
fi

# Проверка frontend процессов (vite)
FRONTEND_REMAINING=$(pgrep -f "vite.*--port" 2>/dev/null || true)
if [ -n "$FRONTEND_REMAINING" ]; then
    echo "⚠️  Найдены оставшиеся frontend процессы, завершаю..."
    pkill -f "vite.*--port" 2>/dev/null || true
    sleep 1
fi

# Очистка PID файлов
rm -f "$PROJECT_ROOT/backend.pid" "$PROJECT_ROOT/frontend.pid" 2>/dev/null || true

echo ""
if [ "$BACKEND_OK" = true ] && [ "$FRONTEND_OK" = true ]; then
    echo "✅ Проект успешно остановлен"
else
    echo "⚠️  Проект остановлен с предупреждениями"
    echo "   Проверьте процессы вручную: ps aux | grep -E '(uvicorn|vite)'"
fi

