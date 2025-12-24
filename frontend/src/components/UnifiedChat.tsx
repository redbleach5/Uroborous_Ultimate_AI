import React, { useEffect, useMemo, useRef, useState } from 'react';
import { executeTask, processBatchTasks, executeTool } from '../api/client';
import { useChatStore, ChatMode } from '../state/chatStore';
import { useExecutionInfo } from '../state/executionContext';
import { LearningProgress } from './LearningProgress';
import {
  MessageSquare, Bot, Brain, Zap, Send, Loader2, User, CircleCheck, CircleX,
  BarChart3, Lightbulb, AlertTriangle, ChevronDown, ChevronRight, ChevronLeft, Copy, 
  Play, Trash2, Plus, Settings, RefreshCw, Pencil, Code, FileText, Globe, Search,
  Clock, type LucideIcon
} from 'lucide-react';

// Helper function to extract code from markdown blocks
const extractCodeFromMarkdown = (text: string): string | null => {
  if (!text) return null;
  
  // Try to find code blocks
  const codeBlockRegex = /```(\w+)?\s*([\s\S]*?)```/g;
  const matches = [];
  let match;
  
  while ((match = codeBlockRegex.exec(text)) !== null) {
    const language = match[1]?.toLowerCase() || '';
    const content = match[2].trim();
    if (content.length > 0) {
      matches.push({ language, content });
    }
  }
  
  // If we found code blocks, return the largest one (likely the main code)
  if (matches.length > 0) {
    const largest = matches.reduce((prev, current) => 
      current.content.length > prev.content.length ? current : prev
    );
    return largest.content;
  }
  
  // If no code blocks, check if the entire text is code (starts with <!DOCTYPE, <html, def, class, etc.)
  const trimmed = text.trim();
  if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
      trimmed.startsWith('def ') || trimmed.startsWith('class ') ||
      trimmed.startsWith('import ') || trimmed.startsWith('function ') ||
      trimmed.startsWith('const ') || trimmed.startsWith('let ')) {
    return trimmed;
  }
  
  return null;
};

// Helper function to detect code type
const detectCodeType = (code: string): 'html' | 'python' | 'node' | 'bash' => {
  const trimmed = code.trim();
  
  // First check for HTML - this has highest priority
  // Check for HTML tags (even if mixed with JavaScript)
  if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
      code.includes('<html') || code.includes('</html>') ||
      code.includes('<head') || code.includes('</head>') ||
      code.includes('<body') || code.includes('</body>') ||
      code.includes('<div') || code.includes('</div>') ||
      code.includes('<style') || code.includes('</style>') ||
      code.includes('<script') || code.includes('</script>')) {
    return 'html';
  }
  
  // Check for CSS (standalone CSS file)
  if (code.includes('{') && code.includes('}') && 
      (code.includes('color:') || code.includes('background:') || 
       code.includes('margin:') || code.includes('padding:') || code.includes('font-')) &&
      !code.includes('def ') && !code.includes('function ') && !code.includes('const ')) {
    return 'html'; // Treat CSS as HTML for preview purposes
  }
  
  // Check for JavaScript/Node (only if no HTML tags)
  if ((code.includes('function ') || code.includes('const ') || 
      code.includes('let ') || code.includes('var ') ||
      code.includes('console.') || code.includes('require(') ||
      code.includes('import ') || code.includes('export ')) &&
      !code.includes('<') && !code.includes('>')) {
    return 'node';
  }
  
  // Check for Bash
  if (code.includes('#!/bin/bash') || code.includes('#!/bin/sh') ||
      code.includes('echo ') || code.includes('ls ') || 
      code.includes('cd ') || code.includes('mkdir ')) {
    return 'bash';
  }
  
  // Default to Python
  return 'python';
};

// Universal code block parser
interface ParsedCodeBlock {
  type: 'html' | 'css' | 'javascript' | 'js' | 'unknown';
  content: string;
  language?: string;
}

const parseCodeBlocks = (code: string): ParsedCodeBlock[] => {
  const blocks: ParsedCodeBlock[] = [];
  const codeBlockRegex = /```(\w+)?\s*([\s\S]*?)```/g;
  let match;
  
  while ((match = codeBlockRegex.exec(code)) !== null) {
    const language = match[1]?.toLowerCase() || '';
    const content = match[2].trim();
    
    let type: ParsedCodeBlock['type'] = 'unknown';
    
    if (language === 'html' || language === 'htm') {
      type = 'html';
    } else if (language === 'css') {
      type = 'css';
    } else if (language === 'javascript' || language === 'js') {
      type = 'javascript';
    } else if (language === 'typescript' || language === 'ts') {
      type = 'javascript';
    } else {
      if (content.includes('<!DOCTYPE') || content.includes('<html') || 
          (content.includes('<') && content.includes('>'))) {
        type = 'html';
      } else if (content.includes('{') && content.includes('}') && 
                 (content.includes(':') && (content.includes('color') || content.includes('background') || 
                  content.includes('margin') || content.includes('padding') || content.includes('font-')))) {
        type = 'css';
      } else if (content.includes('function') || content.includes('const ') || 
                 content.includes('let ') || content.includes('var ') ||
                 content.includes('addEventListener') || content.includes('document.')) {
        type = 'javascript';
      }
    }
    
    if (type !== 'unknown' && content.length > 0) {
      blocks.push({ type, content, language });
    }
  }
  
  if (blocks.length === 0) {
    const trimmed = code.trim();
    if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
        (trimmed.includes('<html') && trimmed.includes('</html>'))) {
      blocks.push({ type: 'html', content: trimmed });
    }
  }
  
  return blocks;
};

