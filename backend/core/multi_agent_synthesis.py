"""
Multi-Agent Synthesis - синтез результатов от нескольких агентов.

Обеспечивает:
- Объединение результатов от разных агентов
- Разрешение конфликтов между ответами
- Генерацию консолидированного ответа
- Оценку качества синтеза
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from .logger import get_logger
from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage

logger = get_logger(__name__)


class SynthesisStrategy(Enum):
    """Стратегия синтеза."""
    MERGE = "merge"              # Объединить все результаты
    SELECT_BEST = "select_best"  # Выбрать лучший результат
    HIERARCHICAL = "hierarchical"  # Иерархическое объединение
    CONSENSUS = "consensus"      # Найти консенсус
    DEBATE = "debate"            # Мульти-агентные дебаты


@dataclass
class AgentResult:
    """Результат от агента."""
    agent_name: str
    agent_type: str
    result: Dict[str, Any]
    success: bool
    confidence: float = 0.5
    execution_time: float = 0.0
    
    def get_content(self) -> str:
        """Извлекает основное содержимое результата."""
        result = self.result
        return (
            result.get("code") or
            result.get("report") or
            result.get("analysis") or
            result.get("final_answer") or
            result.get("answer") or
            str(result.get("result", ""))
        )


@dataclass
class SynthesisResult:
    """Результат синтеза."""
    synthesized_content: str
    strategy_used: SynthesisStrategy
    confidence: float
    contributing_agents: List[str]
    conflicts_resolved: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "synthesized_content": self.synthesized_content,
            "strategy": self.strategy_used.value,
            "confidence": round(self.confidence, 3),
            "contributing_agents": self.contributing_agents,
            "conflicts_resolved": self.conflicts_resolved,
            "quality_score": round(self.quality_score, 3),
            "metadata": self.metadata
        }


class MultiAgentSynthesizer:
    """
    Синтезатор результатов от нескольких агентов.
    
    Особенности:
    - Умное объединение результатов
    - Разрешение противоречий через LLM
    - Оценка качества синтеза
    - Поддержка разных стратегий
    """
    
    def __init__(
        self,
        llm_manager: LLMProviderManager,
        default_strategy: SynthesisStrategy = SynthesisStrategy.MERGE
    ):
        """
        Инициализация.
        
        Args:
            llm_manager: LLM провайдер
            default_strategy: Стратегия синтеза по умолчанию
        """
        self.llm_manager = llm_manager
        self.default_strategy = default_strategy
    
    async def synthesize(
        self,
        results: List[AgentResult],
        original_task: str,
        strategy: Optional[SynthesisStrategy] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> SynthesisResult:
        """
        Синтезирует результаты от нескольких агентов.
        
        Args:
            results: Результаты от агентов
            original_task: Исходная задача
            strategy: Стратегия синтеза
            context: Дополнительный контекст
            
        Returns:
            Синтезированный результат
        """
        if not results:
            return SynthesisResult(
                synthesized_content="Нет результатов для синтеза",
                strategy_used=self.default_strategy,
                confidence=0.0,
                contributing_agents=[]
            )
        
        # Если только один результат, возвращаем его
        if len(results) == 1:
            return SynthesisResult(
                synthesized_content=results[0].get_content(),
                strategy_used=SynthesisStrategy.SELECT_BEST,
                confidence=results[0].confidence,
                contributing_agents=[results[0].agent_name]
            )
        
        strategy = strategy or self.default_strategy
        
        logger.info(
            f"Synthesizing {len(results)} agent results using strategy: {strategy.value}"
        )
        
        # Выбираем метод синтеза
        if strategy == SynthesisStrategy.MERGE:
            return await self._merge_results(results, original_task)
        elif strategy == SynthesisStrategy.SELECT_BEST:
            return await self._select_best(results, original_task)
        elif strategy == SynthesisStrategy.HIERARCHICAL:
            return await self._hierarchical_synthesis(results, original_task)
        elif strategy == SynthesisStrategy.CONSENSUS:
            return await self._find_consensus(results, original_task)
        elif strategy == SynthesisStrategy.DEBATE:
            return await self._multi_agent_debate(results, original_task)
        else:
            return await self._merge_results(results, original_task)
    
    async def _merge_results(
        self,
        results: List[AgentResult],
        original_task: str
    ) -> SynthesisResult:
        """
        Объединяет результаты от всех агентов.
        """
        # Формируем контент для объединения
        agents_content = []
        for r in results:
            if r.success:
                content = r.get_content()
                if content:
                    agents_content.append({
                        "agent": r.agent_name,
                        "type": r.agent_type,
                        "content": content[:3000],  # Ограничиваем размер
                        "confidence": r.confidence
                    })
        
        if not agents_content:
            return SynthesisResult(
                synthesized_content="Все агенты завершились без результата",
                strategy_used=SynthesisStrategy.MERGE,
                confidence=0.0,
                contributing_agents=[]
            )
        
        # Формируем промпт для синтеза
        agents_text = "\n\n".join(
            f"=== {a['agent']} ({a['type']}) [confidence: {a['confidence']:.2f}] ===\n{a['content']}"
            for a in agents_content
        )
        
        synthesis_prompt = f"""Объедини и синтезируй результаты от нескольких экспертных агентов в ЕДИНЫЙ, СВЯЗНЫЙ ответ.

