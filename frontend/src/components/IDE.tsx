import React, { useState, useCallback, useRef, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { executeTask, executeTool } from '../api/client';
import {
  Folder, FolderOpen, File, FileCode, FileJson, FileText, FileCog,
  Code, Code2, Terminal, Database, Globe, Lock,
  Brain, Target, Files, Search, Cpu, Sparkles,
  CircleCheck, CircleX, Clock, Loader2, BarChart3,
  GitCommit, Play, Square, Plus, X, ChevronLeft, ChevronRight,
  Trash2, History, Package, Layers, RefreshCw, Send, Download,
  PanelLeft, ExternalLink, AlertCircle, ChevronUp,
  type LucideIcon
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Saved recent projects in localStorage
const RECENT_PROJECTS_KEY = 'aillm_recent_projects';
const MAX_RECENT_PROJECTS = 5;

const getRecentProjects = (): string[] => {
  try {
    const stored = localStorage.getItem(RECENT_PROJECTS_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
};

const saveRecentProject = (path: string) => {
  try {
    const recent = getRecentProjects().filter(p => p !== path);
    recent.unshift(path);
    localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(recent.slice(0, MAX_RECENT_PROJECTS)));
  } catch {
    // Ignore storage errors
  }
};

// Types
interface FileInfo {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
  extension?: string;
  children?: FileInfo[];
}

interface OpenFile {
  path: string;
  name: string;
  content: string;
  language: string;
  isDirty: boolean;
  isNew?: boolean; // Новый файл (не из проекта)
}

interface ProjectStats {
  files: number;
  dirs: number;
  code_files: number;
}

// File icon mapping
const FILE_ICONS: Record<string, LucideIcon> = {
  '.py': Code,
  '.js': FileCode,
  '.jsx': FileCode,
  '.ts': Code2,
  '.tsx': Code2,
  '.html': Globe,
  '.css': Layers,
  '.json': FileJson,
  '.md': FileText,
  '.yaml': FileCog,
  '.yml': FileCog,
  '.sql': Database,
  '.sh': Terminal,
  '.env': Lock,
};

const getFileIcon = (file: FileInfo, isExpanded?: boolean): LucideIcon => {
  if (file.is_dir) {
    return isExpanded ? FolderOpen : Folder;
  }
  const ext = file.extension?.toLowerCase();
  return FILE_ICONS[ext || ''] || File;
};

// File Tree Component
function FileTree({ 
  node, depth = 0, onFileClick, expandedPaths, toggleExpand 
}: { 
  node: FileInfo; depth?: number; 
  onFileClick: (file: FileInfo) => void;
  expandedPaths: Set<string>;
  toggleExpand: (path: string) => void;
}) {
  const isExpanded = expandedPaths.has(node.path);
  const IconComponent = getFileIcon(node, isExpanded);

  return (
    <div style={{ marginLeft: depth * 12 }}>
      <div
        className={`flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer transition-colors text-sm ${
          node.is_dir ? 'hover:bg-[#1f2236] text-gray-300' : 'hover:bg-blue-900/30 text-gray-400 hover:text-white'
        }`}
        onClick={() => node.is_dir ? toggleExpand(node.path) : onFileClick(node)}
      >
        <IconComponent size={14} strokeWidth={1.5} className="shrink-0 opacity-70" />
        <span className="truncate flex-1">{node.name}</span>
        {!node.is_dir && node.size && node.size > 0 && (
          <span className="text-[10px] text-gray-500">
            {node.size < 1024 ? `${node.size}B` : `${(node.size / 1024).toFixed(1)}KB`}
          </span>
        )}
      </div>
      {node.is_dir && isExpanded && node.children && (
        <div>
          {node.children.map((child, idx) => (
            <FileTree key={`${child.path}-${idx}`} node={child} depth={depth + 1}
              onFileClick={onFileClick} expandedPaths={expandedPaths} toggleExpand={toggleExpand} />
          ))}
        </div>
      )}
    </div>
  );
}

// Main IDE Component
export function IDE() {
  // Project state
  const [projectPath, setProjectPath] = useState('');
  const [projectTree, setProjectTree] = useState<FileInfo | null>(null);
  const [projectStats, setProjectStats] = useState<ProjectStats | null>(null);
  const [projectName, setProjectName] = useState('');
  const [projectLoading, setProjectLoading] = useState(false);
  
  // File state
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['.']));
  
  // Code generation state
  const [task, setTask] = useState('');
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [language, setLanguage] = useState<'python' | 'javascript' | 'typescript' | 'html'>('python');
  const [htmlPreviewUrl, setHtmlPreviewUrl] = useState<string | null>(null);
  
  // AI Analysis state
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [analysisType, setAnalysisType] = useState('overview');
  const [customQuestion, setCustomQuestion] = useState('');
  
  // Progress state
  const [progressStage, setProgressStage] = useState<string>('');
  const [progressMessage, setProgressMessage] = useState<string>('');
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [progressDetails, setProgressDetails] = useState<any>(null);
  
  // UI state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentProjects, setRecentProjects] = useState<string[]>([]);
  const [showRecentProjects, setShowRecentProjects] = useState(false);
  
  // Browser state
  const [showBrowser, setShowBrowser] = useState(false);
  const [browserPath, setBrowserPath] = useState('~');
  const [browserDirs, setBrowserDirs] = useState<Array<{name: string; path: string; has_code: boolean}>>([]);
  const [browserLoading, setBrowserLoading] = useState(false);
  
  const editorRef = useRef<any>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Load recent projects on mount
  useEffect(() => {
    setRecentProjects(getRecentProjects());
  }, []);

  // Open project (defined first to avoid circular dependency)
  const handleOpenProject = useCallback(async (pathOverride?: string) => {
    const path = pathOverride || projectPath;
    if (!path.trim()) return;
    
    setProjectLoading(true);
    setError(null);
    setShowRecentProjects(false);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/project/open`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: path, max_depth: 5 })
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to open project');
      }
      
      const data = await response.json();
      setProjectTree(data.tree);
      setProjectStats(data.stats);
      setProjectName(data.project_name);
      setExpandedPaths(new Set(['.']));
      setProjectPath(path);
      
      // Save to recent projects
      saveRecentProject(path);
      setRecentProjects(getRecentProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setProjectLoading(false);
    }
  }, [projectPath]);

  // Browse directory via backend API
  const browseDirViaAPI = useCallback(async (path: string) => {
    setBrowserLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/project/browse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to browse directory');
      }
      
      const data = await response.json();
      setBrowserPath(data.current_path);
      setBrowserDirs(data.directories || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка при просмотре директории');
    } finally {
      setBrowserLoading(false);
    }
  }, []);

  // Open folder browser
  const handleOpenBrowser = useCallback(() => {
    setShowBrowser(true);
    setShowRecentProjects(false);
    browseDirViaAPI('~');
  }, [browseDirViaAPI]);

  // Navigate to parent directory
  const handleBrowserGoUp = useCallback(() => {
    const parent = browserPath.split('/').slice(0, -1).join('/') || '/';
    browseDirViaAPI(parent);
  }, [browserPath, browseDirViaAPI]);

  // Select directory from browser
  const handleBrowserSelect = useCallback((dir: {name: string; path: string; has_code: boolean}) => {
    if (dir.has_code) {
      // This looks like a project - open it
      setShowBrowser(false);
      handleOpenProject(dir.path);
    } else {
      // Navigate into directory
      browseDirViaAPI(dir.path);
    }
  }, [browseDirViaAPI, handleOpenProject]);

  // Select from recent projects
  const handleSelectRecentProject = useCallback((path: string) => {
    setProjectPath(path);
    setShowRecentProjects(false);
  }, []);

  // Read file from project
  const handleFileClick = useCallback(async (file: FileInfo) => {
    const existing = openFiles.find(f => f.path === file.path);
    if (existing) {
      setActiveFile(file.path);
      return;
    }
    
    try {
      const fullPath = projectPath.endsWith('/') 
        ? `${projectPath}${file.path}` 
        : `${projectPath}/${file.path}`;
      
      const response = await fetch(`${API_BASE_URL}/api/v1/project/read-file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: fullPath })
      });
      
      if (!response.ok) throw new Error('Failed to read file');
      const data = await response.json();
      
      if (data.is_binary) {
        setError(`Cannot open binary file: ${file.name}`);
        return;
      }
      
      const newFile: OpenFile = {
        path: file.path,
        name: file.name,
        content: data.content,
        language: data.language || 'plaintext',
        isDirty: false
      };
      
      setOpenFiles(prev => [...prev, newFile]);
      setActiveFile(file.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file');
    }
  }, [projectPath, openFiles]);

  // Create new file (for code generation)
  const createNewFile = useCallback((name: string, content: string, lang: string) => {
    const path = `__new__/${name}`;
    const existing = openFiles.find(f => f.path === path);
    
    if (existing) {
      setOpenFiles(prev => prev.map(f => f.path === path ? { ...f, content, isDirty: true } : f));
    } else {
      const newFile: OpenFile = { path, name, content, language: lang, isDirty: true, isNew: true };
      setOpenFiles(prev => [...prev, newFile]);
    }
    setActiveFile(path);
  }, [openFiles]);

  // Close file
  const handleCloseFile = useCallback((path: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenFiles(prev => prev.filter(f => f.path !== path));
    if (activeFile === path) {
      const remaining = openFiles.filter(f => f.path !== path);
      setActiveFile(remaining.length > 0 ? remaining[remaining.length - 1].path : null);
    }
  }, [activeFile, openFiles]);

  // Update file content
  const handleEditorChange = useCallback((value: string | undefined, path: string) => {
    setOpenFiles(prev => prev.map(f => 
      f.path === path ? { ...f, content: value || '', isDirty: true } : f
    ));
  }, []);

  // Toggle folder expand
  const toggleExpand = useCallback((path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  }, []);

  // Generate code
  const handleGenerate = useCallback(async () => {
    if (!task.trim()) return;
    setGenerating(true);
    setError(null);
    
    try {
      const activeContent = openFiles.find(f => f.path === activeFile)?.content;
      
      const response = await executeTask({
        task,
        agent_type: 'code_writer',
        context: { existing_code: activeContent || '', language }
      });
      
      if (response.success && response.result?.code) {
        const code = response.result.code;
        const fileName = `generated.${language === 'python' ? 'py' : language === 'html' ? 'html' : language === 'typescript' ? 'ts' : 'js'}`;
        createNewFile(fileName, code, language);
        setBottomPanelOpen(true);
        setRunResult('✅ Код успешно сгенерирован!');
      } else {
        setError('Не удалось сгенерировать код');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  }, [task, language, activeFile, openFiles, createNewFile]);

  // Run code
  const handleRun = useCallback(async () => {
    const activeContent = openFiles.find(f => f.path === activeFile)?.content;
    if (!activeContent) {
      setError('Нет кода для выполнения');
      return;
    }
    
    setRunning(true);
    setRunResult(null);
    setBottomPanelOpen(true);
    
    try {
      const activeLang = openFiles.find(f => f.path === activeFile)?.language || 'python';
      
      // HTML preview
      if (activeLang === 'html' || activeContent.includes('<!DOCTYPE') || activeContent.includes('<html')) {
        if (htmlPreviewUrl?.startsWith('blob:')) URL.revokeObjectURL(htmlPreviewUrl);
        const blob = new Blob([activeContent], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        setHtmlPreviewUrl(url);
        setRunResult('✅ HTML открыт в предпросмотре');
        setRunning(false);
        return;
      }
      
      // Execute code
      const langCmd: Record<string, string> = {
        'python': `python3 - <<'PY'\n${activeContent}\nPY`,
        'javascript': `node - <<'JS'\n${activeContent}\nJS`,
        'typescript': `npx ts-node - <<'TS'\n${activeContent}\nTS`,
      };
      
      const command = langCmd[activeLang] || langCmd['python'];
      
      const response = await executeTool({
        tool_name: 'execute_command',
        input: { command }
      });
      
      const stdout = response?.result?.stdout || '';
      const stderr = response?.result?.stderr || '';
      setRunResult([stdout && `stdout:\n${stdout}`, stderr && `stderr:\n${stderr}`].filter(Boolean).join('\n\n') || 'Нет вывода');
    } catch (err) {
      setRunResult(`Ошибка: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setRunning(false);
    }
  }, [activeFile, openFiles, htmlPreviewUrl]);

  // Analyze project with SSE progress streaming
  const handleAnalyze = useCallback(async () => {
    if (!projectPath) {
      setError('Сначала откройте проект');
      return;
    }
    
    // Reset state
    setAnalyzing(true);
    setAnalysisResult(null);
    setError(null);
    setProgressStage('starting');
    setProgressMessage('Начинаем анализ...');
    setProgressPercent(0);
    setProgressDetails(null);
    setBottomPanelOpen(true);
    
    try {
      // Use SSE endpoint for streaming progress
      const response = await fetch(`${API_BASE_URL}/api/v1/project/analyze-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          analysis_type: analysisType,
          specific_question: customQuestion || null
        })
      });
      
      if (!response.ok) {
        throw new Error(`Ошибка: ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('Stream not available');
      }
      
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Parse SSE events
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              
              // Update progress state
              setProgressStage(event.stage);
              setProgressMessage(event.message);
              setProgressPercent(Math.max(0, event.progress) * 100);
              setProgressDetails(event.details);
              
              // Handle completion
              if (event.stage === 'completed' && event.details?.result) {
                setAnalysisResult(event.details.result);
              } else if (event.stage === 'error') {
                setError(event.message);
                setAnalysisResult({ error: event.message });
              }
            } catch (e) {
              console.debug('Parse error:', e);
            }
          }
        }
      }
      
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка анализа';
      setError(message);
      setProgressStage('error');
      setProgressMessage(message);
      setAnalysisResult({ error: message });
    } finally {
      setAnalyzing(false);
    }
  }, [projectPath, analysisType, customQuestion]);

  const activeFileContent = openFiles.find(f => f.path === activeFile);

  return (
    <div className="flex h-full bg-[#0f111b] text-white overflow-hidden">
      {/* Sidebar */}
      <div className={`${sidebarCollapsed ? 'w-0' : 'w-64'} bg-[#131524] border-r border-[#1f2236] transition-all duration-300 overflow-hidden flex flex-col`}>
        {/* Project Input */}
        <div className="p-3 border-b border-[#1f2236]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <FolderOpen size={18} strokeWidth={1.5} className="text-blue-400" />
              <span className="text-sm font-semibold text-gray-200">
                {projectName || 'Проект'}
              </span>
            </div>
            {recentProjects.length > 0 && (
              <button
                onClick={() => setShowRecentProjects(!showRecentProjects)}
                className="text-[10px] text-gray-400 hover:text-white transition-colors flex items-center gap-1"
                title="Недавние проекты"
              >
                <History size={10} strokeWidth={1.5} /> Недавние
              </button>
            )}
          </div>
          
          {/* Recent Projects Dropdown */}
          {showRecentProjects && recentProjects.length > 0 && (
            <div className="mb-2 bg-[#0a0c14] border border-[#1f2236] rounded-lg overflow-hidden">
              <div className="px-2 py-1 text-[10px] text-gray-500 border-b border-[#1f2236]">
                Недавние проекты
              </div>
              {recentProjects.map((path, idx) => (
                <button
                  key={idx}
                  onClick={() => handleOpenProject(path)}
                  className="w-full px-2 py-1.5 text-xs text-left text-gray-300 hover:bg-[#1f2236] hover:text-white transition-colors truncate flex items-center gap-2"
                  title={path}
                >
                  <Folder size={12} strokeWidth={1.5} />
                  <span className="truncate">{path.split('/').pop() || path}</span>
                </button>
              ))}
            </div>
          )}
          
          {/* Path Input */}
          <div className="relative">
            <div className="flex gap-1">
              <div className="flex-1 relative">
                <input
                  type="text"
                  value={projectPath}
                  onChange={(e) => setProjectPath(e.target.value)}
                  placeholder="Путь к проекту..."
                  className="w-full px-2 py-1.5 pr-8 text-xs bg-[#0f111b] border border-[#1f2236] rounded focus:outline-none focus:border-blue-500 text-white placeholder-gray-500"
                  onKeyPress={(e) => e.key === 'Enter' && handleOpenProject()}
                  onFocus={() => recentProjects.length > 0 && !projectPath && setShowRecentProjects(true)}
                />
                {projectPath && (
                  <button
                    onClick={() => setProjectPath('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white text-xs"
                  >
                    ×
                  </button>
                )}
              </div>
              <button
                onClick={handleOpenBrowser}
                className="px-2 py-1.5 bg-[#1f2236] hover:bg-[#2a2f46] rounded text-xs transition-colors"
                title="Обзор..."
              >
                <Folder size={14} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => handleOpenProject()}
                disabled={projectLoading || !projectPath.trim()}
                className="px-2 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-xs transition-colors"
                title="Открыть проект"
              >
                {projectLoading ? (
                  <Loader2 size={14} strokeWidth={1.5} className="animate-spin" />
                ) : (
                  <ChevronRight size={14} strokeWidth={1.5} />
                )}
              </button>
            </div>
          </div>
          
          {/* Common paths hint */}
          {!projectPath && !showRecentProjects && (
            <div className="mt-2 space-y-1">
              <div className="text-[10px] text-gray-500">Быстрый доступ:</div>
              <div className="flex flex-wrap gap-1">
                {[
                  { label: '~', path: '~' },
                  { label: 'Documents', path: '~/Documents' },
                  { label: 'Projects', path: '~/Projects' },
                ].map(({ label, path }) => (
                  <button
                    key={path}
                    onClick={() => setProjectPath(path)}
                    className="px-1.5 py-0.5 text-[10px] bg-[#1f2236] hover:bg-[#2a2f46] rounded text-gray-400 hover:text-white transition-colors"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
          
          {/* Project Stats */}
          {projectStats && (
            <div className="mt-2 text-[10px] text-gray-500 flex gap-3">
              <span className="flex items-center gap-1"><Folder size={10} strokeWidth={1.5} /> {projectStats.dirs}</span>
              <span className="flex items-center gap-1"><File size={10} strokeWidth={1.5} /> {projectStats.files}</span>
              <span className="flex items-center gap-1"><FileCode size={10} strokeWidth={1.5} /> {projectStats.code_files}</span>
            </div>
          )}
        </div>
        
        {/* File Tree */}
        <div className="flex-1 overflow-y-auto p-2">
          {projectTree ? (
            <FileTree node={projectTree} onFileClick={handleFileClick}
              expandedPaths={expandedPaths} toggleExpand={toggleExpand} />
          ) : (
            <div className="text-center text-gray-500 text-xs py-8">
              <FolderOpen size={24} strokeWidth={1} className="mx-auto mb-2 opacity-50" />
              <p>Откройте проект</p>
              <p className="mt-1 text-[10px]">или создайте новый файл</p>
            </div>
          )}
        </div>
        
        {/* Quick Actions */}
        <div className="p-2 border-t border-[#1f2236] space-y-1">
          <button
            onClick={() => createNewFile('untitled.py', '# Новый файл\n', 'python')}
            className="w-full px-2 py-1.5 text-xs text-left hover:bg-[#1f2236] rounded flex items-center gap-2"
          >
            <Plus size={14} strokeWidth={1.5} />
            <span>Новый файл</span>
          </button>
          {projectTree && (
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className={`w-full px-2 py-1.5 text-xs text-left rounded flex items-center gap-2 transition-all ${
                analyzing 
                  ? 'bg-purple-900/50 text-purple-200 cursor-wait' 
                  : 'hover:bg-purple-900/30 text-purple-300'
              }`}
            >
              {analyzing ? <Loader2 size={14} strokeWidth={1.5} className="animate-spin" /> : <Brain size={14} strokeWidth={1.5} />}
              <span>{analyzing ? 'Анализируем...' : 'AI Анализ проекта'}</span>
            </button>
          )}
          {!projectTree && (
            <div className="px-2 py-1.5 text-[10px] text-gray-500 italic">
              Откройте проект для анализа
            </div>
          )}
        </div>
      </div>
      
      {/* Collapse Toggle */}
      <button
        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        className="absolute left-0 top-1/2 -translate-y-1/2 z-10 w-4 h-12 bg-[#1f2236] hover:bg-[#2a2f46] rounded-r flex items-center justify-center transition-colors"
        style={{ left: sidebarCollapsed ? 0 : 'calc(16rem - 4px)' }}
      >
        {sidebarCollapsed ? 
          <ChevronRight size={10} strokeWidth={1.5} className="text-gray-400" /> : 
          <ChevronLeft size={10} strokeWidth={1.5} className="text-gray-400" />
        }
      </button>

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-3 py-2 bg-[#131524] border-b border-[#1f2236]">
          {/* Task Input */}
          <div className="flex-1 flex items-center gap-2 bg-[#0f111b] border border-[#1f2236] rounded-lg px-3 py-1.5">
            <input
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Опишите что сгенерировать..."
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
              onKeyPress={(e) => e.key === 'Enter' && handleGenerate()}
            />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as any)}
              className="px-2 py-1 text-xs bg-transparent border-l border-[#1f2236] text-gray-300 focus:outline-none cursor-pointer"
            >
              <option value="python" className="bg-[#0f111b]">Python</option>
              <option value="javascript" className="bg-[#0f111b]">JavaScript</option>
              <option value="typescript" className="bg-[#0f111b]">TypeScript</option>
              <option value="html" className="bg-[#0f111b]">HTML</option>
            </select>
          </div>
          
          {/* Buttons */}
          <button
            onClick={handleGenerate}
            disabled={generating || !task.trim()}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5"
          >
            {generating ? <Loader2 size={14} strokeWidth={1.5} className="animate-spin" /> : <Sparkles size={14} strokeWidth={1.5} />}
            <span>Генерация</span>
          </button>
          <button
            onClick={handleRun}
            disabled={running || !activeFile}
            className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5"
          >
            {running ? <Loader2 size={14} strokeWidth={1.5} className="animate-spin" /> : <Play size={14} strokeWidth={1.5} />}
            <span>Запуск</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center bg-[#1a1d2e] border-b border-[#1f2236] h-9 overflow-x-auto">
          {openFiles.map(file => {
            const TabIcon = file.isNew ? Sparkles : FileCode;
            return (
              <div
                key={file.path}
                onClick={() => setActiveFile(file.path)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer border-r border-[#1f2236] transition-colors min-w-0 ${
                  activeFile === file.path ? 'bg-[#0f111b] text-white' : 'bg-[#1a1d2e] text-gray-400 hover:text-white'
                }`}
              >
                <TabIcon size={12} strokeWidth={1.5} className="shrink-0" />
                <span className="truncate max-w-[100px]">{file.name}</span>
                {file.isDirty && <span className="text-blue-400 ml-0.5">●</span>}
                <button onClick={(e) => handleCloseFile(file.path, e)} className="ml-1 hover:text-red-400"><X size={12} strokeWidth={1.5} /></button>
              </div>
            );
          })}
          {openFiles.length === 0 && (
            <div className="px-3 py-1.5 text-xs text-gray-500">Откройте или создайте файл</div>
          )}
        </div>

        {/* Editor */}
        <div className={`flex-1 ${bottomPanelOpen ? 'h-1/2' : ''}`}>
          {activeFileContent ? (
            <Editor
              height="100%"
              language={activeFileContent.language}
              value={activeFileContent.content}
              onChange={(value) => handleEditorChange(value, activeFileContent.path)}
              theme="vs-dark"
              options={{
                minimap: { enabled: true },
                fontSize: 13,
                wordWrap: 'on',
                lineNumbers: 'on',
                folding: true,
                automaticLayout: true
              }}
              onMount={(editor) => { editorRef.current = editor; }}
            />
          ) : (
            <div className="flex-1 h-full flex items-center justify-center text-gray-500">
              <div className="text-center">
                <Terminal size={48} strokeWidth={1} className="mx-auto mb-4 opacity-40" />
                <p className="text-lg font-medium">IDE</p>
                <p className="text-sm mt-2 text-gray-600">
                  Откройте проект или опишите задачу для генерации кода
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Panel */}
        {bottomPanelOpen && (
          <div className="h-1/3 min-h-[150px] border-t border-[#1f2236] bg-[#0a0c14] flex flex-col">
            <div className="flex items-center justify-between px-3 py-1.5 bg-[#131524] border-b border-[#1f2236]">
              <div className="flex items-center gap-4 text-xs">
                <button
                  onClick={() => { setRunResult(null); setAnalysisResult(null); }}
                  className={`px-2 py-1 rounded flex items-center gap-1.5 ${!analysisResult ? 'bg-[#1f2236] text-white' : 'text-gray-400 hover:text-white'}`}
                >
                  <Terminal size={12} strokeWidth={1.5} /> Вывод
                </button>
                {analysisResult && (
                  <button className="px-2 py-1 rounded bg-purple-900/30 text-purple-300 flex items-center gap-1.5">
                    <Brain size={12} strokeWidth={1.5} /> Анализ
                  </button>
                )}
              </div>
              <button onClick={() => setBottomPanelOpen(false)} className="text-gray-400 hover:text-white"><X size={14} strokeWidth={1.5} /></button>
            </div>
            
            <div className="flex-1 overflow-auto p-3">
              {/* HTML Preview */}
              {htmlPreviewUrl && (
                <div className="mb-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-400">HTML Предпросмотр</span>
                    <div className="flex gap-2">
                      <button onClick={() => window.open(htmlPreviewUrl, '_blank')}
                        className="text-xs px-2 py-1 bg-blue-600/50 hover:bg-blue-600 rounded">
                        Открыть в новом окне
                      </button>
                      <button onClick={() => { URL.revokeObjectURL(htmlPreviewUrl); setHtmlPreviewUrl(null); }}
                        className="text-xs px-2 py-1 bg-red-600/50 hover:bg-red-600 rounded">
                        Закрыть
                      </button>
                    </div>
                  </div>
                  <iframe src={htmlPreviewUrl} className="w-full h-[300px] bg-white rounded border border-[#1f2236]"
                    title="Preview" sandbox="allow-scripts allow-same-origin" />
                </div>
              )}
              
              {/* Run Result */}
              {runResult && !analysisResult && (
                <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap">{runResult}</pre>
              )}
              
              {/* Analyzing Progress Indicator */}
              {analyzing && (
                <div className="flex flex-col items-center justify-center py-6 space-y-4">
                  {/* Animated icon based on stage */}
                  <div className="text-purple-400">
                    {progressStage === 'profiling' && <BarChart3 size={40} strokeWidth={1.5} />}
                    {progressStage === 'strategy' && <Target size={40} strokeWidth={1.5} />}
                    {progressStage === 'scanning' && <Files size={40} strokeWidth={1.5} />}
                    {progressStage === 'git' && <GitCommit size={40} strokeWidth={1.5} />}
                    {progressStage === 'rag' && <Search size={40} strokeWidth={1.5} />}
                    {progressStage === 'analyzing' && <Brain size={40} strokeWidth={1.5} className="animate-pulse" />}
                    {progressStage === 'processing' && <Cpu size={40} strokeWidth={1.5} />}
                    {progressStage === 'error' && <CircleX size={40} strokeWidth={1.5} className="text-red-400" />}
                    {(!progressStage || progressStage === 'starting') && <Loader2 size={40} strokeWidth={1.5} className="animate-spin" />}
                  </div>
                  
                  {/* Message */}
                  <div className="text-sm text-purple-300 font-medium">
                    {progressMessage || 'Анализируем проект...'}
                  </div>
                  
                  {/* Progress bar */}
                  <div className="w-full max-w-xs">
                    <div className="h-2 bg-[#1f2236] rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-purple-600 to-blue-500 transition-all duration-500 ease-out"
                        style={{ width: `${Math.max(5, progressPercent)}%` }}
                      />
                    </div>
                    <div className="flex justify-between mt-1 text-[10px] text-gray-500">
                      <span>{progressPercent > 0 ? `${Math.round(progressPercent)}%` : 'Инициализация...'}</span>
                      <span className="capitalize">{progressStage.replace('_', ' ')}</span>
                    </div>
                  </div>
                  
                  {/* Details */}
                  {progressDetails && Object.keys(progressDetails).length > 0 && (
                    <div className="mt-2 p-2 bg-[#1f2236]/50 rounded text-[10px] text-gray-400 max-w-xs">
                      {progressDetails.complexity && (
                        <div>Сложность: <span className="text-purple-300">{progressDetails.complexity}</span></div>
                      )}
                      {progressDetails.files && (
                        <div>Файлов кода: <span className="text-blue-300">{progressDetails.files}</span></div>
                      )}
                      {progressDetails.languages && (
                        <div>Языки: <span className="text-green-300">{progressDetails.languages.join(', ')}</span></div>
                      )}
                      {progressDetails.files_read && (
                        <div>Прочитано: <span className="text-yellow-300">{progressDetails.files_read} файлов</span></div>
                      )}
                      {progressDetails.agents && (
                        <div>Агенты: <span className="text-cyan-300">{progressDetails.agents.join(', ')}</span></div>
                      )}
                      {progressDetails.info && (
                        <div className="mt-1 text-gray-500 italic">{progressDetails.info}</div>
                      )}
                    </div>
                  )}
                </div>
              )}
              
              {/* Analysis Result */}
              {analysisResult && !analyzing && (
                <div className="space-y-4">
                  {analysisResult.error ? (
                    <div className="text-red-400 text-sm flex items-center gap-2">
                      <CircleX size={14} strokeWidth={1.5} /> {analysisResult.error}
                    </div>
                  ) : (
                    <>
                      {/* Profile Summary */}
                      <div className="flex flex-wrap gap-3 text-xs">
                        <div className="px-2 py-1 bg-purple-900/30 rounded text-purple-300 flex items-center gap-1">
                          <Target size={12} strokeWidth={1.5} /> {analysisResult.complexity || 'unknown'}
                        </div>
                        <div className="px-2 py-1 bg-blue-900/30 rounded text-blue-300 flex items-center gap-1">
                          <Files size={12} strokeWidth={1.5} /> {analysisResult.files_analyzed || 0} файлов
                        </div>
                        <div className="px-2 py-1 bg-green-900/30 rounded text-green-300 flex items-center gap-1">
                          <Code size={12} strokeWidth={1.5} /> {(analysisResult.total_lines || 0).toLocaleString()} строк
                        </div>
                        {analysisResult.profile?.languages && Object.keys(analysisResult.profile.languages).length > 0 && (
                          <div className="px-2 py-1 bg-yellow-900/30 rounded text-yellow-300 flex items-center gap-1">
                            <Terminal size={12} strokeWidth={1.5} /> {Object.keys(analysisResult.profile.languages).slice(0, 3).join(', ')}
                          </div>
                        )}
                        {analysisResult.profile?.frameworks && analysisResult.profile.frameworks.length > 0 && (
                          <div className="px-2 py-1 bg-cyan-900/30 rounded text-cyan-300 flex items-center gap-1">
                            <Package size={12} strokeWidth={1.5} /> {analysisResult.profile.frameworks.join(', ')}
                          </div>
                        )}
                        {analysisResult.elapsed_seconds && (
                          <div className="px-2 py-1 bg-gray-800 rounded text-gray-400 flex items-center gap-1">
                            <Clock size={12} strokeWidth={1.5} /> {analysisResult.elapsed_seconds}s
                          </div>
                        )}
                      </div>
                      
                      {/* Strategy info */}
                      {analysisResult.strategy_used && (
                        <div className="text-[10px] text-gray-500">
                          Стратегия: {analysisResult.strategy_used}
                        </div>
                      )}
                      
                      {/* Main analysis */}
                      <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed prose prose-invert prose-sm max-w-none">
                        {analysisResult.result?.final_answer || analysisResult.result?.analysis || analysisResult.analysis || 'Нет результата'}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Folder Browser Modal */}
      {showBrowser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="bg-[#131524] border border-[#1f2236] rounded-xl shadow-2xl w-[500px] max-h-[70vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-[#1f2236]">
              <div className="flex items-center gap-2">
                <FolderOpen size={20} strokeWidth={1.5} className="text-blue-400" />
                <span className="font-semibold text-gray-200">Выбор папки проекта</span>
              </div>
              <button
                onClick={() => setShowBrowser(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X size={18} strokeWidth={1.5} />
              </button>
            </div>
            
            {/* Current Path */}
            <div className="px-4 py-2 bg-[#0a0c14] border-b border-[#1f2236] flex items-center gap-2">
              <button
                onClick={handleBrowserGoUp}
                disabled={browserPath === '/'}
                className="px-2 py-1 bg-[#1f2236] hover:bg-[#2a2f46] disabled:opacity-50 rounded text-xs transition-colors flex items-center gap-1"
              >
                <ChevronUp size={12} strokeWidth={1.5} /> Вверх
              </button>
              <div className="flex-1 text-xs text-gray-400 truncate font-mono">
                {browserPath}
              </div>
            </div>
            
            {/* Directory List */}
            <div className="flex-1 overflow-y-auto p-2">
              {browserLoading ? (
                <div className="flex items-center justify-center py-8 text-gray-400">
                  <Loader2 size={16} strokeWidth={1.5} className="animate-spin mr-2" />
                  Загрузка...
                </div>
              ) : browserDirs.length > 0 ? (
                <div className="space-y-1">
                  {browserDirs.map((dir, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleBrowserSelect(dir)}
                      onDoubleClick={() => {
                        setShowBrowser(false);
                        handleOpenProject(dir.path);
                      }}
                      className={`w-full px-3 py-2 text-left rounded-lg transition-colors flex items-center gap-3 ${
                        dir.has_code
                          ? 'bg-green-900/20 hover:bg-green-900/40 border border-green-500/30'
                          : 'hover:bg-[#1f2236]'
                      }`}
                    >
                      {dir.has_code ? 
                        <Package size={18} strokeWidth={1.5} className="text-green-400 shrink-0" /> : 
                        <Folder size={18} strokeWidth={1.5} className="text-gray-400 shrink-0" />
                      }
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{dir.name}</div>
                        {dir.has_code && (
                          <div className="text-[10px] text-green-400">Проект с кодом</div>
                        )}
                      </div>
                      {dir.has_code ? (
                        <span className="text-xs text-green-400">Открыть</span>
                      ) : (
                        <ChevronRight size={14} strokeWidth={1.5} className="text-gray-500" />
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500 text-sm">
                  Нет подпапок
                </div>
              )}
            </div>
            
            {/* Footer */}
            <div className="p-3 border-t border-[#1f2236] flex items-center justify-between">
              <div className="text-[10px] text-gray-500 flex items-center gap-1">
                <AlertCircle size={10} strokeWidth={1.5} /> Двойной клик или "Открыть" для выбора проекта
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setShowBrowser(false);
                    handleOpenProject(browserPath);
                  }}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs font-medium transition-colors"
                >
                  Открыть текущую
                </button>
                <button
                  onClick={() => setShowBrowser(false)}
                  className="px-3 py-1.5 bg-[#1f2236] hover:bg-[#2a2f46] rounded text-xs transition-colors"
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error Toast */}
      {error && (
        <div className="fixed bottom-4 right-4 bg-red-900/90 border border-red-500 text-red-200 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 z-50">
          <span>⚠️</span>
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-white">×</button>
        </div>
      )}
    </div>
  );
}

