#!/bin/bash
# Скрипт для запуска проекта AILLM
# Находится в корне проекта для удобства: ./start.sh

set -e

# Переходим в директорию скрипта (корень проекта)
cd "$(dirname "$0")"

# Проверяем существование основного скрипта
if [ ! -f "./scripts/start_project.sh" ]; then
    echo "❌ Ошибка: не найден scripts/start_project.sh"
    echo "Убедитесь что вы находитесь в корне проекта"
    exit 1
fi

# Делаем скрипт исполняемым на всякий случай
chmod +x ./scripts/start_project.sh

# Запускаем основной скрипт, передавая все аргументы
exec ./scripts/start_project.sh "$@"
