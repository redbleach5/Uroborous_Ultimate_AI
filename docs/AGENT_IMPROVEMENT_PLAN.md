# 🧠 План улучшения системы агентов AILLM

## ✅ Реализовано

### 1. ReflectionMixin - Самокоррекция агентов

**Файл:** `backend/agents/reflection_mixin.py`

Добавляет агентам способность анализировать свои результаты и автоматически исправлять ошибки:

```python
# Использование (автоматически для всех агентов, наследующих BaseAgent)
result = await agent.execute(task, context)
# result теперь содержит:
# - _reflection: оценка качества (completeness, correctness, quality)
# - _reflection_attempts: количество попыток
# - _corrected: True если результат был исправлен

# Настройка рефлексии
agent.configure_reflection(
    enabled=True,
    max_retries=2,
    min_quality_threshold=70.0  # 0-100
)

# Отключение рефлексии для конкретного вызова
result = await agent.execute(task, {"_skip_reflection": True})
```

### 2. AgentCommunicator - Межагентное взаимодействие

**Файл:** `backend/agents/communicator.py`

Позволяет агентам делегировать задачи друг другу:

```python
# Делегирование задачи другому агенту
result = await agent.delegate_to(
    agent_type="research",
    subtask="Найди документацию по FastAPI",
    context={"project": "my_api"}
)

# Запрос помощи по возможности
result = await agent.request_help(
    capability="code_generation",  # или data_analysis, web_search и т.д.
    task="Напиши функцию валидации",
    context={}
)

# Широковещательное сообщение всем агентам
result = await agent.broadcast_message({
    "event": "project_updated",
    "data": {"files": ["main.py"]}
})
```

### Конфигурация

В `config.yaml`:
```yaml
agents:
  reflection:
    enabled: true
    max_retries: 2
    min_quality_threshold: 60.0
  
  code_writer:
    # ... 
    reflection:
      enabled: true
      max_retries: 2
      min_quality_threshold: 70.0  # Выше для кода
```

---

## 📊 Текущее состояние

### Существующие агенты (7 штук):
1. **CodeWriterAgent** - генерация и рефакторинг кода
2. **DataAnalysisAgent** - анализ данных и ML
3. **ResearchAgent** - исследования и поиск информации
4. **ReactAgent** - интерактивное решение задач (ReAct)
5. **WorkflowAgent** - управление рабочими процессами
6. **IntegrationAgent** - интеграция с внешними сервисами
7. **MonitoringAgent** - мониторинг и метрики

### Оценка эффективности:
- ✅ Модульная архитектура
- ✅ Поддержка мультимодальности
- ✅ Интеграция с памятью
- ✅ Thinking mode для сложных задач
- ❌ Нет межагентного взаимодействия
- ❌ Нет самокоррекции
- ❌ Нет верификации результатов
- ❌ Слабое использование feedback

---

## 🎯 Фаза 1: Критические улучшения базовой инфраструктуры

### 1.1 Механизм межагентной коммуникации

**Проблема:** Агенты работают изолированно, не могут делегировать задачи.

**Решение:** Добавить AgentCommunicator в BaseAgent

```python
# backend/agents/communicator.py
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum

class MessageType(Enum):
    REQUEST = "request"        # Запрос на выполнение задачи
    RESPONSE = "response"      # Ответ на запрос
    DELEGATION = "delegation"  # Делегирование подзадачи
    FEEDBACK = "feedback"      # Обратная связь о результате
    STATUS = "status"          # Статус выполнения

@dataclass
class AgentMessage:
    sender: str                    # Имя отправителя
    receiver: str                  # Имя получателя  
    message_type: MessageType
    content: Dict[str, Any]
    priority: int = 5              # 1-10, где 10 - наивысший
    context: Optional[Dict[str, Any]] = None
    parent_task_id: Optional[str] = None

class AgentCommunicator:
    """Система коммуникации между агентами"""
    
    def __init__(self, agent_registry):
        self.agent_registry = agent_registry
        self.message_queue: List[AgentMessage] = []
        self.pending_responses: Dict[str, asyncio.Future] = {}
    
    async def send_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """Отправить сообщение другому агенту"""
        pass
    
    async def delegate_subtask(
        self,
        from_agent: str,
        to_agent: str,
        subtask: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Делегировать подзадачу другому агенту"""
        pass
    
    async def request_help(
        self,
        from_agent: str,
        task: str,
        required_capability: str
    ) -> Optional[str]:
        """Запросить помощь у агента с нужной способностью"""
        pass
```

