# 🔧 План рефакторинга AILLM

> Документ создан: 2025-01-29
> Статус: В очереди на выполнение

---

## Обзор

Этот документ содержит план рефакторинга функций с высокой цикломатической сложностью (McCabe complexity > 10). Высокая сложность затрудняет тестирование, поддержку и увеличивает вероятность багов.

**Общая статистика:**
- Всего функций с высокой сложностью: **69**
- Критических (>25): **6**
- Высоких (15-25): **14**
- Средних (11-15): **49**

---

## 🔴 КРИТИЧЕСКИЙ ПРИОРИТЕТ (сложность > 25)

### 1. `ollama_provider.generate` — Сложность: 45

**Файл:** `backend/llm/ollama_provider.py:598`

**Проблема:** Функция выполняет слишком много:
- Подготовка запроса
- Обработка streaming/sync режимов
- Thinking mode логика
- Обработка ошибок и fallback
- Парсинг ответа

**План рефакторинга:**
```python
async def generate(self, messages, **kwargs) -> LLMResponse:
    """Главный метод - теперь координатор."""
    request = self._prepare_request(messages, **kwargs)
    
    if self._should_use_streaming(kwargs):
        return await self._generate_streaming(request)
    else:
        return await self._generate_sync(request)

async def _prepare_request(self, messages, **kwargs) -> OllamaRequest:
    """Подготовка и валидация запроса."""
    pass

async def _generate_streaming(self, request) -> LLMResponse:
    """Streaming генерация."""
    pass

async def _generate_sync(self, request) -> LLMResponse:
    """Синхронная генерация."""
    pass

def _process_thinking_response(self, response) -> LLMResponse:
    """Обработка thinking mode."""
    pass

def _handle_generation_error(self, error, request) -> LLMResponse:
    """Централизованная обработка ошибок."""
    pass
```

**Ожидаемая сложность после рефакторинга:** 8-10 на каждую функцию

---

### 2. `chat` endpoint — Сложность: 35

**Файл:** `backend/api/routers/chat.py:201`

**Проблема:** Endpoint обрабатывает множество режимов чата и содержит много ветвлений.

**План рефакторинга:**
```python
# Использовать паттерн Strategy для режимов чата
class ChatModeHandler(ABC):
    @abstractmethod
    async def handle(self, request: ChatRequest) -> ChatResponse:
        pass

class GeneralChatHandler(ChatModeHandler):
    async def handle(self, request):
        # Обычный чат
        pass

class CodeChatHandler(ChatModeHandler):
    async def handle(self, request):
        # Чат для кода
        pass

class AnalysisChatHandler(ChatModeHandler):
    async def handle(self, request):
        # Аналитический чат
        pass

# Router
CHAT_HANDLERS = {
    "general": GeneralChatHandler(),
    "code": CodeChatHandler(),
    "analysis": AnalysisChatHandler(),
}

@router.post("/chat")
async def chat(request: ChatRequest):
    handler = CHAT_HANDLERS.get(request.mode, CHAT_HANDLERS["general"])
    return await handler.handle(request)
```

**Ожидаемая сложность после рефакторинга:** 5-8 на каждый handler

---

### 3. `code_writer._execute_impl` — Сложность: 30

**Файл:** `backend/agents/code_writer.py:374`

**Проблема:** Метод выполняет весь pipeline генерации кода в одном месте.

**План рефакторинга:**
```python
async def _execute_impl(self, task: str, context: dict) -> dict:
    """Координатор pipeline генерации кода."""
    # 1. Анализ задачи
    analysis = await self._analyze_code_task(task, context)
    
    # 2. Генерация кода
    generated = await self._generate_code(analysis)
    
    # 3. Валидация
    validation = await self._validate_generated_code(generated)
    
    # 4. Исправление (если нужно)
    if not validation.is_valid:
        generated = await self._fix_code_issues(generated, validation)
    
    # 5. Формирование результата
    return self._format_code_result(generated, validation)

async def _analyze_code_task(self, task: str, context: dict) -> CodeAnalysis:
    """Анализ и классификация задачи."""
    pass

async def _generate_code(self, analysis: CodeAnalysis) -> GeneratedCode:
    """Генерация кода на основе анализа."""
    pass

async def _validate_generated_code(self, code: GeneratedCode) -> ValidationResult:
    """Валидация сгенерированного кода."""
    pass

async def _fix_code_issues(self, code: GeneratedCode, issues: ValidationResult) -> GeneratedCode:
    """Автоматическое исправление проблем."""
    pass
```

**Ожидаемая сложность после рефакторинга:** 6-8 на каждую функцию

---

### 4. `orchestrator.execute_task` — Сложность: 29

**Файл:** `backend/orchestrator.py:89`

**Проблема:** Центральная точка входа содержит слишком много логики.

