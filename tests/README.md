# Тесты AILLM

## Запуск тестов

```bash
# Все тесты
pytest

# С подробным выводом
pytest -v

# Конкретный файл
pytest tests/test_config.py

# Конкретный тест
pytest tests/test_config.py::test_load_config

# С покрытием
pytest --cov=backend --cov-report=html
```

## Структура тестов

- `test_config.py` - Тесты конфигурации
- `test_llm_providers.py` - Тесты LLM провайдеров
- `test_tools.py` - Тесты инструментов
- `test_safety_guard.py` - Тесты безопасности
- `test_agents.py` - Тесты агентов

## Маркеры

- `@pytest.mark.slow` - Медленные тесты
- `@pytest.mark.integration` - Интеграционные тесты
- `@pytest.mark.unit` - Юнит тесты

## Примеры

```bash
# Только быстрые тесты
pytest -m "not slow"

# Только юнит тесты
pytest -m unit

# Пропустить интеграционные
pytest -m "not integration"
```