### 1.2 Система рефлексии и самокоррекции

**Проблема:** Агенты не анализируют свои результаты.

**Решение:** ReflectionMixin для всех агентов

```python
# backend/agents/reflection_mixin.py
class ReflectionMixin:
    """Миксин для добавления способности к рефлексии"""
    
    async def reflect_on_result(
        self,
        task: str,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Анализирует результат и определяет качество.
        Возвращает оценку и рекомендации по улучшению.
        """
        reflection_prompt = f"""
        Проанализируй результат выполнения задачи:
        
        Задача: {task}
        Результат: {result}
        
        Оцени:
        1. Полнота решения (0-100%)
        2. Корректность (0-100%)
        3. Качество кода/текста (0-100%)
        4. Потенциальные проблемы
        5. Рекомендации по улучшению
        
        JSON ответ:
        {{
            "completeness": 85,
            "correctness": 90,
            "quality": 80,
            "issues": ["issue1", "issue2"],
            "improvements": ["improvement1"],
            "should_retry": false,
            "retry_suggestion": null
        }}
        """
        # Используем быструю модель для рефлексии
        response = await self._get_llm_response([
            LLMMessage(role="system", content="Ты - критик и аналитик качества."),
            LLMMessage(role="user", content=reflection_prompt)
        ], max_tokens=500)
        
        return self._parse_reflection(response)
    
    async def self_correct(
        self,
        task: str,
        original_result: Dict[str, Any],
        reflection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Исправляет результат на основе рефлексии"""
        if not reflection.get("should_retry"):
            return original_result
        
        # Формируем промпт для исправления
        correction_prompt = f"""
        Исходная задача: {task}
        
        Предыдущий результат имел проблемы:
        {reflection.get('issues', [])}
        
        Рекомендации:
        {reflection.get('improvements', [])}
        
        {reflection.get('retry_suggestion', '')}
        
        Создай улучшенное решение, исправив указанные проблемы.
        """
        
        return await self._execute_impl(correction_prompt, {
            "previous_result": original_result,
            "reflection": reflection
        })
```

### 1.3 Улучшенный BaseAgent с рефлексией

```python
# Изменения в backend/agents/base.py
class BaseAgent(ABC, ReflectionMixin):
    """Base class for all agents with reflection capabilities"""
    
    def __init__(self, ...):
        # ... существующий код ...
        self.communicator: Optional[AgentCommunicator] = None
        self.reflection_enabled = config.get("reflection_enabled", True)
        self.max_retries = config.get("max_retries", 2)
    
    async def execute(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute with reflection and self-correction loop"""
        result = await self._execute_impl(task, context or {})
        
        if self.reflection_enabled:
            for retry in range(self.max_retries):
                reflection = await self.reflect_on_result(task, result, context)
                
                if reflection.get("should_retry") and retry < self.max_retries - 1:
                    logger.info(f"Agent {self.name} retrying task (attempt {retry + 2})")
                    result = await self.self_correct(task, result, reflection)
                else:
                    result["reflection"] = reflection
                    break
        
        return result
    
    async def delegate_to(
        self,
        agent_type: str,
        subtask: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Делегировать подзадачу другому агенту"""
        if self.communicator:
            return await self.communicator.delegate_subtask(
                from_agent=self.name,
                to_agent=agent_type,
                subtask=subtask,
                context=context
            )
        raise AgentException("Communicator not available for delegation")
```

---

## 🎯 Фаза 2: Новые специализированные агенты

### 2.1 PlannerAgent - Агент планирования проектов