**План рефакторинга:**
```python
async def execute_task(self, task: str, agent_type: str = None, context: dict = None) -> dict:
    """Координатор выполнения задач."""
    # 1. Подготовка
    execution_context = await self._prepare_execution(task, agent_type, context)
    
    # 2. Маршрутизация
    if execution_context.needs_decomposition:
        return await self._execute_complex_task(execution_context)
    else:
        return await self._execute_simple_task(execution_context)

async def _prepare_execution(self, task, agent_type, context) -> ExecutionContext:
    """Подготовка контекста выполнения."""
    # Анализ сложности, выбор стратегии, получение контекста из RAG
    pass

async def _execute_simple_task(self, ctx: ExecutionContext) -> dict:
    """Выполнение простой задачи одним агентом."""
    pass

async def _execute_complex_task(self, ctx: ExecutionContext) -> dict:
    """Декомпозиция и выполнение сложной задачи."""
    pass
```

---

### 5. `engine.initialize` — Сложность: 28

**Файл:** `backend/core/engine.py:81`

**Проблема:** Инициализация всех компонентов в одном методе.

**План рефакторинга:**
```python
async def initialize(self):
    """Координатор инициализации."""
    await self._initialize_logging()
    await self._initialize_llm_providers()
    await self._initialize_memory()
    await self._initialize_rag()
    await self._initialize_agents()
    await self._initialize_tools()
    await self._start_background_tasks()

async def _initialize_llm_providers(self):
    """Инициализация LLM провайдеров."""
    pass

async def _initialize_memory(self):
    """Инициализация системы памяти."""
    pass

# ... и так далее для каждого компонента
```

---

### 6. `smart_analyzer._profile_project` — Сложность: 28

**Файл:** `backend/api/project/smart_analyzer.py:154`

**Проблема:** Профилирование проекта включает множество проверок.

**План рефакторинга:**
```python
async def _profile_project(self, path: Path) -> ProjectProfile:
    """Координатор профилирования."""
    profile = ProjectProfile(path=path)
    
    # Параллельное профилирование
    await asyncio.gather(
        self._profile_languages(profile),
        self._profile_frameworks(profile),
        self._profile_structure(profile),
        self._profile_dependencies(profile),
        self._profile_git_info(profile),
    )
    
    return profile
```

---

## 🟠 ВЫСОКИЙ ПРИОРИТЕТ (сложность 15-25)

| # | Сложность | Функция | Файл | Рекомендация |
|---|-----------|---------|------|--------------|
| 7 | 22 | `_get_llm_response` | `agents/base.py:518` | Разделить на prepare/execute/parse |
| 8 | 22 | `execute_task` | `api/routers/tasks.py:28` | Strategy pattern для типов задач |
| 9 | 22 | `update_configuration` | `core/engine.py:235` | Разделить по компонентам |
| 10 | 20 | `update_config` | `api/routers/config.py:126` | Выделить валидацию и применение |
| 11 | 19 | `_execute_impl` | `agents/data_analysis.py:128` | Pipeline pattern |
| 12 | 19 | `_execute_subtasks` | `orchestrator.py:679` | Разделить parallel/sequential |
| 13 | 18 | `_execute_impl` | `agents/research.py:22` | Pipeline pattern |
| 14 | 18 | `process_batch` | `core/batch_processor.py:190` | Разделить на фазы |
| 15 | 18 | `_select_default_model` | `llm/ollama_provider.py:220` | Chain of responsibility |
| 16 | 18 | `get_personalization_prompt` | `memory/long_term.py:740` | Builder pattern |
| 17 | 17 | `_execute_code_safely` | `agents/workflow.py:222` | Sandbox isolation |
| 18 | 17 | `websocket_endpoint` | `main.py:158` | Message handler factory |
| 19 | 17 | `_decompose_task_llm` | `orchestrator.py:429` | Выделить parsing |
| 20 | 16 | `get_available_models` | `api/routers/models.py:284` | Cache + parallel fetch |

---

## 🟡 СРЕДНИЙ ПРИОРИТЕТ (сложность 11-15)

<details>
<summary>Показать все 49 функций</summary>

