import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { processBatchTasks } from '../api/client';

export function BatchPanel() {
  const [tasks, setTasks] = useState('');
  const [agentType, setAgentType] = useState('');
  const [results, setResults] = useState<any>(null);

  const batchMutation = useMutation({
    mutationFn: (data: { tasks: string[]; agent_type?: string }) =>
      processBatchTasks(data),
    onSuccess: (data) => {
      setResults(data);
    },
  });

  const handleProcess = () => {
    const taskList = tasks.split('\n').filter(t => t.trim());
    if (taskList.length === 0) return;

    batchMutation.mutate({
      tasks: taskList,
      agent_type: agentType || undefined
    });
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h2 className="text-2xl font-bold mb-4">Пакетная обработка</h2>

      <div className="mb-4">
        <label className="block text-sm mb-2">Тип агента (опционально)</label>
        <input
          type="text"
          value={agentType}
          onChange={(e) => setAgentType(e.target.value)}
          placeholder="code_writer, research, etc."
          className="w-full px-4 py-2 bg-gray-800 rounded text-white mb-4"
        />

        <label className="block text-sm mb-2">Задачи (по одной на строку)</label>
        <textarea
          value={tasks}
          onChange={(e) => setTasks(e.target.value)}
          placeholder="Задача 1&#10;Задача 2&#10;Задача 3"
          className="w-full px-4 py-2 bg-gray-800 rounded text-white mb-2"
          rows={10}
        />
        <button
          onClick={handleProcess}
          disabled={batchMutation.isPending || !tasks.trim()}
          className="px-6 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {batchMutation.isPending ? 'Обработка...' : 'Обработать пакет'}
        </button>
      </div>

      {results && (
        <div className="flex-1 overflow-y-auto">
          <h3 className="text-lg font-semibold mb-2">Результаты</h3>
          <div className="mb-4 p-4 bg-gray-800 rounded">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-sm text-gray-400">Всего</div>
                <div className="text-2xl font-bold">{results.total}</div>
              </div>
              <div>
                <div className="text-sm text-gray-400">Успешных</div>
                <div className="text-2xl font-bold text-green-500">{results.successful}</div>
              </div>
              <div>
                <div className="text-sm text-gray-400">Ошибок</div>
                <div className="text-2xl font-bold text-red-500">{results.failed}</div>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {results.results?.map((result: any, idx: number) => (
              <div
                key={idx}
                className={`p-4 rounded ${
                  result.success ? 'bg-gray-800' : 'bg-red-900/20'
                }`}
              >
                <div className="flex justify-between mb-2">
                  <span className="font-semibold">Задача {idx + 1}</span>
                  <span
                    className={`px-2 py-1 rounded text-sm ${
                      result.success
                        ? 'bg-green-600 text-white'
                        : 'bg-red-600 text-white'
                    }`}
                  >
                    {result.success ? 'Успешно' : 'Ошибка'}
                  </span>
                </div>
                <div className="text-sm text-gray-400 mb-2">
                  {result.task?.task || 'N/A'}
                </div>
                {result.error && (
                  <div className="text-sm text-red-400">{result.error}</div>
                )}
                {result.result && (
                  <pre className="text-xs bg-gray-900 p-2 rounded overflow-x-auto max-h-40">
                    {JSON.stringify(result.result, null, 2).substring(0, 500)}
                    {JSON.stringify(result.result, null, 2).length > 500 && '...'}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

