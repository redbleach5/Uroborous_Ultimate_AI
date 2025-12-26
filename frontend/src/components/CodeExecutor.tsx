import React from 'react';
import { Play, Code, Globe, BarChart3 } from 'lucide-react';
import { executeTool } from '../api/client';

// ============ Code Utility Functions ============

/**
 * Extract code from markdown code blocks
 */
export const extractCodeFromMarkdown = (text: string): string | null => {
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
  
  // If no code blocks, check if the entire text is code
  const trimmed = text.trim();
  if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
      trimmed.startsWith('def ') || trimmed.startsWith('class ') ||
      trimmed.startsWith('import ') || trimmed.startsWith('function ') ||
      trimmed.startsWith('const ') || trimmed.startsWith('let ')) {
    return trimmed;
  }
  
  return null;
};

/**
 * Detect the type of code
 */
export const detectCodeType = (code: string): 'html' | 'python' | 'node' | 'bash' => {
  const trimmed = code.trim();
  
  // First check for HTML - this has highest priority
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

// ============ Code Block Parser ============

interface ParsedCodeBlock {
  type: 'html' | 'css' | 'javascript' | 'js' | 'unknown';
  content: string;
  language?: string;
}

export const parseCodeBlocks = (code: string): ParsedCodeBlock[] => {
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

// ============ Code Fixing Functions ============

/**
 * Fix missing curly braces in CSS and JavaScript
 */
export const fixMissingBraces = (code: string, type: 'css' | 'javascript'): string => {
  if (type === 'css') {
    const lines = code.split('\n');
    const fixedLines: string[] = [];
    let pendingSelector: { line: string; indent: string; index: number } | null = null;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      const indent = line.match(/^\s*/)?.[0] || '';
      const indentLevel = indent.length;
      
      const isSelector = trimmed && 
        !trimmed.includes('{') && 
        !trimmed.includes('}') &&
        !trimmed.includes(':') &&
        (trimmed.match(/^[.#]?[a-zA-Z][a-zA-Z0-9_-]*(\s+[.#]?[a-zA-Z][a-zA-Z0-9_-]*)*\s*$/) ||
         trimmed.match(/^[.#]?[a-zA-Z][a-zA-Z0-9_-]*\s*$/));
      
      const isProperty = trimmed && trimmed.includes(':') && !trimmed.includes('{') && !trimmed.includes('}');
      
      if (isSelector) {
        if (pendingSelector) {
          fixedLines.push(pendingSelector.indent + '}');
        }
        pendingSelector = { line, indent, index: fixedLines.length };
        fixedLines.push(line);
      } else if (isProperty) {
        if (pendingSelector && indentLevel > pendingSelector.indent.length) {
          fixedLines.splice(pendingSelector.index + 1, 0, pendingSelector.indent + '{');
          pendingSelector = null;
        }
        fixedLines.push(line);
      } else if (trimmed === '}') {
        if (pendingSelector) {
          pendingSelector = null;
        }
        fixedLines.push(line);
      } else if (trimmed && indentLevel === 0 && pendingSelector) {
        fixedLines.push(pendingSelector.indent + '}');
        pendingSelector = null;
        fixedLines.push(line);
      } else {
        fixedLines.push(line);
      }
    }
    
    if (pendingSelector) {
      fixedLines.push(pendingSelector.indent + '}');
    }
    
    return fixedLines.join('\n');
  } else if (type === 'javascript') {
    const lines = code.split('\n');
    const fixedLines: string[] = [];
    const braceStack: { type: string; indent: number; lineIndex: number }[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      const indent = line.match(/^\s*/)?.[0] || '';
      const indentLevel = indent.length;
      
      const funcMatch = trimmed.match(/^(function\s+\w+|const\s+\w+\s*=\s*function|let\s+\w+\s*=\s*function|var\s+\w+\s*=\s*function|if|for|while|else)\s*(\([^)]*\))?\s*$/);
      
      if (funcMatch && !trimmed.includes('{') && !trimmed.includes('}')) {
        if (i + 1 < lines.length) {
          const nextLine = lines[i + 1];
          const nextIndent = nextLine.match(/^\s*/)?.[0] || '';
          const nextTrimmed = nextLine.trim();
          if (nextIndent.length > indentLevel && nextTrimmed.length > 0 && !nextTrimmed.startsWith('}')) {
            fixedLines.push(line + ' {');
            braceStack.push({ type: funcMatch[1], indent: indentLevel, lineIndex: i });
            continue;
          }
        }
      }
      
      while (braceStack.length > 0) {
        const lastBrace = braceStack[braceStack.length - 1];
        if (indentLevel <= lastBrace.indent && trimmed.length > 0 && 
            !trimmed.startsWith('}') && !trimmed.includes('{') &&
            !trimmed.match(/^(function|const|let|var|if|for|while|else)\s/)) {
          fixedLines.push(' '.repeat(lastBrace.indent) + '}');
          braceStack.pop();
        } else {
          break;
        }
      }
      
      fixedLines.push(line);
      
      const openBraces = (line.match(/{/g) || []).length;
      const closeBraces = (line.match(/}/g) || []).length;
      for (let j = 0; j < openBraces - closeBraces; j++) {
        braceStack.push({ type: 'manual', indent: indentLevel, lineIndex: i });
      }
      for (let j = 0; j < closeBraces - openBraces; j++) {
        if (braceStack.length > 0) braceStack.pop();
      }
    }
    
    while (braceStack.length > 0) {
      const lastBrace = braceStack.pop();
      fixedLines.push(' '.repeat(lastBrace!.indent) + '}');
    }
    
    return fixedLines.join('\n');
  }
  
  return code;
};

// ============ HTML Processing ============

/**
 * Process HTML code - combine HTML, CSS, and JS into a single valid HTML document
 */
export const processHtmlCode = (code: string): string => {
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

// ============ Code Validation ============

/**
 * Check if code is valid executable code
 */
export const isValidExecutableCode = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
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

/**
 * Check if code requires interactive input
 */
export const requiresInteractiveInput = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
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

// ============ Code Execution Result Interface ============

export interface CodeExecutionResult {
  result: string | null;
  htmlPreviewUrl: string | null;
}

// ============ Code Block Display Component ============

interface CodeBlockProps {
  code: string;
  messageId: string;
  files?: any[];
  runningCodeId: string | null;
  executionResult?: CodeExecutionResult;
  onRunCode: (code: string, messageId: string, files?: any[]) => void;
  onDownloadCode: (code: string, filename: string) => void;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  messageId,
  files,
  runningCodeId,
  executionResult,
  onRunCode,
  onDownloadCode,
}) => {
  const codeType = detectCodeType(code);
  
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <Code size={14} strokeWidth={1.5} className="text-blue-400" />
          <span>Сгенерированный код</span>
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onRunCode(code, messageId, files)}
            disabled={runningCodeId === messageId}
            className="text-xs px-3 py-1.5 bg-green-600/80 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors font-medium flex items-center gap-1.5 shadow-md"
          >
            {runningCodeId === messageId ? (
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
            onClick={() => onDownloadCode(code, `generated_code.${codeType === 'html' ? 'html' : codeType === 'node' ? 'js' : 'py'}`)}
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
        <span className="absolute top-3 right-4 text-xs text-gray-400 font-medium">{codeType}</span>
      </div>
    
      {/* Execution Results */}
      {executionResult && (
        <div className="mt-4 space-y-3">
          {executionResult.htmlPreviewUrl && (
            <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg overflow-hidden">
              <div className="p-3 bg-[#1a1d2e] border-b border-[#2a2f46] flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                  <Globe size={14} strokeWidth={1.5} className="text-cyan-400" />
                  <span>Предпросмотр HTML</span>
                </span>
                <button
                  onClick={() => {
                    if (executionResult.htmlPreviewUrl) {
                      window.open(executionResult.htmlPreviewUrl, '_blank');
                    }
                  }}
                  className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium"
                >
                  Открыть в новом окне
                </button>
              </div>
              <iframe
                src={executionResult.htmlPreviewUrl}
                className="w-full h-96 border-0"
                title="HTML Preview"
                sandbox="allow-scripts allow-same-origin"
              />
            </div>
          )}
          
          {executionResult.result && (
            <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg p-4">
              <div className="text-sm font-semibold text-gray-200 mb-2 flex items-center gap-2">
                <BarChart3 size={14} strokeWidth={1.5} className="text-blue-400" />
                <span>Результат выполнения</span>
              </div>
              <pre className="bg-[#0a0a0f] p-4 rounded-lg overflow-x-auto text-xs font-mono text-gray-300 whitespace-pre-wrap border border-[#1a1d2e]">
                {executionResult.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============ Code Execution Hook ============

export interface UseCodeExecutorReturn {
  runningCodeId: string | null;
  executionResults: Record<string, CodeExecutionResult>;
  handleRunCode: (code: string, messageId: string, files?: any[], conversationMessages?: any[]) => Promise<void>;
  downloadCode: (code: string, filename?: string) => void;
}

export function useCodeExecutor(): UseCodeExecutorReturn {
  const [runningCodeId, setRunningCodeId] = React.useState<string | null>(null);
  const [executionResults, setExecutionResults] = React.useState<Record<string, CodeExecutionResult>>({});

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

  const handleRunCode = async (code: string, messageId: string, files?: any[], conversationMessages?: any[]) => {
    setRunningCodeId(messageId);
    setExecutionResults(prev => ({ ...prev, [messageId]: { result: null, htmlPreviewUrl: null } }));

    try {
      // Check if code seems incomplete (too short for HTML)
      const trimmedCode = code.trim();
      if (trimmedCode.length < 100 && detectCodeType(code) === 'html') {
        // Code might be incomplete, try to find full code in message content
        if (conversationMessages) {
          const message = conversationMessages.find((m: any) => m.id === messageId);
          if (message) {
            const extractedCode = extractCodeFromMarkdown(message.content || '');
            if (extractedCode && extractedCode.length > trimmedCode.length) {
              code = extractedCode;
            }
          }
        }
      }
      
      let codeToRun = code;
      let codeType = detectCodeType(code);
      
      // If there are multiple files, try to find the main executable file
      if (files && files.length > 0 && (!code || code.trim().length < 50)) {
        const mainFile = files.find((f: any) => {
          const path = (f.path || f.name || '').toLowerCase();
          return path.includes('main') || path.includes('app') || path.includes('index') || 
                 path.endsWith('.html') || path.endsWith('.py');
        });
        
        if (mainFile && mainFile.code) {
          codeToRun = mainFile.code;
          codeType = detectCodeType(mainFile.code);
          
          if (codeType === 'python' && files.length > 1) {
            setExecutionResults(prev => ({ 
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
        } catch {
          previewUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(processedCode);
        }
        
        setExecutionResults(prev => ({ 
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
            setExecutionResults(prev => ({ 
              ...prev, 
              [messageId]: { 
                result: '✅ HTML отображается в предпросмотре ниже. Если окно заблокировано, используйте предпросмотр.', 
                htmlPreviewUrl: previewUrl 
              } 
            }));
          }
        } catch {
          // Ignore window open errors
        }
        
        setRunningCodeId(null);
        return;
      }

      // Validate that code is executable
      if (!isValidExecutableCode(codeToRun, finalCodeType)) {
        setExecutionResults(prev => ({ 
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
        setExecutionResults(prev => ({ 
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
      
      setExecutionResults(prev => ({ 
        ...prev, 
        [messageId]: { 
          result, 
          htmlPreviewUrl: null 
        } 
      }));
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setExecutionResults(prev => ({ 
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

  // Cleanup blob URLs on unmount
  React.useEffect(() => {
    return () => {
      Object.values(executionResults).forEach(result => {
        if (result.htmlPreviewUrl && result.htmlPreviewUrl.startsWith('blob:')) {
          URL.revokeObjectURL(result.htmlPreviewUrl);
        }
      });
    };
  }, []);

  return {
    runningCodeId,
    executionResults,
    handleRunCode,
    downloadCode,
  };
}

export default CodeBlock;

