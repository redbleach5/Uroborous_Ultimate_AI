"""
Smart Project Analyzer - комплексный анализ проектов с использованием
всех инструментов системы: агентов, RAG, git, shell.
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import time

from ...core.logger import get_logger

logger = get_logger(__name__)


class ProjectComplexity(Enum):
    SIMPLE = "simple"      # < 10 файлов кода
    MEDIUM = "medium"      # 10-50 файлов
    COMPLEX = "complex"    # 50-200 файлов
    LARGE = "large"        # > 200 файлов


@dataclass
class ProjectProfile:
    """Профиль проекта для адаптивного анализа."""
    path: Path
    name: str
    complexity: ProjectComplexity
    total_files: int
    code_files: int
    total_lines: int
    languages: Dict[str, int] = field(default_factory=dict)
    has_git: bool = False
    has_tests: bool = False
    has_docs: bool = False
    has_ci: bool = False
    frameworks: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)


class SmartProjectAnalyzer:
    """
    Умный анализатор проектов с адаптивной стратегией.
    
    Особенности:
    - Определяет сложность проекта
    - Адаптирует глубину анализа
    - Использует RAG для семантического поиска
    - Задействует git для истории изменений
    - Применяет несколько агентов для разных аспектов
    """
    
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
        '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift',
        '.kt', '.scala', '.vue', '.svelte'
    }
    
    LANGUAGE_MAP = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.jsx': 'React', '.tsx': 'React/TypeScript', '.java': 'Java',
        '.go': 'Go', '.rs': 'Rust', '.c': 'C', '.cpp': 'C++',
        '.cs': 'C#', '.rb': 'Ruby', '.php': 'PHP', '.swift': 'Swift',
        '.kt': 'Kotlin', '.scala': 'Scala', '.vue': 'Vue', '.svelte': 'Svelte'
    }
    
    IGNORE_DIRS = {
        'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
        'dist', 'build', '.next', '.nuxt', 'target', 'vendor',
        '.idea', '.vscode', 'coverage', '.pytest_cache'
    }
    
    def __init__(self, engine):
        self.engine = engine
        self.vector_store = getattr(engine, 'vector_store', None)
        self.tools = getattr(engine, 'tools', {})
    
    async def analyze(
        self,
        project_path: str,
        analysis_type: str = "comprehensive",
        specific_question: Optional[str] = None,
        use_git: bool = True,
        use_rag: bool = True,
        max_depth: int = 5
    ) -> Dict[str, Any]:
        """
        Выполняет комплексный анализ проекта.
        
        Args:
            project_path: Путь к проекту
            analysis_type: Тип анализа (comprehensive, quick, security, performance)
            specific_question: Конкретный вопрос о проекте
            use_git: Использовать git историю
            use_rag: Использовать RAG для поиска
            max_depth: Максимальная глубина сканирования
        """
        start_time = time.time()
        path = Path(project_path).expanduser().resolve()
        
        if not path.exists():
            return {"success": False, "error": f"Проект не найден: {project_path}"}
        
        try:
            # 1. Профилирование проекта
            logger.info(f"[SmartAnalyzer] Profiling project: {path.name}")
            profile = await self._profile_project(path, max_depth)
            
            # 2. Определение стратегии анализа
            strategy = self._determine_strategy(profile, analysis_type)
            logger.info(f"[SmartAnalyzer] Strategy: {strategy['name']} for {profile.complexity.value} project")
            
            # 3. Сбор контекста
            context = await self._gather_context(path, profile, strategy, use_git, use_rag)
            
            # 4. Выполнение анализа через агентов
            analysis_results = await self._run_analysis(
                profile, context, strategy, specific_question
            )
            
            elapsed = time.time() - start_time
            
            return {
                "success": True,
                "project_name": profile.name,
                "project_path": str(path),
                "complexity": profile.complexity.value,
                "profile": {
                    "total_files": profile.total_files,
                    "code_files": profile.code_files,
                    "total_lines": profile.total_lines,
                    "languages": profile.languages,
                    "has_git": profile.has_git,
                    "has_tests": profile.has_tests,
                    "has_docs": profile.has_docs,
                    "frameworks": profile.frameworks
                },
                "strategy_used": strategy['name'],
                "analysis": analysis_results.get("final_answer") or analysis_results.get("analysis"),
                "insights": analysis_results.get("insights", []),
                "recommendations": analysis_results.get("recommendations", []),
                "files_analyzed": len(context.get("files_content", {})),
                "total_lines": profile.total_lines,
                "elapsed_seconds": round(elapsed, 2),
                "result": analysis_results
            }
            
        except Exception as e:
            logger.error(f"[SmartAnalyzer] Error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _profile_project(self, path: Path, max_depth: int) -> ProjectProfile:
        """Профилирует проект для определения стратегии анализа."""
        code_files = []
        total_files = 0
        total_lines = 0
        languages: Dict[str, int] = {}
        
        def scan(current: Path, depth: int = 0):
            nonlocal total_files, total_lines
            if depth > max_depth:
                return
            try:
                for item in current.iterdir():
                    if item.name.startswith('.') or item.name in self.IGNORE_DIRS:
                        continue
                    if item.is_dir():
                        scan(item, depth + 1)
                    elif item.is_file():
                        total_files += 1
                        ext = item.suffix.lower()
                        if ext in self.CODE_EXTENSIONS:
                            code_files.append(item)
                            lang = self.LANGUAGE_MAP.get(ext, ext)
                            languages[lang] = languages.get(lang, 0) + 1
                            try:
                                lines = item.read_text(encoding='utf-8', errors='ignore').count('\n') + 1
                                total_lines += lines
                            except:
                                pass
            except PermissionError:
                pass
        
        scan(path)
        
        # Определяем сложность
        code_count = len(code_files)
        if code_count < 10:
            complexity = ProjectComplexity.SIMPLE
        elif code_count < 50:
            complexity = ProjectComplexity.MEDIUM
        elif code_count < 200:
            complexity = ProjectComplexity.COMPLEX
        else:
            complexity = ProjectComplexity.LARGE
        
        # Определяем характеристики
        has_git = (path / '.git').exists()
        has_tests = any(
            (path / d).exists() for d in ['tests', 'test', '__tests__', 'spec']
        )
        has_docs = any(
            (path / d).exists() for d in ['docs', 'documentation', 'doc']
        ) or (path / 'README.md').exists()
        has_ci = any(
            (path / f).exists() for f in ['.github/workflows', '.gitlab-ci.yml', 'Jenkinsfile', '.travis.yml']
        )
        
        # Определяем фреймворки
        frameworks = []
        if (path / 'package.json').exists():
            try:
                import json
                pkg = json.loads((path / 'package.json').read_text())
                deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                if 'react' in deps:
                    frameworks.append('React')
                if 'vue' in deps:
                    frameworks.append('Vue')
                if 'next' in deps:
                    frameworks.append('Next.js')
                if 'express' in deps:
                    frameworks.append('Express')
            except:
                pass
        
        if (path / 'requirements.txt').exists():
            try:
                reqs = (path / 'requirements.txt').read_text()
                if 'django' in reqs.lower():
                    frameworks.append('Django')
                if 'flask' in reqs.lower():
                    frameworks.append('Flask')
                if 'fastapi' in reqs.lower():
                    frameworks.append('FastAPI')
                if 'pytorch' in reqs.lower() or 'torch' in reqs.lower():
                    frameworks.append('PyTorch')
                if 'tensorflow' in reqs.lower():
                    frameworks.append('TensorFlow')
            except:
                pass
        
        # Ключевые файлы
        key_files = []
        for f in ['README.md', 'package.json', 'requirements.txt', 'pyproject.toml',
                  'Cargo.toml', 'go.mod', 'Makefile', 'docker-compose.yml']:
            if (path / f).exists():
                key_files.append(f)
        
        return ProjectProfile(
            path=path,
            name=path.name,
            complexity=complexity,
            total_files=total_files,
            code_files=code_count,
            total_lines=total_lines,
            languages=languages,
            has_git=has_git,
            has_tests=has_tests,
            has_docs=has_docs,
            has_ci=has_ci,
            frameworks=frameworks,
            key_files=key_files
        )
    
    def _determine_strategy(self, profile: ProjectProfile, analysis_type: str) -> Dict[str, Any]:
        """Определяет стратегию анализа на основе профиля проекта."""
        
        base_strategy = {
            "name": f"{analysis_type}_{profile.complexity.value}",
            "max_files": 20,
            "max_file_size": 3000,
            "use_multi_agent": False,
            "agents": ["research"],
            "git_depth": 0,
            "rag_queries": 0
        }
        
        # Адаптируем под сложность
        if profile.complexity == ProjectComplexity.SIMPLE:
            base_strategy["max_files"] = profile.code_files  # Все файлы
            base_strategy["max_file_size"] = 5000
        elif profile.complexity == ProjectComplexity.MEDIUM:
            base_strategy["max_files"] = 30
            base_strategy["max_file_size"] = 3000
            base_strategy["git_depth"] = 10
        elif profile.complexity == ProjectComplexity.COMPLEX:
            base_strategy["max_files"] = 40
            base_strategy["max_file_size"] = 2500
            base_strategy["use_multi_agent"] = True
            base_strategy["agents"] = ["research", "code_writer"]
            base_strategy["git_depth"] = 20
            base_strategy["rag_queries"] = 3
        else:  # LARGE
            base_strategy["max_files"] = 50
            base_strategy["max_file_size"] = 2000
            base_strategy["use_multi_agent"] = True
            base_strategy["agents"] = ["research", "code_writer", "react"]
            base_strategy["git_depth"] = 30
            base_strategy["rag_queries"] = 5
        
        # Адаптируем под тип анализа
        if analysis_type == "security":
            base_strategy["agents"].append("react")
            base_strategy["focus"] = "security"
        elif analysis_type == "performance":
            base_strategy["focus"] = "performance"
        elif analysis_type == "quick":
            base_strategy["max_files"] = min(10, base_strategy["max_files"])
            base_strategy["git_depth"] = 0
            base_strategy["rag_queries"] = 0
        
        return base_strategy
    
    async def _gather_context(
        self,
        path: Path,
        profile: ProjectProfile,
        strategy: Dict[str, Any],
        use_git: bool,
        use_rag: bool
    ) -> Dict[str, Any]:
        """Собирает контекст для анализа."""
        context = {
            "key_files": {},
            "files_content": {},
            "git_info": None,
            "rag_context": None,
            "structure": []
        }
        
        # 1. Читаем ключевые файлы
        for key_file in profile.key_files:
            file_path = path / key_file
            try:
                content = file_path.read_text(encoding='utf-8')[:5000]
                context["key_files"][key_file] = content
            except:
                pass
        
        # 2. Собираем структуру и код
        code_files = []
        def collect_files(current: Path, depth: int = 0):
            if depth > 3:
                return
            try:
                for item in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                    if item.name.startswith('.') or item.name in self.IGNORE_DIRS:
                        continue
                    rel = item.relative_to(path)
                    if item.is_dir():
                        context["structure"].append(f"{'  ' * depth}📁 {item.name}/")
                        collect_files(item, depth + 1)
                    elif item.suffix.lower() in self.CODE_EXTENSIONS:
                        context["structure"].append(f"{'  ' * depth}📄 {item.name}")
                        code_files.append(item)
            except:
                pass
        
        collect_files(path)
        
        # 3. Читаем файлы кода (по приоритету)
        priority_patterns = ['main', 'app', 'index', 'server', 'api', 'core', 'base']
        sorted_files = sorted(
            code_files[:strategy["max_files"] * 2],
            key=lambda f: (
                not any(p in f.stem.lower() for p in priority_patterns),
                len(str(f))
            )
        )
        
        for code_file in sorted_files[:strategy["max_files"]]:
            try:
                content = code_file.read_text(encoding='utf-8')
                truncated = content[:strategy["max_file_size"]]
                if len(content) > len(truncated):
                    truncated += f"\n... (ещё {len(content) - len(truncated)} символов)"
                context["files_content"][str(code_file.relative_to(path))] = truncated
            except:
                pass
        
        # 4. Git информация
        if use_git and profile.has_git and strategy["git_depth"] > 0:
            context["git_info"] = await self._get_git_info(path, strategy["git_depth"])
        
        # 5. RAG контекст
        if use_rag and self.vector_store and strategy["rag_queries"] > 0:
            context["rag_context"] = await self._get_rag_context(path, profile, strategy)
        
        return context
    
    async def _get_git_info(self, path: Path, depth: int) -> Optional[Dict[str, Any]]:
        """Получает информацию из git."""
        try:
            import subprocess
            
            # Последние коммиты
            result = subprocess.run(
                ['git', 'log', f'-{depth}', '--oneline', '--pretty=format:%h|%s|%an|%ar'],
                cwd=path, capture_output=True, text=True, timeout=5
            )
            commits = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[:depth]:
                    if '|' in line:
                        parts = line.split('|')
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1] if len(parts) > 1 else "",
                            "author": parts[2] if len(parts) > 2 else "",
                            "date": parts[3] if len(parts) > 3 else ""
                        })
            
            # Контрибьюторы
            result = subprocess.run(
                ['git', 'shortlog', '-sn', '--no-merges'],
                cwd=path, capture_output=True, text=True, timeout=5
            )
            contributors = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[:5]:
                    parts = line.strip().split('\t')
                    if len(parts) == 2:
                        contributors.append({"name": parts[1], "commits": int(parts[0])})
            
            # Статус
            result = subprocess.run(
                ['git', 'status', '--short'],
                cwd=path, capture_output=True, text=True, timeout=5
            )
            uncommitted = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            
            return {
                "recent_commits": commits,
                "contributors": contributors,
                "uncommitted_changes": uncommitted
            }
        except Exception as e:
            logger.debug(f"Git info error: {e}")
            return None
    
    async def _get_rag_context(
        self,
        path: Path,
        profile: ProjectProfile,
        strategy: Dict[str, Any]
    ) -> Optional[str]:
        """Получает релевантный контекст через RAG."""
        try:
            if not self.vector_store:
                return None
            
            # Формируем запросы на основе проекта
            queries = [
                f"main functionality of {profile.name}",
                f"architecture and structure of {' '.join(profile.frameworks) if profile.frameworks else 'the project'}"
            ]
            
            if strategy.get("focus") == "security":
                queries.append("security vulnerabilities and authentication")
            elif strategy.get("focus") == "performance":
                queries.append("performance optimization and caching")
            
            results = []
            for query in queries[:strategy["rag_queries"]]:
                try:
                    search_result = await self.vector_store.search(query, k=3)
                    if search_result:
                        results.extend(search_result)
                except:
                    pass
            
            if results:
                return "\n---\n".join([r.get("content", "")[:500] for r in results[:5]])
            
            return None
        except Exception as e:
            logger.debug(f"RAG context error: {e}")
            return None
    
    async def _run_analysis(
        self,
        profile: ProjectProfile,
        context: Dict[str, Any],
        strategy: Dict[str, Any],
        specific_question: Optional[str]
    ) -> Dict[str, Any]:
        """Выполняет анализ через агентов."""
        
        # Формируем промпт
        context_text = self._format_context(profile, context)
        
        if specific_question:
            task = f"""Проанализируй проект и ответь на вопрос.