```python
# backend/agents/planner.py
class PlannerAgent(BaseAgent):
    """
    Агент для планирования сложных проектов.
    
    Возможности:
    - Декомпозиция на подзадачи с зависимостями
    - Создание roadmap проекта
    - Оценка времени и ресурсов
    - Выбор агентов для каждой подзадачи
    """
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Создает детальный план проекта"""
        
        system_prompt = """Ты - эксперт по планированию проектов с глубоким аналитическим мышлением.

Твоя задача - создать детальный план проекта:
1. Декомпозируй проект на логические фазы
2. Определи зависимости между задачами
3. Оцени сложность и время каждой задачи
4. Выбери оптимального агента для каждой задачи
5. Идентифицируй риски и предложи митигации

Доступные агенты:
- code_writer: генерация кода, рефакторинг
- research: исследование, поиск информации  
- data_analysis: анализ данных, ML
- react: сложные задачи с рассуждением
- workflow: автоматизация процессов
- integration: интеграция с API/сервисами
- monitoring: мониторинг и метрики
- tester: тестирование кода (новый)
- verifier: верификация результатов (новый)

Формат ответа:
{
    "project_name": "название",
    "phases": [
        {
            "name": "Фаза 1",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "описание",
                    "agent": "code_writer",
                    "dependencies": [],
                    "estimated_hours": 2,
                    "priority": "high",
                    "deliverables": ["файл1.py", "файл2.py"]
                }
            ]
        }
    ],
    "total_estimated_hours": 10,
    "risks": [{"risk": "описание", "mitigation": "решение"}],
    "success_criteria": ["критерий1", "критерий2"]
}"""

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=f"Создай детальный план для проекта:\n{task}")
        ]
        
        response = await self._get_llm_response(messages, use_thinking=True)
        plan = self._parse_plan(response)
        
        return {
            "agent": self.name,
            "task": task,
            "plan": plan,
            "success": True
        }
    
    async def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет план, координируя другие агенты"""
        results = []
        
        for phase in plan.get("phases", []):
            phase_results = await self._execute_phase(phase)
            results.append(phase_results)
            
            # Проверяем успешность фазы
            if not all(r.get("success") for r in phase_results):
                return {
                    "success": False,
                    "error": f"Phase {phase['name']} failed",
                    "results": results
                }
        
        return {
            "success": True,
            "results": results,
            "deliverables": self._collect_deliverables(results)
        }
```

### 2.2 TesterAgent - Агент тестирования

```python
# backend/agents/tester.py
class TesterAgent(BaseAgent):
    """
    Агент для тестирования и верификации кода.
    
    Возможности:
    - Генерация unit-тестов
    - Запуск тестов
    - Анализ покрытия
    - Выявление edge cases
    """
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        code = context.get("code", "")
        language = context.get("language", "python")
        
        # Генерируем тесты
        tests = await self._generate_tests(code, language)
        
        # Запускаем тесты
        test_results = await self._run_tests(tests, code, language)
        
        # Анализируем результаты
        analysis = await self._analyze_results(test_results)
        
        return {
            "agent": self.name,
            "tests": tests,
            "results": test_results,
            "analysis": analysis,
            "coverage": analysis.get("coverage", 0),
            "passed": analysis.get("passed", 0),
            "failed": analysis.get("failed", 0),
            "success": analysis.get("failed", 0) == 0
        }
    
    async def _generate_tests(self, code: str, language: str) -> str:
        """Генерирует тесты для кода"""
        system_prompt = f"""Ты - эксперт по тестированию {language}.

Создай comprehensive unit-тесты для данного кода:
1. Тесты для каждой функции/метода
2. Edge cases (пустые входы, большие значения, None)
3. Негативные тесты (неверные входы)
4. Тесты граничных условий

Используй pytest для Python, Jest для JavaScript и т.д."""

        response = await self._get_llm_response([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=f"Код для тестирования:\n```{language}\n{code}\n```")
        ])
        
        return self._extract_code(response)
    
    async def _run_tests(self, tests: str, code: str, language: str) -> Dict[str, Any]:
        """Безопасно запускает тесты"""
        # Используем WorkflowAgent для безопасного выполнения
        if self.tool_registry:
            result = await self.tool_registry.execute_tool(
                "execute_command",
                {"command": f"python -m pytest -v --tb=short", "timeout": 60}
            )
            return {"output": result.result, "success": result.success}
        return {"output": "Tool registry not available", "success": False}
```

