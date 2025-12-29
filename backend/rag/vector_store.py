"""
Vector Store for semantic search
"""

import os
import sys
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from ..core.logger import get_logger
logger = get_logger(__name__)

# Fix for multiprocessing issues in Python 3.14
if sys.version_info >= (3, 14):
    os.environ.setdefault('TORCH_MULTIPROCESSING', '0')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available, vector store will use numpy")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    logger.warning("sentence-transformers not available, embeddings will be disabled")

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    BM25Okapi = None
    logger.warning("rank-bm25 not available, BM25 search will be disabled")

from ..config import RAGConfig
from ..core.exceptions import AILLMException


class VectorStore:
    """
    Vector store for semantic search using FAISS and BM25
    """
    
    def __init__(self, config: RAGConfig):
        """
        Initialize vector store
        
        Args:
            config: RAG configuration
        """
        self.config = config
        self.embeddings_model: Optional[SentenceTransformer] = None
        self.index = None
        self.metadata: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[str] = []
        self._initialized = False
        
        # BM25 incremental update tracking
        self._bm25_needs_rebuild = False
        self._bm25_pending_docs: List[str] = []
        self._bm25_rebuild_threshold = 100  # Rebuild after 100 new docs
        
        # Duplicate detection
        self._document_hashes: set = set()
    
    async def initialize(self) -> None:
        """Initialize vector store"""
        if self._initialized:
            return
        
        logger.info("Initializing Vector Store...")
        
        # Initialize embeddings model
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, embeddings disabled")
            self.embeddings_model = None
        else:
            embeddings_config = self.config.embeddings
            model_name = embeddings_config.get("model", "sentence-transformers/all-MiniLM-L6-v2")
            device = embeddings_config.get("device", "cpu")
            cache_dir = embeddings_config.get("cache_dir", "embeddings_cache")
            
            try:
                # Fix for multiprocessing issues (Python 3.12+)
                # Set environment variables BEFORE importing/loading SentenceTransformer
                # This prevents multiprocessing/threading issues
                import os
                os.environ.setdefault('TORCH_MULTIPROCESSING', '0')
                os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
                os.environ.setdefault('OMP_NUM_THREADS', '1')
                
                # DO NOT call set_start_method - it can only be called once and causes
                # "threads can only be started once" errors if called multiple times
                # Environment variables are sufficient to prevent multiprocessing issues
                
                # Загружаем модель с отключенным multiprocessing
                self.embeddings_model = SentenceTransformer(
                    model_name,
                    device=device,
                    cache_folder=cache_dir
                )
                logger.info(f"Loaded embeddings model: {model_name}")
            except Exception as e:
                logger.warning(f"Failed to load embeddings model: {e}")
                self.embeddings_model = None
        
        # Initialize or load FAISS index
        vector_config = self.config.vector_store
        index_path = vector_config.get("index_path", "vector_store/index.faiss")
        metadata_path = vector_config.get("metadata_path", "vector_store/metadata.pkl")
        dimension = vector_config.get("dimension", 384)
        
        # Create directories
        Path(index_path).parent.mkdir(parents=True, exist_ok=True)
        
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            try:
                if FAISS_AVAILABLE:
                    self.index = faiss.read_index(index_path)
                with open(metadata_path, "rb") as f:
                    self.metadata = pickle.load(f)
                    self.documents = [m.get("text", "") for m in self.metadata]
                
                # Initialize BM25
                if self.documents and BM25_AVAILABLE:
                    tokenized_docs = [doc.split() for doc in self.documents]
                    self.bm25 = BM25Okapi(tokenized_docs)
                elif self.documents and not BM25_AVAILABLE:
                    logger.warning("BM25 not available, text search will be limited")
                    self.bm25 = None
                
                logger.info(f"Loaded vector store with {len(self.metadata)} documents")
            except Exception as e:
                logger.warning(f"Failed to load existing index: {e}, creating new one")
                self._create_index(dimension)
        else:
            self._create_index(dimension)
        
        self._initialized = True
        logger.info("Vector Store initialized")
    
    def _create_index(self, dimension: int) -> None:
        """Create new FAISS index"""
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatL2(dimension)
        else:
            # Fallback to numpy-based storage
            self.index = None
            logger.warning("Using numpy-based storage (FAISS not available)")
    
    def _compute_doc_hash(self, doc: str) -> str:
        """Compute hash for duplicate detection"""
        import hashlib
        # Use first 1000 chars for hash (performance)
        return hashlib.md5(doc[:1000].encode()).hexdigest()
    
    async def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        skip_duplicates: bool = True
    ) -> Dict[str, int]:
        """
        Add documents to vector store with duplicate detection
        
        Args:
            documents: List of document texts
            metadatas: Optional list of metadata dictionaries
            skip_duplicates: Skip documents that already exist
            
        Returns:
            Dict with added/skipped counts
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.embeddings_model:
            raise AILLMException("Embeddings model not available. Please install sentence-transformers.")
        
        # Filter duplicates
        unique_docs = []
        unique_metadatas = []
        skipped = 0
        
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        for doc, meta in zip(documents, metadatas):
            if skip_duplicates:
                doc_hash = self._compute_doc_hash(doc)
                if doc_hash in self._document_hashes:
                    skipped += 1
                    continue
                self._document_hashes.add(doc_hash)
            
            unique_docs.append(doc)
            unique_metadatas.append(meta)
        
        if not unique_docs:
            logger.info(f"All {skipped} documents were duplicates, nothing to add")
            return {"added": 0, "skipped": skipped}
        
        logger.info(f"Adding {len(unique_docs)} documents (skipped {skipped} duplicates)...")
        
        # Generate embeddings
        embeddings = self.embeddings_model.encode(
            unique_docs,
            show_progress_bar=len(unique_docs) > 100,
            batch_size=self.config.embeddings.get("batch_size", 32)
        )
        
        # Add to index
        if FAISS_AVAILABLE and self.index:
            embeddings_np = np.array(embeddings).astype("float32")
            self.index.add(embeddings_np)
        else:
            # Store in metadata for numpy fallback
            if not hasattr(self, "_embeddings_list"):
                self._embeddings_list = []
            self._embeddings_list.extend(embeddings)
        
        # Add metadata
        for doc, metadata in zip(unique_docs, unique_metadatas):
            self.metadata.append({
                "text": doc,
                "index": len(self.metadata),
                **metadata
            })
        
        self.documents.extend(unique_docs)
        
        # INCREMENTAL BM25 UPDATE
        # Track pending docs instead of rebuilding every time
        self._bm25_pending_docs.extend(unique_docs)
        
        if BM25_AVAILABLE:
            # Only rebuild if we have enough pending docs or no BM25 yet
            if self.bm25 is None or len(self._bm25_pending_docs) >= self._bm25_rebuild_threshold:
                logger.debug(f"Rebuilding BM25 index ({len(self._bm25_pending_docs)} pending docs)")
                tokenized_docs = [doc.split() for doc in self.documents]
                self.bm25 = BM25Okapi(tokenized_docs)
                self._bm25_pending_docs.clear()
            else:
                logger.debug(f"Deferred BM25 rebuild ({len(self._bm25_pending_docs)} pending docs)")
        
        logger.info(f"Added {len(unique_docs)} documents. Total: {len(self.documents)}")
        
        return {"added": len(unique_docs), "skipped": skipped}
    
    async def flush_bm25(self) -> None:
        """Force rebuild BM25 index with all pending documents"""
        if BM25_AVAILABLE and self._bm25_pending_docs:
            logger.info(f"Flushing BM25 index with {len(self._bm25_pending_docs)} pending docs")
            tokenized_docs = [doc.split() for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
            self._bm25_pending_docs.clear()
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        use_bm25: bool = True,
        use_reranking: bool = False,
        use_mmr: bool = False,
        mmr_lambda: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents
        
        Args:
            query: Search query
            top_k: Number of results to return
            use_bm25: Whether to use BM25 for initial filtering
            use_reranking: Whether to use reranking
            use_mmr: Whether to use MMR for diversity
            mmr_lambda: MMR lambda parameter (0=diversity, 1=relevance)
            filters: Metadata filters (e.g. {"file_type": "python"})
            
        Returns:
            List of search results with metadata
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.documents:
            return []
        
        # Flush pending BM25 docs before search
        if self._bm25_pending_docs:
            await self.flush_bm25()
        
        # Generate query embedding
        if not self.embeddings_model:
            logger.warning("Embeddings model not available, returning empty results")
            return []
        
        query_embedding = self.embeddings_model.encode([query])[0]
        
        # BM25 search for initial filtering
        if use_bm25 and self.bm25:
            bm25_scores = self.bm25.get_scores(query.split())
            bm25_indices = np.argsort(bm25_scores)[::-1][:top_k * 2]  # Get more for reranking
        else:
            bm25_indices = np.arange(len(self.documents))
        
        # Vector similarity search
        if FAISS_AVAILABLE and self.index:
            query_vector = np.array([query_embedding]).astype("float32")
            k = min(top_k * 2, len(self.documents))
            distances, indices = self.index.search(query_vector, k)
            
            # Combine with BM25 results
            if use_bm25:
                combined_indices = np.unique(np.concatenate([indices[0], bm25_indices]))
            else:
                combined_indices = indices[0]
        else:
            # Numpy fallback
            if not hasattr(self, "_embeddings_list"):
                return []
            
            embeddings_array = np.array(self._embeddings_list)
            query_vector = np.array([query_embedding])
            similarities = np.dot(embeddings_array, query_vector.T).flatten()
            combined_indices = np.argsort(similarities)[::-1][:top_k * 2]
        
        # Get results
        results = []
        for idx in combined_indices[:top_k * 3]:  # Get more for filtering
            if idx < len(self.metadata):
                metadata = self.metadata[idx].copy()
                metadata["index"] = int(idx)
                
                # Apply filters
                if filters:
                    if not self._matches_filters(metadata, filters):
                        continue
                
                results.append(metadata)
        
        # MMR for diversity (Maximal Marginal Relevance)
        if use_mmr and len(results) > top_k:
            results = self._mmr_rerank(query_embedding, results, mmr_lambda, top_k)
        # Reranking (if enabled)
        elif use_reranking and len(results) > top_k:
            # Reranking by combining BM25 and vector scores with token overlap
            reranked = self._rerank(query, results)
            results = reranked[:top_k]
        else:
            results = results[:top_k]
        
        return results
    
    def _matches_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if metadata matches all filters"""
        for key, value in filters.items():
            if key not in metadata:
                return False
            
            meta_value = metadata[key]
            
            # Support prefix matching for paths
            if key.endswith("_prefix") and isinstance(value, str):
                actual_key = key.replace("_prefix", "")
                if actual_key in metadata and not str(metadata[actual_key]).startswith(value):
                    return False
            elif isinstance(value, list):
                # Support IN operator
                if meta_value not in value:
                    return False
            elif meta_value != value:
                return False
        
        return True
    
    def _mmr_rerank(
        self,
        query_embedding: np.ndarray,
        results: List[Dict[str, Any]],
        lambda_param: float,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Maximal Marginal Relevance reranking for diversity
        
        Score = λ * sim(query, doc) - (1-λ) * max(sim(doc, selected_docs))
        """
        if not results:
            return []
        
        # Get embeddings for all result documents
        doc_texts = [r.get("text", "") for r in results]
        doc_embeddings = self.embeddings_model.encode(doc_texts)
        
        # Compute relevance scores (similarity to query)
        relevance_scores = np.dot(doc_embeddings, query_embedding)
        
        selected = []
        selected_embeddings = []
        candidates = list(range(len(results)))
        
        while len(selected) < top_k and candidates:
            best_score = float('-inf')
            best_idx = -1
            
            for i in candidates:
                relevance = relevance_scores[i]
                
                # Compute redundancy (max similarity to already selected)
                if selected_embeddings:
                    similarities = np.dot(doc_embeddings[i], np.array(selected_embeddings).T)
                    redundancy = np.max(similarities)
                else:
                    redundancy = 0
                
                # MMR score
                mmr_score = lambda_param * relevance - (1 - lambda_param) * redundancy
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i
            
            if best_idx >= 0:
                selected.append(results[best_idx])
                selected_embeddings.append(doc_embeddings[best_idx])
                candidates.remove(best_idx)
        
        return selected
    
    def _rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rerank results by combining multiple signals:
        - BM25 score
        - Vector similarity score
        - Token overlap score
        """
        query_tokens = set(query.lower().split())
        
        for result in results:
            doc_tokens = set(result.get("text", "").lower().split())
            overlap = len(query_tokens & doc_tokens)
            result["rerank_score"] = overlap / max(len(query_tokens), 1)
        
        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results
    
    async def save(self) -> None:
        """Save vector store to disk"""
        if not self._initialized:
            return
        
        vector_config = self.config.vector_store
        index_path = vector_config.get("index_path", "vector_store/index.faiss")
        metadata_path = vector_config.get("metadata_path", "vector_store/metadata.pkl")
        
        # Save FAISS index
        if FAISS_AVAILABLE and self.index:
            Path(index_path).parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, index_path)
        
        # Save metadata
        Path(metadata_path).parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)
        
        logger.info("Vector store saved")
    
    async def shutdown(self) -> None:
        """Shutdown and save vector store"""
        await self.save()
        self._initialized = False

