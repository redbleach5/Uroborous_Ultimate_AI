# Система Обучения (Learning System)

## Обзор

Система обучения AILLM обеспечивает **персистентное накопление опыта** агентами. В отличие от обычных LLM-систем, где каждый запрос независим, AILLM запоминает результаты своих действий и использует этот опыт для улучшения последующих генераций.

## Как это работает

### 1. Запись результатов рефлексии

Каждый раз, когда агент выполняет задачу, система:
1. Проводит **рефлексию** (самоанализ качества результата)
2. Оценивает результат по критериям: полнота, корректность, качество
3. **Сохраняет результат в SQLite базу данных** (`memory/learning.db`)

```python
# Автоматически вызывается после каждого выполнения задачи
await learning_system.record_reflection(
    agent_name="code_writer",
    task="Создать REST API",
    reflection={
        "completeness": 85,
        "correctness": 90,
        "quality": 80,
        "overall_score": 85.5,
        "issues": ["Отсутствует обработка ошибок"],
        "improvements": ["Добавить try/catch"]
    },
    was_corrected=True,
    correction_attempts=2,
    execution_time=5.3
)
```

### 2. Использование накопленного опыта

При следующем выполнении задачи система:

1. **Получает инсайты** о частых проблемах агента
2. **Дополняет промпт** предупреждениями на основе истории
3. **Ищет похожие успешные решения** для переиспользования

```python
# Автоматически добавляется в промпт
prompt_enhancement = await learning_system.get_prompt_enhancement(
    agent_name="code_writer",
    task="Создать API..."
)
# Например: "ВАЖНО: Избегайте типичных проблем: отсутствует обработка ошибок"
```

### 3. Адаптивные промпты

Промпты автоматически обогащаются:
- Предупреждениями о частых ошибках
- Рекомендациями по улучшению качества
- Ссылками на успешные паттерны

## Архитектура

```
┌──────────────────┐
│    BaseAgent     │
│  (reflection)    │
└────────┬─────────┘
         │ record_reflection()
         ▼
┌──────────────────┐
│  LearningSystem  │
│   (singleton)    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  SQLite Database │
│ memory/learning.db│
└──────────────────┘
```

## База данных

### Таблицы

1. **reflection_history** - История всех рефлексий
   - agent_name, task, completeness, correctness, quality
   - overall_score, issues, improvements
   - was_corrected, correction_attempts

2. **successful_solutions** - Успешные паттерны для переиспользования
   - agent_name, task_pattern, quality_score
   - reuse_count, last_used

3. **prompt_recommendations** - Рекомендации для промптов
   - agent_name, recommendation
   - effectiveness_score

4. **error_patterns** - Частые ошибки и их решения
   - error_pattern, solution_pattern
   - occurrence_count, resolved_count

## API Endpoints

### GET /api/v1/learning/stats
Глобальная статистика обучения всех агентов.

### GET /api/v1/learning/progress
Прогресс обучения с уровнями (начальный → базовый → продвинутый → экспертный).

### GET /api/v1/learning/agent/{agent_name}
Детальная статистика конкретного агента.

### GET /api/v1/learning/recommendations/{agent_name}
Рекомендации по улучшению для агента.

## UI компонент

В sidebar отображается виджет **LearningProgress** с:
- Текущим уровнем обучения
- Success rate
- Количеством обработанных задач
- Статистикой по агентам (при раскрытии)

## Уровни обучения

| Уровень | Задач | Описание |
|---------|-------|----------|
| Начальный | < 10 | Система только начинает накапливать опыт |
| Базовый | 10-50 | Система накапливает базовые паттерны |
| Продвинутый | 50-200 | Система активно обучается на основе опыта |
| Экспертный | > 200 | Система имеет богатый опыт для оптимизации |

## Примеры использования

### Проверка статистики обучения

```bash
curl http://localhost:8000/api/v1/learning/stats
```

### Получение рекомендаций для агента

```bash
curl "http://localhost:8000/api/v1/learning/recommendations/code_writer?task=Создать%20REST%20API"
```

## Преимущества

1. **Персистентность** - опыт сохраняется между сессиями
2. **Адаптивность** - промпты улучшаются на основе истории
3. **Прозрачность** - можно видеть что система изучила
4. **Самоулучшение** - система учится избегать повторяющихся ошибок

## Конфигурация

В `config.yaml`:

```yaml
agents:
  reflection:
    enabled: true
    max_retries: 2
    min_quality_threshold: 60.0
```

Для отдельных агентов:

```yaml
agents:
  code_writer:
    reflection:
      enabled: true
      min_quality_threshold: 70.0  # Более строгий порог для кода
```

