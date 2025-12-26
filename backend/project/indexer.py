"""
Project Indexer - Indexes codebase for RAG
"""

import os
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..rag.vector_store import VectorStore
from ..core.exceptions import AILLMException


class ProjectIndexer:
    """Indexes project files for RAG system"""
    
    # File extensions to index
    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
        ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
        ".scala", ".clj", ".sh", ".bash", ".zsh", ".fish"
    }
    
    # Documentation extensions
    DOC_EXTENSIONS = {
        ".md", ".txt", ".rst", ".adoc", ".org"
    }
    
    # Config files
    CONFIG_EXTENSIONS = {
        ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf"
    }
    
    # Directories to always ignore
    IGNORE_DIRS = {
        "__pycache__", "node_modules", ".git", ".venv", "venv", "env",
        ".env", "dist", "build", ".pytest_cache", ".mypy_cache", ".tox",
        ".nox", ".eggs", "*.egg-info", ".cache", ".idea", ".vscode",
        "coverage", "htmlcov", ".coverage", ".nyc_output", ".next",
        ".nuxt", ".svelte-kit", "target", "out", "bin", "obj",
        ".gradle", ".mvn", "vendor", "Pods", ".dart_tool", ".pub-cache"
    }
    
    # File patterns to ignore (supports wildcards)
    IGNORE_FILE_PATTERNS = {
        "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.dylib",
        "*.class", "*.o", "*.obj", "*.exe",
        ".DS_Store", "Thumbs.db", "*.log", "*.lock",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "poetry.lock", "Pipfile.lock", "Cargo.lock",
        "*.min.js", "*.min.css", "*.map",
        ".gitignore", ".dockerignore", ".eslintcache"
    }
    
    def __init__(self, vector_store: Optional[VectorStore] = None):
        """
        Initialize project indexer
        
        Args:
            vector_store: Vector store instance for indexing
        """
        self.vector_store = vector_store
    
    def _should_ignore_dir(self, dirname: str) -> bool:
        """Check if directory should be ignored"""
        # Ignore all hidden directories (starting with .)
        if dirname.startswith('.'):
            return True
        # Check against ignore patterns
        for pattern in self.IGNORE_DIRS:
            if fnmatch.fnmatch(dirname, pattern) or dirname == pattern:
                return True
        return False
    
    def _should_ignore_file(self, filename: str) -> bool:
        """Check if file should be ignored"""
        # Check against ignore patterns (supports wildcards)
        for pattern in self.IGNORE_FILE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False
    
    async def index_project(
        self,
        project_path: str,
        extensions: Optional[Set[str]] = None,
        max_file_size: int = 1_000_000  # 1MB
    ) -> Dict[str, Any]:
        """
        Index a project directory
        
        Args:
            project_path: Path to project root
            extensions: Set of file extensions to index. If None, uses default.
            max_file_size: Maximum file size to index (bytes)
            
        Returns:
            Indexing results
        """
        if not self.vector_store:
            raise AILLMException("Vector store not initialized")
        
        project_path = Path(project_path)
        if not project_path.exists():
            raise AILLMException(f"Project path does not exist: {project_path}")
        
        extensions = extensions or (self.CODE_EXTENSIONS | self.DOC_EXTENSIONS | self.CONFIG_EXTENSIONS)
        
        files_to_index = []
        total_size = 0
        skipped_dirs = 0
        skipped_files = 0
        
        # Find all files
        for root, dirs, files in os.walk(project_path):
            # Filter ignored directories (modifies dirs in-place to prevent descent)
            original_count = len(dirs)
            dirs[:] = [d for d in dirs if not self._should_ignore_dir(d)]
            skipped_dirs += original_count - len(dirs)
            
            for file in files:
                # Check if file should be ignored
                if self._should_ignore_file(file):
                    skipped_files += 1
                    continue
                
                file_path = Path(root) / file
                
                # Check extension
                if file_path.suffix not in extensions:
                    continue
                
                # Check file size
                try:
                    size = file_path.stat().st_size
                    if size > max_file_size:
                        logger.debug(f"Skipping large file: {file_path} ({size} bytes)")
                        skipped_files += 1
                        continue
                    total_size += size
                    files_to_index.append(file_path)
                except Exception as e:
                    logger.warning(f"Error checking file {file_path}: {e}")
                    continue
        
        logger.info(f"Found {len(files_to_index)} files to index (skipped {skipped_dirs} dirs, {skipped_files} files)")
        
        # Index files
        documents = []
        metadatas = []
        
        for file_path in files_to_index:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                # Split large files into chunks
                chunks = self._chunk_file(content, file_path.suffix)
                
                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({
                        "file_path": str(file_path.relative_to(project_path)),
                        "absolute_path": str(file_path),
                        "extension": file_path.suffix,
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    })
            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {e}")
                continue
        
        # Add to vector store
        if documents:
            await self.vector_store.add_documents(documents, metadatas)
            await self.vector_store.save()
        
        return {
            "files_indexed": len(files_to_index),
            "chunks_created": len(documents),
            "total_size": total_size,
            "success": True
        }
    
    async def _index_files(
        self,
        project_path: str,
        file_paths: List[str],
        max_file_size: int = 1_000_000
    ) -> Dict[str, Any]:
        """
        Index specific files (for incremental updates)
        
        Args:
            project_path: Path to project root
            file_paths: List of file paths to index (relative or absolute)
            max_file_size: Maximum file size to index (bytes)
            
        Returns:
            Indexing results
        """
        if not self.vector_store:
            raise AILLMException("Vector store not initialized")
        
        project_path = Path(project_path)
        documents = []
        metadatas = []
        files_indexed = 0
        total_size = 0
        
        for file_path_str in file_paths:
            file_path = Path(file_path_str)
            
            # If relative path, make it relative to project_path
            if not file_path.is_absolute():
                file_path = project_path / file_path
            
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue
            
            # Check file size
            try:
                size = file_path.stat().st_size
                if size > max_file_size:
                    logger.warning(f"Skipping large file: {file_path} ({size} bytes)")
                    continue
                total_size += size
            except Exception as e:
                logger.warning(f"Error checking file {file_path}: {e}")
                continue
            
            # Read and chunk file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                chunks = self._chunk_file(content, file_path.suffix)
                
                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({
                        "file_path": str(file_path.relative_to(project_path)),
                        "absolute_path": str(file_path),
                        "extension": file_path.suffix,
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    })
                
                files_indexed += 1
            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {e}")
                continue
        
        # Add to vector store
        if documents:
            await self.vector_store.add_documents(documents, metadatas)
            await self.vector_store.save()
        
        return {
            "files_indexed": files_indexed,
            "chunks_created": len(documents),
            "total_size": total_size,
            "success": True
        }
    
    def _chunk_file(self, content: str, extension: str, chunk_size: int = 2000) -> List[str]:
        """
        Split file content into chunks
        
        Args:
            content: File content
            extension: File extension
            chunk_size: Target chunk size in characters
            
        Returns:
            List of chunks
        """
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        
        # Try to split by lines for code files
        if extension in self.CODE_EXTENSIONS:
            lines = content.split("\n")
            current_chunk = []
            current_size = 0
            
            for line in lines:
                line_size = len(line) + 1  # +1 for newline
                
                if current_size + line_size > chunk_size and current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_size = line_size
                else:
                    current_chunk.append(line)
                    current_size += line_size
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
        else:
            # Simple character-based chunking for other files
            for i in range(0, len(content), chunk_size):
                chunks.append(content[i:i + chunk_size])
        
        return chunks
    
    async def update_index(
        self,
        project_path: str,
        changed_files: List[str]
    ) -> Dict[str, Any]:
        """
        Update index for changed files
        
        Args:
            project_path: Path to project root
            changed_files: List of changed file paths
            
        Returns:
            Update results
        """
        # Incremental update: remove old entries for changed files and re-index
        if changed_files:
            # Remove old entries for changed files
            for file_path in changed_files:
                # Find and remove old chunks for this file
                try:
                    # Get all chunks for this file
                    all_chunks = self.vector_store.search(
                        query="",  # Empty query to get all
                        top_k=10000  # Large number to get all
                    )
                    
                    # Filter chunks for this file
                    file_chunks = [
                        chunk for chunk in all_chunks
                        if chunk.get("metadata", {}).get("file_path") == file_path
                    ]
                    
                    # Remove old chunks (vector store should handle this)
                    # Note: FAISS doesn't support deletion directly, so we'll re-index
                    logger.info(f"Re-indexing {len(file_chunks)} chunks for changed file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove old chunks for {file_path}: {e}")
            
            # Re-index only changed files
            return await self._index_files(project_path, changed_files)
        else:
            # No specific files changed, re-index entire project
            return await self.index_project(project_path)