## ИСХОДНАЯ ЗАДАЧА:
{original_task}

## РЕЗУЛЬТАТЫ АГЕНТОВ:
{agents_text}

## ТРЕБОВАНИЯ К СИНТЕЗУ:
1. Объедини лучшие идеи и находки от каждого агента
2. Устрани противоречия и дублирование
3. Сохрани структуру и форматирование
4. Добавь свои выводы если нужно
5. Создай логичный, связный текст
6. Если есть код от нескольких агентов — выбери лучший или объедини

## ФОРМАТ ОТВЕТА:
- Используй markdown для структуры
- Начни с краткого резюме
- Включи все ключевые находки
- Завершай конкретными рекомендациями

СИНТЕЗИРОВАННЫЙ ОТВЕТ:"""

        try:
            response = await self.llm_manager.generate(
                messages=[
                    LLMMessage(
                        role="system",
                        content="Ты эксперт по синтезу информации. Объединяй результаты от разных источников в единый связный ответ."
                    ),
                    LLMMessage(role="user", content=synthesis_prompt)
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            # Оценка качества синтеза
            quality = await self._evaluate_synthesis_quality(
                response.content,
                [a["content"] for a in agents_content],
                original_task
            )
            
            # Вычисляем среднюю уверенность
            avg_confidence = sum(a["confidence"] for a in agents_content) / len(agents_content)
            
            return SynthesisResult(
                synthesized_content=response.content,
                strategy_used=SynthesisStrategy.MERGE,
                confidence=avg_confidence * quality,  # Комбинированная уверенность
                contributing_agents=[a["agent"] for a in agents_content],
                quality_score=quality,
                metadata={
                    "agents_count": len(agents_content),
                    "avg_agent_confidence": avg_confidence
                }
            )
            
        except Exception as e:
            logger.error(f"Merge synthesis failed: {e}")
            # Fallback: просто объединяем тексты
            fallback_content = "\n\n---\n\n".join(
                f"## {a['agent']}\n{a['content']}"
                for a in agents_content
            )
            return SynthesisResult(
                synthesized_content=fallback_content,
                strategy_used=SynthesisStrategy.MERGE,
                confidence=0.3,
                contributing_agents=[a["agent"] for a in agents_content]
            )
    
    async def _select_best(
        self,
        results: List[AgentResult],
        original_task: str
    ) -> SynthesisResult:
        """
        Выбирает лучший результат.
        """
        successful = [r for r in results if r.success]
        
        if not successful:
            return SynthesisResult(
                synthesized_content="Все агенты завершились с ошибкой",
                strategy_used=SynthesisStrategy.SELECT_BEST,
                confidence=0.0,
                contributing_agents=[]
            )
        
        if len(successful) == 1:
            return SynthesisResult(
                synthesized_content=successful[0].get_content(),
                strategy_used=SynthesisStrategy.SELECT_BEST,
                confidence=successful[0].confidence,
                contributing_agents=[successful[0].agent_name]
            )
        
        # Используем LLM для выбора лучшего
        candidates = []
        for i, r in enumerate(successful):
            content = r.get_content()
            candidates.append(f"=== Option {i+1} ({r.agent_name}) ===\n{content[:1500]}")
        
        selection_prompt = f"""Выбери ЛУЧШИЙ ответ на задачу из предложенных вариантов.

