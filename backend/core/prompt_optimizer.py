"""
Prompt Optimizer - Оптимизация промптов для малых моделей
Минимизирует потерю качества при работе с ограниченными ресурсами
"""

from typing import List, Dict, Any, Optional
from .logger import get_logger
logger = get_logger(__name__)

from ..llm.base import LLMMessage


class PromptOptimizer:
    """
    Оптимизатор промптов для работы с малыми моделями
    
    Стратегии оптимизации:
    - Сжатие промптов без потери смысла
    - Упрощение инструкций
    - Удаление избыточной информации
    - Структурирование для лучшего понимания
    """
    
    def __init__(self):
        self.optimization_rules = {
            "remove_greetings": True,
            "simplify_instructions": True,
            "remove_examples": False,  # Примеры важны для понимания
            "compress_redundancy": True,
            "structure_output": True
        }
    
    def optimize_for_small_model(
        self,
        messages: List[LLMMessage],
        max_length: int = 1000
    ) -> List[LLMMessage]:
        """
        Оптимизирует промпты для малых моделей
        
        Args:
            messages: Список сообщений
            max_length: Максимальная длина промпта
        
        Returns:
            Оптимизированный список сообщений
        """
        optimized = []
        
        for message in messages:
            if message.role == "system":
                # Системные промпты оптимизируем особенно тщательно
                optimized_content = self._optimize_system_prompt(
                    message.content,
                    max_length // 2
                )
            elif message.role == "user":
                # Пользовательские промпты оптимизируем менее агрессивно
                optimized_content = self._optimize_user_prompt(
                    message.content,
                    max_length
                )
            else:
                optimized_content = message.content
            
            optimized.append(LLMMessage(
                role=message.role,
                content=optimized_content
            ))
        
        return optimized
    
    def _optimize_system_prompt(self, content: str, max_length: int) -> str:
        """Оптимизирует системный промпт"""
        # Удаляем приветствия
        if self.optimization_rules["remove_greetings"]:
            content = self._remove_greetings(content)
        
        # Упрощаем инструкции
        if self.optimization_rules["simplify_instructions"]:
            content = self._simplify_instructions(content)
        
        # Сжимаем избыточность
        if self.optimization_rules["compress_redundancy"]:
            content = self._compress_redundancy(content)
        
        # Структурируем
        if self.optimization_rules["structure_output"]:
            content = self._structure_prompt(content)
        
        # Обрезаем если слишком длинный
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        return content
    
    def _optimize_user_prompt(self, content: str, max_length: int) -> str:
        """Оптимизирует пользовательский промпт"""
        # Менее агрессивная оптимизация для пользовательских промптов
        # Только сжатие избыточности
        if self.optimization_rules["compress_redundancy"]:
            content = self._compress_redundancy(content)
        
        # Обрезаем если слишком длинный
        if len(content) > max_length:
            # Пытаемся обрезать умно (по предложениям)
            sentences = content.split('. ')
            result = []
            for sentence in sentences:
                if len('. '.join(result + [sentence])) <= max_length:
                    result.append(sentence)
                else:
                    break
            content = '. '.join(result)
            if len(content) < len(content.split('. ')[0]):  # Если ничего не собрали
                content = content[:max_length]
        
        return content
    
    def _remove_greetings(self, content: str) -> str:
        """Удаляет приветствия и вежливые фразы"""
        greetings = [
            "Привет", "Здравствуй", "Добро пожаловать",
            "Hello", "Hi", "Welcome",
            "Спасибо", "Thank you", "Thanks"
        ]
        
        lines = content.split('\n')
        filtered = []
        for line in lines:
            line_lower = line.lower().strip()
            if not any(greeting.lower() in line_lower for greeting in greetings):
                filtered.append(line)
        
        return '\n'.join(filtered)
    
    def _simplify_instructions(self, content: str) -> str:
        """Упрощает инструкции"""
        # Заменяем сложные конструкции на простые
        replacements = {
            "необходимо": "нужно",
            "осуществить": "сделать",
            "реализовать": "создать",
            "обеспечить": "сделать",
            "предоставить": "дать",
            "необходимо убедиться": "проверить",
            "следует": "нужно",
        }
        
        for old, new in replacements.items():
            content = content.replace(old, new)
            content = content.replace(old.capitalize(), new.capitalize())
        
        return content
    
    def _compress_redundancy(self, content: str) -> str:
        """Сжимает избыточность"""
        # Удаляем повторяющиеся слова
        words = content.split()
        compressed = []
        prev_word = None
        
        for word in words:
            if word.lower() != prev_word:
                compressed.append(word)
                prev_word = word.lower()
            # Пропускаем повторения, но сохраняем структуру
        
        return ' '.join(compressed)
    
    def _structure_prompt(self, content: str) -> str:
        """Структурирует промпт для лучшего понимания"""
        # Добавляем нумерацию для списков
        lines = content.split('\n')
        structured = []
        list_counter = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Если строка начинается с дефиса или звездочки, нумеруем
            if stripped.startswith('-') or stripped.startswith('*'):
                list_counter += 1
                structured.append(f"{list_counter}. {stripped[1:].strip()}")
            else:
                structured.append(line)
                if stripped and not stripped.startswith(('1.', '2.', '3.')):
                    list_counter = 0  # Сбрасываем счетчик для нового списка
        
        return '\n'.join(structured)
    
    def create_compact_prompt(
        self,
        task: str,
        context: Optional[str] = None,
        examples: Optional[List[str]] = None
    ) -> str:
        """Создает компактный промпт для малых моделей"""
        parts = []
        
        # Задача (обязательно)
        parts.append(f"Задача: {task}")
        
        # Контекст (если есть, сжимаем)
        if context:
            # Берем только первые 200 символов контекста
            context_short = context[:200] + "..." if len(context) > 200 else context
            parts.append(f"Контекст: {context_short}")
        
        # Примеры (если есть, ограничиваем)
        if examples:
            # Берем только первый пример
            if len(examples) > 0:
                parts.append(f"Пример: {examples[0][:100]}")
        
        return "\n".join(parts)

