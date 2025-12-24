import { useEffect, useState, useCallback } from 'react';
import { Brain, AlertTriangle, ChevronDown, Bot, Loader2 } from 'lucide-react';

interface AgentStats {
  tasks: number;
  success_rate: number;
  avg_quality: number;
}

interface LearningProgress {
  total_experience: number;
  success_rate: number;
  level: string;
  level_description: string;
  quality: string;
  agents_learning: number;
  total_successful: number;
  total_retries: number;
}

interface LearningData {
  success: boolean;
  progress?: LearningProgress;
  agents_summary?: Record<string, AgentStats>;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function LearningProgress() {
  const [data, setData] = useState<LearningData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const fetchLearningProgress = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/learning/progress`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch learning progress');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLearningProgress();
    
    // Обновляем каждые 30 секунд
    const interval = setInterval(fetchLearningProgress, 30000);
    return () => clearInterval(interval);
  }, [fetchLearningProgress]);

  if (loading) {
    return (
      <div className="p-4 bg-gradient-to-br from-indigo-900/30 to-purple-900/20 border border-indigo-500/30 rounded-xl">
        <div className="flex items-center gap-2 text-indigo-300">
          <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
          <span className="text-sm">Загрузка статистики обучения...</span>
        </div>
      </div>
    );
  }

  if (error || !data?.success || !data.progress) {
    return (
      <div className="p-4 bg-gradient-to-br from-red-900/20 to-orange-900/10 border border-red-500/20 rounded-xl">
        <div className="flex items-center gap-2 text-red-300">
          <AlertTriangle size={16} strokeWidth={1.5} />
          <span className="text-sm">{error || 'Нет данных об обучении'}</span>
        </div>
      </div>
    );
  }

  const { progress, agents_summary } = data;

  // Определяем цвет уровня
  const getLevelColor = (level: string) => {
    switch (level) {
      case 'экспертный': return 'from-purple-600 to-pink-500';
      case 'продвинутый': return 'from-blue-500 to-indigo-500';
      case 'базовый': return 'from-green-500 to-teal-500';
      default: return 'from-gray-500 to-slate-500';
    }
  };

  // Определяем цвет качества
  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'отличное': return 'text-green-400';
      case 'хорошее': return 'text-blue-400';
      case 'среднее': return 'text-yellow-400';
      default: return 'text-red-400';
    }
  };

  return (
    <div className="p-4 bg-gradient-to-br from-indigo-900/30 to-purple-900/20 border border-indigo-500/30 rounded-xl shadow-lg">
      {/* Header */}
      <div 
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <Brain size={24} strokeWidth={1.5} className="text-indigo-400" />
          <div>
            <h3 className="text-sm font-semibold text-indigo-200">Система обучения</h3>
            <p className="text-xs text-indigo-400">{progress.level_description}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Level badge */}
          <div className={`px-3 py-1 rounded-full text-xs font-bold text-white bg-gradient-to-r ${getLevelColor(progress.level)}`}>
            {progress.level.toUpperCase()}
          </div>
          
          {/* Expand icon */}
          <ChevronDown size={16} strokeWidth={1.5} className={`text-indigo-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
        </div>
      </div>

      {/* Main stats */}
      <div className="mt-4 grid grid-cols-4 gap-3">
        <div className="text-center p-2 bg-black/20 rounded-lg">
          <div className="text-xl font-bold text-white">{progress.total_experience}</div>
          <div className="text-xs text-indigo-300">Задач обработано</div>
        </div>
        <div className="text-center p-2 bg-black/20 rounded-lg">
          <div className={`text-xl font-bold ${getQualityColor(progress.quality)}`}>
            {(progress.success_rate * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-indigo-300">Success Rate</div>
        </div>
        <div className="text-center p-2 bg-black/20 rounded-lg">
          <div className="text-xl font-bold text-green-400">{progress.total_successful}</div>
          <div className="text-xs text-indigo-300">Успешных</div>
        </div>
        <div className="text-center p-2 bg-black/20 rounded-lg">
          <div className="text-xl font-bold text-yellow-400">{progress.total_retries}</div>
          <div className="text-xs text-indigo-300">Исправлений</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-4">
        <div className="flex justify-between text-xs text-indigo-300 mb-1">
          <span>Прогресс обучения</span>
          <span>{Math.min(progress.total_experience / 200 * 100, 100).toFixed(0)}%</span>
        </div>
        <div className="h-2 bg-black/30 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
            style={{ width: `${Math.min(progress.total_experience / 200 * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Expanded: Agent details */}
      {isExpanded && agents_summary && Object.keys(agents_summary).length > 0 && (
        <div className="mt-4 pt-4 border-t border-indigo-500/20">
          <h4 className="text-xs font-semibold text-indigo-300 mb-3">Статистика по агентам</h4>
          <div className="space-y-2">
            {Object.entries(agents_summary).map(([name, stats]) => (
              <div key={name} className="flex items-center justify-between p-2 bg-black/20 rounded-lg">
                <div className="flex items-center gap-2">
                  <Bot size={14} strokeWidth={1.5} className="text-indigo-300" />
                  <span className="text-sm text-white">{name}</span>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-indigo-300">
                    {stats.tasks} задач
                  </span>
                  <span className={stats.success_rate >= 0.8 ? 'text-green-400' : stats.success_rate >= 0.6 ? 'text-yellow-400' : 'text-red-400'}>
                    {(stats.success_rate * 100).toFixed(0)}% успех
                  </span>
                  <span className="text-purple-400">
                    {stats.avg_quality.toFixed(0)} качество
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quality indicator */}
      <div className="mt-4 flex items-center justify-center gap-2 text-xs">
        <span className="text-indigo-300">Качество обучения:</span>
        <span className={`font-semibold ${getQualityColor(progress.quality)}`}>
          {progress.quality}
        </span>
      </div>
    </div>
  );
}

