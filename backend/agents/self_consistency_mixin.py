"""
Self-Consistency Mixin - генерация нескольких вариантов с выбором лучшего.

Техника улучшения качества ответов через:
- Генерацию N независимых ответов
- Голосование за консенсус
- Выбор наиболее согласованного решения
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple
from abc import ABC

from ..core.logger import get_logger
from ..llm.base import LLMMessage

logger = get_logger(__name__)


@dataclass
class ConsistencyResult:
    """Результат self-consistency."""
    final_answer: str
    confidence: float  # 0.0 - 1.0
    agreement_score: float  # Степень согласия между ответами
    all_responses: List[str] = field(default_factory=list)
    vote_distribution: Dict[str, int] = field(default_factory=dict)
    selected_index: int = 0
    reasoning: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "confidence": round(self.confidence, 3),
            "agreement_score": round(self.agreement_score, 3),
            "responses_count": len(self.all_responses),
            "selected_index": self.selected_index,
            "reasoning": self.reasoning
        }


class SelfConsistencyMixin(ABC):
    """
    Миксин для генерации нескольких вариантов ответа с выбором лучшего.
    
    Техника Self-Consistency:
    1. Генерируем N независимых ответов (с температурой > 0)
    2. Анализируем согласованность между ответами
    3. Выбираем наиболее частый/консенсусный ответ
    4. Оцениваем уверенность на основе согласия
    
    Использование:
    - Критические задачи (генерация production кода)
    - Математические/логические задачи
    - Когда нужна высокая уверенность в ответе
    """
    
    # Требуемые атрибуты от основного класса
    llm_manager: Any
    name: str
    
    def __init__(self, *args, **kwargs):
        # Конфигурация self-consistency
        self._sc_enabled: bool = True
        self._sc_samples: int = 3
        self._sc_temperature: float = 0.7
        self._sc_min_agreement: float = 0.5  # Минимальное согласие для confidence
        super().__init__(*args, **kwargs)
    
    def configure_self_consistency(
        self,
        enabled: bool = True,
        samples: int = 3,
        temperature: float = 0.7,
        min_agreement: float = 0.5
    ) -> None:
        """
        Конфигурирует self-consistency.
        
        Args:
            enabled: Включить self-consistency
            samples: Количество генерируемых ответов
            temperature: Температура для генерации (выше = разнообразнее)
            min_agreement: Минимальное согласие для высокой уверенности
        """
        self._sc_enabled = enabled
        self._sc_samples = max(2, min(samples, 7))  # 2-7 samples
        self._sc_temperature = max(0.3, min(temperature, 1.0))
        self._sc_min_agreement = min_agreement
    
    async def generate_with_self_consistency(
        self,
        messages: List[LLMMessage],
        n_samples: Optional[int] = None,
        temperature: Optional[float] = None,
        extract_answer_fn: Optional[Callable[[str], str]] = None,
        **kwargs
    ) -> ConsistencyResult:
        """
        Генерирует ответ с использованием self-consistency.
        
        Args:
            messages: Список сообщений для LLM
            n_samples: Количество генерируемых ответов (default: configured)
            temperature: Температура генерации (default: configured)
            extract_answer_fn: Функция для извлечения ответа из полного текста
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            ConsistencyResult с лучшим ответом и метриками
        """
        n = n_samples or self._sc_samples
        temp = temperature or self._sc_temperature
        
        logger.debug(f"Self-consistency: generating {n} samples with temperature {temp}")
        
        # Генерируем N ответов параллельно
        tasks = []
        for i in range(n):
            tasks.append(self._generate_single_response(
                messages=messages,
                temperature=temp,
                **kwargs
            ))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем успешные ответы
        valid_responses: List[str] = []
        for resp in responses:
            if isinstance(resp, Exception):
                logger.warning(f"Self-consistency: sample failed: {resp}")
            elif resp:
                valid_responses.append(resp)
        
        if not valid_responses:
            raise RuntimeError("All self-consistency samples failed")
        
        if len(valid_responses) == 1:
            return ConsistencyResult(
                final_answer=valid_responses[0],
                confidence=0.5,  # Low confidence with single sample
                agreement_score=1.0,
                all_responses=valid_responses,
                selected_index=0
            )
        
        # Извлекаем ответы если указана функция
        answers = valid_responses
        if extract_answer_fn:
            try:
                answers = [extract_answer_fn(r) for r in valid_responses]
            except Exception as e:
                logger.warning(f"Answer extraction failed: {e}")
        
        # Анализируем консенсус
        result = await self._analyze_consensus(
            responses=valid_responses,
            answers=answers
        )
        
        return result
    
    async def _generate_single_response(
        self,
        messages: List[LLMMessage],
        temperature: float,
        **kwargs
    ) -> str:
        """Генерирует один ответ от LLM."""
        if not self.llm_manager:
            raise RuntimeError("LLM manager not available")
        
        response = await self.llm_manager.generate(
            messages=messages,
            temperature=temperature,
            **kwargs
        )
        
        return response.content
    
    async def _analyze_consensus(
        self,
        responses: List[str],
        answers: List[str]
    ) -> ConsistencyResult:
        """
        Анализирует консенсус между ответами.
        
        Методы определения консенсуса:
        1. Простое голосование (для коротких ответов)
        2. Семантическое сравнение через LLM (для сложных ответов)
        3. Структурное сравнение (для кода)
        """
        len(responses)
        
        # Для простых коротких ответов используем точное совпадение
        if all(len(a) < 100 for a in answers):
            return self._simple_voting(responses, answers)
        
        # Для сложных ответов используем LLM для оценки
        if self.llm_manager:
            try:
                return await self._llm_consensus(responses, answers)
            except Exception as e:
                logger.warning(f"LLM consensus failed: {e}, falling back to simple voting")
        
        # Fallback к простому голосованию
        return self._simple_voting(responses, answers)
    
    def _simple_voting(
        self,
        responses: List[str],
        answers: List[str]
    ) -> ConsistencyResult:
        """
        Простое голосование по точному совпадению ответов.
        """
        # Считаем голоса
        vote_counts: Dict[str, int] = {}
        answer_to_response: Dict[str, int] = {}  # Сохраняем индекс полного ответа
        
        for i, answer in enumerate(answers):
            # Нормализуем ответ для сравнения
            normalized = answer.strip().lower()
            vote_counts[normalized] = vote_counts.get(normalized, 0) + 1
            if normalized not in answer_to_response:
                answer_to_response[normalized] = i
        
        # Находим победителя
        if not vote_counts:
            return ConsistencyResult(
                final_answer=responses[0],
                confidence=0.5,
                agreement_score=0.0,
                all_responses=responses
            )
        
        winner = max(vote_counts.items(), key=lambda x: x[1])
        winner_normalized, winner_votes = winner
        selected_idx = answer_to_response[winner_normalized]
        
        # Вычисляем метрики
        total_votes = len(answers)
        agreement_score = winner_votes / total_votes
        
        # Confidence на основе согласия и количества уникальных ответов
        unique_answers = len(vote_counts)
        diversity_penalty = (unique_answers - 1) / total_votes  # Больше разных = ниже confidence
        confidence = agreement_score * (1 - diversity_penalty * 0.3)
        
        return ConsistencyResult(
            final_answer=responses[selected_idx],
            confidence=confidence,
            agreement_score=agreement_score,
            all_responses=responses,
            vote_distribution={k: v for k, v in vote_counts.items()},
            selected_index=selected_idx,
            reasoning=f"Selected by voting: {winner_votes}/{total_votes} agreement"
        )
    
    async def _llm_consensus(
        self,
        responses: List[str],
        answers: List[str]
    ) -> ConsistencyResult:
        """
        Использует LLM для определения консенсуса.
        """
        # Формируем промпт для оценки
        responses_text = "\n\n".join(
            f"=== Response {i+1} ===\n{r[:1000]}"
            for i, r in enumerate(answers)
        )
        
        consensus_prompt = f"""Analyze these {len(answers)} responses to the same question.
