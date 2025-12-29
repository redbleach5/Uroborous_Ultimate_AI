"""
Incremental Indexer - инкрементальное индексирование с отслеживанием изменений.

Обеспечивает:
- Отслеживание изменений файлов по хешу
- Индексирование только изменённых файлов
- Персистентный кэш хешей
- Быстрое обновление индекса
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from ..core.logger import get_logger
from .code_intelligence import CodeIntelligence, get_code_intelligence
from ..rag.vector_store import VectorStore

logger = get_logger(__name__)


class FileStatus(Enum):
    """Статус файла."""
    NEW = "new"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


@dataclass
class FileChange:
    """Информация об изменении файла."""
    path: str
    status: FileStatus
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    modified_at: Optional[datetime] = None


@dataclass
class IndexStats:
    """Статистика индексирования."""
    total_files: int = 0
    new_files: int = 0
    modified_files: int = 0
    deleted_files: int = 0
    unchanged_files: int = 0
    entities_indexed: int = 0
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "new_files": self.new_files,
            "modified_files": self.modified_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "entities_indexed": self.entities_indexed,
            "duration_seconds": round(self.duration_seconds, 2)
        }


class IncrementalIndexer:
    """
    Инкрементальный индексатор проектов.
    
    Особенности:
    - Отслеживает изменения файлов по content hash
    - Хранит историю хешей в SQLite
    - Индексирует только изменённые файлы
    - Поддерживает множество проектов
    """
    
    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift"
    }
    
    IGNORE_DIRS = {
        "__pycache__", "node_modules", ".git", ".venv", "venv", "env",
        "dist", "build", ".pytest_cache", ".mypy_cache", "coverage",
        ".next", ".nuxt", "target", "vendor", ".idea", ".vscode"
    }
    
    def __init__(
        self,
        db_path: str = "memory/index_cache.db",
        vector_store: Optional[VectorStore] = None,
        code_intelligence: Optional[CodeIntelligence] = None
    ):
        """
        Инициализация.
        
        Args:
            db_path: Путь к SQLite базе для хранения хешей
            vector_store: Векторное хранилище
            code_intelligence: Анализатор кода
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.vector_store = vector_store
        self.code_intelligence = code_intelligence or get_code_intelligence()
        
        self._init_database()
    
    def _init_database(self) -> None:
        """Инициализирует базу данных."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_hashes (
                    project_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    size_bytes INTEGER,
                    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    entities_count INTEGER DEFAULT 0,
                    PRIMARY KEY (project_path, file_path)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_stats (
                    project_path TEXT PRIMARY KEY,
                    last_full_index TIMESTAMP,
                    last_incremental_index TIMESTAMP,
                    total_files INTEGER DEFAULT 0,
                    total_entities INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_hashes_project 
                ON file_hashes(project_path)
            """)
            
            conn.commit()
    
    async def update_index(
        self,
        project_path: str,
        force_full: bool = False,
        max_files: int = 1000
    ) -> IndexStats:
        """
        Обновляет индекс проекта.
        
        Args:
            project_path: Путь к проекту
            force_full: Принудительная полная переиндексация
            max_files: Максимальное количество файлов
            
        Returns:
            Статистика индексирования
        """
        import time
        start_time = time.time()
        
        project_path = str(Path(project_path).resolve())
        
        logger.info(f"Starting {'full' if force_full else 'incremental'} index update: {project_path}")
        
        # Определяем изменения
        changes = await self._detect_changes(project_path, max_files)
        
        stats = IndexStats(
            total_files=len(changes),
            new_files=sum(1 for c in changes if c.status == FileStatus.NEW),
            modified_files=sum(1 for c in changes if c.status == FileStatus.MODIFIED),
            deleted_files=sum(1 for c in changes if c.status == FileStatus.DELETED),
            unchanged_files=sum(1 for c in changes if c.status == FileStatus.UNCHANGED)
        )
        
        if force_full:
            # Очищаем старые данные
            self._clear_project_hashes(project_path)
            stats.new_files = stats.total_files
            stats.unchanged_files = 0
        
        # Получаем файлы для индексирования
        files_to_index = [
            c for c in changes 
            if c.status in (FileStatus.NEW, FileStatus.MODIFIED) or force_full
        ]
        
        # Удаляем из индекса удалённые файлы
        deleted_files = [c for c in changes if c.status == FileStatus.DELETED]
        if deleted_files:
            await self._remove_deleted_files(project_path, deleted_files)
        
        # Индексируем изменённые файлы
        if files_to_index:
            entities_count = await self._index_files(project_path, files_to_index)
            stats.entities_indexed = entities_count
        
        stats.duration_seconds = time.time() - start_time
        
        # Обновляем статистику проекта
        self._update_project_stats(project_path, stats)
        
        logger.info(
            f"Index update complete: {stats.new_files} new, "
            f"{stats.modified_files} modified, {stats.deleted_files} deleted, "
            f"{stats.unchanged_files} unchanged, {stats.entities_indexed} entities indexed "
            f"in {stats.duration_seconds:.2f}s"
        )
        
        return stats
    
    async def _detect_changes(
        self,
        project_path: str,
        max_files: int
    ) -> List[FileChange]:
        """
        Определяет изменения в файлах проекта.
        
        Args:
            project_path: Путь к проекту
            max_files: Максимальное количество файлов
            
        Returns:
            Список изменений
        """
        # Получаем сохранённые хеши
        stored_hashes = self._get_stored_hashes(project_path)
        
        # Сканируем текущие файлы
        current_files: Dict[str, Tuple[str, int]] = {}  # path -> (hash, size)
        
        project = Path(project_path)
        files_scanned = 0
        
        for path in self._walk_project(project):
            if files_scanned >= max_files:
                break
            
            rel_path = str(path.relative_to(project))
            
            try:
                content = path.read_bytes()
                content_hash = hashlib.md5(content).hexdigest()
                size = len(content)
                current_files[rel_path] = (content_hash, size)
                files_scanned += 1
            except (OSError, IOError) as e:
                logger.debug(f"Cannot read file {path}: {e}")
                continue
        
        # Определяем изменения
        changes: List[FileChange] = []
        
        # Новые и изменённые файлы
        for rel_path, (new_hash, size) in current_files.items():
            if rel_path not in stored_hashes:
                changes.append(FileChange(
                    path=rel_path,
                    status=FileStatus.NEW,
                    new_hash=new_hash,
                    modified_at=datetime.now()
                ))
            elif stored_hashes[rel_path] != new_hash:
                changes.append(FileChange(
                    path=rel_path,
                    status=FileStatus.MODIFIED,
                    old_hash=stored_hashes[rel_path],
                    new_hash=new_hash,
                    modified_at=datetime.now()
                ))
            else:
                changes.append(FileChange(
                    path=rel_path,
                    status=FileStatus.UNCHANGED,
                    old_hash=stored_hashes[rel_path],
                    new_hash=new_hash
                ))
        
        # Удалённые файлы
        for rel_path, old_hash in stored_hashes.items():
            if rel_path not in current_files:
                changes.append(FileChange(
                    path=rel_path,
                    status=FileStatus.DELETED,
                    old_hash=old_hash
                ))
        
        return changes
    
    async def _index_files(
        self,
        project_path: str,
        changes: List[FileChange]
    ) -> int:
        """
        Индексирует файлы.
        
        Args:
            project_path: Путь к проекту
            changes: Список изменений для индексирования
            
        Returns:
            Количество проиндексированных сущностей
        """
        total_entities = 0
        project = Path(project_path)
        
        for change in changes:
            file_path = project / change.path
            
            if not file_path.exists():
                continue
            
            try:
                # Анализируем файл
                module_info = await self.code_intelligence.analyze_file(str(file_path))
                
                if not module_info:
                    continue
                
                entities_count = len(module_info.entities)
                total_entities += entities_count
                
                # Добавляем в векторное хранилище
                if self.vector_store and module_info.entities:
                    documents = []
                    metadatas = []
                    
                    for entity in module_info.entities:
                        documents.append(entity.get_semantic_text())
                        metadatas.append({
                            "entity_id": entity.qualified_name,
                            "entity_type": entity.type.value,
                            "name": entity.name,
                            "file_path": change.path,
                            "start_line": entity.start_line,
                            "end_line": entity.end_line,
                            "complexity": entity.complexity,
                            "project_path": project_path
                        })
                    
                    await self.vector_store.add_documents(documents, metadatas)
                
                # Сохраняем хеш
                self._save_file_hash(
                    project_path,
                    change.path,
                    change.new_hash,
                    file_path.stat().st_size,
                    entities_count
                )
                
            except Exception as e:
                logger.warning(f"Error indexing {file_path}: {e}")
                continue
        
        # Сохраняем индекс
        if self.vector_store:
            await self.vector_store.save()
        
        return total_entities
    
    async def _remove_deleted_files(
        self,
        project_path: str,
        deleted: List[FileChange]
    ) -> None:
        """
        Удаляет из индекса удалённые файлы.
        
        Args:
            project_path: Путь к проекту
            deleted: Список удалённых файлов
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            for change in deleted:
                conn.execute(
                    "DELETE FROM file_hashes WHERE project_path = ? AND file_path = ?",
                    (project_path, change.path)
                )
            conn.commit()
        
        # TODO: Удаление из vector_store требует поддержки deletion
        # Сейчас FAISS не поддерживает удаление, нужен rebuild
        logger.debug(f"Removed {len(deleted)} deleted files from hash cache")
    
    def _walk_project(self, project: Path) -> List[Path]:
        """Обходит проект, игнорируя ненужные директории."""
        files = []
        
        for root, dirs, filenames in project.walk():
            # Фильтруем игнорируемые директории
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
            
            for filename in filenames:
                file_path = root / filename
                
                if file_path.suffix.lower() in self.CODE_EXTENSIONS:
                    files.append(file_path)
        
        return files
    
    def _get_stored_hashes(self, project_path: str) -> Dict[str, str]:
        """Получает сохранённые хеши файлов."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT file_path, content_hash FROM file_hashes WHERE project_path = ?",
                (project_path,)
            )
            return dict(cursor.fetchall())
    
    def _save_file_hash(
        self,
        project_path: str,
        file_path: str,
        content_hash: str,
        size_bytes: int,
        entities_count: int
    ) -> None:
        """Сохраняет хеш файла."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO file_hashes 
                (project_path, file_path, content_hash, size_bytes, entities_count, last_indexed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (project_path, file_path, content_hash, size_bytes, entities_count))
            conn.commit()
    
    def _clear_project_hashes(self, project_path: str) -> None:
        """Очищает хеши проекта."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "DELETE FROM file_hashes WHERE project_path = ?",
                (project_path,)
            )
            conn.commit()
    
    def _update_project_stats(self, project_path: str, stats: IndexStats) -> None:
        """Обновляет статистику проекта."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO project_stats 
                (project_path, last_incremental_index, total_files, total_entities)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?)
            """, (project_path, stats.total_files, stats.entities_indexed))
            conn.commit()
    
    def get_project_status(self, project_path: str) -> Dict[str, Any]:
        """
        Получает статус индекса проекта.
        
        Args:
            project_path: Путь к проекту
            
        Returns:
            Статус проекта
        """
        project_path = str(Path(project_path).resolve())
        
        with sqlite3.connect(str(self.db_path)) as conn:
            # Получаем статистику проекта
            cursor = conn.execute(
                "SELECT * FROM project_stats WHERE project_path = ?",
                (project_path,)
            )
            row = cursor.fetchone()
            
            if not row:
                return {"status": "not_indexed", "project_path": project_path}
            
            # Получаем количество файлов
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(entities_count) FROM file_hashes WHERE project_path = ?",
                (project_path,)
            )
            files_count, entities_count = cursor.fetchone()
            
            return {
                "status": "indexed",
                "project_path": project_path,
                "last_indexed": row[2],  # last_incremental_index
                "files_count": files_count or 0,
                "entities_count": entities_count or 0
            }
    
    def list_indexed_projects(self) -> List[Dict[str, Any]]:
        """
        Возвращает список проиндексированных проектов.
        
        Returns:
            Список проектов с их статусом
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                SELECT project_path, last_incremental_index, total_files, total_entities
                FROM project_stats
                ORDER BY last_incremental_index DESC
            """)
            
            projects = []
            for row in cursor.fetchall():
                projects.append({
                    "project_path": row[0],
                    "last_indexed": row[1],
                    "total_files": row[2],
                    "total_entities": row[3]
                })
            
            return projects
    
    def clear_all(self) -> None:
        """Очищает всю базу данных индексов."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM file_hashes")
            conn.execute("DELETE FROM project_stats")
            conn.commit()
        
        # Очищаем кэш CodeIntelligence
        self.code_intelligence.clear_cache()
        
        logger.info("Cleared all index data")


# Глобальный экземпляр
_incremental_indexer: Optional[IncrementalIndexer] = None


def get_incremental_indexer(
    vector_store: Optional[VectorStore] = None
) -> IncrementalIndexer:
    """Получить экземпляр IncrementalIndexer."""
    global _incremental_indexer
    if _incremental_indexer is None:
        _incremental_indexer = IncrementalIndexer(vector_store=vector_store)
    return _incremental_indexer

