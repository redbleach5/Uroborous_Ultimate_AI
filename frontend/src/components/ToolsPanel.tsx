import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { listTools, executeTool } from '../api/client';
import { Wrench, FileText, CircleX, Zap, ClipboardList, Clock, Loader2 } from 'lucide-react';

export function ToolsPanel() {
  const [selectedTool, setSelectedTool] = useState<string>('');
  const [toolInput, setToolInput] = useState('{}');
  const [results, setResults] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: tools } = useQuery({
    queryKey: ['tools'],
    queryFn: listTools,
  });

  const executeMutation = useMutation({
    mutationFn: ({ tool, input }: { tool: string; input: any }) =>
      executeTool({ tool_name: tool, input }),
    onSuccess: (data) => {
      setResults([{ tool: selectedTool, input: toolInput, result: data, timestamp: new Date() }, ...results]);
    },
  });

  const handleExecute = () => {
    if (!selectedTool) return;
    setError(null); // Clear previous errors
    try {
      const input = JSON.parse(toolInput);
      executeMutation.mutate({ tool: selectedTool, input });
    } catch (e) {
      setError('Неверный JSON формат. Убедитесь, что JSON корректный.');
    }
  };

  return (
    <div className="flex flex-col h-full p-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Wrench size={32} strokeWidth={1.5} className="text-blue-400" />
        <h2 className="text-3xl font-bold text-gray-100">Инструменты</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6 max-h-60 overflow-y-auto">
        {tools?.tools && Object.entries(tools.tools).map(([name, tool]: [string, any]) => (
          <button
            key={name}
            onClick={() => setSelectedTool(name)}
            className={`p-4 rounded-xl border transition-all duration-200 text-left ${
              selectedTool === name
                ? 'border-blue-500/60 bg-gradient-to-br from-blue-600/20 to-blue-700/10 shadow-lg shadow-blue-500/20 ring-2 ring-blue-500/30 scale-105'
                : 'border-[#2a2f46] bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] hover:border-[#3a3f56] hover:bg-[#1a1d2e] hover:scale-102'
            }`}
          >
            <div className="text-sm font-semibold text-gray-100 mb-1">{name}</div>
            <div className="text-xs text-gray-400 truncate leading-relaxed">{tool.description}</div>
          </button>
        ))}
      </div>

      {selectedTool && (
        <div className="mb-6 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
          <label className="block text-sm font-semibold mb-3 text-gray-100 flex items-center gap-2">
            <FileText size={16} strokeWidth={1.5} />
            <span>Входные данные инструмента (JSON)</span>
          </label>
          <textarea
            value={toolInput}
            onChange={(e) => {
              setToolInput(e.target.value);
              setError(null); // Clear error when user types
            }}
            className="w-full px-5 py-3 bg-[#0a0a0f] border-2 border-[#1a1d2e] rounded-xl text-gray-200 font-mono text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all duration-200"
            rows={6}
          />
          {error && (
            <div className="mt-3 px-4 py-3 bg-red-900/30 border-2 border-red-500/60 rounded-xl text-red-300 text-sm flex items-start gap-2">
              <CircleX size={18} strokeWidth={1.5} className="flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
          {executeMutation.isError && (
            <div className="mt-3 px-4 py-3 bg-red-900/30 border-2 border-red-500/60 rounded-xl text-red-300 text-sm flex items-start gap-2">
              <CircleX size={18} strokeWidth={1.5} className="flex-shrink-0 mt-0.5" />
              <span>Ошибка выполнения: {executeMutation.error instanceof Error ? executeMutation.error.message : String(executeMutation.error)}</span>
            </div>
          )}
          <button
            onClick={handleExecute}
            disabled={executeMutation.isPending}
            className="mt-4 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-all duration-200 shadow-lg shadow-blue-600/30 flex items-center gap-2"
          >
            {executeMutation.isPending ? (
              <>
                <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                <span>Выполнение...</span>
              </>
            ) : (
              <>
                <Zap size={16} strokeWidth={1.5} />
                <span>Выполнить инструмент</span>
              </>
            )}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
          <ClipboardList size={18} strokeWidth={1.5} />
          <span>Результаты</span>
        </h3>
        {results.length === 0 ? (
          <div className="text-center py-12 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-xl border border-[#2a2f46]">
            <p className="text-gray-400 text-lg">Инструменты еще не выполнялись</p>
          </div>
        ) : (
          <div className="space-y-4">
            {results.map((item, idx) => (
              <div key={idx} className="p-5 bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] rounded-xl border border-[#2a2f46] shadow-lg hover:border-[#3a3f56] transition-all duration-200">
                <div className="text-sm text-gray-300 mb-3 flex items-center gap-2 font-medium">
                  <Clock size={14} strokeWidth={1.5} />
                  <span>{item.timestamp.toLocaleString('ru-RU')}</span>
                  <span className="text-gray-500">|</span>
                  <span className="text-blue-400">{item.tool}</span>
                </div>
                <pre className="text-sm bg-[#0a0a0f] p-4 rounded-lg border-2 border-[#1a1d2e] overflow-x-auto text-gray-200 font-mono">
                  {JSON.stringify(item.result, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