Determine which response is the best based on:
1. Correctness and accuracy
2. Completeness
3. Clarity
4. Agreement with other responses

{responses_text}

Respond in JSON format:
{{
    "best_response": <1-{len(answers)}>,
    "agreement_score": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

JSON response:"""

        try:
            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=consensus_prompt)],
                temperature=0.1,
                max_tokens=200
            )
            
            # Парсим JSON
            import json
            import re
            
            text = response.content
            # Извлекаем JSON
            json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                best_idx = int(data.get("best_response", 1)) - 1
                best_idx = max(0, min(best_idx, len(responses) - 1))
                
                agreement = float(data.get("agreement_score", 0.5))
                reasoning = data.get("reasoning", "")
                
                # Confidence на основе agreement и качества анализа
                confidence = agreement * 0.8 + 0.2  # Min 0.2 for having done analysis
                
                return ConsistencyResult(
                    final_answer=responses[best_idx],
                    confidence=confidence,
                    agreement_score=agreement,
                    all_responses=responses,
                    selected_index=best_idx,
                    reasoning=reasoning
                )
        except Exception as e:
            logger.debug(f"LLM consensus parsing failed: {e}")
        
        # Fallback
        return self._simple_voting(responses, answers)
    
    async def generate_with_verification(
        self,
        messages: List[LLMMessage],
        verification_prompt: str,
        **kwargs
    ) -> Tuple[str, float]:
        """
        Генерирует ответ и верифицирует его.
        
        Args:
            messages: Сообщения для генерации
            verification_prompt: Промпт для верификации ответа
            **kwargs: Дополнительные параметры
            
        Returns:
            Tuple[ответ, уверенность]
        """
        # Сначала генерируем ответ
        response = await self._generate_single_response(
            messages=messages,
            temperature=0.3,  # Низкая температура для основного ответа
            **kwargs
        )
        
        # Затем верифицируем
        verification = verification_prompt.format(answer=response)
        
        verify_response = await self.llm_manager.generate(
            messages=[
                LLMMessage(
                    role="system",
                    content="You are a careful verifier. Rate the correctness of the answer on a scale 0-100."
                ),
                LLMMessage(role="user", content=verification)
            ],
            temperature=0.1,
            max_tokens=50
        )
        
        # Извлекаем score
        import re
        match = re.search(r'\b(\d{1,3})\b', verify_response.content)
        if match:
            score = int(match.group(1))
            confidence = min(score / 100, 1.0)
        else:
            confidence = 0.5  # Default если не удалось извлечь
        
        return response, confidence


def extract_code_answer(response: str) -> str:
    """
    Извлекает код из ответа для сравнения.
    Убирает markdown, комментарии и пустые строки.
    """
    import re
    
    # Извлекаем код из markdown
    code_match = re.search(r'```\w*\n(.*?)```', response, re.DOTALL)
    if code_match:
        code = code_match.group(1)
    else:
        code = response
    
    # Убираем комментарии и пустые строки для сравнения
    lines = []
    for line in code.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('//'):
            lines.append(line)
    
    return '\n'.join(lines)


def extract_numeric_answer(response: str) -> str:
    """
    Извлекает числовой ответ.
    """
    import re
    
    # Ищем финальный ответ
    patterns = [
        r'(?:answer|result|итог|ответ)[:\s]+(\d+(?:\.\d+)?)',
        r'(?:=\s*)(\d+(?:\.\d+)?)\s*$',
        r'(\d+(?:\.\d+)?)\s*$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    
    return response.strip()