ПРОЕКТ: {profile.name}
Сложность: {profile.complexity.value}
Языки: {', '.join(profile.languages.keys())}
Фреймворки: {', '.join(profile.frameworks) if profile.frameworks else 'Не определены'}

ВОПРОС: {specific_question}

КОНТЕКСТ:
{context_text}

Предоставь детальный ответ на основе анализа кода."""
        else:
            task = f"""Выполни комплексный анализ проекта.

ПРОЕКТ: {profile.name}
Сложность: {profile.complexity.value}
Файлов кода: {profile.code_files}
Строк кода: {profile.total_lines}
Языки: {', '.join(f"{k}: {v}" for k, v in profile.languages.items())}
Фреймворки: {', '.join(profile.frameworks) if profile.frameworks else 'Не определены'}
Тесты: {'✅ Есть' if profile.has_tests else '❌ Нет'}
Документация: {'✅ Есть' if profile.has_docs else '❌ Нет'}
CI/CD: {'✅ Есть' if profile.has_ci else '❌ Нет'}

КОНТЕКСТ:
{context_text}

Предоставь:
1. **Обзор проекта** - назначение и основная функциональность
2. **Архитектура** - структура, паттерны, зависимости
3. **Качество кода** - сильные и слабые стороны
4. **Рекомендации** - конкретные улучшения с примерами
5. **Риски** - потенциальные проблемы и как их избежать

