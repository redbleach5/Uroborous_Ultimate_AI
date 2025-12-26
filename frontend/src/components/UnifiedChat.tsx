import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { executeTask, processBatchTasks, sendChat, ChatMessage as APIChatMessage } from '../api/client';
import { useChatStore, ChatMode, FeedbackData } from '../state/chatStore';
import { useExecutionInfo } from '../state/executionContext';
import {
  MessageSquare, Bot, Zap, ChevronDown, CircleCheck, FileText, Wifi, WifiOff
} from 'lucide-react';

// Import new components
import { ChatMessage } from './ChatMessage';
import { ChatMessage as MessageType } from '../state/chatStore';
import { useCodeExecutor } from './CodeExecutor';
import { useModelSelector, ModelSelectorDropdown } from './ModelSelector';
import { ConversationSidebar, useSidebar, ModeInfo, Conversation } from './ConversationSidebar';
import { useWebSocket, ProgressUpdate } from '../hooks/useWebSocket';
import { InlineProgress } from './ProgressIndicator';

// ============ Constants ============

const AGENTS = [
  { id: 'code_writer', name: 'Генератор кода', description: 'Генерация и рефакторинг кода' },
  { id: 'react', name: 'ReAct', description: 'Интерактивное решение задач' },
  { id: 'research', name: 'Исследователь', description: 'Исследование кодовой базы и требований' },
  { id: 'data_analysis', name: 'Анализ данных', description: 'Анализ данных и создание моделей' },
  { id: 'workflow', name: 'Workflow', description: 'Управление рабочими процессами' },
  { id: 'integration', name: 'Интеграция', description: 'Интеграция с внешними сервисами' },
  { id: 'monitoring', name: 'Мониторинг', description: 'Мониторинг производительности системы' },
];

const MODE_INFO: Record<ChatMode, ModeInfo> = {
  chat: { 
    name: 'Ассистент', 
    description: 'Универсальный помощник: новости, шутки, советы, команды Linux', 
    icon: MessageSquare,
    placeholder: 'Спросите что угодно: новости, погода, шутка, команда Linux...',
    examples: ['📰 Последние новости о ценах на видеокарты', '😄 Расскажи анекдот про программистов', '🐧 Как найти файл в Linux?', '💡 Дай совет по тайм-менеджменту']
  },
  task: { 
    name: 'Задачи', 
    description: 'Выполнение сложных задач с помощью агентов', 
    icon: Zap,
    placeholder: 'Опишите задачу: создать игру, проанализировать код, исследовать тему...',
    examples: ['🎮 Создай игру змейка на HTML/JS', '🔍 Проанализируй архитектуру проекта', '📊 Сравни React и Vue.js', '🛠️ Напиши скрипт для бэкапа']
  },
  agent: { 
    name: 'Агенты', 
    description: 'Работа с конкретным специализированным агентом', 
    icon: Bot,
    placeholder: 'Задача для выбранного агента...',
    examples: ['💻 Code Writer: Напиши REST API', '🔬 Research: Исследуй тему', '📈 Data Analysis: Проанализируй данные']
  },
  batch: { 
    name: 'Пакетная', 
    description: 'Обработка нескольких задач одновременно', 
    icon: Zap,
    placeholder: 'Введите задачи (каждая с новой строки)...',
    examples: ['Задача 1', 'Задача 2', 'Задача 3']
  },
};

// ============ Main Component ============

