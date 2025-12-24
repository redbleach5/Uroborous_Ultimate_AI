#!/bin/bash
# Универсальный запуск backend + frontend с автоподбором портов, проверками и логами
set -euo pipefail

# Определяем корень проекта (на уровень выше scripts/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

BACKEND_HOST=${BACKEND_HOST:-localhost}
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_HOST=${FRONTEND_HOST:-localhost}
FRONTEND_PORT=${FRONTEND_PORT:-1420}
VENV_PATH=${VENV_PATH:-.venv}
BACKEND_LOG=${BACKEND_LOG:-backend.log}
FRONTEND_LOG=${FRONTEND_LOG:-frontend.log}

ORIG_BACKEND_PORT=$BACKEND_PORT
ORIG_FRONTEND_PORT=$FRONTEND_PORT

find_free_port() {
  local start=$1
  local attempts=${2:-50}
  local port=$start
  for _ in $(seq 0 "$attempts"); do
    if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

echo "=========================================="
echo "🚀 Запуск AILLM проекта"
echo "=========================================="

declare BACKEND_PID FRONTEND_PID

cleanup() {
  echo ""
  echo "⚠️  Обнаружено прерывание, останавливаю процессы..."
  if [ -f "$PROJECT_ROOT/backend.pid" ]; then
    BACKEND_PID_TO_KILL=$(cat "$PROJECT_ROOT/backend.pid" 2>/dev/null || true)
    if [ -n "$BACKEND_PID_TO_KILL" ] && kill -0 "$BACKEND_PID_TO_KILL" 2>/dev/null; then
      kill "$BACKEND_PID_TO_KILL" 2>/dev/null || true
      sleep 1
      kill -9 "$BACKEND_PID_TO_KILL" 2>/dev/null || true
    fi
    rm -f "$PROJECT_ROOT/backend.pid"
  fi
  if [ -f "$PROJECT_ROOT/frontend.pid" ]; then
    FRONTEND_PID_TO_KILL=$(cat "$PROJECT_ROOT/frontend.pid" 2>/dev/null || true)
    if [ -n "$FRONTEND_PID_TO_KILL" ] && kill -0 "$FRONTEND_PID_TO_KILL" 2>/dev/null; then
      kill "$FRONTEND_PID_TO_KILL" 2>/dev/null || true
      sleep 1
      kill -9 "$FRONTEND_PID_TO_KILL" 2>/dev/null || true
    fi
    rm -f "$PROJECT_ROOT/frontend.pid"
  fi
  # Дополнительная очистка по имени процесса
  pkill -f "uvicorn.*backend.main:app" 2>/dev/null || true
  pkill -f "vite.*--port" 2>/dev/null || true
}
trap cleanup INT TERM

# Проверка виртуального окружения
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Виртуальное окружение не найдено в $VENV_PATH"
    echo "💡 Создайте его: python3 -m venv $VENV_PATH"
    exit 1
fi

# Активировать виртуальное окружение
source "$VENV_PATH/bin/activate"
echo "✅ Виртуальное окружение активировано ($VENV_PATH)"

# Проверка зависимостей backend (минимум fastapi)
echo ""
echo "📦 Проверка зависимостей backend..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  Зависимости не установлены. Устанавливаю..."
    pip install -r requirements.txt
fi

# Автоподбор портов
NEW_BACKEND_PORT=$(find_free_port "$BACKEND_PORT" 50) || { echo "❌ Не удалось подобрать свободный порт для backend"; exit 1; }
if [ "$NEW_BACKEND_PORT" != "$ORIG_BACKEND_PORT" ]; then
  echo "⚠️  Порт $ORIG_BACKEND_PORT занят, использую backend порт $NEW_BACKEND_PORT"
fi
BACKEND_PORT=$NEW_BACKEND_PORT

NEW_FRONTEND_PORT=$(find_free_port "$FRONTEND_PORT" 50) || { echo "❌ Не удалось подобрать свободный порт для frontend"; exit 1; }
if [ "$NEW_FRONTEND_PORT" != "$ORIG_FRONTEND_PORT" ]; then
  echo "⚠️  Порт $ORIG_FRONTEND_PORT занят, использую frontend порт $NEW_FRONTEND_PORT"
fi
FRONTEND_PORT=$NEW_FRONTEND_PORT

BACKEND_HEALTH="http://${BACKEND_HOST}:${BACKEND_PORT}/health"

# Запуск backend
echo ""
echo "🔧 Запуск backend сервера (порт ${BACKEND_PORT})..."
# Используем uvicorn для запуска FastAPI приложения
uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
echo "   Логи: $BACKEND_LOG"

# Ждать запуска backend
echo ""
echo "⏳ Ожидание запуска backend (${BACKEND_HEALTH})..."
for i in {1..40}; do
    if curl -s "$BACKEND_HEALTH" > /dev/null 2>&1; then
        echo "✅ Backend запущен на http://${BACKEND_HOST}:${BACKEND_PORT}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Проверка Node.js версии (предупреждение, не блокирует)
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    NODE_MINOR=$(echo "$NODE_VERSION" | cut -d. -f2)
    if [ "$NODE_MAJOR" -lt 20 ] || ([ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -lt 12 ]); then
        echo ""
        echo "⚠️  Предупреждение: Node.js версия $NODE_VERSION"
        echo "   Рекомендуется Node.js 20.19+ или 22.12+ для Vite"
        echo "   Продолжаю запуск..."
    fi
fi

# Проверка frontend зависимостей
if [ ! -d "frontend/node_modules" ]; then
    echo ""
    echo "📦 Установка зависимостей frontend..."
    (cd frontend && npm install)
fi

# Запуск frontend (Vite dev) на заданном порту
echo ""
echo "🎨 Запуск frontend (порт ${FRONTEND_PORT})..."
# Vite автоматически использует порт из vite.config.ts, но мы переопределяем через --port
(cd frontend && npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT") > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
echo "   Логи: $FRONTEND_LOG"

# Ждать запуска frontend
echo ""
echo "⏳ Ожидание запуска frontend..."
for i in {1..20}; do
  if curl -s "http://${FRONTEND_HOST}:${FRONTEND_PORT}" > /dev/null 2>&1; then
    echo "✅ Frontend запущен на http://${FRONTEND_HOST}:${FRONTEND_PORT}"
    break
  fi
  sleep 1
  echo -n "."
done
echo ""

# Сохранить PIDs
echo "$BACKEND_PID" > "$PROJECT_ROOT/backend.pid"
echo "$FRONTEND_PID" > "$PROJECT_ROOT/frontend.pid"

# Финальная проверка процессов
echo ""
echo "🔍 Проверка статуса процессов..."
BACKEND_RUNNING=false
FRONTEND_RUNNING=false

if kill -0 "$BACKEND_PID" 2>/dev/null; then
    BACKEND_RUNNING=true
    echo "   ✅ Backend процесс активен (PID: $BACKEND_PID)"
else
    echo "   ❌ Backend процесс не найден"
fi

if kill -0 "$FRONTEND_PID" 2>/dev/null; then
    FRONTEND_RUNNING=true
    echo "   ✅ Frontend процесс активен (PID: $FRONTEND_PID)"
else
    echo "   ❌ Frontend процесс не найден"
fi

echo ""
echo "=========================================="
if [ "$BACKEND_RUNNING" = true ] && [ "$FRONTEND_RUNNING" = true ]; then
    echo "✅ Проект успешно запущен!"
else
    echo "⚠️  Проект запущен с предупреждениями"
fi
echo "=========================================="
echo ""
echo "📍 Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "📍 Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "📍 API Docs: http://${BACKEND_HOST}:${BACKEND_PORT}/docs"
echo ""
echo "📋 Логи:"
echo "   Backend:  tail -f $BACKEND_LOG"
echo "   Frontend: tail -f $FRONTEND_LOG"
echo ""
echo "💡 Для остановки выполните: ./stop.sh или ./scripts/stop_project.sh"
echo "   или: kill \$(cat backend.pid); kill \$(cat frontend.pid)"
echo ""