ЗАДАЧА: {original_task}

ВАРИАНТЫ:
{chr(10).join(candidates)}

Ответь в формате JSON:
{{
    "best_option": <номер 1-{len(candidates)}>,
    "reason": "<кратко почему этот вариант лучше>",
    "score": <0.0-1.0>
}}

JSON:"""

        try:
            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=selection_prompt)],
                temperature=0.1,
                max_tokens=200
            )
            
            import json
            import re
            
            match = re.search(r'\{[^}]+\}', response.content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                best_idx = int(data.get("best_option", 1)) - 1
                best_idx = max(0, min(best_idx, len(successful) - 1))
                score = float(data.get("score", 0.5))
                reason = data.get("reason", "")
                
                best = successful[best_idx]
                return SynthesisResult(
                    synthesized_content=best.get_content(),
                    strategy_used=SynthesisStrategy.SELECT_BEST,
                    confidence=score,
                    contributing_agents=[best.agent_name],
                    metadata={"selection_reason": reason}
                )
        except Exception as e:
            logger.warning(f"Best selection failed: {e}")
        
        # Fallback: выбираем по confidence
        best = max(successful, key=lambda r: r.confidence)
        return SynthesisResult(
            synthesized_content=best.get_content(),
            strategy_used=SynthesisStrategy.SELECT_BEST,
            confidence=best.confidence,
            contributing_agents=[best.agent_name]
        )
    
    async def _hierarchical_synthesis(
        self,
        results: List[AgentResult],
        original_task: str
    ) -> SynthesisResult:
        """
        Иерархический синтез: сначала группируем похожие, потом объединяем.
        """
        successful = [r for r in results if r.success]
        
        if len(successful) <= 2:
            return await self._merge_results(results, original_task)
        
        # Группируем по типу агента
        groups: Dict[str, List[AgentResult]] = {}
        for r in successful:
            key = r.agent_type
            if key not in groups:
                groups[key] = []
            groups[key].append(r)
        
        # Синтезируем внутри каждой группы
        group_syntheses: List[AgentResult] = []
        
        for agent_type, group_results in groups.items():
            if len(group_results) == 1:
                group_syntheses.append(group_results[0])
            else:
                # Синтезируем группу
                group_synthesis = await self._merge_results(group_results, original_task)
                group_syntheses.append(AgentResult(
                    agent_name=f"synthesized_{agent_type}",
                    agent_type=agent_type,
                    result={"content": group_synthesis.synthesized_content},
                    success=True,
                    confidence=group_synthesis.confidence
                ))
        
        # Финальный синтез всех групп
        return await self._merge_results(group_syntheses, original_task)
    
    async def _find_consensus(
        self,
        results: List[AgentResult],
        original_task: str
    ) -> SynthesisResult:
        """
        Находит консенсус между результатами.
        """
        successful = [r for r in results if r.success]
        
        if len(successful) < 2:
            return await self._select_best(results, original_task)
        
        # Формируем промпт для поиска консенсуса
        contents = [r.get_content()[:2000] for r in successful]
        
        consensus_prompt = f"""Найди КОНСЕНСУС между этими ответами. Определи:
1. На чём ВСЕ агенты согласны
2. В чём есть расхождения
3. Сформулируй финальный ответ на основе консенсуса

ЗАДАЧА: {original_task}

ОТВЕТЫ АГЕНТОВ:
{chr(10).join(f"=== {r.agent_name} ===\n{c}" for r, c in zip(successful, contents))}

Ответ:
## Консенсус (на чём все согласны):
[список пунктов]

## Расхождения:
[где мнения расходятся]