export function UnifiedChat() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>(() => {
    return localStorage.getItem('selectedAgent') || '';
  });
  const [modeDropdownOpen, setModeDropdownOpen] = useState(false);
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false);
  const [showModelSelector, setShowModelSelector] = useState(false);
  
  const { setExecutionInfo } = useExecutionInfo();
  
  // Use custom hooks for code execution, model selection, and sidebar
  const codeExecutor = useCodeExecutor();
  const modelSelector = useModelSelector();
  const sidebar = useSidebar();
  
  // WebSocket for real-time progress (optional enhancement)
  const [wsProgress, setWsProgress] = useState<ProgressUpdate | null>(null);
  const [wsEnabled, setWsEnabled] = useState(() => {
    return localStorage.getItem('wsEnabled') === 'true';
  });
  
  const handleWsProgress = useCallback((progress: ProgressUpdate) => {
    setWsProgress(progress);
    // Автоматически скрываем через 2 секунды после завершения
    if (progress.stage === 'completed' || progress.stage === 'error') {
      setTimeout(() => setWsProgress(null), 2000);
    }
  }, []);
  
  const {
    isConnected: wsConnected,
    connect: wsConnect,
    disconnect: wsDisconnect,
  } = useWebSocket({
    autoConnect: wsEnabled,
    onProgress: handleWsProgress,
    onError: (err) => console.warn('[WS Error]', err),
  });
  
  // Toggle WebSocket connection
  const toggleWebSocket = useCallback(() => {
    const newState = !wsEnabled;
    setWsEnabled(newState);
    localStorage.setItem('wsEnabled', String(newState));
    if (newState) {
      wsConnect();
    } else {
      wsDisconnect();
      setWsProgress(null);
    }
  }, [wsEnabled, wsConnect, wsDisconnect]);

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
      createConversation();
    } else if (!currentId || !conversations[currentId]) {
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
      if (!target.closest('.mode-dropdown') && !target.closest('.agent-dropdown') && !target.closest('.model-dropdown')) {
        setModeDropdownOpen(false);
        setAgentDropdownOpen(false);
        setShowModelSelector(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Save selected agent to localStorage
  useEffect(() => {
    localStorage.setItem('selectedAgent', selectedAgent);
  }, [selectedAgent]);

  // Update selected agent when mode changes
  useEffect(() => {
    if (currentMode === 'agent' && !selectedAgent) {
      setSelectedAgent('code_writer');
    } else if (currentMode !== 'agent') {
      setSelectedAgent('');
    }
  }, [currentMode, selectedAgent]);

  const handleModeChange = (mode: ChatMode) => {
    setCurrentMode(mode);
  };

  const handleFeedbackSubmit = (messageId: string, feedback: FeedbackData) => {
    if (currentId) {
      updateMessage(currentId, messageId, { feedback });
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    let convId = currentId;
    if (!convId || !conversations[convId]) {
      convId = createConversation(undefined, currentMode);
    } else {
      convId = currentConversation?.id || convId;
    }
    const userMessageId = `msg-${Date.now()}`;
    
    let userContent = input.trim();
    
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
      } else if (currentMode === 'chat') {
        setExecutionInfo({ agent: 'Ассистент', models: [] });
        
        const history: APIChatMessage[] = messages.slice(-10).map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content
        }));
        
        const chatResponse = await sendChat({
          message: inputToProcess,
          history,
          mode: 'general',
          context: {},
          model: modelSelector.autoSelectModel ? undefined : modelSelector.selectedModel || undefined,
          provider: modelSelector.autoSelectModel ? undefined : 'ollama'
        });
        
        if (chatResponse.success) {
          // Добавляем предупреждение о сложности к ответу если есть
          let finalContent = chatResponse.message;
          if (chatResponse.warning) {
            finalContent = `${chatResponse.warning}\n\n---\n\n${chatResponse.message}`;
          }
          
          updateMessage(convId, assistantMessageId, {
            content: finalContent,
            status: 'completed',
            metadata: chatResponse.metadata
          });
        } else {
          updateMessage(convId, assistantMessageId, {
            content: `❌ Ошибка: ${chatResponse.error}`,
            status: 'error'
          });
        }
        
        setIsLoading(false);
        return;
      } else {
        const agentType = currentMode === 'agent' && selectedAgent ? selectedAgent : undefined;
        
        if (agentType) {
          const agentName = AGENTS.find(a => a.id === agentType)?.name || agentType;
          setExecutionInfo({ agent: agentName, models: [] });
        } else {
          setExecutionInfo({ agent: 'Оркестратор', models: [] });
        }

        response = await executeTask({
          task: inputToProcess,
          agent_type: agentType,
          context: {},
          model: modelSelector.autoSelectModel ? undefined : modelSelector.selectedModel || undefined,
          provider: modelSelector.autoSelectModel ? undefined : 'ollama'
        });

        const models: string[] = [];
        
        if (response.result?.routing?.selected_provider) {
          const provider = response.result.routing.selected_provider;
          const model = response.result.model || response.result.routing.selected_model;
          if (model && model !== provider) {
            models.push(`${provider}/${model}`);
          } else {
            models.push(provider);
          }
        } else if (response.result?.model && !models.includes(response.result.model)) {
          models.push(response.result.model);
        } else if (response.result?.metadata) {
          const metadata = response.result.metadata;
          if (metadata.fast_provider) {
            models.push(metadata.fast_provider);
          }
          if (metadata.powerful_provider && metadata.powerful_provider !== metadata.fast_provider) {
            models.push(metadata.powerful_provider);
          }
        }
        
        if (models.length > 0) {
          const currentInfo = { agent: agentType ? (AGENTS.find(a => a.id === agentType)?.name || agentType) : 'Автовыбор', models: [] };
          setExecutionInfo({ ...currentInfo, models });
        }

        let thinking: string | undefined;
        let metadata: any = {};
        
        if (response.result?.thinking) {
          thinking = response.result.thinking;
        } else if (response.result?.metadata?.thinking) {
          thinking = response.result.metadata.thinking;
        } else if (response.thinking) {
          thinking = response.thinking;
        }
        
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
        
        if (!metadata.provider && metadata.model) {
          if (metadata.model.includes('llama') || metadata.model.includes('mistral') || 
              metadata.model.includes('codellama') || metadata.model.includes('deepseek') ||
              metadata.model.includes('qwen') || metadata.model.includes('neural-chat')) {
            metadata.provider = 'ollama';
          }
        }
        
        let reflection: any = null;
        if (response.result?._reflection) {
          reflection = response.result._reflection;
          metadata.reflection_attempts = response.result._reflection_attempts || 1;
          metadata.corrected = response.result._corrected || false;
          metadata.execution_time = response.result._execution_time;
        } else if (response.result?.result?._reflection) {
          reflection = response.result.result._reflection;
          metadata.reflection_attempts = response.result.result._reflection_attempts || 1;
          metadata.corrected = response.result.result._corrected || false;
          metadata.execution_time = response.result.result._execution_time;
        }
        
        const isSuccess = response && response.success === true;
        let content = '';
        
        // Добавляем предупреждение о сложности если есть (НЕ блокирует!)
        const warningPrefix = response.warning 
          ? `${response.warning}\n\n---\n\n` 
          : '';
        
        try {
          if (isSuccess) {
            if (response.result?.code) {
              content = `${warningPrefix}✅ Задача выполнена успешно!\n\nСгенерированный код:\n\`\`\`python\n${response.result.code}\n\`\`\``;
            } else if (response.result?.message) {
              content = `${warningPrefix}✅ Задача выполнена успешно!\n\n${response.result.message}`;
            } else if (response.result?.report) {
              const reportText = String(response.result.report || '');
              content = `${warningPrefix}✅ Задача выполнена успешно!\n\n${reportText}`;
            } else if (typeof response.result === 'string') {
              content = `${warningPrefix}✅ Задача выполнена успешно!\n\n${response.result}`;
            } else if (response.result && typeof response.result === 'object') {
              const resultStr = JSON.stringify(response.result, null, 2);
              const maxLength = 2000;
              content = `${warningPrefix}✅ Задача выполнена успешно!\n\n${resultStr.length > maxLength ? resultStr.substring(0, maxLength) + '\n\n... (результат обрезан)' : resultStr}`;
            } else {
              content = `${warningPrefix}✅ Задача выполнена успешно!`;
            }
          } else {
            const errorMsg = response.error || 'Неизвестная ошибка';
            content = `${warningPrefix}❌ Ошибка выполнения задачи:\n\n${errorMsg}`;
            
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
      setExecutionInfo(null);
    } finally {
      setIsLoading(false);
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

  const handleRunCode = (code: string, messageId: string, files?: any[]) => {
    codeExecutor.handleRunCode(code, messageId, files, currentConversation?.messages);
  };

  // ============ Render ============

  return (
    <div className="flex h-full bg-[#0f111b] text-white overflow-hidden">
      {/* Sidebar */}
      <ConversationSidebar
        conversations={conversations as unknown as Record<string, Conversation>}
        currentConversationId={currentConversation?.id}
        modeInfo={MODE_INFO}
        sidebar={sidebar}
        onSelectConversation={setCurrentConversation}
        onNewChat={handleNewChat}
        onRenameConversation={handleRename}
        onDeleteConversation={handleDelete}
        onClearHistory={clearHistory}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 py-4">
            <div className="max-w-4xl mx-auto space-y-4">
              {messages.length === 0 ? (
                <WelcomeScreen 
                  currentMode={currentMode} 
                  modeInfo={MODE_INFO} 
                  onExampleClick={setInput} 
                />
              ) : (
                messages.map((message: MessageType, index: number) => (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    index={index}
                    runningCodeId={codeExecutor.runningCodeId}
                    executionResult={codeExecutor.executionResults[message.id]}
                    onRunCode={handleRunCode}
                    onDownloadCode={codeExecutor.downloadCode}
                    onFeedbackSubmit={message.role === 'assistant' ? handleFeedbackSubmit : undefined}
                  />
                ))
              )}
              
              {/* Real-time progress indicator */}
              {wsProgress && isLoading && (
                <InlineProgress progress={wsProgress} />
              )}
              
              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>

        {/* Input Area */}
        <InputArea
          input={input}
          setInput={setInput}
          isLoading={isLoading}
          currentMode={currentMode}
          selectedAgent={selectedAgent}
          modeDropdownOpen={modeDropdownOpen}
          setModeDropdownOpen={setModeDropdownOpen}
          agentDropdownOpen={agentDropdownOpen}
          setAgentDropdownOpen={setAgentDropdownOpen}
          showModelSelector={showModelSelector}
          setShowModelSelector={setShowModelSelector}
          modelSelector={modelSelector}
          onModeChange={handleModeChange}
          onAgentChange={setSelectedAgent}
          onSubmit={handleSubmit}
          onKeyDown={handleKeyDown}
          inputRef={inputRef}
          agents={AGENTS}
          modeInfo={MODE_INFO}
          wsConnected={wsConnected}
          wsEnabled={wsEnabled}
          onToggleWebSocket={toggleWebSocket}
        />
      </div>
    </div>
  );
}

// ============ Welcome Screen Component ============

interface WelcomeScreenProps {
  currentMode: ChatMode;
  modeInfo: Record<ChatMode, ModeInfo>;
  onExampleClick: (text: string) => void;
}

const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ currentMode, modeInfo, onExampleClick }) => {
  const WelcomeIcon = modeInfo[currentMode].icon;
  
  return (
    <div className="text-center mt-12 animate-fade-in">
      <div className="mb-4 animate-bounce-slow flex justify-center">
        <WelcomeIcon size={48} strokeWidth={1} className="text-blue-400" />
      </div>
      <h2 className="text-2xl font-bold mb-2 text-gray-100">Добро пожаловать в {modeInfo[currentMode].name}</h2>
      <p className="text-gray-400 mb-6 text-sm">{modeInfo[currentMode].description}</p>
      
      {(currentMode === 'chat' || currentMode === 'task') && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 max-w-3xl mx-auto text-left">
          {modeInfo[currentMode].examples.map((example, idx) => (
            <div 
              key={idx}
              onClick={() => {
                const cleanExample = example.replace(/^[^\w\sа-яА-ЯёЁ]+\s*/, '');
                onExampleClick(cleanExample);
              }}
              className="p-3 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-lg border border-[#2a2f46] hover:border-blue-500/50 transition-all duration-200 cursor-pointer group hover:shadow-lg hover:shadow-blue-500/10"
            >
              <div className="text-sm text-gray-300 group-hover:text-white transition-colors line-clamp-2">
                {example}
              </div>
            </div>
          ))}
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
};

// ============ Input Area Component ============

interface InputAreaProps {
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  currentMode: ChatMode;
  selectedAgent: string;
  modeDropdownOpen: boolean;
  setModeDropdownOpen: (value: boolean) => void;
  agentDropdownOpen: boolean;
  setAgentDropdownOpen: (value: boolean) => void;
  showModelSelector: boolean;
  setShowModelSelector: (value: boolean) => void;
  modelSelector: ReturnType<typeof useModelSelector>;
  onModeChange: (mode: ChatMode) => void;
  onAgentChange: (agent: string) => void;
  onSubmit: (e?: React.FormEvent) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  agents: typeof AGENTS;
  modeInfo: Record<ChatMode, ModeInfo>;
  // WebSocket props
  wsConnected?: boolean;
  wsEnabled?: boolean;
  onToggleWebSocket?: () => void;
}

const InputArea: React.FC<InputAreaProps> = ({
  input,
  setInput,
  isLoading,
  currentMode,
  selectedAgent,
  modeDropdownOpen,
  setModeDropdownOpen,
  agentDropdownOpen,
  setAgentDropdownOpen,
  showModelSelector,
  setShowModelSelector,
  modelSelector,
  onModeChange,
  onAgentChange,
  onSubmit,
  onKeyDown,
  inputRef,
  agents,
  modeInfo,
  wsConnected,
  wsEnabled,
  onToggleWebSocket,
}) => {
  const ModeIcon = modeInfo[currentMode].icon;
  
  return (
    <div className="border-t border-[#1f2236] bg-gradient-to-r from-[#131524] to-[#1a1d2e] px-4 py-3 shadow-2xl">
      <form onSubmit={onSubmit} className="max-w-4xl mx-auto">
        <div className="relative">
          <div className="relative flex items-center bg-[#0f111b] border-2 border-[#1f2236] rounded-lg focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-all duration-200">
            {/* Mode Dropdown */}
            <div className="relative flex-shrink-0 mode-dropdown">
              <button
                type="button"
                onClick={() => setModeDropdownOpen(!modeDropdownOpen)}
                className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] transition-colors flex items-center gap-1.5 text-xs font-medium text-gray-300 border-r border-[#1f2236]"
                title={modeInfo[currentMode].description}
              >
                <ModeIcon size={14} strokeWidth={1.5} />
                <span className="hidden sm:inline">{modeInfo[currentMode].name}</span>
                <ChevronDown size={10} strokeWidth={1.5} />
              </button>
              {modeDropdownOpen && (
                <div className="absolute bottom-full left-0 mb-2 w-48 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg shadow-xl z-20 overflow-hidden">
                  {Object.entries(modeInfo).map(([mode, info]) => {
                    const DropdownIcon = info.icon;
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => {
                          onModeChange(mode as ChatMode);
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

            {/* Agent Dropdown (only for agent mode) */}
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
                    {selectedAgent ? agents.find(a => a.id === selectedAgent)?.name : 'Агент'}
                  </span>
                  <span className="text-[10px]">▼</span>
                </button>
                {agentDropdownOpen && (
                  <div className="absolute bottom-full left-0 mb-2 w-56 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg shadow-xl z-20 overflow-hidden max-h-64 overflow-y-auto">
                    {agents.map((agent) => (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => {
                          onAgentChange(agent.id);
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

            {/* Model Selector */}
            {currentMode !== 'batch' && (
              <ModelSelectorDropdown
                availableModels={modelSelector.availableModels}
                selectedModel={modelSelector.selectedModel}
                autoSelectModel={modelSelector.autoSelectModel}
                loadingModels={modelSelector.loadingModels}
                resourceLevel={modelSelector.resourceLevel}
                onModelSelect={modelSelector.handleModelSelect}
                isOpen={showModelSelector}
                onToggle={() => setShowModelSelector(!showModelSelector)}
                onClose={() => setShowModelSelector(false)}
              />
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
              onKeyDown={currentMode === 'batch' ? undefined : onKeyDown}
              placeholder={
                currentMode === 'batch' 
                  ? 'Введите задачи (по одной на строку)...'
                  : currentMode === 'agent' && selectedAgent
                  ? `Задача для ${agents.find(a => a.id === selectedAgent)?.name}...`
                  : modeInfo[currentMode].placeholder
              }
              className="flex-1 px-4 py-2.5 min-h-[42px] bg-transparent text-white placeholder-gray-500 resize-none focus:outline-none max-h-[150px] transition-all duration-200 text-sm leading-relaxed"
              rows={1}
              disabled={isLoading}
            />

            {/* WebSocket Toggle */}
            {onToggleWebSocket && (
              <button
                type="button"
                onClick={onToggleWebSocket}
                className={`px-2 py-2.5 h-full bg-transparent hover:bg-[#1f2236] transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236] ${
                  wsEnabled ? (wsConnected ? 'text-green-400' : 'text-yellow-400') : 'text-gray-500'
                }`}
                title={wsEnabled ? (wsConnected ? 'WebSocket подключен (отключить)' : 'WebSocket подключается...') : 'Включить real-time прогресс'}
              >
                {wsEnabled ? (
                  <Wifi size={14} strokeWidth={1.5} className={wsConnected ? '' : 'animate-pulse'} />
                ) : (
                  <WifiOff size={14} strokeWidth={1.5} />
                )}
              </button>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={!input.trim() || isLoading || (currentMode === 'agent' && !selectedAgent)}
              className="px-3 py-2.5 h-full bg-transparent hover:bg-[#1f2236] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center flex-shrink-0 border-l border-[#1f2236]"
              title={currentMode === 'batch' ? 'Обработать пакет' : 'Отправить (Enter)'}
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
      </form>
    </div>
  );
};

export default UnifiedChat;
