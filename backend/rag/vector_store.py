"""
Vector Store for semantic search
"""

import os
import sys
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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
                import sys
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
    
    async def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Add documents to vector store
        
        Args:
            documents: List of document texts
            metadatas: Optional list of metadata dictionaries
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.embeddings_model:
            raise AILLMException("Embeddings model not available. Please install sentence-transformers.")
        
        logger.info(f"Adding {len(documents)} documents to vector store...")
        
        # Generate embeddings
        embeddings = self.embeddings_model.encode(
            documents,
            show_progress_bar=True,
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
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        for i, (doc, metadata) in enumerate(zip(documents, metadatas)):
            self.metadata.append({
                "text": doc,
                "index": len(self.metadata),
                **metadata
            })
        
        self.documents.extend(documents)
        
        # Update BM25
        if BM25_AVAILABLE:
            tokenized_docs = [doc.split() for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
        
        logger.info(f"Added {len(documents)} documents. Total: {len(self.documents)}")
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        use_bm25: bool = True,
        use_reranking: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents
        
        Args:
            query: Search query
            top_k: Number of results to return
            use_bm25: Whether to use BM25 for initial filtering
            use_reranking: Whether to use reranking
            
        Returns:
            List of search results with metadata
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.documents:
            return []
        
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
        for idx in combined_indices[:top_k * 2]:
            if idx < len(self.metadata):
                metadata = self.metadata[idx].copy()
                metadata["index"] = int(idx)
                results.append(metadata)
        
        # Reranking (if enabled)
        if use_reranking and len(results) > top_k:
            # Reranking by combining BM25 and vector scores with token overlap
            reranked = self._rerank(query, results)
            results = reranked[:top_k]
        else:
            results = results[:top_k]
        
        return results
    
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