### 2.3 VerifierAgent - Агент верификации

```python
# backend/agents/verifier.py
class VerifierAgent(BaseAgent):
    """
    Агент для верификации результатов других агентов.
    
    Возможности:
    - Проверка синтаксиса кода
    - Статический анализ
    - Проверка соответствия требованиям
    - Security audit
    """
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        content = context.get("content", "")
        content_type = context.get("type", "code")
        requirements = context.get("requirements", [])
        
        checks = []
        
        if content_type == "code":
            # Синтаксис
            syntax_check = await self._check_syntax(content)
            checks.append(syntax_check)
            
            # Статический анализ
            static_check = await self._static_analysis(content)
            checks.append(static_check)
            
            # Security
            security_check = await self._security_audit(content)
            checks.append(security_check)
        
        # Проверка требований
        requirements_check = await self._check_requirements(content, requirements)
        checks.append(requirements_check)
        
        # Общая оценка
        overall_score = sum(c.get("score", 0) for c in checks) / len(checks)
        all_passed = all(c.get("passed", False) for c in checks)
        
        return {
            "agent": self.name,
            "checks": checks,
            "overall_score": overall_score,
            "passed": all_passed,
            "issues": [issue for c in checks for issue in c.get("issues", [])],
            "success": all_passed
        }
    
    async def _security_audit(self, code: str) -> Dict[str, Any]:
        """Проверка безопасности кода"""
        dangerous_patterns = [
            ("eval\\(", "Использование eval() - потенциальная уязвимость"),
            ("exec\\(", "Использование exec() - потенциальная уязвимость"),
            ("subprocess\\.call.*shell=True", "Shell injection risk"),
            ("pickle\\.load", "Небезопасная десериализация"),
            ("__import__", "Динамический импорт"),
            ("sql.*\\+.*\\w+", "Потенциальная SQL инъекция"),
        ]
        
        issues = []
        for pattern, description in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append({"pattern": pattern, "description": description, "severity": "high"})
        
        return {
            "check": "security",
            "passed": len(issues) == 0,
            "score": 100 - len(issues) * 20,
            "issues": issues
        }
```

### 2.4 DevOpsAgent - Агент DevOps

```python
# backend/agents/devops.py
class DevOpsAgent(BaseAgent):
    """
    Агент для DevOps задач.
    
    Возможности:
    - Генерация Dockerfile
    - CI/CD конфигурации
    - Infrastructure as Code
    - Деплой и оркестрация
    """
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        devops_type = self._detect_devops_task(task)
        
        generators = {
            "dockerfile": self._generate_dockerfile,
            "ci_cd": self._generate_ci_cd,
            "kubernetes": self._generate_k8s,
            "terraform": self._generate_terraform,
            "docker_compose": self._generate_compose
        }
        
        generator = generators.get(devops_type, self._general_devops)
        result = await generator(task, context)
        
        return {
            "agent": self.name,
            "devops_type": devops_type,
            **result,
            "success": True
        }
    
    async def _generate_dockerfile(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Генерирует оптимизированный Dockerfile"""
        code = context.get("code", "")
        language = context.get("language", "python")
        
        system_prompt = """Ты - эксперт по Docker и контейнеризации.

Создай production-ready Dockerfile:
1. Multi-stage build для минимизации размера
2. Оптимальный базовый образ
3. Кэширование слоёв
4. Security best practices (non-root user)
5. Health checks
6. Оптимизация для CI/CD"""

        response = await self._get_llm_response([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=f"Создай Dockerfile для:\n{task}\n\nКод проекта:\n{code[:2000]}")
        ])
        
        dockerfile = self._extract_code(response)
        
        # Генерируем .dockerignore
        dockerignore = await self._generate_dockerignore(language)
        
        return {
            "dockerfile": dockerfile,
            "dockerignore": dockerignore,
            "build_command": f"docker build -t app:latest .",
            "run_command": f"docker run -p 8000:8000 app:latest"
        }
```

