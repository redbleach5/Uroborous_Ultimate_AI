import React, { useState } from 'react';
import Editor from '@monaco-editor/react';
import { executeTask, executeTool } from '../api/client';

// Helper function to detect HTML/CSS code
const detectCodeType = (code: string): 'html' | 'python' | 'node' | 'bash' => {
  const trimmed = code.trim();
  // Check for HTML
  if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
      (code.includes('<html') && code.includes('</html>')) ||
      (code.includes('<div') && code.includes('</div>') && code.includes('<body'))) {
    return 'html';
  }
  // Check for CSS (standalone CSS file)
  if (code.includes('{') && code.includes('}') && 
      (code.includes('color:') || code.includes('background:') || 
       code.includes('margin:') || code.includes('padding:') || code.includes('font-')) &&
      !code.includes('def ') && !code.includes('function ') && !code.includes('const ')) {
    return 'html'; // Treat CSS as HTML for preview purposes
  }
  // Default detection based on language selector would go here
  return 'python';
};

// Universal code block parser - extracts HTML, CSS, and JS from LLM response
interface ParsedCodeBlock {
  type: 'html' | 'css' | 'javascript' | 'js' | 'unknown';
  content: string;
  language?: string;
}

const parseCodeBlocks = (code: string): ParsedCodeBlock[] => {
  const blocks: ParsedCodeBlock[] = [];
  
  // Match all code blocks: ```language ... ``` or ``` ... ```
  const codeBlockRegex = /```(\w+)?\s*([\s\S]*?)```/g;
  let match;
  
  while ((match = codeBlockRegex.exec(code)) !== null) {
    const language = match[1]?.toLowerCase() || '';
    const content = match[2].trim();
    
    // Determine type based on language hint or content analysis
    let type: ParsedCodeBlock['type'] = 'unknown';
    
    if (language === 'html' || language === 'htm') {
      type = 'html';
    } else if (language === 'css') {
      type = 'css';
    } else if (language === 'javascript' || language === 'js') {
      type = 'javascript';
    } else if (language === 'typescript' || language === 'ts') {
      type = 'javascript'; // Treat TS as JS for browser
    } else {
      // Heuristic detection based on content
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
  
  // If no code blocks found, check if the entire code is HTML
  if (blocks.length === 0) {
    const trimmed = code.trim();
    if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
        (trimmed.includes('<html') && trimmed.includes('</html>'))) {
      blocks.push({ type: 'html', content: trimmed });
    }
  }
  
  return blocks;
};

// Smart HTML processor - combines HTML, CSS, and JS into a single valid HTML document
const processHtmlCode = (code: string): string => {
  // Parse all code blocks
  const blocks = parseCodeBlocks(code);
  
  
  // Extract HTML, CSS, and JS
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
  
  // If no HTML block found, check if the entire code is HTML
  if (!htmlContent) {
    const trimmed = code.trim();
    if (trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html') || 
        (trimmed.includes('<html') && trimmed.includes('</html>'))) {
      htmlContent = trimmed;
    } else {
      // Try to find HTML in the code (might be mixed with markdown)
      const htmlMatch = code.match(/<html[\s\S]*?<\/html>/i) || 
                       code.match(/<!DOCTYPE[\s\S]*?<\/html>/i) ||
                       code.match(/<body[\s\S]*?<\/body>/i);
      if (htmlMatch) {
        htmlContent = htmlMatch[0];
      }
    }
  }
  
  // If still no HTML, create a basic structure
  if (!htmlContent) {
    htmlContent = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<title>Generated Page</title>\n</head>\n<body>\n</body>\n</html>';
  }
  
  // Process HTML: remove external resources and extract existing styles/scripts
  let processedHtml = htmlContent;
  
  // Remove external stylesheet links
  processedHtml = processedHtml.replace(/<link[^>]*rel=["']stylesheet["'][^>]*>/gi, '');
  
  // Remove external script sources (but keep inline scripts)
  processedHtml = processedHtml.replace(/<script[^>]*src=["'][^"]+["'][^>]*>[\s\S]*?<\/script>/gi, '');
  
  // Extract existing <style> tags content (we'll merge with new CSS)
  const existingStyleMatches = processedHtml.match(/<style[^>]*>([\s\S]*?)<\/style>/gi);
  const existingStyles: string[] = [];
  if (existingStyleMatches) {
    for (const match of existingStyleMatches) {
      const content = match.replace(/<style[^>]*>|<\/style>/gi, '').trim();
      if (content) existingStyles.push(content);
    }
  }
  
  // Extract existing inline <script> tags content (we'll merge with new JS)
  const existingScriptMatches = processedHtml.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
  const existingScripts: string[] = [];
  if (existingScriptMatches) {
    for (const match of existingScriptMatches) {
      // Skip external scripts (already removed)
      if (!match.includes('src=')) {
        const content = match.replace(/<script[^>]*>|<\/script>/gi, '').trim();
        if (content) existingScripts.push(content);
      }
    }
  }
  
  // Combine all CSS
  const allCss = [...existingStyles, ...cssBlocks].filter(c => c.length > 0);
  
  // Combine all JS
  const allJs = [...existingScripts, ...jsBlocks].filter(j => j.length > 0);
  
  // Remove existing <style> and <script> tags (we'll add them back properly)
  processedHtml = processedHtml.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  processedHtml = processedHtml.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  
  // Insert CSS in <head>
  if (allCss.length > 0) {
    const combinedCss = allCss.join('\n\n');
    if (processedHtml.includes('</head>')) {
      processedHtml = processedHtml.replace('</head>', `<style>\n${combinedCss}\n</style>\n</head>`);
    } else if (processedHtml.includes('<head>')) {
      processedHtml = processedHtml.replace('<head>', `<head>\n<style>\n${combinedCss}\n</style>`);
    } else {
      // No head tag, try to add before </body> or create head
      if (processedHtml.includes('</body>')) {
        processedHtml = processedHtml.replace('</body>', `<style>\n${combinedCss}\n</style>\n</body>`);
      } else if (processedHtml.includes('<body>')) {
        processedHtml = processedHtml.replace('<body>', `<body>\n<style>\n${combinedCss}\n</style>`);
      } else {
        // Create head section
        processedHtml = processedHtml.replace(/<html[^>]*>/i, `$&\n<head>\n<style>\n${combinedCss}\n</style>\n</head>`);
      }
    }
  }
  
  // Insert JS before </body>
  if (allJs.length > 0) {
    const combinedJs = allJs.join('\n\n');
    if (processedHtml.includes('</body>')) {
      processedHtml = processedHtml.replace('</body>', `<script>\n${combinedJs}\n</script>\n</body>`);
    } else if (processedHtml.includes('<body>')) {
      processedHtml = processedHtml.replace('<body>', `<body>\n<script>\n${combinedJs}\n</script>`);
    } else {
      // Add before </html>
      if (processedHtml.includes('</html>')) {
        processedHtml = processedHtml.replace('</html>', `<script>\n${combinedJs}\n</script>\n</html>`);
      } else {
        processedHtml += `\n<script>\n${combinedJs}\n</script>`;
      }
    }
  }
  
  // Ensure HTML structure is valid
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

export function CodeEditor() {
  const [code, setCode] = useState('// Ваш код здесь\n');
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [language, setLanguage] = useState<'python' | 'node' | 'bash'>('python');
  const [htmlPreviewUrl, setHtmlPreviewUrl] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!task.trim()) return;

    setLoading(true);
    setResult(null);


    try {
      const response = await executeTask({
        task,
        agent_type: 'code_writer',
        context: {
          existing_code: code
        }
      });

      if (response.success && response.result?.code) {
        const generatedCode = response.result.code;
        
        // Auto-detect code type and update language if needed
        const detectedType = detectCodeType(generatedCode);
        
        setCode(generatedCode);
        setResult('Код успешно сгенерирован!');
      } else {
        setResult('Не удалось сгенерировать код');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setResult(`Ошибка: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRun = async () => {
    setRunLoading(true);
    setRunResult(null);


    try {
      // Special handling for HTML/CSS: create preview and open in browser
      if (detectedType === 'html') {
        
        // Use smart HTML processor to combine HTML, CSS, and JS
        let processedCode = processHtmlCode(code);
        
        // Validate HTML structure before creating data URL
        const hasHtmlTag = processedCode.includes('<html');
        const hasBodyTag = processedCode.includes('<body');
        const hasClosingHtmlTag = processedCode.includes('</html>');
        const hasClosingBodyTag = processedCode.includes('</body>');
        const htmlTagCount = (processedCode.match(/<html/gi) || []).length;
        const closingHtmlTagCount = (processedCode.match(/<\/html>/gi) || []).length;
        const bodyTagCount = (processedCode.match(/<body/gi) || []).length;
        const closingBodyTagCount = (processedCode.match(/<\/body>/gi) || []).length;
        
        
        // Ensure HTML is properly closed (processHtmlCode should handle this, but double-check)
        if (!hasClosingHtmlTag) {
          processedCode += '\n</html>';
        }
        if (!hasClosingBodyTag && hasBodyTag) {
          processedCode = processedCode.replace(/<\/html>/i, '</body>\n</html>');
        }
        
        // Clean up old blob URL if it exists
        if (htmlPreviewUrl && htmlPreviewUrl.startsWith('blob:')) {
          URL.revokeObjectURL(htmlPreviewUrl);
        }
        
        // Create URL for rendering - use Blob URL for better compatibility
        let previewUrl: string;
        try {
          // Try Blob URL first (better for large HTML and new windows)
          const blob = new Blob([processedCode], { type: 'text/html;charset=utf-8' });
          previewUrl = URL.createObjectURL(blob);
          
        } catch (error) {
          // Fallback to data URL if Blob fails
          previewUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(processedCode);
          
        }
        
        
        // Set preview URL for iframe (use unique key to force reload)
        setHtmlPreviewUrl(previewUrl);
        
        
        // Also try to open in new window
        try {
          const newWindow = window.open(previewUrl, '_blank');
          if (newWindow) {
            setRunResult('✅ HTML открыт в новом окне браузера и в предпросмотре ниже!');
          } else {
            setRunResult('✅ HTML отображается в предпросмотре ниже. Если окно заблокировано, используйте кнопку "Открыть в новом окне".');
          }
        } catch (error) {
          setRunResult('✅ HTML отображается в предпросмотре ниже.');
        }
        
        return;
      }

      // Validate that code is executable before running
      const isValidExecutableCode = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
        const trimmed = code.trim();
        
        // Check if it's a project structure (tree view)
        if (trimmed.includes('├──') || trimmed.includes('└──') || trimmed.includes('│') || 
            (trimmed.includes('/') && trimmed.match(/^\s*[\w\-_]+(\/|\\|├|└)/))) {
          return false;
        }
        
        // Check if it starts with a directory name followed by slash (project structure)
        const firstLine = trimmed.split('\n')[0].trim();
        if (firstLine.match(/^[\w\-_а-яА-Я]+[\/\\]/) && !firstLine.includes('def ') && 
            !firstLine.includes('import ') && !firstLine.includes('class ')) {
          // Check if next lines are file listings
          const nextLines = trimmed.split('\n').slice(1, 5).join('\n');
          if (nextLines.match(/[├└│]/) || nextLines.match(/\.(py|js|ts|html|css|json|md)\s*#/)) {
            return false;
          }
        }
        
        // Check if it's markdown documentation (starts with #, contains markdown links)
        if (trimmed.startsWith('#') && !trimmed.includes('def ') && !trimmed.includes('class ') && 
            !trimmed.includes('import ') && !trimmed.includes('function ')) {
          return false;
        }
        
        // For Python: should contain executable statements
        if (lang === 'python') {
          // Check for Python keywords/constructs
          const hasPythonCode = trimmed.includes('def ') || trimmed.includes('class ') || 
                               trimmed.includes('import ') || trimmed.includes('from ') ||
                               trimmed.includes('if ') || trimmed.includes('for ') || 
                               trimmed.includes('while ') || trimmed.includes('print(') ||
                               (trimmed.includes('=') && (trimmed.includes('(') || trimmed.includes('[')));
          
          // If it looks like a directory structure or file listing, it's not executable
          if (trimmed.split('\n').length > 0) {
            const firstLines = trimmed.split('\n').slice(0, 5).join('\n');
            // Check for directory/file structure patterns
            if ((firstLines.match(/^[\w\-_а-яА-Я]+[\/\\]/) || 
                 firstLines.match(/[├└│]/) ||
                 firstLines.match(/\.(py|js|ts|html|css|json|md)\s*#/)) && !hasPythonCode) {
              return false;
            }
          }
          
          return hasPythonCode || trimmed.length < 100; // Allow short snippets
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
        
        return true; // Default to allowing execution
      };
      
      // Check if code requires interactive input
      const requiresInteractiveInput = (code: string, lang: 'python' | 'node' | 'bash'): boolean => {
        if (lang === 'python') {
          // Check for input() calls
          return /input\s*\(/.test(code) || /raw_input\s*\(/.test(code);
        }
        if (lang === 'node') {
          // Check for readline, prompt, or stdin usage
          return /readline|prompt\(|process\.stdin/.test(code);
        }
        if (lang === 'bash') {
          // Check for read command
          return /read\s+/.test(code);
        }
        return false;
      };
      
      // Check if code is executable
      if (!isValidExecutableCode(code, language)) {
        
        setRunResult('⚠️ Этот код не может быть выполнен напрямую. Похоже, это структура проекта или описание, а не исполняемый код. Попробуйте сгенерировать код заново с более конкретным запросом (например, "напиши полный код игры крестики-нолики на Python").');
        setRunLoading(false);
        return;
      }
      
      // Check if code requires interactive input
      if (requiresInteractiveInput(code, language)) {
        
        setRunResult('⚠️ Этот код требует интерактивного ввода (использует input() или аналогичные функции). Для интерактивных программ рекомендуется:\n\n1. Для игр: запросите веб-версию (HTML/CSS/JS) - она будет работать в браузере\n2. Для консольных программ: запустите код локально в терминале\n3. Попробуйте сгенерировать код заново с запросом веб-версии (например, "напиши игру крестики-нолики в HTML/CSS/JS")');
        setRunLoading(false);
        return;
      }
      
      // For other languages, execute as before
      // Подбираем команду под выбранный язык
      const command = (() => {
        switch (language) {
          case 'python':
            return `python3 - <<'PY'\n${code}\nPY`;
          case 'node':
            return `node - <<'JS'\n${code}\nJS`;
          case 'bash':
            return `bash - <<'SH'\n${code}\nSH`;
          default:
            return `python3 - <<'PY'\n${code}\nPY`;
        }
      })();


      const response = await executeTool({
        tool_name: 'execute_command',
        input: { command },
      });


      // Ожидаем, что тул вернёт stdout/stderr
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
      
      setRunResult(
        [stdout && `stdout:\n${stdout}`, stderr && `stderr:\n${stderr}`]
          .filter(Boolean)
          .join('\n\n') || 'Нет вывода'
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setRunResult(`Ошибка выполнения: ${errorMessage}`);
    } finally {
      setRunLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Task Input */}
      <div className="p-4 bg-gradient-to-r from-[#131524] to-[#1a1d2e] border-b border-[#1f2236] shadow-lg">
        <div className="max-w-6xl mx-auto">
          {/* Объединенная область ввода */}
          <div className="relative flex items-center bg-[#0f111b] border-2 border-[#1f2236] rounded-lg focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-all duration-200">
            {/* Поле ввода задачи */}
            <input
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Опишите, что вы хотите сгенерировать..."
              className="flex-1 px-4 py-2.5 min-h-[42px] bg-transparent text-white placeholder-gray-500 focus:outline-none transition-all duration-200"
              onKeyPress={(e) => e.key === 'Enter' && handleGenerate()}
            />

            {/* Выбор языка */}
            <div className="relative flex-shrink-0">
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as 'python' | 'node' | 'bash')}
                className="px-3 py-2.5 h-[42px] bg-transparent border-l border-[#1f2236] text-white focus:outline-none hover:bg-[#1f2236] transition-colors cursor-pointer appearance-none pr-8"
              >
                <option value="python" className="bg-[#0f111b]">Python</option>
                <option value="node" className="bg-[#0f111b]">Node.js</option>
                <option value="bash" className="bg-[#0f111b]">Bash</option>
              </select>
              <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>

            {/* Кнопка генерации - стрелка справа */}
            <button
              onClick={handleGenerate}
              disabled={loading || !task.trim()}
              className="px-3 py-2.5 h-[42px] bg-transparent hover:bg-[#1f2236] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236]"
              title="Сгенерировать код"
            >
              {loading ? (
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

            {/* Кнопка запуска - стрелка справа */}
            <button
              onClick={handleRun}
              disabled={runLoading}
              className="px-3 py-2.5 h-[42px] bg-transparent hover:bg-[#1f2236] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236]"
              title="Запустить код"
            >
              {runLoading ? (
                <div className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin"></div>
              ) : (
                <svg 
                  className="w-5 h-5 text-green-400 hover:text-green-300 transition-colors" 
                  fill="none" 
                  stroke="currentColor" 
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
            </button>
          </div>
        </div>
        {result && (
          <div className={`mt-4 text-sm px-4 py-3 rounded-xl border-2 flex items-start gap-2 ${
            result.startsWith('Ошибка:') || result.startsWith('Не удалось')
              ? 'bg-red-900/30 border-red-500/60 text-red-300'
              : 'bg-green-900/30 border-green-500/60 text-green-300'
          }`}>
            <span className="text-lg flex-shrink-0">{result.startsWith('Ошибка:') || result.startsWith('Не удалось') ? '❌' : '✅'}</span>
            <span>{result}</span>
          </div>
        )}
        {runResult && (
          <pre className="mt-4 text-xs bg-[#0a0a0f] p-4 rounded-xl border-2 border-[#1a1d2e] overflow-x-auto whitespace-pre-wrap text-gray-200 font-mono">
            {runResult}
          </pre>
        )}
        {htmlPreviewUrl && (
          <div className="mt-4 border-2 border-[#1a1d2e] rounded-xl overflow-hidden bg-[#0a0a0f]">
            <div className="flex items-center justify-between px-4 py-2 bg-[#1a1d2e] border-b border-[#2a2f46]">
              <span className="text-sm font-semibold text-gray-200">Предпросмотр HTML</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    window.open(htmlPreviewUrl, '_blank');
                  }}
                  className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium text-white"
                >
                  Открыть в новом окне
                </button>
                <button
                  onClick={() => {
                    // For blob URLs, we need to fetch and create a download link
                    if (htmlPreviewUrl.startsWith('blob:')) {
                      fetch(htmlPreviewUrl)
                        .then(res => res.blob())
                        .then(blob => {
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = 'generated.html';
                          document.body.appendChild(a);
                          a.click();
                          document.body.removeChild(a);
                          URL.revokeObjectURL(url);
                        })
                        .catch(err => {
                          console.error('Download failed:', err);
                        });
                    } else {
                      const a = document.createElement('a');
                      a.href = htmlPreviewUrl;
                      a.download = 'generated.html';
                      document.body.appendChild(a);
                      a.click();
                      document.body.removeChild(a);
                    }
                  }}
                  className="text-xs px-3 py-1.5 bg-green-600/80 hover:bg-green-600 rounded-lg transition-colors font-medium text-white"
                >
                  Скачать
                </button>
                <button
                  onClick={() => {
                    // Clean up blob URL if it exists
                    if (htmlPreviewUrl && htmlPreviewUrl.startsWith('blob:')) {
                      URL.revokeObjectURL(htmlPreviewUrl);
                    }
                    setHtmlPreviewUrl(null);
                  }}
                  className="text-xs px-3 py-1.5 bg-red-600/80 hover:bg-red-600 rounded-lg transition-colors font-medium text-white"
                >
                  Закрыть
                </button>
              </div>
            </div>
            <iframe
              key={`preview-${Date.now()}-${htmlPreviewUrl?.substring(0, 50)}`}
              src={htmlPreviewUrl || undefined}
              className="w-full h-[600px] border-0 bg-white"
              title="HTML Preview"
              sandbox="allow-scripts allow-same-origin allow-forms"
              onLoad={(e) => {
              }}
            />
          </div>
        )}
      </div>

      {/* Editor */}
      <div className="flex-1">
        <Editor
          height="100%"
          language={detectCodeType(code) === 'html' ? 'html' : language}
          value={code}
          onChange={(value) => setCode(value || '')}
          theme="vs-dark"
          options={{
            minimap: { enabled: true },
            fontSize: 14,
            wordWrap: 'on'
          }}
        />
      </div>
    </div>
  );
}

