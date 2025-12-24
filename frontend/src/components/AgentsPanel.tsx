import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { executeTask } from '../api/client';

const AGENTS = [
  { id: 'code_writer', name: 'Генератор кода', description: 'Генерация и рефакторинг кода' },
  { id: 'react', name: 'ReAct', description: 'Интерактивное решение задач' },
  { id: 'research', name: 'Исследователь', description: 'Исследование кодовой базы и требований' },
  { id: 'data_analysis', name: 'Анализ данных', description: 'Анализ данных и создание моделей' },
  { id: 'workflow', name: 'Workflow', description: 'Управление рабочими процессами' },
  { id: 'integration', name: 'Интеграция', description: 'Интеграция с внешними сервисами' },
  { id: 'monitoring', name: 'Мониторинг', description: 'Мониторинг производительности системы' },
];

export function AgentsPanel() {
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [task, setTask] = useState('');
  const [results, setResults] = useState<any[]>([]);

  const executeMutation = useMutation({
    mutationFn: ({ agent, task }: { agent: string; task: string }) =>
      executeTask({ task, agent_type: agent }),
    onSuccess: (data) => {
      setResults([{ agent: selectedAgent, task, result: data, timestamp: new Date() }, ...results]);
      setTask('');
    },
  });

  const handleExecute = () => {
    if (!task.trim() || !selectedAgent) return;
    executeMutation.mutate({ agent: selectedAgent, task });
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h2 className="text-2xl font-bold mb-4">Агенты</h2>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {AGENTS.map((agent) => (
          <button
            key={agent.id}
            onClick={() => setSelectedAgent(agent.id)}
            className={`p-4 rounded border-2 ${
              selectedAgent === agent.id
                ? 'border-blue-500 bg-blue-900/20'
                : 'border-gray-700 bg-gray-800'
            }`}
          >
            <div className="font-semibold">{agent.name}</div>
            <div className="text-sm text-gray-400">{agent.description}</div>
          </button>
        ))}
      </div>

      {selectedAgent && (
        <div className="mb-4">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder={`Введите задачу для ${AGENTS.find(a => a.id === selectedAgent)?.name}...`}
            className="w-full px-4 py-2 bg-gray-800 rounded text-white mb-2"
            rows={3}
          />
          <button
            onClick={handleExecute}
            disabled={executeMutation.isPending || !task.trim()}
            className="px-6 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {executeMutation.isPending ? 'Выполнение...' : 'Выполнить'}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <h3 className="text-lg font-semibold mb-2">Результаты</h3>
        {results.length === 0 ? (
          <p className="text-gray-400">Задачи еще не выполнялись</p>
        ) : (
          results.map((item, idx) => (
            <div key={idx} className="mb-4 p-4 bg-gray-800 rounded">
              <div className="text-sm text-gray-400 mb-2">
                {item.timestamp.toLocaleString()} - {AGENTS.find(a => a.id === item.agent)?.name}
              </div>
              <div className="font-semibold mb-2">{item.task}</div>
              <pre className="text-sm bg-gray-900 p-2 rounded overflow-x-auto max-h-40">
                {JSON.stringify(item.result, null, 2).substring(0, 500)}
                {JSON.stringify(item.result, null, 2).length > 500 && '...'}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

