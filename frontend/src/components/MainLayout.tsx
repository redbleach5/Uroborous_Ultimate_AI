import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { UnifiedChat } from './UnifiedChat';
import { IDE } from './IDE';
import { ToolsPanel } from './ToolsPanel';
import { MonitoringPanel } from './MonitoringPanel';
import { MetricsPanel } from './MetricsPanel';
import { LearningDashboard } from './LearningDashboard';
import SettingsPanel from './SettingsPanel';
import { getStatus } from '../api/client';
import { useExecutionInfo } from '../state/executionContext';
import {
  MessageSquare, Code2, Activity, BarChart3, 
  GraduationCap, Settings, Bot, Brain, Wrench, AlertCircle, X, RefreshCw
} from 'lucide-react';
import { UroborosLogo } from './icons/UroborosLogo';

export function MainLayout() {
  const [activeTab, setActiveTab] = useState<
    'chat' | 'ide' | 'tools' | 'monitoring' | 'metrics' | 'learning' | 'settings'
  >(() => {
    const saved = localStorage.getItem('activeTab');
    // Redirect old 'indexer' tab to 'ide' (indexing is now in IDE)
    if (saved === 'indexer') return 'ide';
    if (saved && ['chat', 'ide', 'tools', 'monitoring', 'metrics', 'learning', 'settings'].includes(saved)) {
      return saved as 'chat' | 'ide' | 'tools' | 'monitoring' | 'metrics' | 'learning' | 'settings';
    }
    return 'chat';
  });
  
  const [showErrorModal, setShowErrorModal] = useState(false);

  // Save active tab to localStorage
  useEffect(() => {
    localStorage.setItem('activeTab', activeTab);
  }, [activeTab]);

  const { executionInfo } = useExecutionInfo();
  const { data: statusData, isLoading: statusLoading, error: statusError, refetch: refetchStatus } = useQuery({
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
      const errorDetails = statusData?.error_details;
      const technicalInfo = statusData?.technical_info;
      
      return { 
        label: 'Backend: недоступен', 
        color: 'bg-red-500', 
        details: errorDetails,
        error: errorMsg,
        technicalInfo
      };
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
        details: statusData.error_details || 'Движок не инициализирован',
        error: statusData.error,
        technicalInfo: statusData.technical_info
      };
    } else {
      return { 
        label: `Backend: ${status}`, 
        color: 'bg-yellow-500', 
        details: statusData.error_details,
        error: statusData.error,
        technicalInfo: statusData.technical_info
      };
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
            <span className={`w-2.5 h-2.5 rounded-full ${backendStatus.color} shadow-lg ${backendStatus.color === 'bg-red-500' ? 'animate-pulse' : ''}`} />
            <span 
              className={`text-xs font-medium ${(backendStatus.details || backendStatus.error) ? 'cursor-pointer hover:underline' : ''}`}
              onClick={() => (backendStatus.details || backendStatus.error) && setShowErrorModal(true)}
              title={backendStatus.details || backendStatus.error || backendStatus.label}
            >
              {backendStatus.label}
            </span>
            {(backendStatus.details || backendStatus.error) && (
              <button 
                onClick={() => setShowErrorModal(true)}
                className="text-gray-400 hover:text-white transition-colors"
                title="Показать детали"
              >
                <AlertCircle size={14} strokeWidth={1.5} />
              </button>
            )}
            {/* Hover tooltip */}
            {(backendStatus.details || backendStatus.error) && (
              <div className="absolute right-0 top-full mt-2 w-72 p-3 bg-[#1a1d2e] border border-[#2a2f46] rounded-lg text-xs text-gray-300 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 backdrop-blur-sm">
                <div className="font-medium text-red-400 mb-1">Ошибка подключения</div>
                {backendStatus.error && <div className="mb-1">{backendStatus.error}</div>}
                {backendStatus.details && <div className="text-gray-400">{backendStatus.details}</div>}
                <div className="mt-2 text-gray-500 text-[10px]">Кликните для деталей</div>
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
      <div className="flex-1 overflow-auto">
        {activeTab === 'chat' && <UnifiedChat />}
        {activeTab === 'ide' && <IDE />}
        {activeTab === 'tools' && <ToolsPanel />}
        {activeTab === 'monitoring' && <MonitoringPanel />}
        {activeTab === 'metrics' && <MetricsPanel />}
        {activeTab === 'learning' && <LearningDashboard />}
        {activeTab === 'settings' && <SettingsPanel />}
      </div>
      
      {/* Error Modal */}
      {showErrorModal && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setShowErrorModal(false)}
        >
          <div 
            className="bg-[#1a1d2e] border border-[#2a2f46] rounded-xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-[#2a2f46] bg-gradient-to-r from-red-900/30 to-red-800/20">
              <div className="flex items-center gap-2">
                <AlertCircle size={20} strokeWidth={1.5} className="text-red-400" />
                <h3 className="font-semibold text-red-300">Backend недоступен</h3>
              </div>
              <button 
                onClick={() => setShowErrorModal(false)}
                className="text-gray-400 hover:text-white transition-colors p-1 rounded hover:bg-[#2a2f46]"
              >
                <X size={18} strokeWidth={1.5} />
              </button>
            </div>
            
            {/* Content */}
            <div className="p-4 space-y-4">
              {/* Error message */}
              {backendStatus.error && (
                <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-3">
                  <div className="text-xs text-red-400/80 uppercase tracking-wide mb-1">Ошибка</div>
                  <div className="text-sm text-red-300">{backendStatus.error}</div>
                </div>
              )}
              
              {/* Details */}
              {backendStatus.details && (
                <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Детали</div>
                  <div className="text-sm text-gray-300">{backendStatus.details}</div>
                </div>
              )}
              
              {/* Technical info for debugging */}
              {(backendStatus.technicalInfo || statusError) && (
                <div className="bg-[#0f111b] border border-[#2a2f46] rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Техническая информация</div>
                  <pre className="text-xs text-gray-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                    {backendStatus.technicalInfo || (statusError instanceof Error ? statusError.message : JSON.stringify(statusError, null, 2))}
                  </pre>
                </div>
              )}
              
              {/* Suggestions */}
              <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-3">
                <div className="text-xs text-blue-400/80 uppercase tracking-wide mb-2">Рекомендации</div>
                <ul className="text-sm text-blue-300/90 space-y-1.5">
                  <li className="flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5">•</span>
                    <span>Проверьте, что backend запущен: <code className="bg-[#0f111b] px-1.5 py-0.5 rounded text-xs">./start.sh</code></span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5">•</span>
                    <span>Проверьте логи: <code className="bg-[#0f111b] px-1.5 py-0.5 rounded text-xs">tail -f backend.log</code></span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5">•</span>
                    <span>Убедитесь, что порт 8000 не занят другим процессом</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5">•</span>
                    <span>Проверьте конфигурацию в <code className="bg-[#0f111b] px-1.5 py-0.5 rounded text-xs">backend/config/config.yaml</code></span>
                  </li>
                </ul>
              </div>
            </div>
            
            {/* Footer */}
            <div className="flex items-center justify-between p-4 border-t border-[#2a2f46] bg-[#131524]">
              <button
                onClick={() => {
                  refetchStatus();
                  setShowErrorModal(false);
                }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors"
              >
                <RefreshCw size={14} strokeWidth={1.5} />
                <span>Повторить проверку</span>
              </button>
              <button
                onClick={() => setShowErrorModal(false)}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors text-sm"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