---

## 🎯 Фаза 3: Улучшение существующих агентов

### 3.1 CodeWriterAgent - Добавление верификации

```python
# Изменения в backend/agents/code_writer.py
class CodeWriterAgent(BaseAgent, MultimodalMixin):
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # ... существующий код генерации ...
        
        code = await self._generate_code(task, context)
        
        # Новое: Автоматическая верификация
        if self.config.get("auto_verify", True):
            verification = await self._verify_code(code, task)
            
            if not verification.get("passed"):
                # Исправляем на основе верификации
                code = await self._fix_code(code, verification.get("issues", []))
        
        # Новое: Генерация тестов если запрошено
        tests = None
        if context.get("generate_tests", False):
            tests = await self._delegate_to_tester(code)
        
        return {
            "agent": self.name,
            "code": code,
            "tests": tests,
            "verification": verification,
            "success": True
        }
    
    async def _verify_code(self, code: str, task: str) -> Dict[str, Any]:
        """Верифицирует сгенерированный код"""
        # Синтаксическая проверка
        try:
            ast.parse(code)
            syntax_ok = True
        except SyntaxError as e:
            syntax_ok = False
            syntax_error = str(e)
        
        # LLM проверка
        check_prompt = f"""
        Проверь код на соответствие задаче:
        
        Задача: {task}
        Код: {code}
        
        Проверь:
        1. Полнота реализации
        2. Обработка ошибок
        3. Edge cases
        4. Эффективность
        
        JSON: {{"passed": true/false, "issues": [], "score": 0-100}}
        """
        
        response = await self._get_llm_response([
            LLMMessage(role="user", content=check_prompt)
        ], max_tokens=300)
        
        return self._parse_verification(response, syntax_ok)
```

### 3.2 ResearchAgent - Улучшенная агрегация

```python
# Изменения в backend/agents/research.py
class ResearchAgent(BaseAgent, MultimodalMixin):
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Множественные источники поиска
        sources = []
        
        # Web search
        web_results = await self._web_search(task)
        sources.extend(web_results)
        
        # RAG поиск по кодовой базе
        if self.context_manager:
            code_context = await self.context_manager.get_context(task)
            sources.append({"type": "codebase", "content": code_context})
        
        # Поиск в памяти
        if self.memory:
            similar = await self.memory.search_similar_tasks_with_quality(task)
            sources.extend([{"type": "memory", **s} for s in similar])
        
        # Агрегация и синтез
        report = await self._synthesize_report(task, sources)
        
        # Извлечение фактов с источниками
        facts = await self._extract_facts(report, sources)
        
        return {
            "agent": self.name,
            "report": report,
            "sources": sources,
            "facts": facts,
            "confidence": self._calculate_confidence(sources),
            "success": True
        }
    
    async def _synthesize_report(self, task: str, sources: List[Dict]) -> str:
        """Синтезирует отчёт из множественных источников"""
        system_prompt = """Ты - эксперт по синтезу информации.

Правила:
1. Объедини информацию из всех источников
2. Разреши противоречия, указав на них
3. Приоритизируй свежие и надёжные источники
4. Укажи цитаты с номерами источников [1], [2]
5. Выдели ключевые факты и выводы"""

        sources_text = "\n".join([
            f"[{i+1}] {s.get('type', 'unknown')}: {s.get('content', '')[:500]}"
            for i, s in enumerate(sources[:10])
        ])
        
        response = await self._get_llm_response([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=f"Задача: {task}\n\nИсточники:\n{sources_text}")
        ], use_thinking=True)
        
        return response
```

### 3.3 ReactAgent - Улучшенный ReAct с рефлексией

