"""
Semantic Code Search - умный поиск по коду с пониманием семантики.

Обеспечивает:
- Семантический поиск по функциям, классам, методам
- Поиск по описанию функциональности
- Поиск по паттернам использования
- Re-ranking результатов через LLM
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from ..core.logger import get_logger
from ..project.code_intelligence import (
    CodeIntelligence, 
    CodeEntity, 
    EntityType,
    get_code_intelligence
)
from .vector_store import VectorStore
from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage

logger = get_logger(__name__)


@dataclass
class CodeSearchResult:
    """Результат поиска по коду."""
    entity: CodeEntity
    score: float  # Similarity score
    relevance_score: float  # LLM-based relevance (if re-ranked)
    context: Optional[str] = None  # Окружающий код
    explanation: Optional[str] = None  # Объяснение релевантности
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity.to_dict(),
            "score": self.score,
            "relevance_score": self.relevance_score,
            "context": self.context,
            "explanation": self.explanation
        }


class SemanticCodeSearch:
    """
    Умный поиск по коду с пониманием семантики.
    
    Особенности:
    - Индексирует функции/классы как семантические единицы
    - Поддерживает естественные запросы на русском и английском
    - Re-ranking через LLM для повышения точности
    - Инкрементальное обновление индекса
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        llm_manager: Optional[LLMProviderManager] = None,
        code_intelligence: Optional[CodeIntelligence] = None
    ):
        """
        Инициализация.
        
        Args:
            vector_store: Векторное хранилище для эмбеддингов
            llm_manager: LLM провайдер для re-ranking (опционально)
            code_intelligence: Анализатор кода
        """
        self.vector_store = vector_store
        self.llm_manager = llm_manager
        self.code_intelligence = code_intelligence or get_code_intelligence()
        
        # Кэш проиндексированных сущностей
        self._indexed_entities: Dict[str, CodeEntity] = {}
        self._project_path: Optional[str] = None
    
    async def index_project(
        self,
        project_path: str,
        max_files: int = 500,
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        Индексирует проект для семантического поиска.
        
        Args:
            project_path: Путь к проекту
            max_files: Максимальное количество файлов
            force_reindex: Принудительная переиндексация
            
        Returns:
            Статистика индексирования
        """
        if self._project_path == project_path and not force_reindex:
            logger.info(f"Project {project_path} already indexed, skipping")
            return {
                "status": "cached",
                "entities_indexed": len(self._indexed_entities)
            }
        
        logger.info(f"Indexing project for semantic search: {project_path}")
        
        # Анализируем проект
        analysis = await self.code_intelligence.analyze_project(project_path, max_files)
        
        if "error" in analysis:
            return {"status": "error", "error": analysis["error"]}
        
        # Собираем все сущности
        entities: List[CodeEntity] = []
        for module_data in analysis.get("modules", {}).values():
            for entity_data in module_data.get("entities", []):
                entity = self._dict_to_entity(entity_data)
                entities.append(entity)
        
        # Создаём эмбеддинги для сущностей
        documents = []
        metadatas = []
        
        for entity in entities:
            # Создаём богатый текст для эмбеддинга
            semantic_text = entity.get_semantic_text()
            documents.append(semantic_text)
            
            metadata = {
                "entity_id": entity.qualified_name,
                "entity_type": entity.type.value,
                "name": entity.name,
                "file_path": entity.file_path,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
                "complexity": entity.complexity,
            }
            metadatas.append(metadata)
            
            # Кэшируем сущность
            self._indexed_entities[entity.qualified_name] = entity
        
        # Добавляем в векторное хранилище
        if documents:
            await self.vector_store.add_documents(documents, metadatas)
            await self.vector_store.save()
        
        self._project_path = project_path
        
        logger.info(f"Indexed {len(entities)} code entities")
        
        return {
            "status": "success",
            "entities_indexed": len(entities),
            "files_analyzed": analysis.get("files_analyzed", 0),
            "total_complexity": analysis.get("total_complexity", 0),
            "entity_stats": analysis.get("entity_stats", {})
        }
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        entity_types: Optional[List[EntityType]] = None,
        min_score: float = 0.3,
        use_reranking: bool = True,
        include_context: bool = True
    ) -> List[CodeSearchResult]:
        """
        Семантический поиск по коду.
        
        Args:
            query: Поисковый запрос на естественном языке
            top_k: Количество результатов
            entity_types: Фильтр по типам сущностей
            min_score: Минимальный score для результатов
            use_reranking: Использовать LLM для re-ranking
            include_context: Включить окружающий код
            
        Returns:
            Список результатов поиска
        """
        # Расширяем запрос для лучшего поиска
        expanded_query = await self._expand_query(query)
        
        # Поиск в векторном хранилище
        raw_results = await self.vector_store.search(
            expanded_query,
            top_k=top_k * 2,  # Берём больше для фильтрации
            use_reranking=False  # Re-rank сами
        )
        
        # Преобразуем в CodeSearchResult
        results: List[CodeSearchResult] = []
        
        for raw in raw_results:
            score = raw.get("score", 0)
            if score < min_score:
                continue
            
            metadata = raw.get("metadata", {})
            entity_id = metadata.get("entity_id")
            
            if not entity_id:
                continue
            
            # Получаем сущность из кэша
            entity = self._indexed_entities.get(entity_id)
            if not entity:
                # Пробуем восстановить из метаданных
                entity = self._metadata_to_entity(metadata)
            
            if not entity:
                continue
            
            # Фильтр по типу
            if entity_types and entity.type not in entity_types:
                continue
            
            # Получаем контекст (исходный код)
            context = None
            if include_context:
                context = await self._get_code_context(entity)
            
            results.append(CodeSearchResult(
                entity=entity,
                score=score,
                relevance_score=score,  # Будет обновлено при re-ranking
                context=context
            ))
        
        # Re-ranking через LLM
        if use_reranking and self.llm_manager and results:
            results = await self._rerank_results(query, results[:top_k * 2])
        
        # Сортируем по релевантности и обрезаем
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:top_k]
    
    async def search_by_pattern(
        self,
        pattern: str,
        pattern_type: str = "usage"
    ) -> List[CodeSearchResult]:
        """
        Поиск по паттерну использования.
        
        Args:
            pattern: Паттерн (например, "async with", "try except")
            pattern_type: Тип паттерна (usage, decorator, import)
            
        Returns:
            Список результатов
        """
        results = []
        
        for entity in self._indexed_entities.values():
            match_score = 0
            
            if pattern_type == "usage":
                # Ищем в зависимостях
                if any(pattern.lower() in dep.lower() for dep in entity.dependencies):
                    match_score = 0.8
            elif pattern_type == "decorator":
                # Ищем в декораторах
                if any(pattern.lower() in dec.lower() for dec in entity.decorators):
                    match_score = 0.9
            elif pattern_type == "signature":
                # Ищем в сигнатуре
                if entity.signature and pattern.lower() in entity.signature.lower():
                    match_score = 0.85
            
            if match_score > 0:
                results.append(CodeSearchResult(
                    entity=entity,
                    score=match_score,
                    relevance_score=match_score
                ))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:20]
    
    async def find_similar_code(
        self,
        code_snippet: str,
        top_k: int = 5
    ) -> List[CodeSearchResult]:
        """
        Находит похожий код по сниппету.
        
        Args:
            code_snippet: Фрагмент кода
            top_k: Количество результатов
            
        Returns:
            Список похожих сущностей
        """
        # Используем сам код как запрос
        return await self.search(
            query=f"Code similar to:\n{code_snippet}",
            top_k=top_k,
            use_reranking=True
        )
    
    async def get_entity_by_name(
        self,
        name: str,
        exact_match: bool = False
    ) -> Optional[CodeEntity]:
        """
        Получает сущность по имени.
        
        Args:
            name: Имя сущности
            exact_match: Требовать точное совпадение
            
        Returns:
            Сущность или None
        """
        name_lower = name.lower()
        
        for entity_id, entity in self._indexed_entities.items():
            if exact_match:
                if entity.name == name:
                    return entity
            else:
                if name_lower in entity.name.lower() or name_lower in entity_id.lower():
                    return entity
        
        return None
    
    async def _expand_query(self, query: str) -> str:
        """
        Расширяет запрос для улучшения поиска.
        
        Args:
            query: Исходный запрос
            
        Returns:
            Расширенный запрос
        """
        if not self.llm_manager:
            return query
        
        # Для простых запросов не расширяем
        if len(query.split()) <= 3:
            return query
        
        try:
            expansion_prompt = f"""Expand this code search query with relevant technical terms.
Keep the expansion concise (max 2-3 additional terms).

Query: {query}

Expanded query (include original + relevant terms):"""

            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=expansion_prompt)],
                temperature=0.3,
                max_tokens=100
            )
            
            expanded = response.content.strip()
            
            # Убеждаемся, что оригинальный запрос включён
            if query.lower() not in expanded.lower():
                expanded = f"{query} {expanded}"
            
            return expanded[:500]  # Ограничиваем длину
            
        except Exception as e:
            logger.debug(f"Query expansion failed: {e}")
            return query
    
    async def _rerank_results(
        self,
        query: str,
        results: List[CodeSearchResult]
    ) -> List[CodeSearchResult]:
        """
        Re-ranking результатов через LLM.
        
        Args:
            query: Поисковый запрос
            results: Список результатов
            
        Returns:
            Переупорядоченный список
        """
        if not self.llm_manager or not results:
            return results
        
        try:
            # Формируем список для оценки
            candidates = []
            for i, result in enumerate(results[:10]):  # Только топ-10
                candidates.append(
                    f"{i+1}. {result.entity.type.value} {result.entity.name}: "
                    f"{result.entity.docstring[:100] if result.entity.docstring else 'No description'}"
                )
            
            rerank_prompt = f"""Rate the relevance of these code entities to the query.
Return ONLY a comma-separated list of numbers (1-10) in order of relevance.
Most relevant first.

Query: {query}

Candidates:
{chr(10).join(candidates)}

Order (comma-separated numbers, most relevant first):"""

            response = await self.llm_manager.generate(
                messages=[LLMMessage(role="user", content=rerank_prompt)],
                temperature=0.1,
                max_tokens=50
            )
            
            # Парсим ответ
            order_str = response.content.strip()
            order = []
            for part in order_str.replace(" ", "").split(","):
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(results):
                        order.append(idx)
                except ValueError:
                    continue
            
            # Переупорядочиваем результаты
            if order:
                reranked = []
                seen = set()
                
                for idx in order:
                    if idx not in seen:
                        result = results[idx]
                        # Обновляем relevance_score
                        result.relevance_score = 1.0 - (len(reranked) / len(order))
                        reranked.append(result)
                        seen.add(idx)
                
                # Добавляем оставшиеся
                for i, result in enumerate(results):
                    if i not in seen:
                        reranked.append(result)
                
                return reranked
            
        except Exception as e:
            logger.debug(f"Re-ranking failed: {e}")
        
        return results
    
    async def _get_code_context(
        self,
        entity: CodeEntity,
        context_lines: int = 3
    ) -> Optional[str]:
        """
        Получает исходный код сущности с контекстом.
        
        Args:
            entity: Сущность кода
            context_lines: Количество строк контекста
            
        Returns:
            Исходный код или None
        """
        try:
            file_path = Path(entity.file_path)
            if not file_path.exists():
                return None
            
            lines = file_path.read_text(encoding="utf-8", errors="ignore").split("\n")
            
            start = max(0, entity.start_line - 1 - context_lines)
            end = min(len(lines), entity.end_line + context_lines)
            
            code_lines = lines[start:end]
            
            # Добавляем номера строк
            numbered_lines = []
            for i, line in enumerate(code_lines, start=start + 1):
                prefix = ">> " if entity.start_line <= i <= entity.end_line else "   "
                numbered_lines.append(f"{prefix}{i:4d} | {line}")
            
            return "\n".join(numbered_lines)
            
        except Exception as e:
            logger.debug(f"Cannot get code context: {e}")
            return None
    
    def _dict_to_entity(self, data: Dict[str, Any]) -> CodeEntity:
        """Преобразует словарь в CodeEntity."""
        return CodeEntity(
            type=EntityType(data.get("type", "function")),
            name=data.get("name", ""),
            qualified_name=data.get("qualified_name", ""),
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            docstring=data.get("docstring"),
            signature=data.get("signature"),
            dependencies=data.get("dependencies", []),
            imports=data.get("imports", []),
            complexity=data.get("complexity", 1),
            decorators=data.get("decorators", []),
            parent=data.get("parent"),
            children=data.get("children", [])
        )
    
    def _metadata_to_entity(self, metadata: Dict[str, Any]) -> Optional[CodeEntity]:
        """Восстанавливает сущность из метаданных."""
        try:
            return CodeEntity(
                type=EntityType(metadata.get("entity_type", "function")),
                name=metadata.get("name", "unknown"),
                qualified_name=metadata.get("entity_id", ""),
                file_path=metadata.get("file_path", ""),
                start_line=metadata.get("start_line", 0),
                end_line=metadata.get("end_line", 0),
                complexity=metadata.get("complexity", 1)
            )
        except Exception:
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику индекса."""
        entity_types = {}
        total_complexity = 0
        
        for entity in self._indexed_entities.values():
            type_name = entity.type.value
            entity_types[type_name] = entity_types.get(type_name, 0) + 1
            total_complexity += entity.complexity
        
        return {
            "project_path": self._project_path,
            "total_entities": len(self._indexed_entities),
            "entity_types": entity_types,
            "total_complexity": total_complexity,
            "average_complexity": total_complexity / max(len(self._indexed_entities), 1)
        }
    
    def clear_index(self) -> None:
        """Очищает индекс."""
        self._indexed_entities.clear()
        self._project_path = None


# Глобальный экземпляр
_semantic_search: Optional[SemanticCodeSearch] = None


def get_semantic_code_search(
    vector_store: VectorStore,
    llm_manager: Optional[LLMProviderManager] = None
) -> SemanticCodeSearch:
    """Получить экземпляр SemanticCodeSearch."""
    global _semantic_search
    if _semantic_search is None:
        _semantic_search = SemanticCodeSearch(vector_store, llm_manager)
    return _semantic_search

