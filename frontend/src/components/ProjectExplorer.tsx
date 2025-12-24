import React, { useState, useCallback, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { 
  Folder, FolderOpen, File, FileCode, FileText, FileJson, Settings, 
  Globe, Terminal, Database, Lock, Code, Palette, Search, Brain, 
  ChevronRight, ChevronLeft, AlertTriangle, Loader2
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
}

interface ProjectStats {
  files: number;
  dirs: number;
  code_files: number;
}

interface AnalysisResult {
  success: boolean;
  result?: any;
  files_analyzed?: number;
  total_lines?: number;
}

// File Tree Component
function FileTree({ 
  node, 
  depth = 0, 
  onFileClick,
  expandedPaths,
  toggleExpand
}: { 
  node: FileInfo; 
  depth?: number; 
  onFileClick: (file: FileInfo) => void;
  expandedPaths: Set<string>;
  toggleExpand: (path: string) => void;
}) {
  const isExpanded = expandedPaths.has(node.path);
  
  const FILE_ICONS: Record<string, React.ElementType> = {
    '.py': Code,
    '.js': FileCode,
    '.jsx': FileCode,
    '.ts': FileCode,
    '.tsx': FileCode,
    '.html': Globe,
    '.css': Palette,
    '.json': FileJson,
    '.md': FileText,
    '.yaml': Settings,
    '.yml': Settings,
    '.sql': Database,
    '.sh': Terminal,
    '.env': Lock,
  };

  const getFileIcon = (file: FileInfo) => {
    if (file.is_dir) {
      const IconComponent = isExpanded ? FolderOpen : Folder;
      return <IconComponent size={14} strokeWidth={1.5} className="text-yellow-400" />;
    }
    const ext = file.extension?.toLowerCase();
    const IconComponent = FILE_ICONS[ext || ''] || File;
    return <IconComponent size={14} strokeWidth={1.5} className="text-gray-400" />;
  };

  return (
    <div style={{ marginLeft: depth * 12 }}>
      <div
        className={`flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer transition-colors text-sm ${
          node.is_dir 
            ? 'hover:bg-[#1f2236] text-gray-300' 
            : 'hover:bg-blue-900/30 text-gray-400 hover:text-white'
        }`}
        onClick={() => {
          if (node.is_dir) {
            toggleExpand(node.path);
          } else {
            onFileClick(node);
          }
        }}
      >
        {getFileIcon(node)}
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
            <FileTree
              key={`${child.path}-${idx}`}
              node={child}
              depth={depth + 1}
              onFileClick={onFileClick}
              expandedPaths={expandedPaths}
              toggleExpand={toggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Main Component
export function ProjectExplorer() {
  const [projectPath, setProjectPath] = useState('');
  const [projectTree, setProjectTree] = useState<FileInfo | null>(null);
  const [projectStats, setProjectStats] = useState<ProjectStats | null>(null);
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // File management
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['.']));
  
  // Analysis
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisType, setAnalysisType] = useState('overview');
  const [customQuestion, setCustomQuestion] = useState('');

  // Sidebar collapse
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Open project
  const handleOpenProject = useCallback(async () => {
    if (!projectPath.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/project/open`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: projectPath, max_depth: 5 })
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
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [projectPath]);

  // Read file
  const handleFileClick = useCallback(async (file: FileInfo) => {
    // Check if already open
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
      
      if (!response.ok) {
        throw new Error('Failed to read file');
      }
      
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
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  // Analyze project
  const handleAnalyze = useCallback(async () => {
    if (!projectPath) return;
    
    setAnalyzing(true);
    setAnalysisResult(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/project/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          analysis_type: analysisType,
          specific_question: customQuestion || null
        })
      });
      
      if (!response.ok) {
        throw new Error('Analysis failed');
      }
      
      const data = await response.json();
      setAnalysisResult(data);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  }, [projectPath, analysisType, customQuestion]);

  const activeFileContent = openFiles.find(f => f.path === activeFile);

  return (
    <div className="flex h-full bg-[#0f111b] text-white overflow-hidden">
      {/* Sidebar - File Tree */}
      <div className={`${sidebarCollapsed ? 'w-0' : 'w-72'} bg-[#131524] border-r border-[#1f2236] transition-all duration-300 overflow-hidden flex flex-col`}>
        {/* Project Input */}
        <div className="p-3 border-b border-[#1f2236]">
          <div className="flex items-center gap-2 mb-2">
            <Folder size={18} strokeWidth={1.5} className="text-yellow-400" />
            <span className="text-sm font-semibold text-gray-200">Проект</span>
          </div>
          <div className="flex gap-1">
            <input
              type="text"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              placeholder="/путь/к/проекту"
              className="flex-1 px-2 py-1.5 text-xs bg-[#0f111b] border border-[#1f2236] rounded focus:outline-none focus:border-blue-500 text-white placeholder-gray-500"
              onKeyPress={(e) => e.key === 'Enter' && handleOpenProject()}
            />
            <button
              onClick={handleOpenProject}
              disabled={loading || !projectPath.trim()}
              className="px-2 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-xs transition-colors"
            >
              {loading ? '...' : '→'}
            </button>
          </div>
          {projectStats && (
            <div className="mt-2 text-[10px] text-gray-500 flex gap-3">
              <span className="flex items-center gap-1"><Folder size={10} strokeWidth={1.5} /> {projectStats.dirs}</span>
              <span className="flex items-center gap-1"><File size={10} strokeWidth={1.5} /> {projectStats.files}</span>
              <span className="flex items-center gap-1"><Code size={10} strokeWidth={1.5} /> {projectStats.code_files}</span>
            </div>
          )}
        </div>
        
        {/* File Tree */}
        <div className="flex-1 overflow-y-auto p-2">
          {projectTree ? (
            <FileTree
              node={projectTree}
              onFileClick={handleFileClick}
              expandedPaths={expandedPaths}
              toggleExpand={toggleExpand}
            />
          ) : (
            <div className="text-center text-gray-500 text-xs py-8">
              <p>Введите путь к проекту</p>
              <p className="mt-1 text-[10px]">и нажмите Enter</p>
            </div>
          )}
        </div>
        
        {/* Analysis Panel */}
        {projectTree && (
          <div className="p-3 border-t border-[#1f2236]">
            <div className="flex items-center gap-2 mb-2">
              <Search size={14} strokeWidth={1.5} className="text-purple-400" />
              <span className="text-xs font-semibold text-gray-300">AI Анализ</span>
            </div>
            <select
              value={analysisType}
              onChange={(e) => setAnalysisType(e.target.value)}
              className="w-full px-2 py-1.5 text-xs bg-[#0f111b] border border-[#1f2236] rounded focus:outline-none focus:border-blue-500 mb-2"
            >
              <option value="overview">📊 Обзор проекта</option>
              <option value="structure">📁 Структура</option>
              <option value="dependencies">📦 Зависимости</option>
              <option value="issues">⚠️ Проблемы</option>
            </select>
            <input
              type="text"
              value={customQuestion}
              onChange={(e) => setCustomQuestion(e.target.value)}
              placeholder="Или задайте вопрос..."
              className="w-full px-2 py-1.5 text-xs bg-[#0f111b] border border-[#1f2236] rounded focus:outline-none focus:border-blue-500 mb-2"
            />
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="w-full px-2 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded text-xs transition-colors flex items-center justify-center gap-1"
            >
              {analyzing ? (
                <>
                  <Loader2 size={12} strokeWidth={1.5} className="animate-spin" />
                  <span>Анализ...</span>
                </>
              ) : (
                <>
                  <Brain size={12} strokeWidth={1.5} />
                  <span>Анализировать</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
      
      {/* Collapse button */}
      <button
        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        className="absolute left-0 top-1/2 -translate-y-1/2 z-10 w-4 h-12 bg-[#1f2236] hover:bg-[#2a2f46] rounded-r flex items-center justify-center transition-colors"
        style={{ left: sidebarCollapsed ? 0 : 'calc(18rem - 4px)' }}
      >
        {sidebarCollapsed 
          ? <ChevronRight size={10} strokeWidth={2} className="text-gray-400" /> 
          : <ChevronLeft size={10} strokeWidth={2} className="text-gray-400" />
        }
      </button>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Tabs */}
        <div className="flex items-center bg-[#131524] border-b border-[#1f2236] h-9 overflow-x-auto">
          {openFiles.map(file => (
            <div
              key={file.path}
              onClick={() => setActiveFile(file.path)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer border-r border-[#1f2236] transition-colors min-w-0 ${
                activeFile === file.path
                  ? 'bg-[#0f111b] text-white'
                  : 'bg-[#1a1d2e] text-gray-400 hover:text-white'
              }`}
            >
              <span className="truncate max-w-[120px]">{file.name}</span>
              {file.isDirty && <span className="text-blue-400">●</span>}
              <button
                onClick={(e) => handleCloseFile(file.path, e)}
                className="ml-1 hover:text-red-400 transition-colors"
              >
                ×
              </button>
            </div>
          ))}
          {openFiles.length === 0 && (
            <div className="px-3 py-1.5 text-xs text-gray-500">
              Выберите файл для редактирования
            </div>
          )}
        </div>

        {/* Editor / Analysis Result */}
        <div className="flex-1 flex overflow-hidden">
          {/* Editor */}
          <div className={`${analysisResult ? 'w-1/2' : 'flex-1'} flex flex-col transition-all`}>
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
              />
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-500">
                <div className="text-center">
                  <FolderOpen size={48} strokeWidth={1} className="mx-auto mb-4 text-gray-600" />
                  <p className="text-sm">Откройте проект и выберите файл</p>
                  <p className="text-xs mt-2 text-gray-600">
                    Введите путь к папке проекта в панели слева
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Analysis Result Panel */}
          {analysisResult && (
            <div className="w-1/2 border-l border-[#1f2236] flex flex-col bg-[#0f111b]">
              <div className="flex items-center justify-between p-3 border-b border-[#1f2236] bg-[#131524]">
                <div className="flex items-center gap-2">
                  <Brain size={18} strokeWidth={1.5} className="text-purple-400" />
                  <span className="text-sm font-semibold">Результат анализа</span>
                </div>
                <button
                  onClick={() => setAnalysisResult(null)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  ×
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {analysisResult.result?.final_answer && (
                  <div className="prose prose-invert prose-sm max-w-none">
                    <div className="whitespace-pre-wrap text-sm text-gray-300 leading-relaxed">
                      {analysisResult.result.final_answer}
                    </div>
                  </div>
                )}
                {analysisResult.result?.analysis && (
                  <div className="whitespace-pre-wrap text-sm text-gray-300 leading-relaxed">
                    {analysisResult.result.analysis}
                  </div>
                )}
                <div className="mt-4 pt-4 border-t border-[#1f2236] text-xs text-gray-500">
                  <p className="flex items-center gap-1"><File size={10} strokeWidth={1.5} /> Файлов проанализировано: {analysisResult.files_analyzed}</p>
                  <p className="flex items-center gap-1"><Code size={10} strokeWidth={1.5} /> Всего строк кода: {analysisResult.total_lines}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error Toast */}
      {error && (
        <div className="fixed bottom-4 right-4 bg-red-900/90 border border-red-500 text-red-200 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 z-50">
          <AlertTriangle size={16} strokeWidth={1.5} />
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-white">×</button>
        </div>
      )}
    </div>
  );
}