Отвечай структурированно, с конкретными примерами из кода."""
        
        # Выполняем анализ
        if strategy.get("use_multi_agent") and len(strategy.get("agents", [])) > 1:
            # Мульти-агентный анализ для сложных проектов
            return await self._multi_agent_analysis(task, strategy, context)
        else:
            # Одиночный агент
            result = await self.engine.execute_task(
                task=task,
                agent_type=strategy.get("agents", ["research"])[0],
                context={
                    "project_path": str(profile.path),
                    "complexity": profile.complexity.value,
                    "analysis_type": strategy.get("name", "default")
                }
            )
            return result
    
    async def _multi_agent_analysis(
        self,
        task: str,
        strategy: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Мульти-агентный анализ для сложных проектов."""
        results = {}
        
        # Запускаем анализ параллельно
        agents = strategy.get("agents", ["research"])
        tasks = []
        
        for agent in agents:
            agent_task = task
            if agent == "code_writer":
                agent_task = f"Проанализируй код и найди возможные улучшения:\n\n{task}"
            elif agent == "react":
                agent_task = f"Пошагово проанализируй архитектуру и зависимости:\n\n{task}"
            
            tasks.append(
                self.engine.execute_task(
                    task=agent_task,
                    agent_type=agent,
                    context={"analysis_mode": "multi_agent"}
                )
            )
        
        try:
            agent_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for agent, result in zip(agents, agent_results):
                if isinstance(result, Exception):
                    results[agent] = {"error": str(result)}
                else:
                    results[agent] = result
        except Exception as e:
            logger.error(f"Multi-agent analysis error: {e}")
            return {"error": str(e)}
        
        # Объединяем результаты
        combined = {
            "final_answer": "",
            "insights": [],
            "recommendations": [],
            "agent_results": results
        }
        
        for agent, result in results.items():
            if isinstance(result, dict):
                if result.get("final_answer"):
                    combined["final_answer"] += f"\n\n### Анализ от {agent}:\n{result['final_answer']}"
                if result.get("analysis"):
                    combined["final_answer"] += f"\n\n### Анализ от {agent}:\n{result['analysis']}"
        
        return combined
    
    def _format_context(self, profile: ProjectProfile, context: Dict[str, Any]) -> str:
        """Форматирует контекст для промпта."""
        parts = []
        
        # Ключевые файлы
        for name, content in context.get("key_files", {}).items():
            parts.append(f"=== {name} ===\n{content[:3000]}")
        
        # Структура
        if context.get("structure"):
            parts.append("=== Структура проекта ===")
            parts.append('\n'.join(context["structure"][:50]))
            if len(context["structure"]) > 50:
                parts.append(f"... и ещё {len(context['structure']) - 50} элементов")
        
        # Код
        for path, content in list(context.get("files_content", {}).items())[:20]:
            parts.append(f"\n=== {path} ===\n{content}")
        
        # Git
        if context.get("git_info"):
            git = context["git_info"]
            parts.append("\n=== Git информация ===")
            if git.get("recent_commits"):
                parts.append("Последние коммиты:")
                for c in git["recent_commits"][:5]:
                    parts.append(f"  - {c['hash']}: {c['message']} ({c['author']}, {c['date']})")
            if git.get("contributors"):
                parts.append("Контрибьюторы:")
                for c in git["contributors"]:
                    parts.append(f"  - {c['name']}: {c['commits']} коммитов")
        
        # RAG
        if context.get("rag_context"):
            parts.append("\n=== Релевантный контекст из базы знаний ===")
            parts.append(context["rag_context"][:2000])
        
        return '\n'.join(parts)

