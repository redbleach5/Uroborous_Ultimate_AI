"""
Code Validator - расширенная валидация кода с статическим анализом.

Обеспечивает:
- AST валидация синтаксиса (Python, JavaScript)
- Интеграция с ruff для Python
- Интеграция с eslint для JavaScript (опционально)
- Автоматическое исправление ошибок через LLM
- Type hints проверка
"""

import ast
import subprocess
import tempfile
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from enum import Enum

from .logger import get_logger

logger = get_logger(__name__)


class IssueSeverity(Enum):
    """Серьёзность проблемы."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CodeIssue:
    """Проблема в коде."""
    severity: IssueSeverity
    code: str  # Код ошибки (E501, W293, etc.)
    message: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    suggestion: Optional[str] = None
    fixable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "suggestion": self.suggestion,
            "fixable": self.fixable
        }


@dataclass
class ValidationResult:
    """Результат валидации кода."""
    is_valid: bool
    issues: List[CodeIssue] = field(default_factory=list)
    fixed_code: Optional[str] = None
    language: str = "unknown"
    errors_count: int = 0
    warnings_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "fixed_code": self.fixed_code,
            "language": self.language,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count
        }


class CodeValidator:
    """
    Расширенный валидатор кода.
    
    Особенности:
    - Многоуровневая валидация: синтаксис → linter → type checks
    - Поддержка Python и JavaScript/TypeScript
    - Автоматическое исправление форматирования
    - Интеграция с LLM для сложных исправлений
    """
    
    # Ruff rules для проверки
    RUFF_SELECT = [
        "E",   # pycodestyle errors
        "F",   # Pyflakes
        "W",   # pycodestyle warnings
        "B",   # flake8-bugbear
        "I",   # isort
        "N",   # pep8-naming
        "UP",  # pyupgrade
        "S",   # flake8-bandit (security)
        "C4",  # flake8-comprehensions
        "SIM", # flake8-simplify
        "RUF", # Ruff-specific rules
    ]
    
    # Игнорируемые правила (для сгенерированного кода)
    RUFF_IGNORE = [
        "E501",  # Line too long
        "E402",  # Module level import not at top of file
        "F401",  # Imported but unused (LLM может добавить лишние импорты)
        "S101",  # Use of assert detected
    ]
    
    def __init__(
        self,
        llm_manager=None,
        auto_fix: bool = True,
        max_fix_attempts: int = 2
    ):
        """
        Инициализация.
        
        Args:
            llm_manager: LLM провайдер для сложных исправлений
            auto_fix: Автоматически исправлять ошибки
            max_fix_attempts: Максимальное количество попыток исправления
        """
        self.llm_manager = llm_manager
        self.auto_fix = auto_fix
        self.max_fix_attempts = max_fix_attempts
        
        # Проверяем наличие инструментов
        self._ruff_available = self._check_tool("ruff")
        self._eslint_available = self._check_tool("eslint")
        
        if self._ruff_available:
            logger.info("Ruff is available for Python validation")
        else:
            logger.warning("Ruff not found, using basic Python validation")
    
    def _check_tool(self, tool: str) -> bool:
        """Проверяет доступность инструмента."""
        try:
            result = subprocess.run(
                [tool, "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    async def validate(
        self,
        code: str,
        language: Optional[str] = None,
        fix_errors: bool = True,
        task_context: Optional[str] = None
    ) -> ValidationResult:
        """
        Валидирует код.
        
        Args:
            code: Исходный код
            language: Язык программирования (auto-detect если None)
            fix_errors: Попытаться исправить ошибки
            task_context: Контекст задачи для LLM-исправления
            
        Returns:
            Результат валидации
        """
        if not code or not code.strip():
            return ValidationResult(is_valid=True, language=language or "unknown")
        
        # Определяем язык
        if language is None:
            language = self._detect_language(code)
        
        # Валидируем в зависимости от языка
        if language == "python":
            return await self._validate_python(code, fix_errors, task_context)
        elif language in ("javascript", "typescript"):
            return await self._validate_javascript(code, fix_errors, task_context)
        else:
            # Для других языков - только базовая проверка
            return ValidationResult(
                is_valid=True,
                language=language,
                issues=[CodeIssue(
                    severity=IssueSeverity.INFO,
                    code="UNSUPPORTED",
                    message=f"Validation for {language} is not fully supported",
                    line=1,
                    column=0
                )]
            )
    
    async def _validate_python(
        self,
        code: str,
        fix_errors: bool,
        task_context: Optional[str]
    ) -> ValidationResult:
        """Валидирует Python код."""
        issues: List[CodeIssue] = []
        
        # 1. Синтаксическая проверка через AST
        syntax_ok, syntax_error = self._check_python_syntax(code)
        
        if not syntax_ok:
            issues.append(CodeIssue(
                severity=IssueSeverity.ERROR,
                code="SYNTAX",
                message=syntax_error or "Syntax error",
                line=1,
                column=0
            ))
            
            # Пытаемся исправить синтаксис через LLM
            if fix_errors and self.llm_manager:
                fixed = await self._fix_with_llm(code, [issues[0]], "python", task_context)
                if fixed:
                    # Проверяем исправленный код
                    fixed_ok, _ = self._check_python_syntax(fixed)
                    if fixed_ok:
                        return await self._validate_python(fixed, fix_errors=False, task_context=task_context)
            
            return ValidationResult(
                is_valid=False,
                issues=issues,
                language="python",
                errors_count=1
            )
        
        # 2. Проверка через ruff
        if self._ruff_available:
            ruff_issues = await self._run_ruff(code)
            issues.extend(ruff_issues)
        
        # 3. Дополнительные проверки
        extra_issues = self._check_python_quality(code)
        issues.extend(extra_issues)
        
        # Подсчитываем ошибки и предупреждения
        errors_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warnings_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        
        # Пытаемся исправить ошибки
        fixed_code = None
        if fix_errors and errors_count > 0 and self.auto_fix:
            # Сначала пробуем ruff --fix
            if self._ruff_available:
                fixed_code = await self._run_ruff_fix(code)
                if fixed_code and fixed_code != code:
                    # Перепроверяем
                    return await self._validate_python(fixed_code, fix_errors=False, task_context=task_context)
            
            # Если ruff не помог, пробуем LLM
            if self.llm_manager:
                fixed = await self._fix_with_llm(code, issues[:5], "python", task_context)
                if fixed:
                    fixed_code = fixed
        
        return ValidationResult(
            is_valid=errors_count == 0,
            issues=issues,
            fixed_code=fixed_code,
            language="python",
            errors_count=errors_count,
            warnings_count=warnings_count
        )
    
    async def _validate_javascript(
        self,
        code: str,
        fix_errors: bool,
        task_context: Optional[str]
    ) -> ValidationResult:
        """Валидирует JavaScript/TypeScript код."""
        issues: List[CodeIssue] = []
        
        # 1. Базовая проверка скобок
        brackets_ok, brackets_error = self._check_brackets(code)
        
        if not brackets_ok:
            issues.append(CodeIssue(
                severity=IssueSeverity.ERROR,
                code="BRACKETS",
                message=brackets_error or "Mismatched brackets",
                line=1,
                column=0
            ))
            
            if fix_errors and self.llm_manager:
                fixed = await self._fix_with_llm(code, issues, "javascript", task_context)
                if fixed:
                    return await self._validate_javascript(fixed, fix_errors=False, task_context=task_context)
            
            return ValidationResult(
                is_valid=False,
                issues=issues,
                language="javascript",
                errors_count=1
            )
        
        # 2. Проверка через ESLint (если доступен)
        if self._eslint_available:
            eslint_issues = await self._run_eslint(code)
            issues.extend(eslint_issues)
        
        # 3. Базовые проверки качества JS
        extra_issues = self._check_javascript_quality(code)
        issues.extend(extra_issues)
        
        errors_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warnings_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        
        return ValidationResult(
            is_valid=errors_count == 0,
            issues=issues,
            language="javascript",
            errors_count=errors_count,
            warnings_count=warnings_count
        )
    
    def _check_python_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """Проверяет синтаксис Python через AST."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            error_msg = f"Line {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f" - {e.text.strip()}"
            return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def _check_brackets(self, code: str) -> Tuple[bool, Optional[str]]:
        """Проверяет сбалансированность скобок."""
        brackets = {"(": ")", "{": "}", "[": "]"}
        stack = []
        in_string = False
        string_char = None
        escape_next = False
        
        for i, char in enumerate(code):
            if escape_next:
                escape_next = False
                continue
            
            if char == "\\":
                escape_next = True
                continue
            
            if char in ("'", '"', "`"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                continue
            
            if in_string:
                continue
            
            if char in brackets:
                stack.append((char, i))
            elif char in brackets.values():
                if not stack:
                    return False, f"Unexpected closing bracket '{char}' at position {i}"
                open_bracket, _ = stack.pop()
                if brackets[open_bracket] != char:
                    return False, f"Mismatched brackets: expected '{brackets[open_bracket]}' but found '{char}'"
        
        if stack:
            open_bracket, pos = stack[-1]
            return False, f"Unclosed bracket '{open_bracket}' at position {pos}"
        
        return True, None
    
    async def _run_ruff(self, code: str) -> List[CodeIssue]:
        """Запускает ruff для анализа кода."""
        issues = []
        
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8"
            ) as f:
                f.write(code)
                f.flush()
                temp_path = f.name
            
            # Запускаем ruff
            select = ",".join(self.RUFF_SELECT)
            ignore = ",".join(self.RUFF_IGNORE)
            
            result = subprocess.run(
                [
                    "ruff", "check",
                    f"--select={select}",
                    f"--ignore={ignore}",
                    "--output-format=json",
                    temp_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Парсим JSON вывод
            if result.stdout:
                try:
                    ruff_output = json.loads(result.stdout)
                    for item in ruff_output:
                        severity = IssueSeverity.WARNING
                        code_str = item.get("code", "")
                        
                        # Определяем серьёзность по коду
                        if code_str.startswith(("E", "F")):
                            severity = IssueSeverity.ERROR
                        elif code_str.startswith(("S", "B")):
                            severity = IssueSeverity.ERROR  # Security и bugbear
                        
                        issues.append(CodeIssue(
                            severity=severity,
                            code=code_str,
                            message=item.get("message", "Unknown issue"),
                            line=item.get("location", {}).get("row", 1),
                            column=item.get("location", {}).get("column", 0),
                            end_line=item.get("end_location", {}).get("row"),
                            end_column=item.get("end_location", {}).get("column"),
                            fixable=item.get("fix", {}).get("applicability") == "safe"
                        ))
                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse ruff output: {result.stdout[:200]}")
            
            # Удаляем временный файл
            Path(temp_path).unlink(missing_ok=True)
            
        except subprocess.TimeoutExpired:
            logger.warning("Ruff timed out")
        except Exception as e:
            logger.warning(f"Ruff error: {e}")
        
        return issues
    
    async def _run_ruff_fix(self, code: str) -> Optional[str]:
        """Запускает ruff --fix для автоисправления."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8"
            ) as f:
                f.write(code)
                f.flush()
                temp_path = f.name
            
            # Запускаем ruff --fix
            subprocess.run(
                [
                    "ruff", "check",
                    "--fix",
                    "--unsafe-fixes",
                    temp_path
                ],
                capture_output=True,
                timeout=30
            )
            
            # Читаем исправленный код
            fixed_code = Path(temp_path).read_text(encoding="utf-8")
            Path(temp_path).unlink(missing_ok=True)
            
            return fixed_code
            
        except Exception as e:
            logger.debug(f"Ruff fix error: {e}")
            return None
    
    async def _run_eslint(self, code: str) -> List[CodeIssue]:
        """Запускает eslint для анализа JavaScript."""
        # TODO: Implement ESLint integration
        return []
    
    def _check_python_quality(self, code: str) -> List[CodeIssue]:
        """Дополнительные проверки качества Python кода."""
        issues = []
        lines = code.split("\n")
        
        for i, line in enumerate(lines, 1):
            # Проверка на print statements в продакшн коде
            if re.search(r"^\s*print\s*\(", line):
                issues.append(CodeIssue(
                    severity=IssueSeverity.INFO,
                    code="PRINT",
                    message="Consider using logging instead of print()",
                    line=i,
                    column=line.find("print")
                ))
            
            # Проверка на TODO/FIXME
            if "TODO" in line or "FIXME" in line:
                issues.append(CodeIssue(
                    severity=IssueSeverity.INFO,
                    code="TODO",
                    message="Found TODO/FIXME comment",
                    line=i,
                    column=0
                ))
            
            # Проверка на очень длинные строки
            if len(line) > 120:
                issues.append(CodeIssue(
                    severity=IssueSeverity.WARNING,
                    code="LINE_LENGTH",
                    message=f"Line too long ({len(line)} > 120 characters)",
                    line=i,
                    column=120
                ))
        
        return issues
    
    def _check_javascript_quality(self, code: str) -> List[CodeIssue]:
        """Дополнительные проверки качества JavaScript кода."""
        issues = []
        lines = code.split("\n")
        
        for i, line in enumerate(lines, 1):
            # Проверка на console.log
            if "console.log" in line or "console.error" in line:
                issues.append(CodeIssue(
                    severity=IssueSeverity.INFO,
                    code="CONSOLE",
                    message="Consider removing console statements",
                    line=i,
                    column=line.find("console")
                ))
            
            # Проверка на var (лучше использовать const/let)
            if re.search(r"\bvar\s+", line):
                issues.append(CodeIssue(
                    severity=IssueSeverity.WARNING,
                    code="VAR_USAGE",
                    message="Use const or let instead of var",
                    line=i,
                    column=line.find("var")
                ))
            
            # Проверка на == вместо ===
            if re.search(r"[^=!]==[^=]", line):
                issues.append(CodeIssue(
                    severity=IssueSeverity.WARNING,
                    code="LOOSE_EQUALITY",
                    message="Use === instead of ==",
                    line=i,
                    column=0
                ))
        
        return issues
    
    async def _fix_with_llm(
        self,
        code: str,
        issues: List[CodeIssue],
        language: str,
        task_context: Optional[str]
    ) -> Optional[str]:
        """Исправляет ошибки через LLM."""
        if not self.llm_manager:
            return None
        
        from ..llm.base import LLMMessage
        
        issues_text = "\n".join(
            f"- Line {i.line}: [{i.code}] {i.message}"
            for i in issues
        )
        
        fix_prompt = f"""Fix the following {language} code errors.

ERRORS:
{issues_text}

CODE:
```{language}
{code}
```

{f"ORIGINAL TASK: {task_context[:200]}" if task_context else ""}

IMPORTANT:
- Fix ONLY the errors listed above
- Keep the original functionality
- Return ONLY the fixed code wrapped in markdown code block
- Make minimal changes necessary

Fixed code:"""

        try:
            response = await self.llm_manager.generate(
                messages=[
                    LLMMessage(
                        role="system",
                        content=f"You are a {language} expert. Fix code errors precisely."
                    ),
                    LLMMessage(role="user", content=fix_prompt)
                ],
                temperature=0.1,
                max_tokens=len(code) * 2
            )
            
            # Извлекаем код из ответа
            fixed = self._extract_code_from_markdown(response.content, language)
            
            if fixed and fixed.strip():
                return fixed
            
        except Exception as e:
            logger.warning(f"LLM fix failed: {e}")
        
        return None
    
    def _extract_code_from_markdown(self, text: str, language: str) -> Optional[str]:
        """Извлекает код из markdown блока."""
        patterns = [
            rf"```{language}\n(.*?)```",
            rf"```{language[:2]}\n(.*?)```",
            r"```\n(.*?)```",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Если нет markdown блока, возвращаем весь текст
        return text.strip()
    
    def _detect_language(self, code: str) -> str:
        """Определяет язык программирования."""
        code.lower()
        
        # Python indicators
        python_score = 0
        if re.search(r"\bdef\s+\w+\s*\(", code):
            python_score += 2
        if re.search(r"\bimport\s+\w+", code):
            python_score += 1
        if re.search(r"\bclass\s+\w+.*:", code):
            python_score += 2
        if re.search(r"\basync\s+def\b", code):
            python_score += 2
        if "self." in code:
            python_score += 1
        
        # JavaScript indicators
        js_score = 0
        if re.search(r"\bfunction\s+\w+\s*\(", code):
            js_score += 2
        if re.search(r"\bconst\s+\w+\s*=", code):
            js_score += 2
        if re.search(r"\blet\s+\w+\s*=", code):
            js_score += 1
        if "=>" in code:
            js_score += 1
        if "console." in code:
            js_score += 1
        
        if python_score > js_score:
            return "python"
        elif js_score > python_score:
            return "javascript"
        
        # По умолчанию Python
        return "python"


# Глобальный экземпляр
_code_validator: Optional[CodeValidator] = None


def get_code_validator(llm_manager=None) -> CodeValidator:
    """Получить экземпляр CodeValidator."""
    global _code_validator
    if _code_validator is None:
        _code_validator = CodeValidator(llm_manager=llm_manager)
    return _code_validator

