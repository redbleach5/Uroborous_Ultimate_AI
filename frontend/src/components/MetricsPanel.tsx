import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMetricsStats } from '../api/client';
import { BarChart3, ClipboardList, Bot, Wrench, Brain, Loader2 } from 'lucide-react';

export function MetricsPanel() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['metrics'],
    queryFn: getMetricsStats,
    refetchInterval: 10000
  });

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 size={48} strokeWidth={1.5} className="animate-spin mx-auto mb-4 text-blue-400" />
          <p className="text-gray-400 text-lg">Загрузка метрик...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <BarChart3 size={32} strokeWidth={1.5} className="text-blue-400" />
        <h2 className="text-3xl font-bold text-gray-100">Метрики производительности</h2>
      </div>

      {/* Tasks Overview */}
      <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
        <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
          <ClipboardList size={18} strokeWidth={1.5} />
          <span>Задачи</span>
        </h3>
        {stats?.tasks && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46]">
              <div className="text-sm text-gray-400 mb-2">Всего</div>
              <div className="text-3xl font-bold text-gray-100">{stats.tasks.total || 0}</div>
            </div>
            <div className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46]">
              <div className="text-sm text-gray-400 mb-2">Успешных</div>
              <div className="text-3xl font-bold text-green-400">{stats.tasks.success || 0}</div>
            </div>
            <div className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46]">
              <div className="text-sm text-gray-400 mb-2">Успешность</div>
              <div className="text-3xl font-bold text-blue-400">
                {((stats.tasks.success_rate || 0) * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Agents Stats */}
      {stats?.agents && Object.keys(stats.agents).length > 0 && (
        <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
          <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
            <Bot size={18} strokeWidth={1.5} />
            <span>Агенты</span>
          </h3>
          <div className="space-y-3">
            {Object.entries(stats.agents).map(([name, agentStats]: [string, any]) => (
              <div key={name} className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors">
                <div className="font-semibold text-gray-100 mb-3 flex items-center gap-2">
                  <Bot size={16} strokeWidth={1.5} />
                  <span>{name}</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Выполнений</span>
                    <span className="text-gray-200 font-semibold">{agentStats.total_executions || 0}</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Успешность</span>
                    <span className="text-green-400 font-semibold">{((agentStats.success_rate || 0) * 100).toFixed(1)}%</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Среднее время</span>
                    <span className="text-gray-200 font-semibold">{(agentStats.avg_duration || 0).toFixed(2)}s</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Токенов</span>
                    <span className="text-blue-400 font-semibold">{agentStats.total_tokens || 0}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tools Stats */}
      {stats?.tools && Object.keys(stats.tools).length > 0 && (
        <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
          <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
            <Wrench size={18} strokeWidth={1.5} />
            <span>Инструменты</span>
          </h3>
          <div className="space-y-3">
            {Object.entries(stats.tools).map(([name, toolStats]: [string, any]) => (
              <div key={name} className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors">
                <div className="font-semibold text-gray-100 mb-3 flex items-center gap-2">
                  <Wrench size={16} strokeWidth={1.5} />
                  <span>{name}</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Выполнений</span>
                    <span className="text-gray-200 font-semibold">{toolStats.total_executions || 0}</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Успешность</span>
                    <span className="text-green-400 font-semibold">{((toolStats.success_rate || 0) * 100).toFixed(1)}%</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Среднее время</span>
                    <span className="text-gray-200 font-semibold">{(toolStats.avg_duration || 0).toFixed(2)}s</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* LLM Stats */}
      {stats?.llm && Object.keys(stats.llm).length > 0 && (
        <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
          <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
            <Brain size={18} strokeWidth={1.5} />
            <span>LLM провайдеры</span>
          </h3>
          <div className="space-y-3">
            {Object.entries(stats.llm).map(([key, llmStats]: [string, any]) => (
              <div key={key} className="p-4 bg-[#0f111b]/60 rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors">
                <div className="font-semibold text-gray-100 mb-3 flex items-center gap-2">
                  <Brain size={16} strokeWidth={1.5} />
                  <span>{key}</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Запросов</span>
                    <span className="text-gray-200 font-semibold">{llmStats.total_requests || 0}</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Успешность</span>
                    <span className="text-green-400 font-semibold">{((llmStats.success_rate || 0) * 100).toFixed(1)}%</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Среднее время</span>
                    <span className="text-gray-200 font-semibold">{(llmStats.avg_duration || 0).toFixed(2)}s</span>
                  </div>
                  <div className="p-2 bg-[#0a0a0f] rounded-lg">
                    <span className="text-gray-400 block mb-1">Токенов</span>
                    <span className="text-blue-400 font-semibold">{llmStats.total_tokens || 0}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

