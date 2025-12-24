# Thinking Mode в Ollama: Нативная поддержка vs Эмуляция

## Обзор

Ollama провайдер поддерживает thinking mode двумя способами в зависимости от возможностей модели:

1. **Нативная поддержка** - для моделей с встроенной поддержкой thinking mode
2. **Эмуляция** - для моделей без нативной поддержки через оптимизированные промпты

## Нативная поддержка thinking mode

### Поддерживаемые модели

Следующие модели имеют встроенную поддержку thinking mode:

- **Llama 3.3** и новее (`llama3.3`, `llama3.3:70b`)
- **Qwen 2.5** (`qwen2.5`, `qwen2.5:72b`)
- **DeepSeek** модели (`deepseek`, `deepseek-coder`)

### Как это работает

1. **Автоматическое определение**: Система проверяет имя модели и определяет поддержку нативного thinking mode
2. **API параметры**: Для поддерживающих моделей добавляется параметр `thinking` в запрос:
   ```json
   {
     "model": "llama3.3",
     "messages": [...],
     "thinking": {
       "enabled": true,
       "budget_tokens": 4096
     }
   }
   ```
3. **Извлечение thinking**: Thinking traces извлекаются из структурированного ответа API
4. **Минимальные инструкции**: Используются минимальные промпт-инструкции, так как модель сама поддерживает thinking

### Преимущества нативной поддержки

- ✅ Более точное и структурированное reasoning
- ✅ Меньше токенов на промпты (экономия ресурсов)
- ✅ Лучшая производительность
- ✅ Надежное извлечение thinking traces

## Эмуляция thinking mode

### Когда используется

Эмуляция используется для моделей, которые **не имеют** встроенной поддержки thinking mode:
- Llama 2.x
- Mistral (базовые версии)
- CodeLlama (старые версии)
- Другие модели без нативной поддержки

### Как это работает

1. **Расширенные промпты**: Система добавляет детальные инструкции для глубокого мышления в системный промпт
2. **Step-by-step reasoning**: Модель инструктируется думать через:
   - Анализ проблемы
   - Рассмотрение факторов
   - Оценку подходов
   - Выбор решения
3. **Извлечение thinking**: Thinking traces извлекаются из текста ответа по маркерам:
   - "Let me think", "Thinking:", "Reasoning:"
   - "Думаю:", "Рассуждение:", "Анализ:"
   - XML теги `<think>...</think>` (если модель их использует)

### Преимущества эмуляции

- ✅ Работает со всеми моделями Ollama
- ✅ Улучшает качество reasoning даже для моделей без нативной поддержки
- ✅ Обратная совместимость

### Ограничения эмуляции

- ⚠️ Менее структурированное reasoning (зависит от модели)
- ⚠️ Больше токенов на промпты
- ⚠️ Извлечение thinking менее надежно (зависит от формата ответа модели)

## Автоматическое определение

Система автоматически определяет, какую реализацию использовать:

```python
def _check_thinking_support(self, model_name: str) -> bool:
    """Проверяет поддержку нативного thinking mode"""
    thinking_models = [
        "llama3.3", "llama3.2", "qwen2.5", "deepseek"
    ]
    return any(model in model_name.lower() for model in thinking_models)
```

### Логика выбора

1. Проверяется имя модели
2. Если модель поддерживает нативный thinking → используется нативная реализация
3. Иначе → используется эмуляция

## Использование

### Включение thinking mode

```python
# Автоматический выбор (нативная или эмуляция)
response = await ollama_provider.generate(
    messages=messages,
    model="llama3.3",  # Нативная поддержка
    thinking_mode=True
)

# Для модели без нативной поддержки (автоматически использует эмуляцию)
response = await ollama_provider.generate(
    messages=messages,
    model="llama2",  # Эмуляция
    thinking_mode=True
)
```

### Проверка типа thinking mode

```python
response = await provider.generate(...)

if response.metadata.get("thinking_native"):
    print("Использован нативный thinking mode")
elif response.metadata.get("thinking_emulated"):
    print("Использована эмуляция thinking mode")
```

## Конфигурация

### Рекомендуемые модели для thinking mode

```yaml
llm:
  providers:
    ollama:
      recommended_models:
        reasoning:  # Модели с нативной поддержкой thinking
          - "llama3.3"
          - "qwen2.5:72b"
          - "deepseek-coder"
        code:  # Модели с эмуляцией thinking
          - "codellama"
          - "mistral"
```

## Метрики и логирование

Система логирует тип используемого thinking mode:

```
DEBUG: Model llama3.3 supports native thinking mode
DEBUG: Using native thinking mode for Ollama model llama3.3

DEBUG: Model llama2 does not support native thinking, using emulation
DEBUG: Using emulated thinking mode for Ollama model llama2
```

## Будущие улучшения

1. **Расширение списка поддерживающих моделей** по мере обновления Ollama
2. **Улучшение извлечения thinking** для эмуляции
3. **Метрики качества** reasoning для разных моделей
4. **Автоматическая оптимизация** промптов для эмуляции

## Рекомендации

1. **Используйте модели с нативной поддержкой** для лучшего качества reasoning:
   - `llama3.3` для общего использования
   - `qwen2.5:72b` для сложных задач
   - `deepseek-coder` для генерации кода

2. **Для моделей без нативной поддержки**:
   - Эмуляция все равно улучшает качество reasoning
   - Используйте более детальные промпты для лучших результатов

3. **Мониторинг**:
   - Проверяйте логи для определения типа thinking mode
   - Сравнивайте качество reasoning между нативной поддержкой и эмуляцией

