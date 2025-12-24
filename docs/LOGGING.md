# Единая система логирования

Все модули проекта используют централизованную систему логирования через `backend.core.logger`.

## Использование

### Базовое использование

```python
from ..core.logger import get_logger

logger = get_logger(__name__)

logger.info("Сообщение")
logger.debug("Отладочное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
```

### Настройка через конфигурацию

Настройки логирования управляются через секцию `logging` в конфигурации:

```yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  format: "text"  # text, json
  file: "logs/app.log"
  max_size_mb: 100
  backup_count: 5
```

### Управление через интерфейс

Настройки логирования можно изменять через интерфейс настроек. Изменения применяются динамически без перезапуска сервера.

### Структурированное логирование

Для структурированного логирования используется `structured_logger`:

```python
from backend.core.logger import structured_logger

structured_logger.log_agent_action(
    agent_name="code_writer",
    action="execute",
    task="Create function",
    context={},
    result={"success": True},
    duration=1.5
)
```

## Форматы логов

### Текстовый формат (по умолчанию)
Человекочитаемый формат с цветами в консоли.

### JSON формат
Структурированный формат для машинной обработки.

## Файлы логов

- `logs/app.log` - все логи (уровень DEBUG)
- `logs/error.log` - только ошибки (уровень ERROR)

Оба файла используют ротацию при достижении максимального размера.