```python
# Изменения в backend/agents/react.py
class ReactAgent(BaseAgent):
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # ... существующий код ...
        
        # Добавляем reflection loop
        while iteration < max_iterations:
            response = await self._get_llm_response(messages, use_thinking=True)
            
            # Новое: Рефлексия после каждых 3 итераций
            if iteration > 0 and iteration % 3 == 0:
                reflection = await self._mid_task_reflection(
                    task, messages, iteration
                )
                if reflection.get("should_change_approach"):
                    messages.append(LLMMessage(
                        role="user",
                        content=f"Рефлексия: {reflection['suggestion']}. Попробуй другой подход."
                    ))
            
            # ... остальной код ...
    
    async def _mid_task_reflection(
        self,
        task: str,
        messages: List[LLMMessage],
        iteration: int
    ) -> Dict[str, Any]:
        """Рефлексия в процессе выполнения"""
        reflection_prompt = f"""
        Ты выполняешь задачу уже {iteration} итераций.
        
        Задача: {task}
        Прогресс: {len(messages)} сообщений
        
        Оцени:
        1. Приближаешься ли к решению?
        2. Нужно ли изменить подход?
        3. Какие инструменты ещё не использованы?
        
        JSON: {{"making_progress": true/false, "should_change_approach": true/false, "suggestion": ""}}
        """
        
        response = await self._get_llm_response([
            LLMMessage(role="user", content=reflection_prompt)
        ], max_tokens=200)
        
        return self._parse_reflection(response)
```

---

## 🎯 Фаза 4: Система обучения и адаптации

### 4.1 LearningSystem - Обучение на основе feedback

```python
# backend/core/learning_system.py
class LearningSystem:
    """
    Система обучения агентов на основе feedback.
    
    Возможности:
    - Сбор статистики по агентам
    - Анализ успешных/неуспешных решений
    - Адаптация промптов
    - Оптимизация выбора агентов
    """
    
    def __init__(self, memory: LongTermMemory, config: Dict[str, Any]):
        self.memory = memory
        self.config = config
        self.agent_stats: Dict[str, AgentStats] = {}
        self.prompt_variants: Dict[str, List[PromptVariant]] = {}
    
    async def record_execution(
        self,
        agent_name: str,
        task: str,
        result: Dict[str, Any],
        feedback: Optional[Dict[str, Any]] = None
    ):
        """Записывает выполнение для обучения"""
        stats = self.agent_stats.setdefault(agent_name, AgentStats())
        stats.total_executions += 1
        
        if result.get("success"):
            stats.successful_executions += 1
        
        # Анализируем паттерны успешных задач
        if feedback and feedback.get("rating", 0) >= 4:
            stats.successful_patterns.append({
                "task_type": self._classify_task(task),
                "task_length": len(task),
                "result_quality": feedback.get("rating")
            })
    
    async def get_optimized_prompt(
        self,
        agent_name: str,
        task_type: str
    ) -> Optional[str]:
        """Возвращает оптимизированный промпт для агента"""
        variants = self.prompt_variants.get(agent_name, [])
        
        # Выбираем вариант с лучшей статистикой
        if variants:
            best = max(variants, key=lambda v: v.success_rate)
            if best.success_rate > 0.7:
                return best.content
        
        return None
    
    async def analyze_failures(
        self,
        agent_name: str,
        time_range: str = "24h"
    ) -> Dict[str, Any]:
        """Анализирует неудачи для улучшения"""
        # Получаем неудачные выполнения
        failures = await self.memory.get_failures(agent_name, time_range)
        
        # Классифицируем типы ошибок
        error_types = {}
        for failure in failures:
            error_type = self._classify_error(failure)
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Генерируем рекомендации
        recommendations = await self._generate_recommendations(error_types)
        
        return {
            "total_failures": len(failures),
            "error_distribution": error_types,
            "recommendations": recommendations
        }
```

### 4.2 PromptOptimizer - Автоматическая оптимизация промптов

