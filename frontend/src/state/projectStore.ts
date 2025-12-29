/**
 * ProjectStore - Shared state between Chat and IDE components
 * 
 * This store enables the Chat to be aware of the currently open project
 * and its files, allowing for context-aware assistance.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
  content?: string;
  language?: string;
  size?: number;
  modified?: number;
}

export interface OpenFile {
  path: string;
  name: string;
  content: string;
  language: string;
  modified: boolean;
  cursor?: {
    line: number;
    column: number;
  };
}

export interface ProjectContext {
  /** Summary of the project structure for LLM context */
  summary: string;
  /** Main languages used in the project */
  languages: string[];
  /** Key files (README, package.json, etc.) */
  keyFiles: string[];
  /** Total file count */
  fileCount: number;
  /** Generated at timestamp */
  generatedAt: number;
}

interface ProjectState {
  // Project info
  projectPath: string | null;
  projectName: string | null;
  projectTree: FileNode[];
  projectContext: ProjectContext | null;
  
  // Open files in IDE
  openFiles: OpenFile[];
  activeFilePath: string | null;
  
  // Recent projects
  recentProjects: Array<{
    path: string;
    name: string;
    openedAt: number;
  }>;
  
  // Actions
  setProject: (path: string, name: string, tree: FileNode[]) => void;
  clearProject: () => void;
  updateProjectTree: (tree: FileNode[]) => void;
  setProjectContext: (context: ProjectContext) => void;
  
  // File actions
  openFile: (file: OpenFile) => void;
  closeFile: (path: string) => void;
  setActiveFile: (path: string | null) => void;
  updateFileContent: (path: string, content: string) => void;
  markFileSaved: (path: string) => void;
  
  // Helpers
  getContextForChat: () => string;
  getActiveFileContent: () => string | null;
}

/**
 * Generate a summary of the project for LLM context
 */