// Function to fix missing curly braces in CSS and JavaScript
const fixMissingBraces = (code: string, type: 'css' | 'javascript'): string => {
  if (type === 'css') {
    // Fix CSS: add braces after selectors
    const lines = code.split('\n');
    const fixedLines: string[] = [];
    let pendingSelector: { line: string; indent: string; index: number } | null = null;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      const indent = line.match(/^\s*/)?.[0] || '';
      const indentLevel = indent.length;
      
      // Check if line is a CSS selector (body, .class, #id, etc.)
      const isSelector = trimmed && 
        !trimmed.includes('{') && 
        !trimmed.includes('}') &&
        !trimmed.includes(':') &&
        (trimmed.match(/^[.#]?[a-zA-Z][a-zA-Z0-9_-]*(\s+[.#]?[a-zA-Z][a-zA-Z0-9_-]*)*\s*$/) ||
         trimmed.match(/^[.#]?[a-zA-Z][a-zA-Z0-9_-]*\s*$/));
      
      // Check if line is a CSS property (contains : and ;)
      const isProperty = trimmed && trimmed.includes(':') && !trimmed.includes('{') && !trimmed.includes('}');
      
      if (isSelector) {
        // Close previous block if exists
        if (pendingSelector) {
          fixedLines.push(pendingSelector.indent + '}');
        }
        pendingSelector = { line, indent, index: fixedLines.length };
        fixedLines.push(line);
      } else if (isProperty) {
        // If we have a pending selector and this is a property, add opening brace
        if (pendingSelector && indentLevel > pendingSelector.indent.length) {
          // Insert opening brace after the selector
          fixedLines.splice(pendingSelector.index + 1, 0, pendingSelector.indent + '{');
          pendingSelector = null;
        }
        fixedLines.push(line);
      } else if (trimmed === '}') {
        // Closing brace found
        if (pendingSelector) {
          pendingSelector = null;
        }
        fixedLines.push(line);
      } else if (trimmed && indentLevel === 0 && pendingSelector) {
        // New block at root level, close previous
        fixedLines.push(pendingSelector.indent + '}');
        pendingSelector = null;
        fixedLines.push(line);
      } else {
        fixedLines.push(line);
      }
    }
    
    // Close last pending block if exists
    if (pendingSelector) {
      fixedLines.push(pendingSelector.indent + '}');
    }
    
    return fixedLines.join('\n');
  } else if (type === 'javascript') {
    // Fix JavaScript: add braces after function declarations, if statements, loops, etc.
    const lines = code.split('\n');
    const fixedLines: string[] = [];
    const braceStack: { type: string; indent: number; lineIndex: number }[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      const indent = line.match(/^\s*/)?.[0] || '';
      const indentLevel = indent.length;
      
      // Check for function/if/for/while/else declarations without braces
      const funcMatch = trimmed.match(/^(function\s+\w+|const\s+\w+\s*=\s*function|let\s+\w+\s*=\s*function|var\s+\w+\s*=\s*function|if|for|while|else)\s*(\([^)]*\))?\s*$/);
      
      if (funcMatch && !trimmed.includes('{') && !trimmed.includes('}')) {
        // Check if next line is indented (suggesting missing brace)
        if (i + 1 < lines.length) {
          const nextLine = lines[i + 1];
          const nextIndent = nextLine.match(/^\s*/)?.[0] || '';
          const nextTrimmed = nextLine.trim();
          if (nextIndent.length > indentLevel && nextTrimmed.length > 0 && !nextTrimmed.startsWith('}')) {
            // Add opening brace
            fixedLines.push(line + ' {');
            braceStack.push({ type: funcMatch[1], indent: indentLevel, lineIndex: i });
            continue;
          }
        }
      }
      
      // Check if we need to close braces based on indentation
      while (braceStack.length > 0) {
        const lastBrace = braceStack[braceStack.length - 1];
        // If current line is at same or less indentation, and it's not a closing brace or opening brace
        if (indentLevel <= lastBrace.indent && trimmed.length > 0 && 
            !trimmed.startsWith('}') && !trimmed.includes('{') &&
            !trimmed.match(/^(function|const|let|var|if|for|while|else)\s/)) {
          // Close the brace
          fixedLines.push(' '.repeat(lastBrace.indent) + '}');
          braceStack.pop();
        } else {
          break;
        }
      }
      
      fixedLines.push(line);
      
      // Track existing braces in the line
      const openBraces = (line.match(/{/g) || []).length;
      const closeBraces = (line.match(/}/g) || []).length;
      for (let j = 0; j < openBraces - closeBraces; j++) {
        braceStack.push({ type: 'manual', indent: indentLevel, lineIndex: i });
      }
      for (let j = 0; j < closeBraces - openBraces; j++) {
        if (braceStack.length > 0) braceStack.pop();
      }
    }
    
    // Close any remaining open braces
    while (braceStack.length > 0) {
      const lastBrace = braceStack.pop();
      fixedLines.push(' '.repeat(lastBrace!.indent) + '}');
    }
    
    return fixedLines.join('\n');
  }
  
  return code;
};

// Smart HTML processor - combines HTML, CSS, and JS into a single valid HTML document
const processHtmlCode = (code: string): string => {
  const blocks = parseCodeBlocks(code);
  
  let htmlContent = '';
  const cssBlocks: string[] = [];
  const jsBlocks: string[] = [];
  
  for (const block of blocks) {
    if (block.type === 'html') {
      htmlContent = block.content;
    } else if (block.type === 'css') {
      cssBlocks.push(block.content);
    } else if (block.type === 'javascript' || block.type === 'js') {
      jsBlocks.push(block.content);
    }
  }
  
  if (!htmlContent) {
    const trimmed = code.trim();
    if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
        (trimmed.includes('<html') && trimmed.includes('</html>'))) {
      htmlContent = trimmed;
    } else {
      const htmlMatch = code.match(/<html[\s\S]*?<\/html>/i) || 
                       code.match(/<!DOCTYPE[\s\S]*?<\/html>/i) ||
                       code.match(/<body[\s\S]*?<\/body>/i);
      if (htmlMatch) {
        htmlContent = htmlMatch[0];
      }
    }
  }
  
  if (!htmlContent) {
    htmlContent = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<title>Generated Page</title>\n</head>\n<body>\n</body>\n</html>';
  }
  
  let processedHtml = htmlContent;
  processedHtml = processedHtml.replace(/<link[^>]*rel=["']stylesheet["'][^>]*>/gi, '');
  processedHtml = processedHtml.replace(/<script[^>]*src=["'][^"]+["'][^>]*>[\s\S]*?<\/script>/gi, '');
  
  const existingStyleMatches = processedHtml.match(/<style[^>]*>([\s\S]*?)<\/style>/gi);
  const existingStyles: string[] = [];
  if (existingStyleMatches) {
    for (const match of existingStyleMatches) {
      const content = match.replace(/<style[^>]*>|<\/style>/gi, '').trim();
      if (content) existingStyles.push(content);
    }
  }
  
  const existingScriptMatches = processedHtml.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
  const existingScripts: string[] = [];
  if (existingScriptMatches) {
    for (const match of existingScriptMatches) {
      if (!match.includes('src=')) {
        const content = match.replace(/<script[^>]*>|<\/script>/gi, '').trim();
        if (content) existingScripts.push(content);
      }
    }
  }
  
  // Combine all CSS and fix missing braces
  const allCss = [...existingStyles, ...cssBlocks]
    .filter(c => c.length > 0)
    .map(css => {
      // Always try to fix CSS - check for common patterns of missing braces
      const hasSelectorWithoutBrace = /^[.#]?[a-zA-Z][a-zA-Z0-9_-]*\s*$/m.test(css) && 
                                      !css.includes('{') && 
                                      css.includes(':');
      const braceMismatch = css.split('{').length !== css.split('}').length;
      
      if (hasSelectorWithoutBrace || braceMismatch || !css.includes('{')) {
        return fixMissingBraces(css, 'css');
      }
      return css;
    });
  
  // Combine all JS and fix missing braces
  const allJs = [...existingScripts, ...jsBlocks]
    .filter(j => j.length > 0)
    .map(js => {
      // Always try to fix JS - check for common patterns of missing braces
      const hasFunctionsWithoutBraces = /function\s+\w+\s*\([^)]*\)\s*\n\s*[^{]/.test(js);
      const hasIfForWhileWithoutBraces = /(if|for|while)\s*\([^)]*\)\s*\n\s*[^{]/.test(js);
      const braceMismatch = js.split('{').length !== js.split('}').length;
      
      if (hasFunctionsWithoutBraces || hasIfForWhileWithoutBraces || braceMismatch) {
        return fixMissingBraces(js, 'javascript');
      }
      return js;
    });
  
  processedHtml = processedHtml.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  processedHtml = processedHtml.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  
  if (allCss.length > 0) {
    const combinedCss = allCss.join('\n\n');
    if (processedHtml.includes('</head>')) {
      processedHtml = processedHtml.replace('</head>', `<style>\n${combinedCss}\n</style>\n</head>`);
    } else if (processedHtml.includes('<head>')) {
      processedHtml = processedHtml.replace('<head>', `<head>\n<style>\n${combinedCss}\n</style>`);
    } else {
      if (processedHtml.includes('</body>')) {
        processedHtml = processedHtml.replace('</body>', `<style>\n${combinedCss}\n</style>\n</body>`);
      } else if (processedHtml.includes('<body>')) {
        processedHtml = processedHtml.replace('<body>', `<body>\n<style>\n${combinedCss}\n</style>`);
      } else {
        processedHtml = processedHtml.replace(/<html[^>]*>/i, `$&\n<head>\n<style>\n${combinedCss}\n</style>\n</head>`);
      }
    }
  }
  
  if (allJs.length > 0) {
    const combinedJs = allJs.join('\n\n');
    if (processedHtml.includes('</body>')) {
      processedHtml = processedHtml.replace('</body>', `<script>\n${combinedJs}\n</script>\n</body>`);
    } else if (processedHtml.includes('<body>')) {
      processedHtml = processedHtml.replace('<body>', `<body>\n<script>\n${combinedJs}\n</script>`);
    } else {
      if (processedHtml.includes('</html>')) {
        processedHtml = processedHtml.replace('</html>', `<script>\n${combinedJs}\n</script>\n</html>`);
      } else {
        processedHtml += `\n<script>\n${combinedJs}\n</script>`;
      }
    }
  }
  
  if (!processedHtml.includes('<!DOCTYPE')) {
    if (processedHtml.includes('<html')) {
      processedHtml = '<!DOCTYPE html>\n' + processedHtml;
    }
  }
  
  if (!processedHtml.includes('</html>')) {
    processedHtml += '\n</html>';
  }
  
  if (processedHtml.includes('<body') && !processedHtml.includes('</body>')) {
    processedHtml = processedHtml.replace(/<\/html>/i, '</body>\n</html>');
  }
  
  return processedHtml;
};

// Простая функция для рендеринга markdown
function renderMarkdown(text: string): string {
  if (!text) return '';
  
  let html = text;
  
  // Блоки кода (обрабатываем первыми, чтобы не затронуть их содержимое)
  const codeBlocks: string[] = [];
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (_match, lang, code) => {
    const id = `CODE_BLOCK_${codeBlocks.length}`;
    const langLabel = lang ? `<span class="absolute top-2 right-3 text-xs text-gray-400 font-medium">${lang}</span>` : '';
    codeBlocks.push(`<div class="relative my-4"><pre class="bg-[#0a0a0f] p-4 rounded-xl overflow-x-auto border-2 border-[#1a1d2e] shadow-inner"><code class="text-sm font-mono text-gray-200">${code.trim().replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>${langLabel}</div>`);
    return id;
  });
  
  // Код в обратных кавычках (только если не внутри блока кода)
  html = html.replace(/`([^`\n]+)`/g, '<code class="bg-[#0f111b] px-2 py-1 rounded-lg text-sm font-mono text-blue-300 border border-[#1f2236]">$1</code>');
  
  // Заголовки
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-lg font-bold mt-6 mb-3 text-gray-100 border-b border-[#2a2f46] pb-2">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold mt-8 mb-4 text-gray-100 border-b border-[#2a2f46] pb-2">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-10 mb-5 text-gray-100 border-b-2 border-[#2a2f46] pb-3">$1</h1>');
  
  // Жирный текст
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-100">$1</strong>');
  
  // Курсив (только если не часть жирного)
  html = html.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em class="italic">$1</em>');
  
  // Ссылки в формате [текст](URL)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline break-words transition-colors">$1</a>');
  
  // Разделители
  html = html.replace(/^---$/gim, '<hr class="my-6 border-[#2a2f46]" />');
  
  // Обрабатываем списки построчно
  const lines = html.split('\n');
  const processedLines: string[] = [];
  let inList = false;
  let listType: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    
    // Проверяем, является ли строка элементом списка
    const ulMatch = trimmed.match(/^[\*\-\+]\s+(.+)$/);
    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    
    if (ulMatch || olMatch) {
      const itemText = ulMatch ? ulMatch[1] : olMatch![1];
      const currentListType = ulMatch ? 'ul' : 'ol';
      
      if (!inList || listType !== currentListType) {
        // Закрываем предыдущий список
        if (inList && listItems.length > 0) {
          const tag = listType === 'ul' ? 'ul' : 'ol';
          processedLines.push(`<${tag} class="list-${listType === 'ul' ? 'disc' : 'decimal'} ml-6 my-3 space-y-1">`);
          listItems.forEach(item => processedLines.push(`  <li class="mb-1">${item}</li>`));
          processedLines.push(`</${tag}>`);
          listItems = [];
        }
        inList = true;
        listType = currentListType;
      }
      listItems.push(itemText);
    } else {
      // Закрываем список, если он был открыт
      if (inList && listItems.length > 0) {
        const tag = listType === 'ul' ? 'ul' : 'ol';
        processedLines.push(`<${tag} class="list-${listType === 'ul' ? 'disc' : 'decimal'} ml-6 my-3 space-y-1">`);
        listItems.forEach(item => processedLines.push(`  <li class="mb-1">${item}</li>`));
        processedLines.push(`</${tag}>`);
        listItems = [];
        inList = false;
        listType = null;
      }
      
      if (trimmed) {
        // Если строка не пустая и не начинается с HTML тега, оборачиваем в параграф
        if (!trimmed.startsWith('<')) {
          processedLines.push(`<p class="mb-3 leading-relaxed">${trimmed}</p>`);
        } else {
          processedLines.push(line);
        }
      } else {
        processedLines.push('');
      }
    }
  }
  
  // Закрываем список, если он остался открытым
  if (inList && listItems.length > 0) {
    const tag = listType === 'ul' ? 'ul' : 'ol';
    processedLines.push(`<${tag} class="list-${listType === 'ul' ? 'disc' : 'decimal'} ml-6 my-3 space-y-1">`);
    listItems.forEach(item => processedLines.push(`  <li class="mb-1">${item}</li>`));
    processedLines.push(`</${tag}>`);
  }
  
  html = processedLines.join('\n');
  
  // Восстанавливаем блоки кода
  codeBlocks.forEach((block, index) => {
    html = html.replace(`CODE_BLOCK_${index}`, block);
  });
  
  return html;
}

const AGENTS = [
  { id: 'code_writer', name: 'Генератор кода', description: 'Генерация и рефакторинг кода' },
  { id: 'react', name: 'ReAct', description: 'Интерактивное решение задач' },
  { id: 'research', name: 'Исследователь', description: 'Исследование кодовой базы и требований' },
  { id: 'data_analysis', name: 'Анализ данных', description: 'Анализ данных и создание моделей' },
  { id: 'workflow', name: 'Workflow', description: 'Управление рабочими процессами' },
  { id: 'integration', name: 'Интеграция', description: 'Интеграция с внешними сервисами' },
  { id: 'monitoring', name: 'Мониторинг', description: 'Мониторинг производительности системы' },
];

const MODE_INFO: Record<ChatMode, { name: string; description: string; icon: LucideIcon }> = {
  chat: { name: 'Чат', description: 'Обычный режим общения', icon: MessageSquare },
  task: { name: 'Задачи', description: 'Выполнение сложных задач', icon: Zap },
  agent: { name: 'Агенты', description: 'Работа с конкретным агентом', icon: Bot },
  batch: { name: 'Пакетная обработка', description: 'Обработка нескольких задач', icon: RefreshCw },
};

export function UnifiedChat() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [modeDropdownOpen, setModeDropdownOpen] = useState(false);
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false);
  const { setExecutionInfo } = useExecutionInfo();
  // State for code execution
  const [runningCodeId, setRunningCodeId] = useState<string | null>(null);
  const [codeExecutionResults, setCodeExecutionResults] = useState<Record<string, { result: string | null; htmlPreviewUrl: string | null }>>({});

  const {
    conversations,
    currentId,
    currentMode,
    createConversation,
    setCurrentConversation,
    setCurrentMode,
    renameConversation,
    deleteConversation,
    clearConversation,
    addMessage,
    updateMessage,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Ensure at least one conversation exists
  useEffect(() => {
    const conversationCount = Object.keys(conversations).length;
    if (conversationCount === 0) {
      // Only create if there are no conversations at all
      createConversation();
    } else if (!currentId || !conversations[currentId]) {
      // If current conversation was deleted, switch to first available
      const firstId = Object.keys(conversations)[0];
      if (firstId) {
        setCurrentConversation(firstId);
      }
    }
  }, [conversations, currentId, createConversation, setCurrentConversation]);

  const currentConversation = useMemo(() => {
    if (currentId && conversations[currentId]) return conversations[currentId];
    return undefined;
  }, [conversations, currentId]);

  const messages = currentConversation?.messages ?? [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.mode-dropdown') && !target.closest('.agent-dropdown')) {
        setModeDropdownOpen(false);
        setAgentDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(codeExecutionResults).forEach(result => {
        if (result.htmlPreviewUrl && result.htmlPreviewUrl.startsWith('blob:')) {
          URL.revokeObjectURL(result.htmlPreviewUrl);
        }
      });
    };
  }, []);

  // Update selected agent when mode changes
  useEffect(() => {
    if (currentMode === 'agent' && !selectedAgent) {
      setSelectedAgent('code_writer');
    } else if (currentMode !== 'agent') {
      setSelectedAgent('');
    }
  }, [currentMode]);

  const handleModeChange = (mode: ChatMode) => {
    setCurrentMode(mode);
    // Don't create new conversations when switching modes
    // Just update the mode of current conversation if it exists
    // If no conversation exists, it will be created when user sends first message
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    // Create conversation if it doesn't exist or is empty
    let convId = currentId;
    if (!convId || !conversations[convId]) {
      convId = createConversation(undefined, currentMode);
    } else {
      // Ensure we're using the current conversation
      convId = currentConversation?.id || convId;
    }
    const userMessageId = `msg-${Date.now()}`;
    
    let userContent = input.trim();
    
    // Format user message based on mode
    if (currentMode === 'batch') {
      userContent = `Пакетная обработка:\n${input.trim()}`;
    } else if (currentMode === 'agent' && selectedAgent) {
      const agentName = AGENTS.find(a => a.id === selectedAgent)?.name || selectedAgent;
      userContent = `[${agentName}] ${input.trim()}`;
    }

    addMessage(convId, {
      id: userMessageId,
      role: 'user',
      content: userContent,
      timestamp: Date.now(),
    });

    const inputToProcess = input.trim();
    setInput('');
    setIsLoading(true);

    const assistantMessageId = `msg-${Date.now() + 1}`;
    addMessage(convId, {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      status: 'streaming',
    });

    try {
      let response;

      if (currentMode === 'batch') {
        const taskList = inputToProcess.split('\n').filter(t => t.trim());
        if (taskList.length === 0) {
          throw new Error('Нет задач для обработки');
        }
        response = await processBatchTasks({
          tasks: taskList,
          agent_type: selectedAgent || undefined,
        });
        
        updateMessage(convId, assistantMessageId, {
          content: `✅ Пакетная обработка завершена!\n\nВсего задач: ${response.total}\nУспешных: ${response.successful}\nОшибок: ${response.failed}\n\n${JSON.stringify(response.results, null, 2).substring(0, 2000)}`,
          status: response.failed === 0 ? 'completed' : 'error',
          result: response,
        });
      } else {
        const agentType = currentMode === 'agent' && selectedAgent ? selectedAgent : undefined;
        
        // Сохраняем информацию об агенте для отображения
        if (agentType) {
          const agentName = AGENTS.find(a => a.id === agentType)?.name || agentType;
          setExecutionInfo({ agent: agentName, models: [] });
        } else {
          setExecutionInfo({ agent: 'Автовыбор', models: [] });
        }

        response = await executeTask({
          task: inputToProcess,
          agent_type: agentType,
          context: {},
        });


        // Пытаемся извлечь информацию о моделях из ответа
        // Модели могут быть в разных местах ответа в зависимости от того, как обрабатывалась задача
        const models: string[] = [];
        
        // Вариант 1: routing из TaskRouter
        if (response.result?.routing?.selected_provider) {
          const provider = response.result.routing.selected_provider;
          // В TaskRouting нет selected_model, но model может быть в response.result.model
          const model = response.result.model || response.result.routing.selected_model;
          if (model && model !== provider) {
            models.push(`${provider}/${model}`);
          } else {
            models.push(provider);
          }
        }
        // Вариант 2: model напрямую в result
        else if (response.result?.model && !models.includes(response.result.model)) {
          models.push(response.result.model);
        }
        // Вариант 3: metadata с информацией о провайдерах
        else if (response.result?.metadata) {
          const metadata = response.result.metadata;
          if (metadata.fast_provider) {
            models.push(metadata.fast_provider);
          }
          if (metadata.powerful_provider && metadata.powerful_provider !== metadata.fast_provider) {
            models.push(metadata.powerful_provider);
          }
        }
        
        // Обновляем информацию о моделях, если они найдены
        if (models.length > 0) {
          const currentInfo = { agent: agentType ? (AGENTS.find(a => a.id === agentType)?.name || agentType) : 'Автовыбор', models: [] };
          setExecutionInfo({ ...currentInfo, models });
        }
        // Если моделей нет, но есть агент, оставляем только агента (уже установлено выше)

        // Извлекаем thinking traces и metadata из ответа
        let thinking: string | undefined;
        let metadata: any = {};
        
        // Ищем thinking в разных местах ответа
        if (response.result?.thinking) {
          thinking = response.result.thinking;
        } else if (response.result?.metadata?.thinking) {
          thinking = response.result.metadata.thinking;
        } else if (response.thinking) {
          thinking = response.thinking;
        }
        
        // Извлекаем metadata о провайдере и модели
        if (response.result?.metadata) {
          metadata = {
            provider: response.result.metadata.provider || response.result.metadata.selected_provider,
            model: response.result.metadata.model || response.result.model,
            thinking_mode: response.result.metadata.thinking_mode || false,
            thinking_native: response.result.metadata.thinking_native || false,
            thinking_emulated: response.result.metadata.thinking_emulated || false,
          };
        } else if (response.result?.routing) {
          metadata = {
            provider: response.result.routing.selected_provider,
            model: response.result.routing.selected_model,
          };
        }
        
        // Если провайдер не указан, но есть информация о модели, пробуем определить провайдер
        if (!metadata.provider && metadata.model) {
          // Ollama модели обычно имеют специфичные имена
          if (metadata.model.includes('llama') || metadata.model.includes('mistral') || 
              metadata.model.includes('codellama') || metadata.model.includes('deepseek') ||
              metadata.model.includes('qwen') || metadata.model.includes('neural-chat')) {
            metadata.provider = 'ollama';
          }
        }
        
        // Извлекаем данные рефлексии (self-correction)
        let reflection: any = null;
        if (response.result?._reflection) {
          reflection = response.result._reflection;
          // Добавляем информацию о рефлексии в metadata
          metadata.reflection_attempts = response.result._reflection_attempts || 1;
          metadata.corrected = response.result._corrected || false;
          metadata.execution_time = response.result._execution_time;
        } else if (response.result?.result?._reflection) {
          // Вложенная структура
          reflection = response.result.result._reflection;
          metadata.reflection_attempts = response.result.result._reflection_attempts || 1;
          metadata.corrected = response.result.result._corrected || false;
          metadata.execution_time = response.result.result._execution_time;
        }
        
        // Форматируем ответ в зависимости от типа результата
        // Проверяем response.success явно (до блока try, чтобы была доступна везде)
        const isSuccess = response && response.success === true;
        let content = '';
        
        try {
          
          if (isSuccess) {
            if (response.result?.code) {
              // Если есть код, показываем его красиво
              content = `✅ Задача выполнена успешно!\n\nСгенерированный код:\n\`\`\`python\n${response.result.code}\n\`\`\``;
            } else if (response.result?.message) {
              // Если есть сообщение
              content = `✅ Задача выполнена успешно!\n\n${response.result.message}`;
            } else if (response.result?.report) {
              // Если есть report (от ResearchAgent)
              const reportText = String(response.result.report || '');
              content = `✅ Задача выполнена успешно!\n\n${reportText}`;
            } else if (typeof response.result === 'string') {
              // Если результат - строка
              content = `✅ Задача выполнена успешно!\n\n${response.result}`;
            } else if (response.result && typeof response.result === 'object') {
              // Если результат - объект, пытаемся извлечь полезную информацию
              const resultStr = JSON.stringify(response.result, null, 2);
              // Ограничиваем длину для отображения
              const maxLength = 2000;
              content = `✅ Задача выполнена успешно!\n\n${resultStr.length > maxLength ? resultStr.substring(0, maxLength) + '\n\n... (результат обрезан)' : resultStr}`;
            } else {
              content = '✅ Задача выполнена успешно!';
            }
          } else {
          
          // Обработка ошибок
          const errorMsg = response.error || 'Неизвестная ошибка';
          content = `❌ Ошибка выполнения задачи:\n\n${errorMsg}`;
          
          // Если есть дополнительная информация об ошибке
          if (response.result?.error) {
            content += `\n\nДетали: ${response.result.error}`;
          }
        }
        } catch (formatError: any) {
          content = `❌ Ошибка форматирования ответа: ${formatError?.message || 'Неизвестная ошибка'}`;
        }
        
        const messageStatus = isSuccess ? 'completed' : 'error';
        
        updateMessage(convId, assistantMessageId, {
          content: content,
          status: messageStatus,
          result: response.result,
          thinking: thinking,
          reflection: reflection || undefined,
          metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
          subtasks:
            response.subtasks?.map((st: string) => ({
              subtask: st,
              status: 'completed',
            })) || [],
        });
      }
    } catch (error: any) {
      updateMessage(convId, assistantMessageId, {
        content: `❌ Ошибка выполнения: ${error.message || 'Неизвестная ошибка'}`,
        status: 'error',
      });
      // Очищаем информацию об исполнении при ошибке
      setExecutionInfo(null);
    } finally {
      setIsLoading(false);
      // Очищаем информацию через 5 секунд после завершения (успешного или с ошибкой)
      setTimeout(() => {
        setExecutionInfo(null);
      }, 5000);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && currentMode !== 'batch') {
      e.preventDefault();
      handleSubmit();
    }
  };

  const downloadCode = (code: string, filename: string = 'generated_code.py') => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleRunCode = async (code: string, messageId: string, files?: any[]) => {
    setRunningCodeId(messageId);
    setCodeExecutionResults(prev => ({ ...prev, [messageId]: { result: null, htmlPreviewUrl: null } }));

    try {
      // Check if code seems incomplete (too short for HTML)
      const trimmedCode = code.trim();
      if (trimmedCode.length < 100 && detectCodeType(code) === 'html') {
        // Code might be incomplete, try to find full code in message content
        const allMessages = currentConversation?.messages || [];
        const message = allMessages.find(m => m.id === messageId);
        if (message) {
          const extractedCode = extractCodeFromMarkdown(message.content || '');
          if (extractedCode && extractedCode.length > trimmedCode.length) {
            code = extractedCode;
          }
        }
      }
      
      // If we have multiple files, try to find the main file to run
      let codeToRun = code;
      let codeType = detectCodeType(code);
      
      // If there are multiple files, try to find the main executable file
      // But prioritize the main code if it exists and is executable
      if (files && files.length > 0 && (!code || code.trim().length < 50)) {
        // Only look for main file if main code is very short or empty
        // Look for main file (usually main.py, app.py, index.html, etc.)
        const mainFile = files.find(f => {
          const path = (f.path || f.name || '').toLowerCase();
          return path.includes('main') || path.includes('app') || path.includes('index') || 
                 path.endsWith('.html') || path.endsWith('.py');
        });
        
        if (mainFile && mainFile.code) {
          codeToRun = mainFile.code;
          codeType = detectCodeType(mainFile.code);
          
          // If it's a Python project with multiple files, we might need to save files first
          // For now, we'll try to run the main file directly
          if (codeType === 'python' && files.length > 1) {
            // Try to extract just the main file code
            // This is a simple approach - for complex projects, files should be saved first
            setCodeExecutionResults(prev => ({ 
              ...prev, 
              [messageId]: { 
                result: '⚠️ Обнаружено несколько файлов. Запускается основной файл. Для сложных проектов с зависимостями между файлами рекомендуется сохранить все файлы и запустить проект локально.', 
                htmlPreviewUrl: null 
              } 
            }));
          }
        }
      }
      
      const finalCodeType = codeType;
      
      // Special handling for HTML/CSS: create preview and open in browser
      if (finalCodeType === 'html') {
        let processedCode = processHtmlCode(codeToRun);
        
        // Ensure HTML is properly closed
        if (!processedCode.includes('</html>')) {
          processedCode += '\n</html>';
        }
        if (!processedCode.includes('</body>') && processedCode.includes('<body')) {
          processedCode = processedCode.replace(/<\/html>/i, '</body>\n</html>');
        }
        
        // Create URL for rendering
        let previewUrl: string;
        try {
          const blob = new Blob([processedCode], { type: 'text/html;charset=utf-8' });
          previewUrl = URL.createObjectURL(blob);
        } catch (error) {
          previewUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(processedCode);
        }
        
        setCodeExecutionResults(prev => ({ 
          ...prev, 
          [messageId]: { 
            result: '✅ HTML готов к просмотру! Откройте предпросмотр ниже или в новом окне.', 
            htmlPreviewUrl: previewUrl 
          } 
        }));
        
        // Try to open in new window
        try {
          const newWindow = window.open(previewUrl, '_blank');
          if (!newWindow) {
            // Window was blocked, update message
            setCodeExecutionResults(prev => ({ 
              ...prev, 
              [messageId]: { 
                result: '✅ HTML отображается в предпросмотре ниже. Если окно заблокировано, используйте предпросмотр.', 
                htmlPreviewUrl: previewUrl 
              } 
            }));
          }
        } catch (error) {
          // Ignore window open errors
        }
        
        setRunningCodeId(null);
        return;
      }

      // Validate that code is executable
      const isValidExecutableCode = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
        const trimmed = code.trim();
        
        // Check if it's a project structure (tree view)
        if (trimmed.includes('├──') || trimmed.includes('└──') || trimmed.includes('│') || 
            (trimmed.includes('/') && trimmed.match(/^\s*[\w\-_]+(\/|\\|├|└)/))) {
          return false;
        }
        
        // Check if it starts with a directory name followed by slash
        const firstLine = trimmed.split('\n')[0].trim();
        if (firstLine.match(/^[\w\-_а-яА-Я]+[\/\\]/) && !firstLine.includes('def ') && 
            !firstLine.includes('import ') && !firstLine.includes('class ')) {
          const nextLines = trimmed.split('\n').slice(1, 5).join('\n');
          if (nextLines.match(/[├└│]/) || nextLines.match(/\.(py|js|ts|html|css|json|md)\s*#/)) {
            return false;
          }
        }
        
        // Check if it's markdown documentation
        if (trimmed.startsWith('#') && !trimmed.includes('def ') && !trimmed.includes('class ') && 
            !trimmed.includes('import ') && !trimmed.includes('function ')) {
          return false;
        }
        
        // For Python: should contain executable statements
        if (lang === 'python') {
          const hasPythonCode = trimmed.includes('def ') || trimmed.includes('class ') || 
                               trimmed.includes('import ') || trimmed.includes('from ') ||
                               trimmed.includes('if ') || trimmed.includes('for ') || 
                               trimmed.includes('while ') || trimmed.includes('print(') ||
                               (trimmed.includes('=') && (trimmed.includes('(') || trimmed.includes('[')));
          
          if (trimmed.split('\n').length > 0) {
            const firstLines = trimmed.split('\n').slice(0, 5).join('\n');
            if ((firstLines.match(/^[\w\-_а-яА-Я]+[\/\\]/) || 
                 firstLines.match(/[├└│]/) ||
                 firstLines.match(/\.(py|js|ts|html|css|json|md)\s*#/)) && !hasPythonCode) {
              return false;
            }
          }
          
          return hasPythonCode || trimmed.length < 100;
        }
        
        // For Node/JS: should contain JS code
        if (lang === 'node') {
          return trimmed.includes('function ') || trimmed.includes('const ') || 
                 trimmed.includes('let ') || trimmed.includes('var ') ||
                 trimmed.includes('console.') || trimmed.includes('require(') ||
                 trimmed.includes('import ') || trimmed.includes('export ');
        }
        
        // For Bash: should contain shell commands
        if (lang === 'bash') {
          return trimmed.includes('echo ') || trimmed.includes('ls ') || 
                 trimmed.includes('cd ') || trimmed.includes('mkdir ') ||
                 trimmed.includes('#!/bin/bash') || trimmed.includes('#!/bin/sh') ||
                 trimmed.includes('$') || trimmed.includes('export ');
        }
        
        return true;
      };
      
      // Check if code requires interactive input
      const requiresInteractiveInput = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
        if (lang === 'python') {
          return /input\s*\(/.test(code) || /raw_input\s*\(/.test(code);
        }
        if (lang === 'node') {
          return /readline|prompt\(|process\.stdin/.test(code);
        }
        if (lang === 'bash') {
          return /read\s+/.test(code);
        }
        return false;
      };
      
      // Check if code is executable
      if (!isValidExecutableCode(codeToRun, finalCodeType)) {
        setCodeExecutionResults(prev => ({ 
          ...prev, 
          [messageId]: { 
            result: '⚠️ Этот код не может быть выполнен напрямую. Похоже, это структура проекта или описание, а не исполняемый код. Попробуйте сгенерировать код заново с более конкретным запросом.', 
            htmlPreviewUrl: null 
          } 
        }));
        setRunningCodeId(null);
        return;
      }
      
      // Check if code requires interactive input
      if (requiresInteractiveInput(codeToRun, finalCodeType)) {
        setCodeExecutionResults(prev => ({ 
          ...prev, 
          [messageId]: { 
            result: '⚠️ Этот код требует интерактивного ввода (использует input() или аналогичные функции). Для интерактивных программ рекомендуется:\n\n1. Для игр: запросите веб-версию (HTML/CSS/JS) - она будет работать в браузере\n2. Для консольных программ: запустите код локально в терминале\n3. Попробуйте сгенерировать код заново с запросом веб-версии', 
            htmlPreviewUrl: null 
          } 
        }));
        setRunningCodeId(null);
        return;
      }
      
      // Execute code based on type
      const command = (() => {
        switch (finalCodeType) {
          case 'python':
            return `python3 - <<'PY'\n${codeToRun}\nPY`;
          case 'node':
            return `node - <<'JS'\n${codeToRun}\nJS`;
          case 'bash':
            return `bash - <<'SH'\n${codeToRun}\nSH`;
          default:
            return `python3 - <<'PY'\n${codeToRun}\nPY`;
        }
      })();

      const response = await executeTool({
        tool_name: 'execute_command',
        input: { command },
      });

      const stdout = response?.result?.stdout || '';
      let stderr = response?.result?.stderr || '';
      
      // Check for EOFError and provide helpful message
      if (stderr.includes('EOFError: EOF when reading a line') || 
          stderr.includes('EOFError') && stderr.includes('input')) {
        stderr = '⚠️ Ошибка: Код требует интерактивного ввода (использует input()), но выполнение происходит неинтерактивно.\n\n' +
                 'Рекомендации:\n' +
                 '1. Для игр: запросите веб-версию (HTML/CSS/JS) - она будет работать в браузере\n' +
                 '2. Для консольных программ: запустите код локально в терминале\n' +
                 '3. Попробуйте сгенерировать код заново с запросом веб-версии\n\n' +
                 'Оригинальная ошибка:\n' + stderr;
      }
      
      const result = [stdout && `stdout:\n${stdout}`, stderr && `stderr:\n${stderr}`]
        .filter(Boolean)
        .join('\n\n') || 'Нет вывода';
      
      setCodeExecutionResults(prev => ({ 
        ...prev, 
        [messageId]: { 
          result, 
          htmlPreviewUrl: null 
        } 
      }));
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setCodeExecutionResults(prev => ({ 
        ...prev, 
        [messageId]: { 
          result: `❌ Ошибка выполнения: ${errorMessage}`, 
          htmlPreviewUrl: null 
        } 
      }));
    } finally {
      setRunningCodeId(null);
    }
  };

  const clearHistory = () => {
    if (currentConversation && confirm('Очистить историю разговора?')) {
      clearConversation(currentConversation.id);
    }
  };

  const handleNewChat = () => {
    const newId = createConversation(undefined, currentMode);
    setCurrentConversation(newId);
    setInput('');
  };

  const handleRename = (id: string) => {
    const title = prompt('Название чата', conversations[id]?.title || '');
    if (title !== null) {
      renameConversation(id, title);
    }
  };

  const handleDelete = (id: string) => {
    if (confirm('Удалить этот чат?')) {
      deleteConversation(id);
    }
  };

  return (
    <div className="flex h-full bg-[#0f111b] text-white overflow-hidden">
      {/* Sidebar */}
      <div
        className={`${
          sidebarOpen ? 'w-64' : 'w-0'
        } bg-[#131524] border-r border-[#1f2236] transition-all duration-300 overflow-hidden flex flex-col shadow-xl`}
      >
        <div className="p-3 border-b border-[#1f2236] bg-gradient-to-r from-[#131524] to-[#1a1d2e]">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-base font-bold text-gray-100 flex items-center gap-1.5">
              <MessageSquare size={16} strokeWidth={1.5} className="text-blue-400" />
              <span>Чаты</span>
            </h2>
            <button
              onClick={handleNewChat}
              className="text-xs px-2 py-1 rounded-lg bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white font-medium shadow-md transition-all duration-200 flex items-center gap-1"
            >
              <span>+</span>
              <span className="hidden sm:inline">Новый</span>
            </button>
          </div>
          <div className="flex items-center justify-between text-xs">
            <button 
              onClick={() => setSidebarOpen(false)} 
              className="text-gray-400 hover:text-white transition-colors flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-[#1f2236] text-[10px]"
            >
              <ChevronLeft size={10} strokeWidth={2} />
              <span>Скрыть</span>
            </button>
            <button 
              onClick={clearHistory} 
              className="text-gray-400 hover:text-red-400 transition-colors flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-[#1f2236] text-[10px]"
            >
              <Trash2 size={10} strokeWidth={1.5} />
              <span>Очистить</span>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {Object.values(conversations)
            .sort((a, b) => b.updatedAt - a.updatedAt)
            .map((conv) => (
              <div
                key={conv.id}
                className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-all duration-200 group ${
                  conv.id === currentConversation?.id
                    ? 'border-blue-500/60 bg-gradient-to-br from-[#1a1e30] to-[#1f2236] shadow-md shadow-blue-500/10 ring-1 ring-blue-500/20'
                    : 'border-[#1f2236] bg-[#0f111b] hover:border-[#2a2f46] hover:bg-[#131524]'
                }`}
                onClick={() => setCurrentConversation(conv.id)}
              >
                <div className="flex items-center justify-between gap-1.5 mb-1">
                  <div className="font-semibold truncate flex-1 text-gray-100 text-xs">{conv.title}</div>
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRename(conv.id);
                      }}
                      className="text-[10px] text-gray-400 hover:text-blue-400 p-1 rounded hover:bg-[#1f2236] transition-colors"
                      title="Переименовать"
                    >
                      <Pencil size={10} strokeWidth={1.5} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(conv.id);
                      }}
                      className="text-[10px] text-gray-400 hover:text-red-400 p-1 rounded hover:bg-[#1f2236] transition-colors"
                      title="Удалить"
                    >
                      <Trash2 size={10} strokeWidth={1.5} />
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 mb-1">
                  {conv.mode && (() => {
                    const ModeIcon = MODE_INFO[conv.mode].icon;
                    return (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#1f2236]/80 border border-[#2a2f46] text-gray-300 font-medium flex items-center gap-1">
                        <ModeIcon size={10} strokeWidth={1.5} /> {MODE_INFO[conv.mode].name}
                      </span>
                    );
                  })()}
                </div>
                <div className="text-[10px] text-gray-500 mb-1">{new Date(conv.updatedAt).toLocaleString('ru-RU', { 
                  day: '2-digit', 
                  month: '2-digit', 
                  hour: '2-digit', 
                  minute: '2-digit' 
                })}</div>
                <div className="text-[11px] text-gray-400 overflow-hidden text-ellipsis line-clamp-2 leading-snug">
                  {conv.messages[conv.messages.length - 1]?.content || 'Пустой чат'}
                </div>
              </div>
            ))}
        </div>
        
        {/* Learning Progress */}
        <div className="p-2 border-t border-[#1f2236]">
          <LearningProgress />
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 py-4">
              <div className="max-w-4xl mx-auto space-y-4">
                {messages.length === 0 ? (() => {
                  const WelcomeIcon = MODE_INFO[currentMode].icon;
                  return (
                  <div className="text-center mt-12 animate-fade-in">
                    <div className="mb-4 animate-bounce-slow flex justify-center">
                      <WelcomeIcon size={48} strokeWidth={1} className="text-blue-400" />
                    </div>
                    <h2 className="text-2xl font-bold mb-2 text-gray-100">Добро пожаловать в {MODE_INFO[currentMode].name}</h2>
                    <p className="text-gray-400 mb-6 text-sm">{MODE_INFO[currentMode].description}</p>
                    {currentMode === 'chat' && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 max-w-3xl mx-auto text-left">
                        <div className="p-3 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-all duration-200 cursor-pointer group">
                          <div className="font-semibold mb-1 text-gray-100 flex items-center gap-1.5 text-sm">
                            <span>🎮</span>
                            <span>Простые</span>
                        </div>
                          <div className="text-xs text-gray-400 group-hover:text-gray-300 transition-colors">Игра змейка</div>
                        </div>
                        <div className="p-3 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-all duration-200 cursor-pointer group">
                          <div className="font-semibold mb-1 text-gray-100 flex items-center gap-1.5 text-sm">
                            <span>☁️</span>
                            <span>Сложные</span>
                        </div>
                          <div className="text-xs text-gray-400 group-hover:text-gray-300 transition-colors">Облако</div>
                        </div>
                        <div className="p-3 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-all duration-200 cursor-pointer group">
                          <div className="font-semibold mb-1 text-gray-100 flex items-center gap-1.5 text-sm">
                            <Code size={14} strokeWidth={1.5} className="text-purple-400" />
                            <span>Разработка</span>
                          </div>
                          <div className="text-xs text-gray-400 group-hover:text-gray-300 transition-colors">IDE</div>
                        </div>
                        <div className="p-3 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-all duration-200 cursor-pointer group">
                          <div className="font-semibold mb-1 text-gray-100 flex items-center gap-1.5 text-sm">
                            <Zap size={14} strokeWidth={1.5} className="text-yellow-400" />
                            <span>Оптимизация</span>
                          </div>
                          <div className="text-xs text-gray-400 group-hover:text-gray-300 transition-colors">LLM модуль</div>
                        </div>
                      </div>
                    )}
                    {currentMode === 'batch' && (
                      <div className="max-w-2xl mx-auto text-left">
                        <div className="p-4 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46]">
                          <div className="font-semibold mb-2 text-gray-100 flex items-center gap-2 text-sm">
                            <FileText size={14} strokeWidth={1.5} className="text-gray-400" />
                            <span>Пример:</span>
                          </div>
                          <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono bg-[#0f111b] p-3 rounded border border-[#1f2236]">
{`Сгенерировать игру змейка
Создать REST API для блога
Написать тесты для модуля`}</pre>
                        </div>
                      </div>
                    )}
                  </div>
                  );
                })() : (
                  messages.map((message, index) => (
                    <div
                      key={message.id}
                      id={`message-${message.id}`}
                      className={`flex gap-3 mb-4 group animate-fade-in ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                      style={{ animationDelay: `${index * 0.1}s` }}
                    >
                      {message.role === 'assistant' && (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center flex-shrink-0 shadow-md shadow-blue-500/30 ring-1 ring-blue-500/20">
                          <span className="text-xs font-bold text-white">AI</span>
                        </div>
                      )}
                      <div
                        className={`max-w-3xl rounded-2xl px-6 py-4 transition-all duration-200 ${
                          message.role === 'user'
                            ? 'bg-gradient-to-br from-blue-600/90 to-blue-700/90 text-white shadow-lg shadow-blue-500/20'
                            : message.status === 'error'
                            ? 'bg-red-900/30 border-2 border-red-500/60 shadow-lg shadow-red-500/20'
                            : 'bg-[#1a1d2e] border border-[#2a2f46] shadow-lg hover:border-[#3a3f56]'
                        }`}
                      >
                        {message.role === 'user' ? (
                          <div className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</div>
                        ) : (
                          <div>
                            {message.status === 'streaming' && (
                              <div className="flex items-center gap-3 text-gray-300">
                                <div className="flex gap-1">
                                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                                </div>
                                <span className="text-sm font-medium">Выполняется...</span>
                              </div>
                            )}
                            {message.status === 'completed' && (
                              <div className="space-y-3">
                                {message.subtasks && message.subtasks.length > 0 && (
                                  <div className="text-sm mb-3">
                                    <div className="text-gray-300 mb-3 font-medium flex items-center gap-2">
                                      <CircleCheck size={14} strokeWidth={1.5} className="text-green-400" />
                                      <span>Выполненные шаги</span>
                                    </div>
                                    <div className="space-y-2">
                                      {message.subtasks.map((st, idx) => (
                                        <div key={idx} className="flex items-start gap-3 text-gray-300 bg-[#0f111b]/40 p-2.5 rounded-lg border border-[#2a2f46]/50">
                                          <span className="text-green-400 text-lg mt-0.5 flex-shrink-0">✓</span>
                                          <span className="leading-relaxed">{st.subtask}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {(() => {
                                  // Try to get code from result.code first, then from content markdown
                                  const code = message.result?.code || extractCodeFromMarkdown(message.content || '');
                                  if (!code) return null;
                                  
                                  return (
                                    <div className="mt-3">
                                      <div className="flex items-center justify-between mb-3">
                                        <span className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                                          <Code size={14} strokeWidth={1.5} className="text-blue-400" />
                                          <span>Сгенерированный код</span>
                                        </span>
                                        <div className="flex items-center gap-2">
                                          <button
                                            onClick={() => handleRunCode(code, message.id, message.result?.files)}
                                            disabled={runningCodeId === message.id}
                                            className="text-xs px-3 py-1.5 bg-green-600/80 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors font-medium flex items-center gap-1.5 shadow-md"
                                          >
                                            {runningCodeId === message.id ? (
                                              <>
                                                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                                <span>Запуск...</span>
                                              </>
                                            ) : (
                                              <>
                                                <Play size={12} strokeWidth={1.5} />
                                                <span>Запустить</span>
                                              </>
                                            )}
                                          </button>
                                          <button
                                            onClick={() => downloadCode(code, `generated_code.${detectCodeType(code) === 'html' ? 'html' : detectCodeType(code) === 'node' ? 'js' : 'py'}`)}
                                            className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium flex items-center gap-1.5 shadow-md"
                                          >
                                            <span>⬇️</span>
                                            <span>Скачать</span>
                                          </button>
                                        </div>
                                      </div>
                                      <div className="relative">
                                        <pre className="bg-[#0a0a0f] p-5 rounded-xl overflow-x-auto text-sm border-2 border-[#1a1d2e] shadow-inner">
                                          <code className="text-gray-200 font-mono leading-relaxed">{code}</code>
                                      </pre>
                                        <span className="absolute top-3 right-4 text-xs text-gray-400 font-medium">{detectCodeType(code)}</span>
                                      </div>
                                    
                                      {/* Execution Results */}
                                      {codeExecutionResults[message.id] && (
                                        <div className="mt-4 space-y-3">
                                          {codeExecutionResults[message.id].htmlPreviewUrl && (
                                            <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg overflow-hidden">
                                              <div className="p-3 bg-[#1a1d2e] border-b border-[#2a2f46] flex items-center justify-between">
                                                <span className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                                                  <Globe size={14} strokeWidth={1.5} className="text-cyan-400" />
                                                  <span>Предпросмотр HTML</span>
                                                </span>
                                                <button
                                                  onClick={() => {
                                                    if (codeExecutionResults[message.id].htmlPreviewUrl) {
                                                      window.open(codeExecutionResults[message.id].htmlPreviewUrl!, '_blank');
                                                    }
                                                  }}
                                                  className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium"
                                                >
                                                  Открыть в новом окне
                                                </button>
                                              </div>
                                              <iframe
                                                src={codeExecutionResults[message.id].htmlPreviewUrl!}
                                                className="w-full h-96 border-0"
                                                title="HTML Preview"
                                              />
                                            </div>
                                          )}
                                          
                                          {codeExecutionResults[message.id].result && (
                                            <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg p-4">
                                              <div className="text-sm font-semibold text-gray-200 mb-2 flex items-center gap-2">
                                                <BarChart3 size={14} strokeWidth={1.5} className="text-blue-400" />
                                                <span>Результат выполнения</span>
                                              </div>
                                              <pre className="bg-[#0a0a0f] p-4 rounded-lg overflow-x-auto text-xs font-mono text-gray-300 whitespace-pre-wrap border border-[#1a1d2e]">
                                                {codeExecutionResults[message.id].result}
                                              </pre>
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* Thinking trace - показываем если есть */}
                                {message.thinking && (
                                  <div className="mb-4 p-4 bg-gradient-to-br from-purple-900/30 to-purple-800/20 border border-purple-500/40 rounded-xl shadow-lg">
                                    <div className="flex items-center justify-between mb-3">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm font-semibold text-purple-300 flex items-center gap-2">
                                          <Brain size={18} strokeWidth={1.5} />
                                          <span>Reasoning Process</span>
                                        </span>
                                      </div>
                                    </div>
                                    <div className="text-xs text-purple-200/90 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto leading-relaxed bg-[#0f111b]/40 p-3 rounded-lg border border-purple-500/20">
                                      {message.thinking}
                                    </div>
                                  </div>
                                )}

                                {/* Reflection - Self-correction data */}
                                {message.reflection && (
                                  <div className="mb-4 p-4 bg-gradient-to-br from-emerald-900/30 to-teal-800/20 border border-emerald-500/40 rounded-xl shadow-lg">
                                    <div className="flex items-center justify-between mb-3">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm font-semibold text-emerald-300 flex items-center gap-2">
                                          <Search size={18} strokeWidth={1.5} />
                                          <span>Quality Analysis</span>
                                        </span>
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                          message.reflection.quality_level === 'excellent' ? 'bg-green-500/30 text-green-300 border border-green-500/40' :
                                          message.reflection.quality_level === 'good' ? 'bg-blue-500/30 text-blue-300 border border-blue-500/40' :
                                          message.reflection.quality_level === 'acceptable' ? 'bg-yellow-500/30 text-yellow-300 border border-yellow-500/40' :
                                          'bg-red-500/30 text-red-300 border border-red-500/40'
                                        }`}>
                                          {message.reflection.quality_level === 'excellent' ? 'Отлично' :
                                           message.reflection.quality_level === 'good' ? 'Хорошо' :
                                           message.reflection.quality_level === 'acceptable' ? 'Приемлемо' :
                                           message.reflection.quality_level === 'poor' ? 'Слабо' : 'Неудача'}
                                        </span>
                                      </div>
                                      {message.metadata?.corrected && (
                                        <span className="px-2 py-0.5 bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-full text-xs font-medium flex items-center gap-1">
                                          <RefreshCw size={10} strokeWidth={1.5} />
                                          <span>Исправлено</span>
                                        </span>
                                      )}
                                    </div>
                                    
                                    {/* Score bars */}
                                    <div className="grid grid-cols-3 gap-3 mb-3">
                                      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
                                        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Полнота</div>
                                        <div className="flex items-center gap-2">
                                          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                            <div 
                                              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
                                              style={{ width: `${message.reflection.completeness}%` }}
                                            />
                                          </div>
                                          <span className="text-xs font-mono text-emerald-300">{Math.round(message.reflection.completeness)}%</span>
                                        </div>
                                      </div>
                                      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
                                        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Корректность</div>
                                        <div className="flex items-center gap-2">
                                          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                            <div 
                                              className="h-full bg-gradient-to-r from-blue-500 to-blue-400 rounded-full transition-all duration-500"
                                              style={{ width: `${message.reflection.correctness}%` }}
                                            />
                                          </div>
                                          <span className="text-xs font-mono text-blue-300">{Math.round(message.reflection.correctness)}%</span>
                                        </div>
                                      </div>
                                      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
                                        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Качество</div>
                                        <div className="flex items-center gap-2">
                                          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                            <div 
                                              className="h-full bg-gradient-to-r from-purple-500 to-purple-400 rounded-full transition-all duration-500"
                                              style={{ width: `${message.reflection.quality}%` }}
                                            />
                                          </div>
                                          <span className="text-xs font-mono text-purple-300">{Math.round(message.reflection.quality)}%</span>
                                        </div>
                                      </div>
                                    </div>
                                    
                                    {/* Overall score */}
                                    <div className="flex items-center justify-between mb-3 p-2 bg-[#0f111b]/60 rounded-lg border border-emerald-500/20">
                                      <span className="text-xs text-emerald-400/80">Общая оценка</span>
                                      <div className="flex items-center gap-2">
                                        <div className="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
                                          <div 
                                            className={`h-full rounded-full transition-all duration-500 ${
                                              message.reflection.overall_score >= 90 ? 'bg-gradient-to-r from-green-500 to-emerald-400' :
                                              message.reflection.overall_score >= 70 ? 'bg-gradient-to-r from-blue-500 to-cyan-400' :
                                              message.reflection.overall_score >= 50 ? 'bg-gradient-to-r from-yellow-500 to-amber-400' :
                                              'bg-gradient-to-r from-red-500 to-orange-400'
                                            }`}
                                            style={{ width: `${message.reflection.overall_score}%` }}
                                          />
                                        </div>
                                        <span className={`text-sm font-bold ${
                                          message.reflection.overall_score >= 90 ? 'text-green-400' :
                                          message.reflection.overall_score >= 70 ? 'text-blue-400' :
                                          message.reflection.overall_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                                        }`}>
                                          {Math.round(message.reflection.overall_score)}
                                        </span>
                                      </div>
                                    </div>
                                    
                                    {/* Issues and improvements */}
                                    {(message.reflection.issues?.length > 0 || message.reflection.improvements?.length > 0) && (
                                      <div className="grid grid-cols-2 gap-3 text-xs">
                                        {message.reflection.issues?.length > 0 && (
                                          <div className="bg-red-900/20 p-2 rounded-lg border border-red-500/20">
                                            <div className="text-red-400 font-medium mb-1 flex items-center gap-1">
                                              <AlertTriangle size={12} strokeWidth={1.5} /> Замечания
                                            </div>
                                            <ul className="text-red-300/80 space-y-0.5">
                                              {message.reflection.issues.slice(0, 3).map((issue, i) => (
                                                <li key={i} className="truncate">• {issue}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}
                                        {message.reflection.improvements?.length > 0 && (
                                          <div className="bg-emerald-900/20 p-2 rounded-lg border border-emerald-500/20">
                                            <div className="text-emerald-400 font-medium mb-1 flex items-center gap-1">
                                              <Lightbulb size={12} strokeWidth={1.5} /> Улучшения
                                            </div>
                                            <ul className="text-emerald-300/80 space-y-0.5">
                                              {message.reflection.improvements.slice(0, 3).map((imp, i) => (
                                                <li key={i} className="truncate">• {imp}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}
                                      </div>
                                    )}
                                    
                                    {/* Reflection attempts info */}
                                    {message.metadata?.reflection_attempts && message.metadata.reflection_attempts > 1 && (
                                      <div className="mt-2 text-[10px] text-emerald-400/60 flex items-center gap-1">
                                        <RefreshCw size={10} strokeWidth={1.5} />
                                        <span>Попыток: {message.metadata.reflection_attempts}</span>
                                        {message.metadata.execution_time && (
                                          <span className="ml-2 flex items-center gap-1"><Clock size={10} strokeWidth={1.5} /> {message.metadata.execution_time.toFixed(1)}с</span>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )}

                                {/* Provider and model info */}
                                {message.metadata && (message.metadata.provider || message.metadata.model) && (
                                  <div className="mb-3 -mt-1 flex items-center gap-2 flex-wrap">
                                    {message.metadata.provider && (
                                      <span className="px-2.5 py-1 bg-[#0f111b]/60 backdrop-blur-sm border border-[#2a2f46] rounded-lg text-xs font-medium text-gray-300 flex items-center gap-1.5">
                                        {message.metadata.provider === 'ollama' ? (
                                          <>
                                            <Bot size={12} strokeWidth={1.5} />
                                            <span>Ollama</span>
                                          </>
                                        ) : (
                                          <span>{message.metadata.provider}</span>
                                        )}
                                      </span>
                                    )}
                                    {message.metadata.model && (
                                      <span className="px-2.5 py-1 bg-[#0f111b]/60 backdrop-blur-sm border border-[#2a2f46] rounded-lg text-xs font-medium text-gray-300">
                                        {message.metadata.model}
                                      </span>
                                    )}
                                    {message.metadata.thinking_mode && (
                                      <span className="px-2.5 py-1 bg-purple-900/40 border border-purple-500/30 rounded-lg text-xs font-medium text-purple-300 flex items-center gap-1.5">
                                        <Brain size={12} strokeWidth={1.5} />
                                        <span>Thinking Mode</span>
                                      </span>
                                    )}
                                    {message.metadata.thinking_native && (
                                      <span className="px-2.5 py-1 bg-green-900/40 border border-green-500/30 rounded-lg text-xs font-medium text-green-300 flex items-center gap-1.5">
                                        <span>✓</span>
                                        <span>Native</span>
                                      </span>
                                    )}
                                    {message.metadata.thinking_emulated && (
                                      <span className="px-2.5 py-1 bg-yellow-900/40 border border-yellow-500/30 rounded-lg text-xs font-medium text-yellow-300 flex items-center gap-1.5">
                                        <Zap size={12} strokeWidth={1.5} />
                                        <span>Emulated</span>
                                      </span>
                                    )}
                                  </div>
                                )}

                                {message.content && !message.result?.code && !extractCodeFromMarkdown(message.content) && (
                                  <div className="prose prose-invert max-w-none">
                                    <div 
                                      className="text-[15px] leading-relaxed markdown-content"
                                      dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
                                    />
                                  </div>
                                )}

                                {message.result?.files && Array.isArray(message.result.files) && message.result.files.length > 0 && (
                                  <div className="mt-3">
                                    <div className="text-sm font-semibold mb-3 text-gray-200 flex items-center gap-2">
                                      <FileText size={14} strokeWidth={1.5} className="text-gray-400" />
                                      <span>Созданные файлы</span>
                                    </div>
                                    <div className="space-y-2">
                                      {message.result.files.map((file: any, idx: number) => (
                                        <div
                                          key={idx}
                                          className="flex items-center justify-between p-3 bg-[#0f111b]/60 backdrop-blur-sm rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors"
                                        >
                                          <span className="text-sm text-gray-300 font-mono">{file.path || file.name || `Файл ${idx + 1}`}</span>
                                          {file.code && (
                                            <button
                                              onClick={() => downloadCode(file.code, file.path || file.name || `file_${idx}.py`)}
                                              className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium flex items-center gap-1.5 shadow-md"
                                            >
                                              <span>⬇️</span>
                                              <span>Скачать</span>
                                            </button>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                            {message.status === 'error' && (
                              <div className="text-red-300 leading-relaxed flex items-start gap-2">
                                <CircleX size={18} strokeWidth={1.5} className="flex-shrink-0 mt-0.5" />
                                <div className="flex-1">{message.content}</div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                      {message.role === 'user' && (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gray-600 to-gray-700 flex items-center justify-center flex-shrink-0 shadow-md ring-1 ring-gray-500/20">
                          <span className="text-sm">👤</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>
        </div>

        {/* Input Area */}
        <div className="border-t border-[#1f2236] bg-gradient-to-r from-[#131524] to-[#1a1d2e] px-4 py-3 shadow-2xl">
            <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
              {currentMode === 'batch' ? (() => {
                const BatchModeIcon = MODE_INFO[currentMode].icon;
                return (
                <div className="relative">
                  {/* Объединенная область ввода */}
                  <div className="relative flex items-center bg-[#0f111b] border-2 border-[#1f2236] rounded-lg focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-all duration-200">
                    {/* Mode Dropdown - слева внутри поля */}
                    <div className="relative flex-shrink-0 mode-dropdown">
                      <button
                        type="button"
                        onClick={() => setModeDropdownOpen(!modeDropdownOpen)}
                        className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] transition-colors flex items-center gap-1.5 text-xs font-medium text-gray-300 border-r border-[#1f2236]"
                        title={MODE_INFO[currentMode].description}
                      >
                        <BatchModeIcon size={14} strokeWidth={1.5} />
                        <span className="hidden sm:inline">{MODE_INFO[currentMode].name}</span>
                        <ChevronDown size={10} strokeWidth={1.5} />
                      </button>
                      {modeDropdownOpen && (
                        <div className="absolute bottom-full left-0 mb-2 w-48 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg shadow-xl z-20 overflow-hidden">
                          {Object.entries(MODE_INFO).map(([mode, info]) => {
                            const DropdownIcon = info.icon;
                            return (
                            <button
                              key={mode}
                              type="button"
                              onClick={() => {
                                handleModeChange(mode as ChatMode);
                                setModeDropdownOpen(false);
                              }}
                              className={`w-full px-3 py-2 text-left text-xs font-medium transition-colors flex items-center gap-2 ${
                                currentMode === mode
                                  ? 'bg-blue-600/30 text-blue-300'
                                  : 'text-gray-300 hover:bg-[#1f2236]'
                              }`}
                            >
                              <DropdownIcon size={14} strokeWidth={1.5} />
                              <span className="flex-1">{info.name}</span>
                              {currentMode === mode && <CircleCheck size={12} strokeWidth={1.5} className="text-blue-400" />}
                            </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Textarea */}
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={(e) => {
                        setInput(e.target.value);
                        e.target.style.height = 'auto';
                        e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
                      }}
                      placeholder="Введите задачи (по одной на строку)..."
                      className="flex-1 px-4 py-2.5 min-h-[42px] bg-transparent text-white placeholder-gray-500 resize-none focus:outline-none max-h-[150px] transition-all duration-200 text-sm leading-relaxed"
                      rows={1}
                      disabled={isLoading}
                    />

                    {/* Кнопка отправки - стрелка справа внутри поля */}
                    <button
                      type="submit"
                      disabled={!input.trim() || isLoading}
                      className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236]"
                      title="Обработать пакет"
                    >
                      {isLoading ? (
                        <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg 
                          className="w-5 h-5 text-blue-400 hover:text-blue-300 transition-colors" 
                          fill="none" 
                          stroke="currentColor" 
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
                );
              })() : (() => {
                const NormalModeIcon = MODE_INFO[currentMode].icon;
                return (
                <div className="relative">
                  {/* Объединенная область ввода */}
                  <div className="relative flex items-center bg-[#0f111b] border-2 border-[#1f2236] rounded-lg focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-all duration-200">
                    {/* Mode Dropdown - слева внутри поля */}
                    <div className="relative flex-shrink-0 mode-dropdown">
                      <button
                        type="button"
                        onClick={() => setModeDropdownOpen(!modeDropdownOpen)}
                        className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] transition-colors flex items-center gap-1.5 text-xs font-medium text-gray-300 border-r border-[#1f2236]"
                        title={MODE_INFO[currentMode].description}
                      >
                        <NormalModeIcon size={14} strokeWidth={1.5} />
                        <span className="hidden sm:inline">{MODE_INFO[currentMode].name}</span>
                        <ChevronDown size={10} strokeWidth={1.5} />
                      </button>
                      {modeDropdownOpen && (
                        <div className="absolute bottom-full left-0 mb-2 w-48 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg shadow-xl z-20 overflow-hidden">
                          {Object.entries(MODE_INFO).map(([mode, info]) => {
                            const ModeOptionIcon = info.icon;
                            return (
                            <button
                              key={mode}
                              type="button"
                              onClick={() => {
                                handleModeChange(mode as ChatMode);
                                setModeDropdownOpen(false);
                              }}
                              className={`w-full px-3 py-2 text-left text-xs font-medium transition-colors flex items-center gap-2 ${
                                currentMode === mode
                                  ? 'bg-blue-600/30 text-blue-300'
                                  : 'text-gray-300 hover:bg-[#1f2236]'
                              }`}
                            >
                              <ModeOptionIcon size={14} strokeWidth={1.5} />
                              <span className="flex-1">{info.name}</span>
                              {currentMode === mode && <CircleCheck size={12} strokeWidth={1.5} className="text-blue-400" />}
                            </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Agent Dropdown (only for agent mode) - внутри поля */}
                    {currentMode === 'agent' && (
                      <div className="relative flex-shrink-0 agent-dropdown">
                        <button
                          type="button"
                          onClick={() => setAgentDropdownOpen(!agentDropdownOpen)}
                          className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] transition-colors flex items-center gap-1.5 text-xs font-medium text-gray-300 border-r border-[#1f2236]"
                          title="Выбрать агента"
                        >
                          <Bot size={14} strokeWidth={1.5} />
                          <span className="hidden sm:inline max-w-[80px] truncate">
                            {selectedAgent ? AGENTS.find(a => a.id === selectedAgent)?.name : 'Агент'}
                          </span>
                          <span className="text-[10px]">▼</span>
                        </button>
                        {agentDropdownOpen && (
                          <div className="absolute bottom-full left-0 mb-2 w-56 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg shadow-xl z-20 overflow-hidden max-h-64 overflow-y-auto">
                            {AGENTS.map((agent) => (
                              <button
                                key={agent.id}
                                type="button"
                                onClick={() => {
                                  setSelectedAgent(agent.id);
                                  setAgentDropdownOpen(false);
                                }}
                                className={`w-full px-3 py-2 text-left text-xs font-medium transition-colors flex items-center gap-2 ${
                                  selectedAgent === agent.id
                                    ? 'bg-blue-600/30 text-blue-300'
                                    : 'text-gray-300 hover:bg-[#1f2236]'
                                }`}
                                title={agent.description}
                              >
                                <span className="flex-1">{agent.name}</span>
                                {selectedAgent === agent.id && <span className="text-blue-400">✓</span>}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Textarea */}
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={(e) => {
                        setInput(e.target.value);
                        e.target.style.height = 'auto';
                        e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
                      }}
                      onKeyDown={handleKeyDown}
                      placeholder={
                        currentMode === 'agent' && selectedAgent
                          ? `Введите задачу для ${AGENTS.find(a => a.id === selectedAgent)?.name}...`
                          : 'Введите вашу задачу... (Enter для отправки, Shift+Enter для новой строки)'
                      }
                      className="flex-1 px-4 py-2.5 min-h-[42px] bg-transparent text-white placeholder-gray-500 resize-none focus:outline-none max-h-[150px] transition-all duration-200 text-sm leading-relaxed"
                      rows={1}
                      disabled={isLoading}
                    />

                    {/* Кнопка отправки - стрелка справа внутри поля */}
                    <button
                      type="submit"
                      disabled={!input.trim() || isLoading || (currentMode === 'agent' && !selectedAgent)}
                      className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236]"
                      title="Отправить (Enter)"
                    >
                      {isLoading ? (
                        <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg 
                          className="w-5 h-5 text-blue-400 hover:text-blue-300 transition-colors" 
                          fill="none" 
                          stroke="currentColor" 
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
                );
              })()}
            </form>
          </div>
      </div>
    </div>
  );
}

