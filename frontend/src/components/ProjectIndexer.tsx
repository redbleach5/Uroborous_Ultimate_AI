import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { indexProject } from '../api/client';

export function ProjectIndexer() {
  const [projectPath, setProjectPath] = useState('');
  const [status, setStatus] = useState<string | null>(null);

  const indexMutation = useMutation({
    mutationFn: (path: string) => indexProject({ project_path: path }),
    onSuccess: (data) => {
      setStatus(`✓ Проиндексировано ${data.files_indexed} файлов, ${data.chunks_created} фрагментов`);
    },
    onError: (error: any) => {
      setStatus(`✗ Ошибка: ${error.message}`);
    }
  });

  const handleIndex = () => {
    if (!projectPath.trim()) return;
    setStatus('Индексация...');
    indexMutation.mutate(projectPath);
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-3xl">📚</span>
          <h3 className="text-2xl font-bold text-gray-100">Индексация проекта</h3>
        </div>
        <div className="space-y-5">
          <div>
            <label className="block text-sm font-semibold mb-3 text-gray-100 flex items-center gap-2">
              <span>📁</span>
              <span>Путь к проекту</span>
            </label>
            <input
              type="text"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              placeholder="/путь/к/проекту"
              className="w-full px-5 py-3 bg-[#0f111b] border-2 border-[#1f2236] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all duration-200"
            />
          </div>
          <button
            onClick={handleIndex}
            disabled={indexMutation.isPending || !projectPath.trim()}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-all duration-200 shadow-lg shadow-blue-600/30 flex items-center gap-2"
          >
            {indexMutation.isPending ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Индексация...</span>
              </>
            ) : (
              <>
                <span>⚡</span>
                <span>Индексировать проект</span>
              </>
            )}
          </button>
          {status && (
            <div className={`p-4 rounded-xl border-2 flex items-start gap-2 ${
              status.startsWith('✓')
                ? 'bg-green-900/30 border-green-500/60 text-green-300'
                : status.startsWith('✗')
                ? 'bg-red-900/30 border-red-500/60 text-red-300'
                : 'bg-blue-900/30 border-blue-500/60 text-blue-300'
            }`}>
              <span className="text-lg flex-shrink-0">{status.startsWith('✓') ? '✅' : status.startsWith('✗') ? '❌' : '⏳'}</span>
              <span className="text-sm font-medium">{status}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

