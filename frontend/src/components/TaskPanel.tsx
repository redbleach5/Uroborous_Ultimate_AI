import React, { useState } from 'react';
import { executeTask } from '../api/client';

export function TaskPanel() {
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleExecute = async () => {
    if (!task.trim()) return;

    setLoading(true);
    setError(null); // Clear previous errors

    try {
      const response = await executeTask({
        task,
        agent_type: undefined, // Let orchestrator decide
        context: {}
      });

      setResults([{ task, result: response, timestamp: new Date() }, ...results]);
      setTask('');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setError(`Ошибка выполнения задачи: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full p-4">
      <div className="mb-4">
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Введите вашу задачу..."
          className="w-full px-4 py-2 bg-gray-800 rounded text-white mb-2"
          rows={3}
        />
        <button
          onClick={handleExecute}
          disabled={loading || !task.trim()}
          className="px-6 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Выполнение...' : 'Выполнить задачу'}
        </button>
        {error && (
          <div className="mt-2 px-4 py-2 bg-red-900/50 border border-red-600 rounded text-red-200 text-sm">
            {error}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        <h2 className="text-xl font-bold mb-4">История задач</h2>
        {results.length === 0 ? (
          <p className="text-gray-400">Задачи еще не выполнялись</p>
        ) : (
          results.map((item, idx) => (
            <div key={idx} className="mb-4 p-4 bg-gray-800 rounded">
              <div className="text-sm text-gray-400 mb-2">
                {item.timestamp.toLocaleString()}
              </div>
              <div className="font-semibold mb-2">{item.task}</div>
              <pre className="text-sm bg-gray-900 p-2 rounded overflow-x-auto">
                {JSON.stringify(item.result, null, 2)}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

