import React, { useEffect, useMemo, useRef, useState } from 'react';
import { executeTask } from '../api/client';
import SettingsPanel from './SettingsPanel';
import { useChatStore } from '../state/chatStore';

export function ManusStyleLayout() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showSettings, setShowSettings] = useState(false);

  const {
    conversations,
    currentId,
    createConversation,
    setCurrentConversation,
    renameConversation,
    clearConversation,
    addMessage,
    updateMessage,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Ensure at least one conversation exists
  useEffect(() => {
    if (!currentId || !conversations[currentId]) {
      createConversation();
    }
  }, [conversations, currentId, createConversation]);

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

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading || !currentConversation) return;

    const convId = currentConversation.id;
    const userMessageId = `msg-${Date.now()}`;
    addMessage(convId, {
      id: userMessageId,
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    });
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
      const response = await executeTask({
        task: input.trim(),
        agent_type: undefined,
        context: {},
      });

      updateMessage(convId, assistantMessageId, {
        content: response.success
          ? response.result?.code
            ? `✅ Задача выполнена успешно!\n\nСгенерированный код:\n\`\`\`python\n${response.result.code.substring(0, 500)}${response.result.code.length > 500 ? '...' : ''}\n\`\`\``
            : `✅ Задача выполнена успешно!\n\n${JSON.stringify(response.result, null, 2).substring(0, 1000)}`
          : `❌ Ошибка: ${response.error || 'Неизвестная ошибка'}`,
        status: response.success ? 'completed' : 'error',
        result: response.result,
        subtasks:
          response.subtasks?.map((st: string) => ({
            subtask: st,
            status: 'completed',
          })) || [],
      });
    } catch (error: any) {
      updateMessage(convId, assistantMessageId, {
        content: `❌ Ошибка выполнения: ${error.message || 'Неизвестная ошибка'}`,
        status: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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

  const clearHistory = () => {
    if (currentConversation && confirm('Очистить историю разговора?')) {
      clearConversation(currentConversation.id);
    }
  };

  const handleNewChat = () => {
    const newId = createConversation('Новый чат');
    setCurrentConversation(newId);
    setInput('');
  };

  const handleRename = (id: string) => {
    const title = prompt('Название чата', conversations[id]?.title || '');
    if (title !== null) {
      renameConversation(id, title);
    }
  };

  return (
    <div className="flex h-screen bg-[#0f111b] text-white overflow-hidden">
      {/* Sidebar */}
      <div
        className={`${
          sidebarOpen ? 'w-72' : 'w-0'
        } bg-[#131524] border-r border-[#1f2236] transition-all duration-300 overflow-hidden flex flex-col`}
      >
        <div className="p-4 border-b border-[#1f2236]">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">Чаты</h2>
            <button
              onClick={handleNewChat}
              className="text-xs px-3 py-1 rounded bg-accent-600 hover:bg-accent-700 text-white"
            >
              Новый
            </button>
          </div>
          <div className="flex items-center justify-between text-xs text-gray-400">
            <button onClick={() => setSidebarOpen(false)} className="hover:text-white">
              ← Скрыть
            </button>
            <button onClick={clearHistory} className="hover:text-white">
              Очистить чат
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {Object.values(conversations)
            .sort((a, b) => b.updatedAt - a.updatedAt)
            .map((conv) => (
              <div
                key={conv.id}
                className={`p-3 rounded border text-sm cursor-pointer transition-colors ${
                  conv.id === currentConversation?.id
                    ? 'border-accent-500 bg-[#1a1e30]'
                    : 'border-[#1f2236] bg-[#0f111b] hover:border-[#2a2f46]'
                }`}
                onClick={() => setCurrentConversation(conv.id)}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="font-semibold truncate">{conv.title}</div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRename(conv.id);
                    }}
                    className="text-xs text-gray-400 hover:text-white"
                    title="Переименовать"
                  >
                    ✎
                  </button>
                </div>
                <div className="text-[11px] text-gray-500">{new Date(conv.updatedAt).toLocaleString()}</div>
                <div className="text-xs text-gray-400 overflow-hidden text-ellipsis mt-1">
                  {conv.messages[conv.messages.length - 1]?.content || 'Пустой чат'}
                </div>
              </div>
            ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-16 bg-[#131524] border-b border-[#1f2236] flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            {!sidebarOpen && (
              <button onClick={() => setSidebarOpen(true)} className="text-gray-400 hover:text-white">
                ☰
              </button>
            )}
            <div>
              <div className="text-sm text-gray-400">Автономные агенты</div>
              <h1 className="text-xl font-semibold">AILLM</h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`px-4 py-2 rounded-md transition-colors ${
                showSettings ? 'bg-blue-600 text-white' : 'bg-[#1f2236] text-gray-300 hover:bg-[#2a2f46]'
              }`}
              title="Настройки"
            >
              ⚙️ Настройки
            </button>
            {!showSettings && <div className="text-sm text-gray-400">Автономные интеллектуальные LLM агенты</div>}
          </div>
        </header>

        {/* Messages Area or Settings */}
        <div className="flex-1 overflow-y-auto">
          {showSettings ? (
            <SettingsPanel />
          ) : (
            <div className="px-6 py-8">
              <div className="max-w-4xl mx-auto space-y-6">
                {messages.length === 0 ? (
                  <div className="text-center mt-20">
                    <div className="text-6xl mb-4">🤖</div>
                    <h2 className="text-2xl font-semibold mb-2">Добро пожаловать в AILLM</h2>
                    <p className="text-gray-400 mb-6">Я могу помочь вам с задачами любой сложности</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl mx-auto text-left">
                      <div className="p-4 bg-[#1a1a1a] rounded-lg border border-[#2a2a2a]">
                        <div className="font-semibold mb-1">🎮 Простые задачи</div>
                        <div className="text-sm text-gray-400">Сгенерировать игру змейка</div>
                      </div>
                      <div className="p-4 bg-[#1a1a1a] rounded-lg border border-[#2a2a2a]">
                        <div className="font-semibold mb-1">☁️ Сложные проекты</div>
                        <div className="text-sm text-gray-400">Создать облачное хранилище</div>
                      </div>
                      <div className="p-4 bg-[#1a1a1a] rounded-lg border border-[#2a2a2a]">
                        <div className="font-semibold mb-1">💻 Разработка</div>
                        <div className="text-sm text-gray-400">Разработать IDE с нуля</div>
                      </div>
                      <div className="p-4 bg-[#1a1a1a] rounded-lg border border-[#2a2a2a]">
                        <div className="font-semibold mb-1">⚡ Оптимизация</div>
                        <div className="text-sm text-gray-400">Модуль для оптимизации LLM</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  messages.map((message) => (
                    <div
                      key={message.id}
                      id={`message-${message.id}`}
                      className={`flex gap-4 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      {message.role === 'assistant' && (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                          <span className="text-sm">AI</span>
                        </div>
                      )}
                      <div
                        className={`max-w-3xl rounded-2xl px-5 py-4 ${
                          message.role === 'user'
                            ? 'bg-[#1f2236] text-white'
                            : message.status === 'error'
                            ? 'bg-red-900/20 border border-red-500/50'
                            : 'bg-[#0f111b] border border-[#1f2236]'
                        }`}
                      >
                        {message.role === 'user' ? (
                          <div className="whitespace-pre-wrap">{message.content}</div>
                        ) : (
                          <div>
                            {message.status === 'streaming' && (
                              <div className="flex items-center gap-2 text-gray-400">
                                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                                <span>Выполняется...</span>
                              </div>
                            )}
                            {message.status === 'completed' && (
                              <div className="space-y-3">
                                {message.subtasks && message.subtasks.length > 0 && (
                                  <div className="text-sm">
                                    <div className="text-gray-400 mb-2">Выполненные шаги:</div>
                                    <div className="space-y-1">
                                      {message.subtasks.map((st, idx) => (
                                        <div key={idx} className="flex items-center gap-2 text-gray-300">
                                          <span className="text-green-500">✓</span>
                                          <span>{st.subtask}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {message.result?.code && (
                                  <div>
                                    <div className="flex items-center justify-between mb-2">
                                      <span className="text-sm font-semibold">Сгенерированный код:</span>
                                      <button
                                        onClick={() => downloadCode(message.result.code, 'generated_code.py')}
                                        className="text-xs px-3 py-1 bg-blue-600 rounded hover:bg-blue-700"
                                      >
                                        Скачать
                                      </button>
                                    </div>
                                    <pre className="bg-[#0f0f0f] p-4 rounded-lg overflow-x-auto text-sm border border-[#2a2a2a]">
                                      <code>{message.result.code}</code>
                                    </pre>
                                  </div>
                                )}

                                {message.content && !message.result?.code && (
                                  <div className="prose prose-invert max-w-none">
                                    <div className="whitespace-pre-wrap text-sm markdown-content">{message.content}</div>
                                  </div>
                                )}

                                {message.result?.files && Array.isArray(message.result.files) && message.result.files.length > 0 && (
                                  <div>
                                    <div className="text-sm font-semibold mb-2">Созданные файлы:</div>
                                    <div className="space-y-2">
                                      {message.result.files.map((file: any, idx: number) => (
                                        <div
                                          key={idx}
                                          className="flex items-center justify-between p-2 bg-[#0f0f0f] rounded border border-[#2a2a2a]"
                                        >
                                          <span className="text-sm">{file.path || file.name || `Файл ${idx + 1}`}</span>
                                          {file.code && (
                                            <button
                                              onClick={() => downloadCode(file.code, file.path || file.name || `file_${idx}.py`)}
                                              className="text-xs px-2 py-1 bg-blue-600 rounded hover:bg-blue-700"
                                            >
                                              Скачать
                                            </button>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                            {message.status === 'error' && <div className="text-red-400">{message.content}</div>}
                          </div>
                        )}
                      </div>
                      {message.role === 'user' && (
                        <div className="w-8 h-8 rounded-full bg-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                          <span className="text-sm">👤</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>
          )}
        </div>

        {/* Input Area */}
        {!showSettings && (
          <div className="border-t border-[#1f2236] bg-[#131524] px-6 py-4">
            <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
              <div className="flex items-end gap-3">
                <div className="flex-1 relative">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => {
                      setInput(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder="Введите вашу задачу... (Enter для отправки, Shift+Enter для новой строки)"
                    className="w-full px-4 py-3 bg-[#0f111b] border border-[#1f2236] rounded-lg text-white placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500 max-h-[200px]"
                    rows={1}
                    disabled={isLoading}
                  />
                </div>
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
                >
                  {isLoading ? (
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Выполняется</span>
                    </div>
                  ) : (
                    'Отправить'
                  )}
                </button>
              </div>
              <div className="mt-2 text-xs text-gray-500 text-center">
                AILLM может выполнять задачи любой сложности - от простых скриптов до сложных систем
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
