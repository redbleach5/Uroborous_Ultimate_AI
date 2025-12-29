# 🦉 План интеграции OWL → AILLM

> **Дата анализа:** 29 декабря 2025  
> **Источник:** [camel-ai/owl](https://github.com/camel-ai/owl)  
> **Лицензия:** Apache 2.0 (совместима с нашим проектом)

---

## 📊 Резюме анализа

После детального изучения репозитория OWL (~15k звёзд на GitHub, #1 на GAIA benchmark среди open-source), выделены **6 ключевых компонентов** для интеграции в AILLM.

### Сравнительная таблица

| Компонент | OWL | AILLM | Рекомендация |
|-----------|-----|-------|--------------|
| **Browser Automation** | ✅ BrowserToolkit (Playwright) | ❌ Нет | 🔴 **ВНЕДРИТЬ** |
| **MCP Protocol** | ✅ MCPToolkit | ❌ Нет | 🟡 Рассмотреть |
| **Document Processing** | ✅ PDF/DOCX/Excel | ⚠️ Частично | 🟢 Расширить |
| **User-Assistant RolePlaying** | ✅ OwlRolePlaying | ⚠️ Отличается | 🟡 Адаптировать |
| **Learning System** | ❌ Нет | ✅ Полноценная | AILLM лучше |
| **Reflection** | ⚠️ Базовая | ✅ ReflectionMixin | AILLM лучше |
| **Model Router** | ⚠️ Простой | ✅ IntelligentRouter | AILLM лучше |
| **Long-Term Memory** | ❌ Нет | ✅ Полноценная | AILLM лучше |

---

## 🔴 ПРИОРИТЕТ 1: BrowserToolkit (Playwright)

### Что это даёт
- Полная автоматизация браузера (Chrome/Edge/Chromium)
- Навигация, клики, ввод текста, скроллинг
- Скриншоты и анализ страниц
- Загрузка файлов
- Мультимодальный анализ веб-страниц

### Как использует OWL

```python
from camel.toolkits import BrowserToolkit

tools = [
    *BrowserToolkit(
        headless=False,  # True для серверов
        web_agent_model=models["browsing"],
        planning_agent_model=models["planning"],
    ).get_tools(),
]
```

### План интеграции в AILLM

**Файл:** `backend/tools/browser_tools.py`

```python
"""
Browser automation tools using Playwright
Based on CAMEL-AI BrowserToolkit
"""

from playwright.async_api import async_playwright, Browser, Page
from typing import Dict, Any, Optional, List
from ..core.logger import get_logger
from .base import BaseTool, ToolResult

logger = get_logger(__name__)


class BrowserTool(BaseTool):
    """Browser automation tool with Playwright"""
    
    def __init__(self, headless: bool = True, channel: str = "chrome"):
        self.headless = headless
        self.channel = channel
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
    
    async def initialize(self):
        """Initialize browser instance"""
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(
            headless=self.headless,
            channel=self.channel
        )
        self._page = await self._browser.new_page()
    
    async def navigate(self, url: str) -> ToolResult:
        """Navigate to URL"""
        try:
            await self._page.goto(url, wait_until="networkidle")
            return ToolResult(
                success=True,
                result={"url": url, "title": await self._page.title()}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def click(self, selector: str) -> ToolResult:
        """Click element by selector"""
        try:
            await self._page.click(selector)
            return ToolResult(success=True, result={"clicked": selector})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def fill(self, selector: str, text: str) -> ToolResult:
        """Fill input field"""
        try:
            await self._page.fill(selector, text)
            return ToolResult(success=True, result={"filled": selector})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def screenshot(self, path: str = None, full_page: bool = False) -> ToolResult:
        """Take screenshot"""
        try:
            screenshot = await self._page.screenshot(
                path=path,
                full_page=full_page
            )
            return ToolResult(
                success=True,
                result={"path": path, "size": len(screenshot)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def get_content(self) -> ToolResult:
        """Get page text content"""
        try:
            content = await self._page.inner_text("body")
            return ToolResult(success=True, result={"content": content[:5000]})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def execute_script(self, script: str) -> ToolResult:
        """Execute JavaScript"""
        try:
            result = await self._page.evaluate(script)
            return ToolResult(success=True, result={"output": result})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def close(self):
        """Close browser"""
        if self._browser:
            await self._browser.close()
```

### Зависимости

```bash
# Добавить в requirements.txt
playwright>=1.40.0

# После установки
playwright install chromium
```

---

## 🟡 ПРИОРИТЕТ 2: DocumentProcessingToolkit

### Что это даёт
- Парсинг PDF, DOCX, PPTX
- Извлечение таблиц из Excel
- Конвертация в Markdown
- Работа с ZIP архивами
- Парсинг JSON/XML

### Как использует OWL

```python
from owl.utils import DocumentProcessingToolkit

tools = [
    *DocumentProcessingToolkit(model=models["document"]).get_tools(),
]

# Метод extract_document_content(path) автоматически определяет тип файла
```

### План интеграции в AILLM

**Файл:** `backend/tools/document_tools.py`

```python
"""
Enhanced document processing tools
Based on OWL DocumentProcessingToolkit
"""

import os
import json
from typing import Tuple, List, Optional
from pathlib import Path

from ..core.logger import get_logger
from .base import BaseTool, ToolResult

logger = get_logger(__name__)


class DocumentTool(BaseTool):
    """Universal document processing tool"""
    
    SUPPORTED_EXTENSIONS = {
        'pdf': '_process_pdf',
        'docx': '_process_docx',
        'doc': '_process_docx',
        'xlsx': '_process_excel',
        'xls': '_process_excel',
        'pptx': '_process_pptx',
        'json': '_process_json',
        'xml': '_process_xml',
        'zip': '_process_zip',
    }
    
    def __init__(self, cache_dir: str = "tmp/"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    async def extract_content(self, path: str) -> ToolResult:
        """Extract content from any supported document"""
        try:
            ext = Path(path).suffix.lower().strip('.')
            
            if ext not in self.SUPPORTED_EXTENSIONS:
                return ToolResult(
                    success=False,
                    error=f"Unsupported format: {ext}"
                )
            
            method = getattr(self, self.SUPPORTED_EXTENSIONS[ext])
            content = await method(path)
            
            return ToolResult(success=True, result={"content": content})
            
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _process_pdf(self, path: str) -> str:
        """Process PDF file"""
        import pypdf
        
        reader = pypdf.PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    async def _process_docx(self, path: str) -> str:
        """Process Word document"""
        from docx import Document
        
        doc = Document(path)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    
    async def _process_excel(self, path: str) -> str:
        """Process Excel file"""
        import pandas as pd
        
        xl = pd.ExcelFile(path)
        result = []
        
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name)
            result.append(f"## Sheet: {sheet_name}\n")
            result.append(df.to_markdown())
            result.append("\n")
        
        return "\n".join(result)
    
    async def _process_json(self, path: str) -> str:
        """Process JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    async def _process_zip(self, path: str) -> str:
        """Extract and list ZIP contents"""
        import zipfile
        
        extract_path = os.path.join(self.cache_dir, Path(path).stem)
        
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        files = []
        for root, _, filenames in os.walk(extract_path):
            for filename in filenames:
                files.append(os.path.join(root, filename))
        
        return f"Extracted {len(files)} files to {extract_path}:\n" + "\n".join(files)
```

### Зависимости

```bash
# Добавить в requirements.txt
pypdf>=3.0.0
python-docx>=0.8.11
pandas>=2.0.0
openpyxl>=3.1.0
```

---

## 🟡 ПРИОРИТЕТ 3: OwlRolePlaying Pattern

### Что это даёт
OWL использует паттерн "User → Instruction → Assistant → Solution":
- **User Agent**: Декомпозирует задачу на подзадачи
- **Assistant Agent**: Выполняет подзадачи с инструментами
- **Итеративный цикл** до `TASK_DONE`

### Ключевые идеи для AILLM

```python
# Системный промпт User Agent (планировщик)
USER_SYSTEM_PROMPT = """
===== RULES OF USER =====
- Instruct assistant step by step
- One instruction at a time
- Use format: `Instruction: [YOUR INSTRUCTION]`
- Tips for complex tasks:
  * First search for initial info
  * Then visit specific URLs
  * Verify final answers
  * Remind to run code
- Say <TASK_DONE> when complete
"""

# Системный промпт Assistant Agent (исполнитель)
ASSISTANT_SYSTEM_PROMPT = """
===== RULES OF ASSISTANT =====
- Never instruct, only execute
- Use available tools
- Format: `Solution: [YOUR_SOLUTION]`
- Tips:
  * If one way fails, try another
  * Check Wikipedia first
  * Verify accuracy with multiple sources
  * Always run written code
"""
```

### Адаптация для AILLM

**Файл:** `backend/agents/task_planner.py`

```python
"""
Task Planner Agent inspired by OWL's OwlRolePlaying
Decomposes complex tasks into executable steps
"""

from typing import List, Dict, Any, Optional
from .base import BaseAgent
from ..llm.base import LLMMessage


class TaskPlannerAgent(BaseAgent):
    """
    Планировщик задач в стиле OWL.
    Декомпозирует сложные задачи на пошаговые инструкции.
    """
    
    SYSTEM_PROMPT = """You are a Task Planner Agent.
Your role is to break down complex tasks into step-by-step instructions.

Rules:
1. Give ONE instruction at a time
2. Format: "Instruction: [clear, actionable step]"
3. Consider what tools might be needed
4. After each step completion, evaluate if more steps needed
5. When task is complete, respond with: TASK_DONE

Tips for effective planning:
- Start with information gathering (search, read)
- Then process/analyze the information
- Verify results before concluding
- If code is written, ensure it's executed
"""
    
    async def plan_task(
        self,
        task: str,
        available_tools: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Decompose task into steps
        
        Args:
            task: Complex task description
            available_tools: List of available tool names
            context: Additional context
            
        Returns:
            List of instruction strings
        """
        messages = [
            LLMMessage(role="system", content=self.SYSTEM_PROMPT),
            LLMMessage(role="user", content=f"""
Task: {task}

Available tools: {', '.join(available_tools)}

Please provide the first instruction to solve this task.
""")
        ]
        
        instructions = []
        max_steps = 15
        
        for step in range(max_steps):
            response = await self._get_llm_response(messages)
            
            if "TASK_DONE" in response:
                break
            
            # Extract instruction
            if "Instruction:" in response:
                instruction = response.split("Instruction:")[-1].strip()
                instructions.append(instruction)
            else:
                instructions.append(response)
            
            # Add to conversation for context
            messages.append(LLMMessage(role="assistant", content=response))
            messages.append(LLMMessage(
                role="user",
                content="Instruction completed. What's the next step?"
            ))
        
        return instructions
```

---

## 🟢 ПРИОРИТЕТ 4: MCPToolkit (Model Context Protocol)

### Что это даёт
MCP — стандартный протокол для взаимодействия AI с внешними сервисами:
- Playwright automation (browser)
- File system access
- Database connections
- Custom tools

### Пример конфигурации OWL

```json
// mcp_servers_config.json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server"]
    },
    "fetch": {
      "command": "python",
      "args": ["-m", "mcp_server_fetch"]
    }
  }
}
```

### Рекомендация для AILLM
MCP добавляет значительную сложность. **Рекомендую отложить** до версии 2.0 и сначала внедрить BrowserToolkit напрямую.

---

## 📦 Зависимости для полной интеграции

```bash
# Добавить в requirements.txt

# Browser automation
playwright>=1.40.0

# Document processing
pypdf>=3.0.0
python-docx>=0.8.11
python-pptx>=0.6.21
openpyxl>=3.1.0
xmltodict>=0.14.2

# Web scraping (опционально)
firecrawl>=2.5.3

# MCP (для будущего)
# mcp>=1.0.0
```

---

## 🗓️ Roadmap интеграции

### Фаза 1: Browser & Documents (1-2 недели)
- [ ] Создать `backend/tools/browser_tools.py`
- [ ] Создать `backend/tools/document_tools.py`
- [ ] Добавить в ToolRegistry
- [ ] Написать тесты
- [ ] Обновить документацию

### Фаза 2: TaskPlanner Agent (1 неделя)
- [ ] Создать `backend/agents/task_planner.py`
- [ ] Интегрировать с Orchestrator
- [ ] Добавить паттерн User-Assistant для сложных задач

### Фаза 3: Enhanced Search (1 неделя)
- [ ] Добавить DuckDuckGo search
- [ ] Добавить Wikipedia search
- [ ] Улучшить WebSearchTool

### Фаза 4: MCP Integration (будущее)
- [ ] Изучить MCP спецификацию
- [ ] Создать MCPToolkit wrapper
- [ ] Добавить поддержку внешних MCP серверов

---

## ✅ Что НЕ нужно брать из OWL

1. **Система агентов** — наша архитектура более зрелая (ReflectionMixin, LongTermMemory)
2. **LLM провайдеры** — у нас уже есть полноценная поддержка
3. **Логирование** — наша система логирования лучше (correlation_id, structured logs)
4. **Конфигурация** — наш config.yaml более гибкий
5. **Web UI** — наш React+Tauri UI более функционален

---

## 🎯 Ожидаемый результат

После интеграции AILLM получит:
- ✅ **Browser automation** для web-задач
- ✅ **Universal document parsing** (PDF, Word, Excel, PowerPoint)
- ✅ **Enhanced task decomposition** для сложных задач
- ✅ **Сохранение всех существующих преимуществ** (Learning, Reflection, Memory)

**Итоговая оценка системы:** 8.5/10 → **9.2/10**

---

*Документ создан на основе анализа репозитория OWL v0.2.57*

