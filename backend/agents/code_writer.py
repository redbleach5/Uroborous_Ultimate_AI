"""
CodeWriterAgent - Generates and refactors code with syntax validation

Features:
- AST-based syntax validation (Python, JavaScript)
- Integration with ruff for enhanced Python analysis
- Automatic error correction via LLM
- Self-consistency for critical code generation
"""

from typing import Dict, Any, Optional, Tuple
import re
import ast
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from .multimodal_mixin import MultimodalMixin
from .self_consistency_mixin import SelfConsistencyMixin
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException
from ..core.two_stage_processor import TwoStageProcessor, ProcessingStage
from ..core.text_utils import extract_code_from_markdown, detect_language_from_task
from ..core.code_validator import CodeValidator, get_code_validator, ValidationResult


def validate_python_syntax(code: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Python code syntax using AST parser.
    
    Args:
        code: Python code string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not code or not code.strip():
        return True, None  # Empty code is technically valid
    
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
        if e.text:
            error_msg += f"\n  Code: {e.text.strip()}"
        return False, error_msg
    except Exception as e:
        return False, f"Parsing error: {str(e)}"


def validate_javascript_syntax(code: str) -> Tuple[bool, Optional[str]]:
    """
    Basic JavaScript syntax validation using heuristics.
    For full validation, would need a JS parser.
    
    Args:
        code: JavaScript code string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not code or not code.strip():
        return True, None
    
    # Basic bracket matching
    brackets = {'(': ')', '{': '}', '[': ']'}
    stack = []
    in_string = False
    string_char = None
    escape_next = False
    
    for i, char in enumerate(code):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char in ('"', "'", '`'):
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
                return False, f"Unmatched closing bracket '{char}' at position {i}"
            open_bracket, _ = stack.pop()
            if brackets[open_bracket] != char:
                return False, f"Mismatched brackets: expected '{brackets[open_bracket]}' but found '{char}' at position {i}"
    
    if stack:
        open_bracket, pos = stack[-1]
        return False, f"Unclosed bracket '{open_bracket}' at position {pos}"
    
    return True, None


def detect_code_language(code: str) -> str:
    """
    Detect the programming language of a code snippet.
    
    Args:
        code: Code string to analyze
        
    Returns:
        Detected language: 'python', 'javascript', 'html', 'css', or 'unknown'
    """
    code.lower().strip()
    
    # Python indicators
    python_patterns = [
        r'\bdef\s+\w+\s*\(',
        r'\bclass\s+\w+',
        r'\bimport\s+\w+',
        r'\bfrom\s+\w+\s+import',
        r'if\s+__name__\s*==',
        r':\s*$',  # Colons at end of lines
        r'\bprint\s*\(',
        r'\basync\s+def\b',
    ]
    
    # JavaScript indicators
    js_patterns = [
        r'\bfunction\s+\w+\s*\(',
        r'\bconst\s+\w+\s*=',
        r'\blet\s+\w+\s*=',
        r'\bvar\s+\w+\s*=',
        r'=>\s*[{\(]',  # Arrow functions
        r'\bconsole\.(log|error|warn)',
        r'\bdocument\.',
        r'\bwindow\.',
    ]
    
    # HTML indicators
    html_patterns = [
        r'<!DOCTYPE\s+html',
        r'<html',
        r'<head>',
        r'<body>',
        r'<div',
        r'<script',
        r'<style',
    ]
    
    python_score = sum(1 for p in python_patterns if re.search(p, code, re.MULTILINE | re.IGNORECASE))
    js_score = sum(1 for p in js_patterns if re.search(p, code, re.MULTILINE | re.IGNORECASE))
    html_score = sum(1 for p in html_patterns if re.search(p, code, re.IGNORECASE))
    
    if html_score >= 2:
        return 'html'
    if python_score > js_score and python_score >= 1:
        return 'python'
    if js_score > python_score and js_score >= 1:
        return 'javascript'
    if python_score >= 1:
        return 'python'
    if js_score >= 1:
        return 'javascript'
    
    return 'unknown'


class CodeWriterAgent(BaseAgent, MultimodalMixin, SelfConsistencyMixin):
    """
    Agent for code generation and refactoring with automatic syntax validation.
    
    Features:
    - Generates code based on user requirements
    - Validates generated code syntax (Python, JavaScript)
    - Integration with ruff for enhanced Python validation
    - Automatically attempts to fix syntax errors via LLM
    - Self-consistency for critical code generation
    - Saves successful solutions to memory for few-shot learning
    """
    
    # Maximum number of syntax fix attempts
    MAX_SYNTAX_FIX_ATTEMPTS = 2
    
    def __init__(self, *args, **kwargs):
        BaseAgent.__init__(self, *args, **kwargs)
        MultimodalMixin.__init__(self)
        SelfConsistencyMixin.__init__(self)
        
        # Initialize advanced code validator
        self._code_validator: Optional[CodeValidator] = None
        
        # Configure self-consistency for critical tasks
        self.configure_self_consistency(
            enabled=True,
            samples=3,
            temperature=0.6,
            min_agreement=0.5
        )
    
    @property
    def code_validator(self) -> CodeValidator:
        """Lazy initialization of code validator."""
        if self._code_validator is None:
            self._code_validator = get_code_validator(llm_manager=self.llm_manager)
        return self._code_validator
    
    async def _validate_and_fix_code(
        self,
        code: str,
        task: str,
        language: Optional[str] = None,
        use_advanced_validator: bool = True
    ) -> Tuple[str, bool, Optional[str]]:
        """
        Validate code syntax and attempt to fix errors.
        
        Uses advanced CodeValidator with ruff integration for Python.
        
        Args:
            code: Generated code to validate
            task: Original task description (for context in fix attempts)
            language: Programming language (auto-detected if not provided)
            use_advanced_validator: Use enhanced validator with ruff/eslint
            
        Returns:
            Tuple of (possibly_fixed_code, is_valid, error_message)
        """
        if not code or not code.strip():
            return code, True, None
        
        # Detect language if not provided
        lang = language or detect_code_language(code)
        
        # Try advanced validator first (with ruff integration)
        if use_advanced_validator:
            try:
                validation_result: ValidationResult = await self.code_validator.validate(
                    code=code,
                    language=lang,
                    fix_errors=True,
                    task_context=task
                )
                
                if validation_result.is_valid:
                    logger.info(
                        f"CodeWriterAgent: Advanced validation passed ({lang}), "
                        f"warnings: {validation_result.warnings_count}"
                    )
                    return code, True, None
                
                # If validator auto-fixed the code, return fixed version
                if validation_result.fixed_code:
                    logger.info("CodeWriterAgent: Code auto-fixed by validator")
                    return validation_result.fixed_code, True, None
                
                # Collect error messages
                errors = [
                    f"Line {i.line}: [{i.code}] {i.message}"
                    for i in validation_result.issues
                    if i.severity.value == "error"
                ]
                error = "\n".join(errors) if errors else "Validation failed"
                
                logger.warning(f"CodeWriterAgent: Advanced validation failed: {len(errors)} errors")
                
            except Exception as e:
                logger.warning(f"Advanced validator failed: {e}, falling back to basic")
                use_advanced_validator = False
        
        # Fallback to basic validation
        if not use_advanced_validator:
            if lang == 'python':
                is_valid, error = validate_python_syntax(code)
            elif lang == 'javascript':
                is_valid, error = validate_javascript_syntax(code)
            else:
                return code, True, None
            
            if is_valid:
                logger.info(f"CodeWriterAgent: Basic syntax validation passed ({lang})")
                return code, True, None
        
        logger.warning(f"CodeWriterAgent: Syntax error detected in {lang} code: {error}")
        
        # Attempt to fix the code
        for attempt in range(self.MAX_SYNTAX_FIX_ATTEMPTS):
            try:
                fixed_code = await self._attempt_syntax_fix(code, error, lang, task)
                
                # Re-validate
                if lang == 'python':
                    is_fixed, new_error = validate_python_syntax(fixed_code)
                else:
                    is_fixed, new_error = validate_javascript_syntax(fixed_code)
                
                if is_fixed:
                    logger.info(f"CodeWriterAgent: Syntax error fixed on attempt {attempt + 1}")
                    return fixed_code, True, None
                else:
                    error = new_error  # Use new error for next attempt
                    code = fixed_code  # Use partially fixed code
                    
            except Exception as e:
                logger.warning(f"CodeWriterAgent: Fix attempt {attempt + 1} failed: {e}")
        
        # All fix attempts failed
        logger.error(f"CodeWriterAgent: Could not fix syntax error after {self.MAX_SYNTAX_FIX_ATTEMPTS} attempts")
        return code, False, error
    
    async def _attempt_syntax_fix(
        self,
        code: str,
        error: str,
        language: str,
        task: str
    ) -> str:
        """
        Attempt to fix syntax errors using LLM.
        
        Args:
            code: Code with syntax error
            error: Error message from validator
            language: Programming language
            task: Original task description
            
        Returns:
            Fixed code (may still have errors)
        """
        fix_prompt = f"""The following {language} code has a syntax error. Please fix ONLY the syntax error and return the corrected code.

SYNTAX ERROR:
{error}

CODE WITH ERROR:
```{language}
{code}
```

ORIGINAL TASK: {task[:200]}

IMPORTANT:
- Fix ONLY the syntax error, don't change the functionality
- Return ONLY the corrected code wrapped in markdown code block
- Keep all the original logic and structure
- Make minimal changes necessary to fix the syntax

Return the fixed code:"""
        
        messages = [
            LLMMessage(
                role="system",
                content=f"You are a {language} syntax expert. Fix syntax errors with minimal changes."
            ),
            LLMMessage(role="user", content=fix_prompt)
        ]
        
        response = await self._get_llm_response(
            messages,
            include_few_shot=False,  # Don't include examples for fix attempts
            temperature=0.1  # Low temperature for precise fixes
        )
        
        # Extract fixed code
        fixed_code = extract_code_from_markdown(response)
        return fixed_code if fixed_code else code
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute code writing task
        
        Args:
            task: Task description
            context: Additional context (e.g., file paths, code snippets)
            
        Returns:
            Result with generated code
        """
        logger.info(f"CodeWriterAgent executing task: {task}")
        
        # Process multimodal input if present
        multimodal_content = ""
        if context:
            multimodal_result = await self.process_multimodal_input(context)
            if multimodal_result.get("text"):
                multimodal_content = multimodal_result["text"]
        
        # Get relevant context
        context_text = await self._get_context(task)
        
        # Build prompt
        system_prompt = """You are an expert software developer with exceptional reasoning capabilities, capable of building complex systems from scratch. Your task is to generate, refactor, or improve code based on user requirements.

THINKING PROCESS:
Before writing code, think deeply about:
1. Requirements analysis: What exactly needs to be built? What are the implicit requirements?
2. Architecture design: What is the best structure? What patterns should be used?
3. Edge cases: What could go wrong? What inputs need validation?
4. Dependencies: What libraries/frameworks are needed? Are there alternatives?
5. Testing strategy: How can this be tested? What test cases are important?
6. Performance considerations: Are there bottlenecks? How can this be optimized?
7. Security: Are there vulnerabilities? How can security be improved?

GUIDELINES:
- Write clean, well-documented code with clear reasoning behind design decisions
- Follow best practices and design patterns, but think about when to deviate
- Include comprehensive error handling - think about all failure modes
- Write code that is maintainable and testable - consider future changes
- Consider performance and security implications deeply
- For complex projects (systems, applications, frameworks):
  * Think through the architecture before implementing
  * Create proper project structure with clear separation of concerns
  * Include all necessary files (config, requirements, README)
  * Implement core functionality completely with proper abstraction
  * Add proper error handling and logging throughout
  * Include setup and installation instructions
- For games and interactive applications:
  * Design the game loop architecture thoughtfully
  * Include complete, runnable code with proper state management
  * Proper game loop, input handling, and rendering
  * All necessary dependencies with version specifications
- Always provide complete, executable solutions
- Include necessary imports and dependencies
- Add comments explaining key logic, architecture decisions, and reasoning
- Think through the user experience and edge cases
"""
        
        user_prompt = f"""Task: {task}

"""
        
        # Add context about previous steps if this is part of a larger project
        if context and "previous_results" in context:
            user_prompt += "This is part of a larger project. Previous steps have been completed:\n"
            prev_results = context.get("previous_results", [])
            for i, prev in enumerate(prev_results[:5]):  # Show last 5 results
                if prev.get("success"):
                    user_prompt += f"- Step {i+1}: {prev.get('subtask', '')[:100]}\n"
            user_prompt += "\nBuild upon the previous work and ensure consistency.\n\n"
        
        if context_text:
            user_prompt += f"Relevant context from codebase:\n{context_text}\n\n"
        
        if multimodal_content:
            user_prompt += f"Multimodal input (images, audio, etc.):\n{multimodal_content}\n\n"
        
        if context:
            if "file_path" in context:
                user_prompt += f"Target file: {context['file_path']}\n"
            if "existing_code" in context:
                user_prompt += f"Existing code:\n{context['existing_code']}\n"
            if "requirements" in context:
                user_prompt += f"Requirements:\n{context['requirements']}\n"
            if "generated_files" in context:
                user_prompt += "\nPreviously generated files in this project:\n"
                for file_info in context["generated_files"][-3:]:  # Show last 3 files
                    user_prompt += f"- {file_info.get('subtask', 'unknown')}\n"
                user_prompt += "\n"
        
        user_prompt += "\nPlease provide the complete code solution. For complex projects, include all necessary files and structure."
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        try:
            # Use TwoStageProcessor for complex code generation tasks
            if len(task) > 100 or any(keyword in task.lower() for keyword in ["игра", "game", "приложение", "app", "система", "system"]):
                try:
                    processor = TwoStageProcessor(
                        llm_manager=self.llm_manager,
                        fast_provider=None,  # Auto-select
                        powerful_provider=None  # Auto-select
                    )
                    
                    async def fast_code_analysis(task: str) -> Dict[str, Any]:
                        """Быстрый анализ требований к коду"""
                        analysis_prompt = f"""Проанализируй задачу генерации кода и определи:
1. Язык программирования
2. Тип кода (функция, класс, модуль, приложение, игра)
3. Ключевые требования
4. Примерная сложность

Задача: {task}

JSON ответ:
{{
    "language": "язык",
    "code_type": "тип",
    "requirements": ["требование1", "требование2"],
    "complexity": "сложность"
}}"""
                        
                        analysis_messages = [
                            LLMMessage(role="system", content="Ты - эксперт по анализу задач программирования. Отвечай только в формате JSON."),
                            LLMMessage(role="user", content=analysis_prompt)
                        ]
                        
                        response = await self.llm_manager.generate(
                            messages=analysis_messages,
                            provider_name=None,  # Auto-select fast provider
                            temperature=0.2,
                            max_tokens=200
                        )
                        
                        if response and response.content:
                            import json
                            content = response.content.strip()
                            json_start = content.find('{')
                            json_end = content.rfind('}') + 1
                            if json_start >= 0 and json_end > json_start:
                                try:
                                    return json.loads(content[json_start:json_end])
                                except Exception as e:
                                    logger.debug(f"Failed to parse JSON from LLM response: {e}")
                                    # Fallback to language detection
                        # Fallback to heuristic autodetect (no hard default to Python)
                        lang, _ = detect_language_from_task(task)
                        return {"language": lang or "auto", "code_type": "function", "requirements": [], "complexity": "medium"}
                    
                    async def powerful_code_generation(task: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
                        """Мощная генерация кода на основе анализа"""
                        # Resolve language priority: LLM analysis -> heuristic -> default python
                        lang = analysis.get("language")
                        heuristic_lang, _ = detect_language_from_task(task)
                        language = lang if lang and lang != "auto" else heuristic_lang or "python"
                        code_type = analysis.get("code_type", "function")
                        requirements = analysis.get("requirements", [])
                        
                        generation_prompt = f"""Сгенерируй ПОЛНЫЙ, РАБОЧИЙ код на языке {language}.

Тип кода: {code_type}
Требования: {', '.join(requirements) if requirements else 'Стандартные практики'}

Задача: {task}

ВАЖНО: 
- Сгенерируй ПОЛНЫЙ, РАБОЧИЙ код, а не только описание или план
- Включи все необходимые импорты и зависимости
- Код должен быть готов к запуску
- Для игр: включи полный игровой цикл, обработку ввода, отрисовку
- Оберни код в блок markdown с указанием языка (```{language} ... ```)

Начни генерацию кода прямо сейчас."""
                        
                        gen_messages = [
                            LLMMessage(role="system", content=system_prompt),
                            LLMMessage(role="user", content=generation_prompt)
                        ]
                        
                        response = await self.llm_manager.generate(
                            messages=gen_messages,
                            provider_name=None,  # Auto-select powerful provider
                            temperature=0.2,
                            max_tokens=4000
                        )
                        
                        if response and response.content:
                            code = extract_code_from_markdown(response.content)
                            return {"code": code, "analysis": analysis}
                        
                        return {"code": "", "analysis": analysis}
                    
                    result = await processor.process(
                        task,
                        fast_analysis=fast_code_analysis,
                        powerful_processing=powerful_code_generation
                    )
                    
                    if result.stage == ProcessingStage.COMPLETED:
                        code = result.data.get("powerful_result", {}).get("code", "")
                        # Если код пустой, но есть результат, попробуем извлечь из result
                        if not code:
                            powerful_result = result.data.get("powerful_result", {})
                            if isinstance(powerful_result, dict):
                                code = powerful_result.get("code", "")
                            elif isinstance(powerful_result, str):
                                # Если результат - строка, попробуем извлечь код из markdown
                                code = powerful_result
                        
                        if code:
                            # Extract code from markdown if present
                            code = extract_code_from_markdown(code)
                            
                            # Validate syntax and attempt to fix errors
                            validated_code, is_valid, syntax_error = await self._validate_and_fix_code(
                                code, task
                            )
                            
                            result_dict = {
                                "agent": self.name,
                                "task": task,
                                "code": validated_code,
                                "success": True,
                                "two_stage": True,
                                "syntax_validated": is_valid,
                                "syntax_error": syntax_error if not is_valid else None
                            }
                            
                            # Save to memory only if syntax is valid (quality control)
                            if self.memory and is_valid:
                                await self.memory.save_solution(
                                    task=task,
                                    solution=validated_code,
                                    agent=self.name,
                                    metadata={**(context or {}), "syntax_validated": True}
                                )
                            
                            return result_dict
                        else:
                            logger.warning("TwoStageProcessor completed but no code generated, falling back to direct generation")
                    else:
                        logger.warning(f"TwoStageProcessor did not complete (stage: {result.stage}), falling back to direct generation")
                except Exception as e:
                    logger.warning(f"TwoStageProcessor failed: {e}, falling back to direct generation")
            
            # Fallback to direct LLM call
            code = await self._get_llm_response(messages)
            
            # Extract code from markdown if present
            code = extract_code_from_markdown(code)
            
            # Validate syntax and attempt to fix errors
            validated_code, is_valid, syntax_error = await self._validate_and_fix_code(
                code, task
            )
            
            result = {
                "agent": self.name,
                "task": task,
                "code": validated_code,
                "success": True,
                "syntax_validated": is_valid,
                "syntax_error": syntax_error if not is_valid else None
            }
            
            # Save to memory only if syntax is valid (quality control)
            if self.memory and is_valid:
                await self.memory.save_solution(
                    task=task,
                    solution=validated_code,
                    agent=self.name,
                    metadata={**(context or {}), "syntax_validated": True}
                )
            
            return result
            
        except Exception as e:
            logger.error(f"CodeWriterAgent error: {e}")
            raise AgentException(f"Failed to generate code: {e}") from e

