/**
 * ProgressIndicator - компонент для отображения real-time прогресса выполнения задач
 */

import React from 'react';
import { Loader2, CheckCircle2, XCircle, Zap } from 'lucide-react';
import { ProgressUpdate } from '../hooks/useWebSocket';

interface ProgressIndicatorProps {
  progress: ProgressUpdate | null;
  isVisible: boolean;
}

const stageIcons: Record<string, React.ReactNode> = {
  started: <Zap className="animate-pulse" size={16} />,
  processing: <Loader2 className="animate-spin" size={16} />,
  completed: <CheckCircle2 size={16} className="text-green-400" />,
  error: <XCircle size={16} className="text-red-400" />,
};

const stageColors: Record<string, string> = {
  started: 'from-blue-500/20 to-purple-500/20 border-blue-500/40',
  processing: 'from-purple-500/20 to-pink-500/20 border-purple-500/40',
  completed: 'from-green-500/20 to-emerald-500/20 border-green-500/40',
  error: 'from-red-500/20 to-orange-500/20 border-red-500/40',
};

const progressBarColors: Record<string, string> = {
  started: 'from-blue-500 to-purple-500',
  processing: 'from-purple-500 to-pink-500',
  completed: 'from-green-500 to-emerald-500',
  error: 'from-red-500 to-orange-500',
};

export const ProgressIndicator: React.FC<ProgressIndicatorProps> = ({ progress, isVisible }) => {
  if (!isVisible || !progress) return null;

  const stage = progress.stage || 'processing';
  const colorClass = stageColors[stage] || stageColors.processing;
  const barColor = progressBarColors[stage] || progressBarColors.processing;
  const icon = stageIcons[stage] || stageIcons.processing;

  return (
    <div className={`
      fixed bottom-24 left-1/2 -translate-x-1/2 z-50
      bg-gradient-to-r ${colorClass}
      backdrop-blur-xl border rounded-xl shadow-2xl
      px-5 py-3 min-w-[300px] max-w-[500px]
      animate-fade-in
    `}>
      <div className="flex items-center gap-3 mb-2">
        <div className="text-gray-300">
          {icon}
        </div>
        <span className="text-sm font-medium text-gray-200 flex-1 truncate">
          {progress.message}
        </span>
        <span className="text-xs font-mono text-gray-400">
          {Math.round(progress.progress)}%
        </span>
      </div>
      
      {/* Progress bar */}
      <div className="h-1.5 bg-gray-700/50 rounded-full overflow-hidden">
        <div 
          className={`h-full bg-gradient-to-r ${barColor} rounded-full transition-all duration-300 ease-out`}
          style={{ width: `${progress.progress}%` }}
        />
      </div>

      {/* Stage indicator dots */}
      <div className="flex justify-center gap-2 mt-2">
        {['started', 'processing', 'completed'].map((s, idx) => (
          <div 
            key={s}
            className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
              stage === s 
                ? 'bg-white scale-125' 
                : progress.progress >= (idx + 1) * 33 
                  ? 'bg-gray-400' 
                  : 'bg-gray-600'
            }`}
          />
        ))}
      </div>
    </div>
  );
};

// Compact версия для встраивания в чат
export const InlineProgress: React.FC<{ progress: ProgressUpdate | null }> = ({ progress }) => {
  if (!progress) return null;

  const stage = progress.stage || 'processing';
  const isCompleted = stage === 'completed';
  const isError = stage === 'error';

  if (isCompleted) return null;

  return (
    <div className={`
      flex items-center gap-2 px-3 py-2 rounded-lg text-sm
      ${isError 
        ? 'bg-red-500/10 border border-red-500/30 text-red-300' 
        : 'bg-purple-500/10 border border-purple-500/30 text-purple-300'
      }
    `}>
      {isError ? (
        <XCircle size={14} className="text-red-400" />
      ) : (
        <Loader2 size={14} className="animate-spin" />
      )}
      <span className="flex-1 truncate">{progress.message}</span>
      {!isError && (
        <span className="text-xs font-mono opacity-70">
          {Math.round(progress.progress)}%
        </span>
      )}
    </div>
  );
};

export default ProgressIndicator;