function generateProjectSummary(tree: FileNode[], path: string): ProjectContext {
  const languages: Set<string> = new Set();
  const keyFiles: string[] = [];
  let fileCount = 0;
  
  const languageExtensions: Record<string, string> = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript React',
    '.jsx': 'JavaScript React',
    '.rs': 'Rust',
    '.go': 'Go',
    '.java': 'Java',
    '.cpp': 'C++',
    '.c': 'C',
    '.rb': 'Ruby',
    '.php': 'PHP',
    '.swift': 'Swift',
    '.kt': 'Kotlin',
    '.cs': 'C#',
    '.vue': 'Vue',
    '.svelte': 'Svelte',
  };
  
  const keyFilePatterns = [
    'README.md',
    'readme.md',
    'package.json',
    'requirements.txt',
    'Cargo.toml',
    'go.mod',
    'pyproject.toml',
    'setup.py',
    'Makefile',
    'Dockerfile',
    'docker-compose.yml',
    '.env.example',
    'tsconfig.json',
    'vite.config.ts',
  ];
  
  function traverse(nodes: FileNode[]) {
    for (const node of nodes) {
      if (node.type === 'file') {
        fileCount++;
        
        // Detect language
        const ext = node.name.slice(node.name.lastIndexOf('.'));
        if (languageExtensions[ext]) {
          languages.add(languageExtensions[ext]);
        }
        
        // Check for key files
        if (keyFilePatterns.includes(node.name)) {
          keyFiles.push(node.path);
        }
      } else if (node.children) {
        traverse(node.children);
      }
    }
  }
  
  traverse(tree);
  
  const languageList = Array.from(languages);
  const summary = `Project at ${path} with ${fileCount} files. ` +
    `Main languages: ${languageList.join(', ') || 'Unknown'}. ` +
    `Key files: ${keyFiles.slice(0, 5).join(', ') || 'None detected'}.`;
  
  return {
    summary,
    languages: languageList,
    keyFiles: keyFiles.slice(0, 10),
    fileCount,
    generatedAt: Date.now(),
  };
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set, get) => ({
      // Initial state
      projectPath: null,
      projectName: null,
      projectTree: [],
      projectContext: null,
      openFiles: [],
      activeFilePath: null,
      recentProjects: [],
      
      // Set project
      setProject: (path: string, name: string, tree: FileNode[]) => {
        const context = generateProjectSummary(tree, path);
        
        set((state) => {
          // Add to recent projects
          const recentProjects = [
            { path, name, openedAt: Date.now() },
            ...state.recentProjects.filter((p) => p.path !== path),
          ].slice(0, 10);
          
          return {
            projectPath: path,
            projectName: name,
            projectTree: tree,
            projectContext: context,
            recentProjects,
            // Keep open files if same project, clear otherwise
            openFiles: state.projectPath === path ? state.openFiles : [],
            activeFilePath: state.projectPath === path ? state.activeFilePath : null,
          };
        });
      },
      
      // Clear project
      clearProject: () => {
        set({
          projectPath: null,
          projectName: null,
          projectTree: [],
          projectContext: null,
          openFiles: [],
          activeFilePath: null,
        });
      },
      
      // Update project tree
      updateProjectTree: (tree: FileNode[]) => {
        const state = get();
        if (state.projectPath) {
          const context = generateProjectSummary(tree, state.projectPath);
          set({ projectTree: tree, projectContext: context });
        }
      },
      
      // Set project context
      setProjectContext: (context: ProjectContext) => {
        set({ projectContext: context });
      },
      
      // Open file
      openFile: (file: OpenFile) => {
        set((state) => {
          const existing = state.openFiles.findIndex((f) => f.path === file.path);
          if (existing >= 0) {
            // Update existing file
            const openFiles = [...state.openFiles];
            openFiles[existing] = { ...openFiles[existing], ...file };
            return { openFiles, activeFilePath: file.path };
          }
          return {
            openFiles: [...state.openFiles, file],
            activeFilePath: file.path,
          };
        });
      },
      
      // Close file
      closeFile: (path: string) => {
        set((state) => {
          const openFiles = state.openFiles.filter((f) => f.path !== path);
          let activeFilePath = state.activeFilePath;
          
          // If closing active file, switch to another
          if (activeFilePath === path) {
            activeFilePath = openFiles.length > 0 ? openFiles[openFiles.length - 1].path : null;
          }
          
          return { openFiles, activeFilePath };
        });
      },
      
      // Set active file
      setActiveFile: (path: string | null) => {
        set({ activeFilePath: path });
      },
      
      // Update file content
      updateFileContent: (path: string, content: string) => {
        set((state) => ({
          openFiles: state.openFiles.map((f) =>
            f.path === path ? { ...f, content, modified: true } : f
          ),
        }));
      },
      
      // Mark file as saved
      markFileSaved: (path: string) => {
        set((state) => ({
          openFiles: state.openFiles.map((f) =>
            f.path === path ? { ...f, modified: false } : f
          ),
        }));
      },
      
      // Get context string for chat
      getContextForChat: () => {
        const state = get();
        
        if (!state.projectPath) {
          return '';
        }
        
        let context = `\n\n📁 **Current Project Context:**\n`;
        context += `- Path: ${state.projectPath}\n`;
        
        if (state.projectContext) {
          context += `- ${state.projectContext.summary}\n`;
        }
        
        // Add active file info
        if (state.activeFilePath) {
          const activeFile = state.openFiles.find((f) => f.path === state.activeFilePath);
          if (activeFile) {
            context += `\n📄 **Currently Editing:** ${activeFile.name} (${activeFile.language})\n`;
            
            // Add first 50 lines of active file for context
            const lines = activeFile.content.split('\n');
            if (lines.length > 0) {
              const preview = lines.slice(0, 50).join('\n');
              context += `\`\`\`${activeFile.language}\n${preview}\n`;
              if (lines.length > 50) {
                context += `... (${lines.length - 50} more lines)\n`;
              }
              context += `\`\`\`\n`;
            }
          }
        }
        
        return context;
      },
      
      // Get active file content
      getActiveFileContent: () => {
        const state = get();
        if (!state.activeFilePath) return null;
        const file = state.openFiles.find((f) => f.path === state.activeFilePath);
        return file?.content || null;
      },
    }),
    {
      name: 'aillm-project-store',
      // Only persist certain fields
      partialize: (state) => ({
        recentProjects: state.recentProjects,
      }),
    }
  )
);

export default useProjectStore;

