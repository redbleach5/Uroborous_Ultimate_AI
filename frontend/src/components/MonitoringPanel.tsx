import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStatus, getMetrics } from '../api/client';

export function MonitoringPanel() {
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: 5000
  });

  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: getMetrics,
    refetchInterval: 5000
  });

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <span className="text-3xl">📊</span>
        <h2 className="text-3xl font-bold text-gray-100">Мониторинг системы</h2>
      </div>

      {/* Status */}
      <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
        <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
          <span>⚙️</span>
          <span>Статус движка</span>
        </h3>
        <pre className="text-sm overflow-x-auto bg-[#0a0a0f] p-4 rounded-lg border-2 border-[#1a1d2e] text-gray-200 font-mono">
          {JSON.stringify(status, null, 2)}
        </pre>
      </div>

      {/* Metrics */}
      <div className="bg-gradient-to-br from-[#1a1d2e] to-[#0f111b] p-6 rounded-xl border border-[#2a2f46] shadow-lg">
        <h3 className="text-lg font-semibold mb-4 text-gray-100 flex items-center gap-2">
          <span>📈</span>
          <span>Метрики</span>
        </h3>
        <pre className="text-sm overflow-x-auto bg-[#0a0a0f] p-4 rounded-lg border-2 border-[#1a1d2e] text-gray-200 font-mono">
          {JSON.stringify(metrics, null, 2)}
        </pre>
      </div>
    </div>
  );
}

