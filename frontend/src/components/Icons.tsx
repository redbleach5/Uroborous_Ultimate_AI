/**
 * Unified Icon System - монохромные иконки для всего проекта
 * Использует lucide-react для консистентного минималистичного стиля
 */

import {
  // Navigation & Actions
  ChevronRight,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  X,
  Plus,
  Minus,
  Check,
  Search,
  Settings,
  MoreHorizontal,
  MoreVertical,
  
  // Files & Folders
  Folder,
  FolderOpen,
  File,
  FileText,
  FileCode,
  FileCog,
  FileJson,
  FileType,
  Files,
  
  // Code & Development
  Code,
  Code2,
  Terminal,
  Bug,
  Play,
  Square,
  RefreshCw,
  Cpu,
  Braces,
  Hash,
  
  // AI & Brain
  Brain,
  Sparkles,
  Zap,
  Lightbulb,
  Target,
  Crosshair,
  
  // Git & Version Control
  GitBranch,
  GitCommit,
  GitMerge,
  GitPullRequest,
  History,
  
  // Analysis & Data
  BarChart3,
  PieChart,
  TrendingUp,
  Activity,
  LineChart,
  Database,
  
  // Status & Progress
  Loader2,
  Clock,
  Timer,
  CircleCheck,
  CircleX,
  AlertCircle,
  Info,
  AlertTriangle,
  
  // Communication
  MessageSquare,
  Send,
  Bot,
  User,
  Users,
  
  // Layout & UI
  Layout,
  Sidebar,
  PanelLeft,
  PanelRight,
  Maximize2,
  Minimize2,
  Copy,
  Trash2,
  Edit3,
  Save,
  Download,
  Upload,
  ExternalLink,
  Link,
  
  // Misc
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Shield,
  Key,
  Globe,
  Package,
  Layers,
  Box,
  
  // Types from lucide
  type LucideIcon,
  type LucideProps,
} from 'lucide-react';

// Re-export all icons for easy access
export {
  ChevronRight,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  X,
  Plus,
  Minus,
  Check,
  Search,
  Settings,
  MoreHorizontal,
  MoreVertical,
  Folder,
  FolderOpen,
  File,
  FileText,
  FileCode,
  FileCog,
  FileJson,
  FileType,
  Files,
  Code,
  Code2,
  Terminal,
  Bug,
  Play,
  Square,
  RefreshCw,
  Cpu,
  Braces,
  Hash,
  Brain,
  Sparkles,
  Zap,
  Lightbulb,
  Target,
  Crosshair,
  GitBranch,
  GitCommit,
  GitMerge,
  GitPullRequest,
  History,
  BarChart3,
  PieChart,
  TrendingUp,
  Activity,
  LineChart,
  Database,
  Loader2,
  Clock,
  Timer,
  CircleCheck,
  CircleX,
  AlertCircle,
  Info,
  AlertTriangle,
  MessageSquare,
  Send,
  Bot,
  User,
  Users,
  Layout,
  Sidebar,
  PanelLeft,
  PanelRight,
  Maximize2,
  Minimize2,
  Copy,
  Trash2,
  Edit3,
  Save,
  Download,
  Upload,
  ExternalLink,
  Link,
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Shield,
  Key,
  Globe,
  Package,
  Layers,
  Box,
};

export type { LucideIcon, LucideProps };

// Icon mapping for file extensions
const FILE_ICON_MAP: Record<string, LucideIcon> = {
  '.py': Code,
  '.js': Braces,
  '.jsx': Braces,
  '.ts': Code2,
  '.tsx': Code2,
  '.html': Globe,
  '.css': FileType,
  '.json': FileJson,
  '.md': FileText,
  '.yaml': FileCog,
  '.yml': FileCog,
  '.sql': Database,
  '.sh': Terminal,
  '.env': Lock,
  '.git': GitBranch,
};

// Get icon for file based on extension
export function getFileIcon(extension?: string, isDir?: boolean, isExpanded?: boolean): LucideIcon {
  if (isDir) {
    return isExpanded ? FolderOpen : Folder;
  }
  if (!extension) return File;
  return FILE_ICON_MAP[extension.toLowerCase()] || File;
}

// Common icon component with default styling
interface IconProps extends LucideProps {
  icon: LucideIcon;
}

export function Icon({ icon: IconComponent, className = '', size = 16, strokeWidth = 1.5, ...props }: IconProps) {
  return (
    <IconComponent 
      className={`shrink-0 ${className}`}
      size={size}
      strokeWidth={strokeWidth}
      {...props}
    />
  );
}

// Spinner component
export function Spinner({ className = '', size = 16 }: { className?: string; size?: number }) {
  return <Loader2 className={`animate-spin ${className}`} size={size} strokeWidth={1.5} />;
}

// Progress stage icons mapping
export const PROGRESS_ICONS: Record<string, LucideIcon> = {
  starting: Clock,
  profiling: BarChart3,
  strategy: Target,
  scanning: Files,
  git: GitCommit,
  rag: Search,
  analyzing: Brain,
  processing: Cpu,
  generating: Sparkles,
  completed: CircleCheck,
  error: CircleX,
};

// Get progress icon
export function getProgressIcon(stage: string): LucideIcon {
  return PROGRESS_ICONS[stage] || Loader2;
}

