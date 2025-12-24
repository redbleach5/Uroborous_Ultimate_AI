import React, { useState, useEffect, useRef } from 'react';
import { executeTask } from '../api/client';

interface SubtaskProgress {
  subtask: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: any;
  error?: string;
}

interface TaskExecution {
  id: string;
  task: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress: number;
  subtasks?: SubtaskProgress[];
  result?: any;
  error?: string;
  startTime: Date;
  endTime?: Date;
}

export function EnhancedTaskPanel() {
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [currentExecution, setCurrentExecution] = useState<TaskExecution | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleExecute = async () => {
    if (!task.trim()) return;

    const executionId = `task-${Date.now()}`;
    const newExecution: TaskExecution = {
      id: executionId,
      task: task.trim(),
      status: 'running',
      progress: 0,
      startTime: new Date(),
    };

    setCurrentExecution(newExecution);
    setExecutions([newExecution, ...executions]);
    setLoading(true);
    setTask('');

    // Create abort controller for cancellation
    abortControllerRef.current = new AbortController();

    try {
      const response = await executeTask(
        {
          task: newExecution.task,
          agent_type: undefined, // Let orchestrator decide
          context: {}
        },
        abortControllerRef.current.signal
      );

      // Update execution with result
      const updatedExecution: TaskExecution = {
        ...newExecution,
        status: response.success ? 'completed' : 'error',
        progress: 100,
        result: response.result,
        error: response.error,
        endTime: new Date(),
        subtasks: response.subtasks?.map((st: string, idx: number) => ({
          subtask: st,
          status: 'completed' as const,
        })) || [],
      };

      setCurrentExecution(null);
      setExecutions(prev => prev.map(e => e.id === executionId ? updatedExecution : e));
    } catch (error: any) {
      if (error.name === 'AbortError') {
        const cancelledExecution: TaskExecution = {
          ...newExecution,
          status: 'error',
          error: 'Задача отменена пользователем',
          endTime: new Date(),
        };
        setExecutions(prev => prev.map(e => e.id === executionId ? cancelledExecution : e));
      } else {
        const errorExecution: TaskExecution = {
          ...newExecution,
          status: 'error',
          error: error.message || 'Ошибка выполнения задачи',
          endTime: new Date(),
        };
        setExecutions(prev => prev.map(e => e.id === executionId ? errorExecution : e));
      }
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setLoading(false);
    }
  };

  const formatDuration = (start: Date, end?: Date) => {
    const duration = (end || new Date()).getTime() - start.getTime();
    const seconds = Math.floor(duration / 1000);
    if (seconds < 60) return `${seconds}с`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}м ${seconds % 60}с`;
  };

  const downloadCode = (code: string, filename: string) => {
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

  return (
    <div className="flex flex-col h-full p-4 space-y-4">
      {/* Task Input */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h2 className="text-xl font-bold mb-4">Выполнение задач</h2>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Введите вашу задачу (любой сложности)...&#10;Примеры:&#10;- сгенерировать игру змейка&#10;- создать облачное хранилище&#10;- разработать IDE с нуля&#10;- модуль для оптимизации локальных LLM"
          className="w-full px-4 py-3 bg-gray-900 rounded text-white mb-3 resize-none"
          rows={6}
          disabled={loading}
        />
        <div className="flex gap-2">
          <button
            onClick={handleExecute}
            disabled={loading || !task.trim()}
            className="px-6 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex-1"
          >
            {loading ? 'Выполнение...' : 'Выполнить задачу'}
          </button>
          {loading && (
            <button
              onClick={handleCancel}
              className="px-6 py-2 bg-red-600 rounded hover:bg-red-700"
            >
              Отменить
            </button>
          )}
        </div>
        {loading && currentExecution && (
          <div className="mt-4">
            <div className="flex justify-between text-sm text-gray-400 mb-2">
              <span>Выполняется: {currentExecution.task.substring(0, 50)}...</span>
              <span>{formatDuration(currentExecution.startTime)}</span>
            </div>
            <div className="w-full bg-gray-900 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${currentExecution.progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Executions List */}
      <div className="flex-1 overflow-y-auto space-y-4">
        <h3 className="text-lg font-semibold">История выполнения</h3>
        {executions.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            <p>Задачи еще не выполнялись</p>
            <p className="text-sm mt-2">Введите задачу выше и нажмите "Выполнить"</p>
          </div>
        ) : (
          executions.map((execution) => (
            <div
              key={execution.id}
              className={`bg-gray-800 rounded-lg p-4 ${
                execution.status === 'error' ? 'border-l-4 border-red-500' :
                execution.status === 'completed' ? 'border-l-4 border-green-500' :
                'border-l-4 border-blue-500'
              }`}
            >
              {/* Header */}
              <div className="flex justify-between items-start mb-3">
                <div className="flex-1">
                  <div className="font-semibold text-lg mb-1">{execution.task}</div>
                  <div className="flex items-center gap-4 text-sm text-gray-400">
                    <span>{execution.startTime.toLocaleString()}</span>
                    {execution.endTime && (
                      <span>Длительность: {formatDuration(execution.startTime, execution.endTime)}</span>
                    )}
                    <span
                      className={`px-2 py-1 rounded ${
                        execution.status === 'completed'
                          ? 'bg-green-600 text-white'
                          : execution.status === 'error'
                          ? 'bg-red-600 text-white'
                          : 'bg-blue-600 text-white'
                      }`}
                    >
                      {execution.status === 'completed' ? 'Завершено' :
                       execution.status === 'error' ? 'Ошибка' :
                       'Выполняется'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Subtasks */}
              {execution.subtasks && execution.subtasks.length > 0 && (
                <div className="mb-3">
                  <div className="text-sm font-semibold mb-2">Подзадачи:</div>
                  <div className="space-y-1">
                    {execution.subtasks.map((subtask, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2 text-sm bg-gray-900 px-2 py-1 rounded"
                      >
                        <span
                          className={`w-2 h-2 rounded-full ${
                            subtask.status === 'completed'
                              ? 'bg-green-500'
                              : subtask.status === 'error'
                              ? 'bg-red-500'
                              : subtask.status === 'running'
                              ? 'bg-blue-500 animate-pulse'
                              : 'bg-gray-500'
                          }`}
                        />
                        <span className="flex-1">{subtask.subtask}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Result */}
              {execution.status === 'completed' && execution.result && (
                <div className="mt-3">
                  {execution.result.code && (
                    <div className="mb-3">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-sm font-semibold">Сгенерированный код:</span>
                        <button
                          onClick={() => downloadCode(execution.result.code, 'generated_code.py')}
                          className="px-3 py-1 bg-green-600 rounded hover:bg-green-700 text-sm"
                        >
                          Скачать код
                        </button>
                      </div>
                      <pre className="text-xs bg-gray-900 p-3 rounded overflow-x-auto max-h-60">
                        {execution.result.code.substring(0, 2000)}
                        {execution.result.code.length > 2000 && (
                          <span className="text-gray-400">... (еще {execution.result.code.length - 2000} символов)</span>
                        )}
                      </pre>
                    </div>
                  )}
                  {execution.result.files && Array.isArray(execution.result.files) && (
                    <div className="mb-3">
                      <div className="text-sm font-semibold mb-2">Созданные файлы:</div>
                      <div className="space-y-1">
                        {execution.result.files.map((file: any, idx: number) => (
                          <div key={idx} className="text-sm bg-gray-900 px-2 py-1 rounded">
                            {file.path || file.name || `Файл ${idx + 1}`}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {!execution.result.code && !execution.result.files && (
                    <pre className="text-xs bg-gray-900 p-3 rounded overflow-x-auto max-h-60">
                      {JSON.stringify(execution.result, null, 2).substring(0, 1000)}
                      {JSON.stringify(execution.result, null, 2).length > 1000 && '...'}
                    </pre>
                  )}
                </div>
              )}

              {/* Error */}
              {execution.status === 'error' && execution.error && (
                <div className="mt-3 p-3 bg-red-900/20 rounded text-red-400 text-sm">
                  {execution.error}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

