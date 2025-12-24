import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFeedbackStats, getFeedbackRecommendations } from '../api/client';

// Компонент прогресс-бара
function ProgressBar({ value, max = 100, color = 'blue', label }: { 
  value: number; 
  max?: number; 
  color?: string;
  label?: string;
}) {
  const percentage = Math.min((value / max) * 100, 100);
  const colorClasses: Record<string, string> = {
    blue: 'from-blue-500 to-blue-600',
    green: 'from-emerald-500 to-emerald-600',
    yellow: 'from-amber-500 to-amber-600',
    red: 'from-red-500 to-red-600',
    purple: 'from-purple-500 to-purple-600',
    cyan: 'from-cyan-500 to-cyan-600',
  };
  
  return (
    <div className="w-full">
      {label && <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span>
        <span>{value.toFixed(1)}{max === 100 ? '%' : `/${max}`}</span>
      </div>}
      <div className="w-full h-2 bg-gray-700/50 rounded-full overflow-hidden">
        <div 
          className={`h-full bg-gradient-to-r ${colorClasses[color] || colorClasses.blue} transition-all duration-500 ease-out rounded-full`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

// Компонент круговой диаграммы
function CircularProgress({ value, size = 120, strokeWidth = 8, color = '#3b82f6' }: {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (value / 100) * circumference;
  
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg className="transform -rotate-90" width={size} height={size}>
        <circle
          className="text-gray-700"
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        <circle
          className="transition-all duration-500 ease-out"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          stroke={color}
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-2xl font-bold text-white">{value.toFixed(0)}%</span>
      </div>
    </div>
  );
}

// Карточка статистики
function StatCard({ title, value, subtitle, icon, trend, color = 'blue' }: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: string;
  trend?: { value: number; positive: boolean };
  color?: string;
}) {
  const bgColors: Record<string, string> = {
    blue: 'from-blue-600/20 to-blue-700/10 border-blue-500/30',
    green: 'from-emerald-600/20 to-emerald-700/10 border-emerald-500/30',
    purple: 'from-purple-600/20 to-purple-700/10 border-purple-500/30',
    amber: 'from-amber-600/20 to-amber-700/10 border-amber-500/30',
    cyan: 'from-cyan-600/20 to-cyan-700/10 border-cyan-500/30',
  };
  
  return (
    <div className={`p-4 rounded-xl bg-gradient-to-br ${bgColors[color] || bgColors.blue} border backdrop-blur-sm`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
      {trend && (
        <div className={`flex items-center gap-1 mt-2 text-xs ${trend.positive ? 'text-emerald-400' : 'text-red-400'}`}>
          <span>{trend.positive ? '↑' : '↓'}</span>
          <span>{Math.abs(trend.value).toFixed(1)}%</span>
          <span className="text-gray-500">за последние 7 дней</span>
        </div>
      )}
    </div>
  );
}

// Компонент модели
function ModelPerformanceCard({ model }: { model: any }) {
  const score = model.performance_score || 0;
  const successRate = (model.success_rate || 0) * 100;
  
  let statusColor = 'text-emerald-400';
  let statusBg = 'bg-emerald-500/20';
  if (score < 50) {
    statusColor = 'text-red-400';
    statusBg = 'bg-red-500/20';
  } else if (score < 70) {
    statusColor = 'text-amber-400';
    statusBg = 'bg-amber-500/20';
  }
  
  return (
    <div className="p-4 bg-[#1a1d2e]/50 rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🧠</span>
          <div>
            <p className="font-medium text-white text-sm">{model.model_name}</p>
            <p className="text-xs text-gray-500">{model.provider}</p>
          </div>
        </div>
        <div className={`px-2 py-1 rounded-md ${statusBg} ${statusColor} text-xs font-medium`}>
          {score.toFixed(1)} pts
        </div>
      </div>
      
      <div className="space-y-2">
        <ProgressBar 
          value={successRate} 
          color={successRate >= 90 ? 'green' : successRate >= 70 ? 'yellow' : 'red'}
          label="Success Rate"
        />
        <div className="flex justify-between text-xs text-gray-400">
          <span>📊 {model.total_requests || 0} запросов</span>
          <span>⚡ {(model.avg_tokens_per_sec || 0).toFixed(1)} tok/s</span>
        </div>
      </div>
    </div>
  );
}

// Компонент рекомендации
function RecommendationCard({ rec }: { rec: any }) {
  const typeIcons: Record<string, string> = {
    agent_improvement: '🤖',
    model_concern: '⚠️',
    general: '💡',
    performance: '📈',
  };
  
  const typeColors: Record<string, string> = {
    agent_improvement: 'border-blue-500/30 bg-blue-500/10',
    model_concern: 'border-amber-500/30 bg-amber-500/10',
    general: 'border-purple-500/30 bg-purple-500/10',
    performance: 'border-emerald-500/30 bg-emerald-500/10',
  };
  
  return (
    <div className={`p-3 rounded-lg border ${typeColors[rec.type] || typeColors.general}`}>
      <div className="flex items-start gap-2">
        <span className="text-lg">{typeIcons[rec.type] || '💡'}</span>
        <p className="text-sm text-gray-300">{rec.suggestion}</p>
      </div>
    </div>
  );
}

// Главный компонент
export function LearningDashboard() {
  const [_selectedTimeRange, _setSelectedTimeRange] = useState<'7d' | '30d' | 'all'>('7d');
  
  const { data: statsData, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['feedback-stats'],
    queryFn: getFeedbackStats,
    refetchInterval: 30000,
  });
  
  const { data: recsData } = useQuery({
    queryKey: ['feedback-recommendations'],
    queryFn: getFeedbackRecommendations,
    refetchInterval: 60000,
  });

  const stats = statsData || {};
  const solutionFeedback = stats.solution_feedback || {};
  const learningInsights = stats.learning_insights || {};
  const recommendations = recsData?.recommendations || [];
  
  // Вычисляем общий прогресс обучения
  const totalExperience = learningInsights.total_experience || 0;
  const learningProgress = Math.min((totalExperience / 100) * 100, 100); // 100 запросов = 100%
  
  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-[#0f111b]">
        <div className="text-center">
          <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-gray-400">Загрузка данных обучения...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-[#0f111b] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <span className="text-3xl">🎓</span>
              Обучение системы
            </h1>
            <p className="text-gray-400 mt-1">
              Мониторинг процесса обучения и качества работы агентов
            </p>
          </div>
          <button 
            onClick={() => refetchStats()}
            className="px-4 py-2 bg-blue-600/20 border border-blue-500/30 text-blue-300 rounded-lg hover:bg-blue-600/30 transition-colors flex items-center gap-2"
          >
            <span>🔄</span>
            Обновить
          </button>
        </div>

        {/* Main Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Общий опыт"
            value={totalExperience}
            subtitle="обработанных запросов"
            icon="📚"
            color="blue"
          />
          <StatCard
            title="Средний рейтинг"
            value={`${(solutionFeedback.avg_rating || 0).toFixed(1)} ⭐`}
            subtitle="из 5.0"
            icon="⭐"
            color="amber"
          />
          <StatCard
            title="Полезность"
            value={`${(solutionFeedback.helpful_percentage || 0).toFixed(0)}%`}
            subtitle="полезных решений"
            icon="✅"
            color="green"
          />
          <StatCard
            title="Модели"
            value={learningInsights.models_analyzed || 0}
            subtitle="отслеживается"
            icon="🧠"
            color="purple"
          />
        </div>

        {/* Learning Progress Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Progress Circle */}
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-6 border border-[#2a2f46]">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span>📊</span>
              Прогресс обучения
            </h3>
            <div className="flex flex-col items-center">
              <CircularProgress 
                value={learningProgress} 
                size={160}
                strokeWidth={12}
                color={learningProgress >= 70 ? '#10b981' : learningProgress >= 40 ? '#f59e0b' : '#3b82f6'}
              />
              <p className="text-gray-400 text-sm mt-4 text-center">
                {learningProgress < 30 && '🌱 Начальный этап обучения'}
                {learningProgress >= 30 && learningProgress < 70 && '📈 Активное накопление опыта'}
                {learningProgress >= 70 && '🎯 Система обучена и оптимизирована'}
              </p>
            </div>
            
            {/* Learning Milestones */}
            <div className="mt-6 space-y-3">
              <div className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${totalExperience >= 10 ? 'bg-emerald-500 text-white' : 'bg-gray-700 text-gray-400'}`}>
                  {totalExperience >= 10 ? '✓' : '1'}
                </div>
                <span className={totalExperience >= 10 ? 'text-emerald-400' : 'text-gray-500'}>10+ запросов обработано</span>
              </div>
              <div className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${totalExperience >= 50 ? 'bg-emerald-500 text-white' : 'bg-gray-700 text-gray-400'}`}>
                  {totalExperience >= 50 ? '✓' : '2'}
                </div>
                <span className={totalExperience >= 50 ? 'text-emerald-400' : 'text-gray-500'}>50+ запросов (базовое обучение)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${totalExperience >= 100 ? 'bg-emerald-500 text-white' : 'bg-gray-700 text-gray-400'}`}>
                  {totalExperience >= 100 ? '✓' : '3'}
                </div>
                <span className={totalExperience >= 100 ? 'text-emerald-400' : 'text-gray-500'}>100+ запросов (полное обучение)</span>
              </div>
            </div>
          </div>

          {/* Top Performers */}
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-6 border border-[#2a2f46]">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span>🏆</span>
              Лучшие модели
            </h3>
            <div className="space-y-3">
              {learningInsights.top_performers && learningInsights.top_performers.length > 0 ? (
                learningInsights.top_performers.map((model: any, idx: number) => (
                  <ModelPerformanceCard key={idx} model={model} />
                ))
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <span className="text-4xl block mb-2">📊</span>
                  <p>Пока недостаточно данных</p>
                  <p className="text-xs mt-1">Нужно минимум 3 запроса к модели</p>
                </div>
              )}
            </div>
          </div>

          {/* Recommendations */}
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-6 border border-[#2a2f46]">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span>💡</span>
              Рекомендации
            </h3>
            <div className="space-y-3">
              {recommendations.length > 0 ? (
                recommendations.slice(0, 5).map((rec: any, idx: number) => (
                  <RecommendationCard key={idx} rec={rec} />
                ))
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <span className="text-4xl block mb-2">✨</span>
                  <p>Все работает отлично!</p>
                  <p className="text-xs mt-1">Рекомендации появятся по мере использования</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Models Grid */}
        {learningInsights.top_performers && learningInsights.top_performers.length > 0 && (
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-6 border border-[#2a2f46]">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span>🧠</span>
              Производительность моделей
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(stats.learning_insights?.models || []).slice(0, 6).map((model: any, idx: number) => (
                <ModelPerformanceCard key={idx} model={model} />
              ))}
            </div>
          </div>
        )}

        {/* Feedback Trends */}
        {solutionFeedback.recent_trends && solutionFeedback.recent_trends.length > 0 && (
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-6 border border-[#2a2f46]">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span>📈</span>
              Тренды за последние 7 дней
            </h3>
            <div className="grid grid-cols-7 gap-2">
              {solutionFeedback.recent_trends.slice(0, 7).reverse().map((day: any, idx: number) => {
                const rating = day.avg_rating || 0;
                const height = (rating / 5) * 100;
                return (
                  <div key={idx} className="flex flex-col items-center">
                    <div className="w-full h-24 bg-gray-800 rounded-lg relative overflow-hidden">
                      <div 
                        className={`absolute bottom-0 w-full rounded-lg transition-all duration-300 ${
                          rating >= 4 ? 'bg-gradient-to-t from-emerald-600 to-emerald-400' :
                          rating >= 3 ? 'bg-gradient-to-t from-amber-600 to-amber-400' :
                          'bg-gradient-to-t from-red-600 to-red-400'
                        }`}
                        style={{ height: `${height}%` }}
                      />
                      <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-white text-sm font-bold drop-shadow-lg">
                          {rating.toFixed(1)}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 mt-1">
                      {new Date(day.date).toLocaleDateString('ru', { weekday: 'short' })}
                    </span>
                    <span className="text-xs text-gray-600">
                      {day.count} отзывов
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Underperformers Alert */}
        {learningInsights.underperformers && learningInsights.underperformers.length > 0 && (
          <div className="bg-gradient-to-br from-red-900/20 to-red-800/10 rounded-xl p-6 border border-red-500/30">
            <h3 className="text-lg font-semibold text-red-300 mb-4 flex items-center gap-2">
              <span>⚠️</span>
              Требуют внимания
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {learningInsights.underperformers.map((model: any, idx: number) => (
                <div key={idx} className="p-4 bg-red-900/20 rounded-lg border border-red-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">🔴</span>
                    <div>
                      <p className="font-medium text-red-300">{model.model}</p>
                      <p className="text-xs text-red-400/60">{model.provider}</p>
                    </div>
                  </div>
                  <p className="text-sm text-red-200/80">
                    Success rate: {(model.success_rate * 100).toFixed(1)}%
                  </p>
                  {model.common_errors && Object.keys(model.common_errors).length > 0 && (
                    <p className="text-xs text-red-400/60 mt-1">
                      Частые ошибки: {Object.keys(model.common_errors).join(', ')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {totalExperience === 0 && (
          <div className="bg-gradient-to-br from-[#131524] to-[#1a1d2e] rounded-xl p-12 border border-[#2a2f46] text-center">
            <span className="text-6xl block mb-4">🎓</span>
            <h3 className="text-xl font-semibold text-white mb-2">
              Система готова к обучению
            </h3>
            <p className="text-gray-400 max-w-md mx-auto">
              Начните использовать AILLM для выполнения задач. 
              Система автоматически будет учиться на каждом запросе и улучшать качество ответов.
            </p>
            <div className="mt-6 flex justify-center gap-4">
              <div className="px-4 py-2 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-300 text-sm">
                💬 Отправьте первый запрос в чате
              </div>
              <div className="px-4 py-2 bg-purple-600/20 border border-purple-500/30 rounded-lg text-purple-300 text-sm">
                ⭐ Оценивайте ответы для обучения
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

