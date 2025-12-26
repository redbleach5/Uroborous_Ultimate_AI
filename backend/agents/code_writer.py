"""
CodeWriterAgent - Generates and refactors code
"""

from typing import Dict, Any, Optional, List, Tuple
import re
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from .multimodal_mixin import MultimodalMixin
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException
from ..core.two_stage_processor import TwoStageProcessor, ProcessingStage
from ..core.text_utils import extract_code_from_markdown, detect_language_from_task


class CodeWriterAgent(BaseAgent, MultimodalMixin):
    """Agent for code generation and refactoring"""
    
    def __init__(self, *args, **kwargs):
        BaseAgent.__init__(self, *args, **kwargs)
        MultimodalMixin.__init__(self)
    
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
                user_prompt += f"\nPreviously generated files in this project:\n"
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
                            
                            result_dict = {
                                "agent": self.name,
                                "task": task,
                                "code": code,
                                "success": True,
                                "two_stage": True
                            }
                            
                            # Save to memory if available
                            if self.memory:
                                await self.memory.save_solution(
                                    task=task,
                                    solution=code,
                                    agent=self.name,
                                    metadata=context
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
            
            result = {
                "agent": self.name,
                "task": task,
                "code": code,
                "success": True
            }
            
            # Save to memory if available
            if self.memory:
                await self.memory.save_solution(
                    task=task,
                    solution=code,
                    agent=self.name,
                    metadata=context
                )
            
            return result
            
        except Exception as e:
            logger.error(f"CodeWriterAgent error: {e}")
            raise AgentException(f"Failed to generate code: {e}") from e

