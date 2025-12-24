import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { UnifiedChat } from './UnifiedChat';
import { IDE } from './IDE';
import { ToolsPanel } from './ToolsPanel';
import { ProjectIndexer } from './ProjectIndexer';
import { MonitoringPanel } from './MonitoringPanel';
import { MetricsPanel } from './MetricsPanel';
import { LearningDashboard } from './LearningDashboard';
import SettingsPanel from './SettingsPanel';
import { getStatus } from '../api/client';
import { useExecutionInfo } from '../state/executionContext';
import {
  MessageSquare, Code2, Terminal, Database, Activity, BarChart3, 
  GraduationCap, Settings, Bot, Brain, Wrench
} from 'lucide-react';
import { UroborosLogo } from './icons/UroborosLogo';

export function MainLayout() {
  const [activeTab, setActiveTab] = useState<
    'chat' | 'ide' | 'tools' | 'indexer' | 'monitoring' | 'metrics' | 'learning' | 'settings'
  >('chat');

  const { executionInfo } = useExecutionInfo();
  const { data: statusData, isLoading: statusLoading, error: statusError } = useQuery({
    queryKey: ['backend-status'],
    queryFn: getStatus,
    refetchInterval: 10000,
    retry: 1,
  });

  // Определяем статус бэкенда более точно
  const backendStatus = (() => {
    if (statusLoading) {
      return { label: 'Проверка...', color: 'bg-yellow-400', details: null };
    }
    
    // Проверяем ошибку запроса
    if (statusError) {
      const errorMsg = statusData?.error || 'Не удалось подключиться к серверу';
      const errorType = statusData?.error_type;
      let details = null;
      
      if (errorType === 'port_in_use') {
        details = 'Порт 8000 занят. Остановите другой процесс или измените порт.';
      } else if (errorType === 'connection_refused') {
        details = 'Backend не запущен или недоступен.';
      } else if (errorType === 'timeout') {
        details = 'Таймаут подключения. Проверьте, что backend запущен.';
      }
      
      return { label: 'Backend: недоступен', color: 'bg-red-500', details, error: errorMsg };
    }
    
    // Проверяем данные ответа
    if (!statusData) {
      return { label: 'Backend: недоступен', color: 'bg-red-500', details: 'Нет данных о статусе' };
    }
    
    // Проверяем статус из ответа
    const status = statusData.status;
    if (status === 'ok') {
      const warnings: string[] = [];
      
      // Проверяем компоненты
      if (statusData.components) {
        const missing = Object.entries(statusData.components)
          .filter(([_, available]) => !available)
          .map(([name]) => name);
        if (missing.length > 0) {
          warnings.push(`Недоступны: ${missing.join(', ')}`);
        }
      }
      
      return { 
        label: 'Backend: OK', 
        color: 'bg-green-500', 
        details: warnings.length > 0 ? warnings.join('; ') : null 
      };
    } else if (status === 'не_инициализирован' || status === 'недоступен') {
      return { 
        label: 'Backend: недоступен', 
        color: 'bg-red-500', 
        details: statusData.error || 'Движок не инициализирован' 
      };
    } else {
      return { label: `Backend: ${status}`, color: 'bg-yellow-500', details: statusData.error };
    }
  })();

  return (
    <div className="flex flex-col h-screen bg-[#0f111b] text-white">
      {/* Header */}
      <header className="bg-gradient-to-r from-[#131524] to-[#1a1d2e] px-6 py-3 border-b border-[#1f2236] flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
            <UroborosLogo size={32} className="drop-shadow-lg" />
            <span className="bg-gradient-to-r from-blue-400 via-purple-400 to-violet-400 bg-clip-text text-transparent">AILLM</span>
          </h1>
          <span className="text-xs text-gray-500">|</span>
          <span className="text-xs text-gray-400">Автономные интеллектуальные LLM агенты</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {executionInfo && (
            <>
              {executionInfo.agent && (
                <span className="px-2.5 py-1 bg-blue-600/30 border border-blue-500/30 text-blue-300 rounded-lg text-[11px] font-medium backdrop-blur-sm flex items-center gap-1">
                  <Bot size={12} strokeWidth={1.5} /> {executionInfo.agent}
                </span>
              )}
              {executionInfo.models && executionInfo.models.length > 0 && (
                <span className="px-2.5 py-1 bg-purple-600/30 border border-purple-500/30 text-purple-300 rounded-lg text-[11px] font-medium backdrop-blur-sm flex items-center gap-1">
                  <Brain size={12} strokeWidth={1.5} /> {executionInfo.models.slice(0, 2).join(', ')}
                  {executionInfo.models.length > 2 && '...'}
                </span>
              )}
              {(executionInfo.agent || (executionInfo.models && executionInfo.models.length > 0)) && (
                <span className="text-gray-600">|</span>
              )}
            </>
          )}
          <div className="flex items-center gap-2 text-gray-300 group relative">
            <span className={`w-2.5 h-2.5 rounded-full ${backendStatus.color} shadow-lg`} />
            <span className="cursor-help text-xs font-medium" title={backendStatus.details || backendStatus.error || backendStatus.label}>
              {backendStatus.label}
            </span>
            {backendStatus.details && (
              <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg text-xs text-gray-300 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 backdrop-blur-sm">
                {backendStatus.details}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex border-b border-[#1f2236] overflow-x-auto bg-[#131524]">
        <button
          onClick={() => setActiveTab('chat')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'chat' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <MessageSquare size={16} strokeWidth={1.5} />
          <span>Чат</span>
        </button>
        <button
          onClick={() => setActiveTab('ide')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'ide' 
              ? 'bg-gradient-to-r from-green-600 to-teal-600 text-white shadow-lg shadow-green-600/30 border-b-2 border-green-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <Code2 size={16} strokeWidth={1.5} />
          <span>IDE</span>
        </button>
        <button
          onClick={() => setActiveTab('tools')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'tools' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <Wrench size={16} strokeWidth={1.5} />
          <span>Инструменты</span>
        </button>
        <button
          onClick={() => setActiveTab('indexer')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'indexer' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <Database size={16} strokeWidth={1.5} />
          <span>Индексация</span>
        </button>
        <button
          onClick={() => setActiveTab('monitoring')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'monitoring' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <Activity size={16} strokeWidth={1.5} />
          <span>Мониторинг</span>
        </button>
        <button
          onClick={() => setActiveTab('metrics')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'metrics' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <BarChart3 size={16} strokeWidth={1.5} />
          <span>Метрики</span>
        </button>
        <button
          onClick={() => setActiveTab('learning')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'learning' 
              ? 'bg-gradient-to-r from-purple-600 to-purple-700 text-white shadow-lg shadow-purple-600/30 border-b-2 border-purple-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <GraduationCap size={16} strokeWidth={1.5} />
          <span>Обучение</span>
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className={`px-5 py-3 whitespace-nowrap font-medium transition-all duration-200 flex items-center gap-2 ${
            activeTab === 'settings' 
              ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-600/30 border-b-2 border-blue-500' 
              : 'text-gray-400 hover:text-white hover:bg-[#1f2236]'
          }`}
        >
          <Settings size={16} strokeWidth={1.5} />
          <span>Настройки</span>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'chat' && <UnifiedChat />}
        {activeTab === 'ide' && <IDE />}
        {activeTab === 'tools' && <ToolsPanel />}
        {activeTab === 'indexer' && <ProjectIndexer />}
        {activeTab === 'monitoring' && <MonitoringPanel />}
        {activeTab === 'metrics' && <MetricsPanel />}
        {activeTab === 'learning' && <LearningDashboard />}
        {activeTab === 'settings' && <SettingsPanel />}
      </div>
    </div>
  );
}