## Финальный ответ:
[объединённый ответ на основе консенсуса]"""

        try:
            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=consensus_prompt)],
                temperature=0.2,
                max_tokens=3000
            )
            
            return SynthesisResult(
                synthesized_content=response.content,
                strategy_used=SynthesisStrategy.CONSENSUS,
                confidence=0.7,  # Консенсус даёт среднюю уверенность
                contributing_agents=[r.agent_name for r in successful]
            )
            
        except Exception as e:
            logger.warning(f"Consensus failed: {e}")
            return await self._merge_results(results, original_task)
    
    async def _multi_agent_debate(
        self,
        results: List[AgentResult],
        original_task: str,
        max_rounds: int = 2
    ) -> SynthesisResult:
        """
        Мульти-агентные дебаты для улучшения качества.
        
        Агенты критикуют и улучшают ответы друг друга.
        """
        successful = [r for r in results if r.success]
        
        if len(successful) < 2:
            return await self._select_best(results, original_task)
        
        current_answers = [r.get_content()[:2000] for r in successful]
        agent_names = [r.agent_name for r in successful]
        
        for round_num in range(max_rounds):
            logger.debug(f"Debate round {round_num + 1}/{max_rounds}")
            
            # Каждый агент критикует других
            improved_answers = []
            
            for i, (answer, name) in enumerate(zip(current_answers, agent_names)):
                other_answers = [
                    f"**{agent_names[j]}**: {a[:500]}"
                    for j, a in enumerate(current_answers)
                    if j != i
                ]
                
                debate_prompt = f"""Ты играешь роль агента {name}.
Ваш текущий ответ на задачу:
{answer}

Другие агенты ответили:
{chr(10).join(other_answers)}

ЗАДАЧА: {original_task}

Проанализируй ответы других агентов. Учти их критику и улучшения.
Сформулируй УЛУЧШЕННЫЙ ответ, включая лучшие идеи от всех агентов.

Улучшенный ответ:"""

                try:
                    response = await self.llm_manager.generate(
                        messages=[LLMMessage(role="user", content=debate_prompt)],
                        temperature=0.4,
                        max_tokens=2000
                    )
                    improved_answers.append(response.content)
                except Exception as e:
                    logger.warning(f"Debate round failed for {name}: {e}")
                    improved_answers.append(answer)
            
            current_answers = improved_answers
        
        # Финальный синтез после дебатов
        debate_results = [
            AgentResult(
                agent_name=f"{name}_debated",
                agent_type=successful[i].agent_type,
                result={"content": answer},
                success=True,
                confidence=0.8  # Повышенная уверенность после дебатов
            )
            for i, (name, answer) in enumerate(zip(agent_names, current_answers))
        ]
        
        result = await self._merge_results(debate_results, original_task)
        result.strategy_used = SynthesisStrategy.DEBATE
        result.metadata["debate_rounds"] = max_rounds
        
        return result
    
    async def _evaluate_synthesis_quality(
        self,
        synthesis: str,
        original_contents: List[str],
        original_task: str
    ) -> float:
        """
        Оценивает качество синтеза.
        
        Returns:
            Оценка качества от 0.0 до 1.0
        """
        try:
            eval_prompt = f"""Оцени качество синтеза результатов от 0 до 100.

ЗАДАЧА: {original_task[:200]}

СИНТЕЗ:
{synthesis[:1500]}

Критерии:
- Полнота (все ключевые идеи включены)
- Связность (логичное изложение)
- Отсутствие противоречий
- Практичность (полезные выводы)

Ответь ТОЛЬКО числом от 0 до 100:"""

            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=eval_prompt)],
                temperature=0.1,
                max_tokens=10
            )
            
            import re
            match = re.search(r'\b(\d{1,3})\b', response.content)
            if match:
                score = int(match.group(1))
                return min(score / 100, 1.0)
            
        except Exception as e:
            logger.debug(f"Quality evaluation failed: {e}")
        
        return 0.5  # Default quality


# Глобальный экземпляр
_synthesizer: Optional[MultiAgentSynthesizer] = None


def get_multi_agent_synthesizer(
    llm_manager: LLMProviderManager
) -> MultiAgentSynthesizer:
    """Получить экземпляр MultiAgentSynthesizer."""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = MultiAgentSynthesizer(llm_manager)
    return _synthesizer