| Сложность | Функция | Файл |
|-----------|---------|------|
| 15 | `_gather_context` | `api/project/smart_analyzer.py:319` |
| 15 | `get_context` | `rag/context_manager.py:70` |
| 15 | `search` | `rag/vector_store.py:267` |
| 15 | `execute_with_reflection` | `agents/reflection_mixin.py:465` |
| 14 | `validate_javascript_syntax` | `agents/code_writer.py:52` |
| 14 | `_validate_and_fix_code` | `agents/code_writer.py:214` |
| 14 | `_select_from_tier` | `core/smart_model_selector.py:273` |
| 14 | `_select_agent` | `orchestrator.py:574` |
| 13 | `process_multimodal_input` | `agents/multimodal_mixin.py:54` |
| 13 | `select_model` | `core/intelligent_model_router.py:395` |
| 13 | `_fallback_classification` | `core/llm_classifier.py:266` |
| 13 | `select_model_for_complexity` | `llm/ollama_provider.py:261` |
| 13 | `stream` | `llm/ollama_provider.py:968` |
| 13 | `add_documents` | `rag/vector_store.py:166` |
| 13 | `index_project` | `project/indexer.py:85` |
| 13 | `_check_brackets` | `core/code_validator.py:341` |
| 13 | `_detect_language` | `core/code_validator.py:648` |
| 12 | `_parse_reflection_response` | `agents/reflection_mixin.py:294` |
| 12 | `_validate_workflow` | `agents/workflow.py:137` |
| 12 | `_get_ollama_url` | `core/complexity_analyzer.py:237` |
| 12 | `_infer_capabilities` | `core/intelligent_model_router.py:91` |
| 12 | `shutdown` | `core/engine.py:371` |
| 12 | `_periodic_status_update` | `core/engine.py:505` |
| 12 | `recommend_model` | `api/routers/models.py:441` |
| 12 | `browse_directory` | `api/routers/project.py:156` |
| 12 | `_structure_preserving_summarize` | `rag/context_summarizer.py:285` |
| 12 | `search_similar_failed_tasks` | `memory/long_term.py:850` |
| 12 | `_rerank_results` | `rag/semantic_code_search.py:376` |
| 12 | `_get_powerful_model` | `core/two_stage_processor.py:145` |
| 11 | `execute` | `agents/base.py:108` |
| 11 | `get_config` | `api/routers/config.py:17` |
| 11 | `_get_model_info` | `api/routers/models.py:214` |
| 11 | `proxy_preview_ws` | `api/routers/preview.py:129` |
| 11 | `_format_context` | `api/project/smart_analyzer.py:667` |
| 11 | `auto_train` | `automl/automl_engine.py:161` |
| 11 | `_validate_python` | `core/code_validator.py:200` |
| 11 | `_estimate_resources_from_models` | `core/complexity_analyzer.py:428` |
| 11 | `from_task_analysis` | `core/intelligent_model_router.py:149` |
| 11 | `get_learning_insights` | `core/model_performance_tracker.py:522` |
| 11 | `discover_resources` | `core/resource_aware_selector.py:117` |
| 11 | `_determine_resource_level` | `core/resource_aware_selector.py:201` |
| 11 | `_get_fast_model` | `core/two_stage_processor.py:106` |
| 11 | `generate` | `llm/anthropic_provider.py:44` |
| 11 | `stream` | `llm/anthropic_provider.py:194` |
| 11 | `_parse_ndjson_response` | `llm/ollama_provider.py:466` |
| 11 | `generate` | `llm/providers.py:135` |
| 11 | `initialize` | `llm/providers.py:35` |
| 11 | `initialize` | `tools/registry.py:35` |

</details>

---

## Общие паттерны для рефакторинга

### 1. Pipeline Pattern
Для функций, выполняющих последовательные операции:
```python
async def process(self, input):
    result = input
    for step in self.pipeline:
        result = await step.execute(result)
    return result
```

### 2. Strategy Pattern
Для функций с множеством ветвлений по типу:
```python
handlers = {
    "type_a": HandlerA(),
    "type_b": HandlerB(),
}
handler = handlers.get(type, DefaultHandler())
return handler.handle(data)
```

### 3. Chain of Responsibility
Для функций с fallback логикой:
```python
class Handler:
    def __init__(self, next_handler=None):
        self.next = next_handler
    
    def handle(self, request):
        if self.can_handle(request):
            return self.do_handle(request)
        elif self.next:
            return self.next.handle(request)
```

### 4. Extract Method
Для монолитных функций - выделять логические блоки:
```python
# Было:
def big_function():
    # 100 строк кода
    
# Стало:
def big_function():
    self._step1()
    self._step2()
    self._step3()
```

---

## Метрики успеха

После рефакторинга каждой функции:
- [ ] Сложность < 10
- [ ] Покрытие тестами > 80%
- [ ] Документация обновлена
- [ ] Производительность не ухудшилась

---

## Приоритет выполнения

1. **Неделя 1:** `ollama_provider.generate` (критично для LLM)
2. **Неделя 2:** `orchestrator.execute_task` + `engine.initialize`
3. **Неделя 3:** `chat` endpoint + `code_writer._execute_impl`
4. **Неделя 4:** Высокий приоритет (7-20)
5. **Далее:** Средний приоритет по мере возможности

---

*Документ будет обновляться по мере выполнения рефакторинга.*

