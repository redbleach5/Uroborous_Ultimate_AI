"""
Context Manager for hierarchical context management and query expansion
"""

from typing import List, Dict, Any, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..config import ContextConfig
from .vector_store import VectorStore
from ..llm.providers import LLMProviderManager
from ..llm.base import LLMMessage
from ..core.exceptions import AILLMException
from ..core.advanced_cache import AdvancedCache
from ..core.pydantic_utils import pydantic_to_dict
from .context_summarizer import ContextSummarizer, SummarizationStrategy


class ContextManager:
    """
    Manages context for LLM interactions with hierarchical structure,
    query expansion, and multi-query retrieval
    """
    
    def __init__(
        self,
        config: ContextConfig,
        vector_store: Optional[VectorStore],
        llm_manager: Optional[LLMProviderManager]
    ):
        """
        Initialize context manager
        
        Args:
            config: Context configuration
            vector_store: Vector store instance
            llm_manager: LLM provider manager
        """
        self.config = config
        self.vector_store = vector_store
        self.llm_manager = llm_manager
        self._context_history: List[Dict[str, Any]] = []
        self._initialized = False
        
        # Кэширование контекста для эффективности
        cache_config = pydantic_to_dict(config)
        cache_config = cache_config.get("cache", {}) if isinstance(cache_config, dict) else {}
        self.context_cache = AdvancedCache(
            memory_size=cache_config.get("memory_size", 1000),
            disk_cache_dir=cache_config.get("disk_cache_dir", "cache/context"),
            redis_url=cache_config.get("redis_url"),
            ttl=cache_config.get("ttl", 3600)  # 1 час для контекста
        )
        
        # Суммирование контекста для больших проектов
        summarizer_config = pydantic_to_dict(config)
        summarizer_config = summarizer_config.get("summarization", {}) if isinstance(summarizer_config, dict) else {}
        self.summarizer = ContextSummarizer(
            llm_manager=llm_manager,
            config=summarizer_config
        )
        self.enable_summarization = summarizer_config.get("enabled", True)
        self.summarization_threshold = summarizer_config.get("threshold", 8000)  # Токенов
    
    async def initialize(self) -> None:
        """Initialize context manager"""
        self._initialized = True
        logger.info("Context Manager initialized")
    
    async def get_context(
        self,
        query: str,
        max_tokens: Optional[int] = None,
        use_expansion: bool = True,
        use_multi_query: bool = True
    ) -> str:
        """
        Get relevant context for a query
        
        Args:
            query: User query
            max_tokens: Maximum tokens for context
            use_expansion: Whether to expand query
            use_multi_query: Whether to use multi-query retrieval
            
        Returns:
            Context string
        """
        if not self._initialized:
            await self.initialize()
        
        max_tokens = max_tokens or self.config.max_tokens
        
        # Генерируем ключ кэша
        import hashlib
        import json
        cache_key_data = {
            "query": query,
            "max_tokens": max_tokens,
            "use_expansion": use_expansion if use_expansion is not None else self.config.query_expansion,
            "use_multi_query": use_multi_query if use_multi_query is not None else self.config.multi_query
        }
        cache_key_str = json.dumps(cache_key_data, sort_keys=True)
        cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()
        
        # Проверяем кэш
        cached_context = self.context_cache.get(cache_key)
        if cached_context:
            logger.debug(f"Context cache HIT for query: {query[:50]}")
            return cached_context
        
        # Если не в кэше, получаем контекст
        logger.debug(f"Context cache MISS for query: {query[:50]}")
        
        # Query expansion
        if use_expansion and self.config.query_expansion and self.llm_manager:
            expanded_queries = await self._expand_query(query)
        else:
            expanded_queries = [query]
        
        # Multi-query retrieval
        if use_multi_query and self.config.multi_query and len(expanded_queries) > 1:
            all_results = []
            for q in expanded_queries:
                if self.vector_store:
                    results = await self.vector_store.search(q, top_k=5)
                    all_results.extend(results)
            
            # Deduplicate and rank
            seen_indices = set()
            unique_results = []
            for result in all_results:
                idx = result.get("index")
                if idx not in seen_indices:
                    seen_indices.add(idx)
                    unique_results.append(result)
            
            results = unique_results[:10]
        else:
            # Single query search
            if self.vector_store:
                results = await self.vector_store.search(
                    expanded_queries[0],
                    top_k=10,
                    use_reranking=True
                )
            else:
                results = []
        
        # Build context string
        context_parts = []
        current_tokens = 0
        
        for result in results:
            text = result.get("text", "")
            # Rough token estimation (1 token ≈ 4 characters)
            text_tokens = len(text) // 4
            
            if current_tokens + text_tokens > max_tokens:
                break
            
            context_parts.append(text)
            current_tokens += text_tokens
        
        context = "\n\n".join(context_parts)
        
        # Суммируем контекст если он слишком большой
        if self.enable_summarization:
            estimated_tokens = len(context) // 4
            if estimated_tokens > self.summarization_threshold:
                logger.info(
                    f"Context too large ({estimated_tokens} tokens), "
                    f"summarizing to {self.config.max_tokens} tokens"
                )
                try:
                    context = await self.summarizer.summarize(
                        context=context,
                        query=query,
                        max_tokens=self.config.max_tokens
                    )
                    logger.info(f"Context summarized: {len(context) // 4} tokens")
                except Exception as e:
                    logger.warning(f"Summarization failed: {e}, using original context")
        
        # Сохраняем в кэш для будущих запросов
        try:
            self.context_cache.set(cache_key, context)
            logger.debug(f"Context cached for query: {query[:50]}")
        except Exception as e:
            logger.warning(f"Failed to cache context: {e}")
        
        return context
    
    async def _expand_query(self, query: str) -> List[str]:
        """
        Expand query using LLM
        
        Args:
            query: Original query
            
        Returns:
            List of expanded queries
        """
        if not self.llm_manager:
            return [query]
        
        try:
            expansion_prompt = f"""Given the following query, generate 2-3 alternative phrasings or related queries that would help find relevant information.

Original query: {query}

Generate alternative queries (one per line, no numbering):"""

            messages = [
                LLMMessage(role="user", content=expansion_prompt)
            ]
            
            response = await self.llm_manager.generate(
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )
            
            expanded = response.content.strip().split("\n")
            expanded = [q.strip() for q in expanded if q.strip()]
            
            # Include original query
            return [query] + expanded[:3]
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return [query]
    
    def add_to_history(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add entry to context history
        
        Args:
            role: Role (user, assistant, system)
            content: Content
            metadata: Optional metadata
        """
        self._context_history.append({
            "role": role,
            "content": content,
            "metadata": metadata or {}
        })
    
    def get_history(self, max_entries: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get context history
        
        Args:
            max_entries: Maximum number of entries to return
            
        Returns:
            List of history entries
        """
        if max_entries:
            return self._context_history[-max_entries:]
        return self._context_history.copy()
    
    def clear_history(self) -> None:
        """Clear context history"""
        self._context_history.clear()
    
    async def shutdown(self) -> None:
        """Shutdown context manager"""
        self._initialized = False