```python
# backend/core/prompt_optimizer.py
class PromptOptimizer:
    """Автоматическая оптимизация промптов на основе результатов"""
    
    async def optimize_prompt(
        self,
        base_prompt: str,
        task_examples: List[Dict[str, Any]],
        metrics: Dict[str, float]
    ) -> str:
        """Оптимизирует промпт на основе примеров"""
        
        # Анализируем успешные примеры
        successful = [e for e in task_examples if e.get("rating", 0) >= 4]
        failed = [e for e in task_examples if e.get("rating", 0) < 3]
        
        optimization_prompt = f"""
        Текущий промпт:
        {base_prompt}
        
        Статистика:
        - Успешных: {len(successful)}
        - Неуспешных: {len(failed)}
        - Средний рейтинг: {metrics.get('avg_rating', 0):.2f}
        
        Примеры успешных задач:
        {[e['task'][:100] for e in successful[:3]]}
        
        Примеры неудачных задач:
        {[e['task'][:100] for e in failed[:3]]}
        
        Улучши промпт, чтобы:
        1. Лучше обрабатывать неудачные случаи
        2. Сохранить успешные паттерны
        3. Быть более конкретным в инструкциях
        """
        
        # Генерируем улучшенный промпт
        # ...
```

---

## 🎯 Фаза 5: Улучшенная координация

### 5.1 SmartOrchestrator - Улучшенный оркестратор

```python
# Изменения в backend/orchestrator.py
class SmartOrchestrator(Orchestrator):
    """Улучшенный оркестратор с продвинутой координацией"""
    
    def __init__(self, ...):
        super().__init__(...)
        self.planner = None  # PlannerAgent
        self.learning_system = LearningSystem(self.memory, {})
    
    async def execute_task(
        self,
        task: str,
        agent_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Умное выполнение с планированием"""
        
        # Определяем сложность
        complexity = await self._assess_complexity(task)
        
        if complexity == "high":
            # Для сложных задач используем PlannerAgent
            plan = await self.planner.execute(task, context)
            result = await self.planner.execute_plan(plan.get("plan", {}))
        else:
            # Для простых - прямое выполнение
            result = await super().execute_task(task, agent_type, context)
        
        # Записываем для обучения
        await self.learning_system.record_execution(
            agent_name=result.get("agent", "unknown"),
            task=task,
            result=result
        )
        
        return result
    
    async def _assess_complexity(self, task: str) -> str:
        """Оценивает сложность задачи"""
        # Используем LLM для оценки
        assessment = await self.llm_classifier.classify(
            text=task,
            classification_schema=COMPLEXITY_SCHEMA,
            use_cache=True
        )
        return assessment.get("complexity", "medium")
```

---

## 📅 Приоритеты реализации

### Высокий приоритет (Неделя 1-2):
1. ✅ ReflectionMixin - самокоррекция
2. ✅ AgentCommunicator - межагентное взаимодействие
3. ✅ TesterAgent - тестирование кода
4. ✅ VerifierAgent - верификация

### Средний приоритет (Неделя 3-4):
5. ⏳ PlannerAgent - планирование проектов
6. ⏳ LearningSystem - обучение на feedback
7. ⏳ Улучшения ResearchAgent
8. ⏳ Улучшения ReactAgent

### Низкий приоритет (Неделя 5+):
9. 📋 DevOpsAgent
10. 📋 PromptOptimizer
11. 📋 SmartOrchestrator improvements

---

## 📊 Метрики успеха

| Метрика | Текущее | Цель |
|---------|---------|------|
| Успешность агентов | ~70% | >90% |
| Требуется retry | 30% | <10% |
| Качество кода | - | >80% проходят верификацию |
| Удовлетворённость (rating) | - | >4.0/5.0 |
| Время выполнения | - | -20% |

---

## 🔧 Технические требования

### Новые зависимости:
```txt
# requirements.txt additions
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
pylint>=2.17.0
bandit>=1.7.0  # Security analysis
```

### Новые конфигурации:
```yaml
# config.yaml additions
agents:
  planner:
    enabled: true
    default_model: null
    temperature: 0.3
    max_iterations: 5
  tester:
    enabled: true
    default_model: null
    temperature: 0.2
  verifier:
    enabled: true
    default_model: null
    temperature: 0.1
  devops:
    enabled: true
    default_model: null
    temperature: 0.4

reflection:
  enabled: true
  max_retries: 2
  min_quality_threshold: 70

learning:
  enabled: true
  feedback_collection: true
  prompt_optimization: true
  optimization_interval_hours: 24
```

