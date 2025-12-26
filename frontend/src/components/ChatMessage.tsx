import React, { useState } from 'react';
import { 
  CircleCheck, CircleX, Brain, Search, RefreshCw, Zap, 
  AlertTriangle, Lightbulb, Clock, Bot, FileText, ThumbsUp, ThumbsDown
} from 'lucide-react';
import { renderMarkdown } from './MarkdownRenderer';
import { CodeBlock, extractCodeFromMarkdown, CodeExecutionResult } from './CodeExecutor';
import { ChatMessage as Message, ReflectionData, FeedbackData } from '../state/chatStore';
import { submitFeedback } from '../api/client';

// Re-export for convenience
export type { Message };

// Type aliases for component props
type MessageReflection = ReflectionData;
type MessageMetadata = Message['metadata'];

// ============ Subcomponents ============

interface ThinkingTraceProps {
  thinking: string;
}

const ThinkingTrace: React.FC<ThinkingTraceProps> = ({ thinking }) => (
  <div className="mb-4 p-4 bg-gradient-to-br from-purple-900/30 to-purple-800/20 border border-purple-500/40 rounded-xl shadow-lg">
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-purple-300 flex items-center gap-2">
          <Brain size={18} strokeWidth={1.5} />
          <span>Reasoning Process</span>
        </span>
      </div>
    </div>
    <div className="text-xs text-purple-200/90 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto leading-relaxed bg-[#0f111b]/40 p-3 rounded-lg border border-purple-500/20">
      {thinking}
    </div>
  </div>
);

interface ReflectionPanelProps {
  reflection: MessageReflection;
  metadata?: MessageMetadata;
}

const ReflectionPanel: React.FC<ReflectionPanelProps> = ({ reflection, metadata }) => (
  <div className="mb-4 p-4 bg-gradient-to-br from-emerald-900/30 to-teal-800/20 border border-emerald-500/40 rounded-xl shadow-lg">
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-emerald-300 flex items-center gap-2">
          <Search size={18} strokeWidth={1.5} />
          <span>Quality Analysis</span>
        </span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
          reflection.quality_level === 'excellent' ? 'bg-green-500/30 text-green-300 border border-green-500/40' :
          reflection.quality_level === 'good' ? 'bg-blue-500/30 text-blue-300 border border-blue-500/40' :
          reflection.quality_level === 'acceptable' ? 'bg-yellow-500/30 text-yellow-300 border border-yellow-500/40' :
          'bg-red-500/30 text-red-300 border border-red-500/40'
        }`}>
          {reflection.quality_level === 'excellent' ? 'Отлично' :
           reflection.quality_level === 'good' ? 'Хорошо' :
           reflection.quality_level === 'acceptable' ? 'Приемлемо' :
           reflection.quality_level === 'poor' ? 'Слабо' :
           reflection.quality_level === 'failed' ? 'Неудача' : 'Неизвестно'}
        </span>
      </div>
      {metadata?.corrected && (
        <span className="px-2 py-0.5 bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-full text-xs font-medium flex items-center gap-1">
          <RefreshCw size={10} strokeWidth={1.5} />
          <span>Исправлено</span>
        </span>
      )}
    </div>
    
    {/* Score bars */}
    <div className="grid grid-cols-3 gap-3 mb-3">
      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Полнота</div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${reflection.completeness}%` }}
            />
          </div>
          <span className="text-xs font-mono text-emerald-300">{Math.round(reflection.completeness)}%</span>
        </div>
      </div>
      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Корректность</div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-blue-500 to-blue-400 rounded-full transition-all duration-500"
              style={{ width: `${reflection.correctness}%` }}
            />
          </div>
          <span className="text-xs font-mono text-blue-300">{Math.round(reflection.correctness)}%</span>
        </div>
      </div>
      <div className="bg-[#0f111b]/40 p-2 rounded-lg border border-emerald-500/20">
        <div className="text-[10px] text-emerald-400/70 uppercase tracking-wide mb-1">Качество</div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-purple-500 to-purple-400 rounded-full transition-all duration-500"
              style={{ width: `${reflection.quality}%` }}
            />
          </div>
          <span className="text-xs font-mono text-purple-300">{Math.round(reflection.quality)}%</span>
        </div>
      </div>
    </div>
    
    {/* Overall score */}
    <div className="flex items-center justify-between mb-3 p-2 bg-[#0f111b]/60 rounded-lg border border-emerald-500/20">
      <span className="text-xs text-emerald-400/80">Общая оценка</span>
      <div className="flex items-center gap-2">
        <div className="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
          <div 
            className={`h-full rounded-full transition-all duration-500 ${
              reflection.overall_score >= 90 ? 'bg-gradient-to-r from-green-500 to-emerald-400' :
              reflection.overall_score >= 70 ? 'bg-gradient-to-r from-blue-500 to-cyan-400' :
              reflection.overall_score >= 50 ? 'bg-gradient-to-r from-yellow-500 to-amber-400' :
              'bg-gradient-to-r from-red-500 to-orange-400'
            }`}
            style={{ width: `${reflection.overall_score}%` }}
          />
        </div>
        <span className={`text-sm font-bold ${
          reflection.overall_score >= 90 ? 'text-green-400' :
          reflection.overall_score >= 70 ? 'text-blue-400' :
          reflection.overall_score >= 50 ? 'text-yellow-400' : 'text-red-400'
        }`}>
          {Math.round(reflection.overall_score)}
        </span>
      </div>
    </div>
    
    {/* Issues and improvements */}
    {(reflection.issues?.length || reflection.improvements?.length) && (
      <div className="grid grid-cols-2 gap-3 text-xs">
        {reflection.issues && reflection.issues.length > 0 && (
          <div className="bg-red-900/20 p-2 rounded-lg border border-red-500/20">
            <div className="text-red-400 font-medium mb-1 flex items-center gap-1">
              <AlertTriangle size={12} strokeWidth={1.5} /> Замечания
            </div>
            <ul className="text-red-300/80 space-y-0.5">
              {reflection.issues.slice(0, 3).map((issue, i) => (
                <li key={i} className="truncate">• {issue}</li>
              ))}
            </ul>
          </div>
        )}
        {reflection.improvements && reflection.improvements.length > 0 && (
          <div className="bg-emerald-900/20 p-2 rounded-lg border border-emerald-500/20">
            <div className="text-emerald-400 font-medium mb-1 flex items-center gap-1">
              <Lightbulb size={12} strokeWidth={1.5} /> Улучшения
            </div>
            <ul className="text-emerald-300/80 space-y-0.5">
              {reflection.improvements.slice(0, 3).map((imp, i) => (
                <li key={i} className="truncate">• {imp}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )}
    
    {/* Reflection attempts info */}
    {metadata?.reflection_attempts && metadata.reflection_attempts > 1 && (
      <div className="mt-2 text-[10px] text-emerald-400/60 flex items-center gap-1">
        <RefreshCw size={10} strokeWidth={1.5} />
        <span>Попыток: {metadata.reflection_attempts}</span>
        {metadata.execution_time && (
          <span className="ml-2 flex items-center gap-1"><Clock size={10} strokeWidth={1.5} /> {metadata.execution_time.toFixed(1)}с</span>
        )}
      </div>
    )}
  </div>
);

interface ProviderInfoProps {
  metadata: NonNullable<MessageMetadata>;
}

const ProviderInfo: React.FC<ProviderInfoProps> = ({ metadata }) => (
  <div className="mb-3 -mt-1 flex items-center gap-2 flex-wrap">
    {metadata?.provider && (
      <span className="px-2.5 py-1 bg-[#0f111b]/60 backdrop-blur-sm border border-[#2a2f46] rounded-lg text-xs font-medium text-gray-300 flex items-center gap-1.5">
        {metadata.provider === 'ollama' ? (
          <>
            <Bot size={12} strokeWidth={1.5} />
            <span>Ollama</span>
          </>
        ) : (
          <span>{metadata.provider}</span>
        )}
      </span>
    )}
    {metadata?.model && (
      <span className="px-2.5 py-1 bg-[#0f111b]/60 backdrop-blur-sm border border-[#2a2f46] rounded-lg text-xs font-medium text-gray-300">
        {metadata.model}
      </span>
    )}
    {metadata?.thinking_mode && (
      <span className="px-2.5 py-1 bg-purple-900/40 border border-purple-500/30 rounded-lg text-xs font-medium text-purple-300 flex items-center gap-1.5">
        <Brain size={12} strokeWidth={1.5} />
        <span>Thinking Mode</span>
      </span>
    )}
    {metadata?.thinking_native && (
      <span className="px-2.5 py-1 bg-green-900/40 border border-green-500/30 rounded-lg text-xs font-medium text-green-300 flex items-center gap-1.5">
        <span>✓</span>
        <span>Native</span>
      </span>
    )}
    {metadata?.thinking_emulated && (
      <span className="px-2.5 py-1 bg-yellow-900/40 border border-yellow-500/30 rounded-lg text-xs font-medium text-yellow-300 flex items-center gap-1.5">
        <Zap size={12} strokeWidth={1.5} />
        <span>Emulated</span>
      </span>
    )}
  </div>
);

interface FilesListProps {
  files: any[];
  onDownloadCode: (code: string, filename: string) => void;
}

const FilesList: React.FC<FilesListProps> = ({ files, onDownloadCode }) => (
  <div className="mt-3">
    <div className="text-sm font-semibold mb-3 text-gray-200 flex items-center gap-2">
      <FileText size={14} strokeWidth={1.5} className="text-gray-400" />
      <span>Созданные файлы</span>
    </div>
    <div className="space-y-2">
      {files.map((file: any, idx: number) => (
        <div
          key={idx}
          className="flex items-center justify-between p-3 bg-[#0f111b]/60 backdrop-blur-sm rounded-lg border border-[#2a2f46] hover:border-[#3a3f56] transition-colors"
        >
          <span className="text-sm text-gray-300 font-mono">{file.path || file.name || `Файл ${idx + 1}`}</span>
          {file.code && (
            <button
              onClick={() => onDownloadCode(file.code, file.path || file.name || `file_${idx}.py`)}
              className="text-xs px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 rounded-lg transition-colors font-medium flex items-center gap-1.5 shadow-md"
            >
              <span>⬇️</span>
              <span>Скачать</span>
            </button>
          )}
        </div>
      ))}
    </div>
  </div>
);

// ============ Feedback Component ============

interface FeedbackButtonsProps {
  message: Message;
  onFeedbackSubmit: (messageId: string, feedback: FeedbackData) => void;
}

const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({ message, onFeedbackSubmit }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localFeedback, setLocalFeedback] = useState<FeedbackData | undefined>(message.feedback);

  const handleFeedback = async (rating: 'positive' | 'negative') => {
    if (isSubmitting || localFeedback?.submitted) return;
    
    setIsSubmitting(true);
    const newFeedback: FeedbackData = { rating, submitted: false };
    setLocalFeedback(newFeedback);

    try {
      await submitFeedback({
        task: message.content?.substring(0, 500) || 'Unknown task',
        solution: message.result?.code || message.content || '',
        rating: rating === 'positive' ? 5 : 1,
        is_helpful: rating === 'positive',
        agent: message.metadata?.model,
        model: message.metadata?.model,
        provider: message.metadata?.provider,
        solution_id: message.id,
      });
      
      const submittedFeedback: FeedbackData = { rating, submitted: true };
      setLocalFeedback(submittedFeedback);
      onFeedbackSubmit(message.id, submittedFeedback);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      // Still mark as submitted locally to avoid spam
      const failedFeedback: FeedbackData = { rating, submitted: true };
      setLocalFeedback(failedFeedback);
      onFeedbackSubmit(message.id, failedFeedback);
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentRating = localFeedback?.rating || message.feedback?.rating;
  const isSubmitted = localFeedback?.submitted || message.feedback?.submitted;

  return (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[#2a2f46]/50">
      <span className="text-xs text-gray-500 mr-1">Оценить ответ:</span>
      <button
        onClick={() => handleFeedback('positive')}
        disabled={isSubmitting || isSubmitted}
        className={`p-1.5 rounded-lg transition-all duration-200 ${
          currentRating === 'positive'
            ? 'bg-green-500/30 text-green-400 border border-green-500/50'
            : 'bg-[#0f111b]/60 text-gray-400 hover:text-green-400 hover:bg-green-500/20 border border-transparent hover:border-green-500/30'
        } ${isSubmitting ? 'opacity-50 cursor-wait' : isSubmitted && currentRating !== 'positive' ? 'opacity-30' : ''}`}
        title="Полезный ответ"
      >
        <ThumbsUp size={14} strokeWidth={1.5} />
      </button>
      <button
        onClick={() => handleFeedback('negative')}
        disabled={isSubmitting || isSubmitted}
        className={`p-1.5 rounded-lg transition-all duration-200 ${
          currentRating === 'negative'
            ? 'bg-red-500/30 text-red-400 border border-red-500/50'
            : 'bg-[#0f111b]/60 text-gray-400 hover:text-red-400 hover:bg-red-500/20 border border-transparent hover:border-red-500/30'
        } ${isSubmitting ? 'opacity-50 cursor-wait' : isSubmitted && currentRating !== 'negative' ? 'opacity-30' : ''}`}
        title="Неполезный ответ"
      >
        <ThumbsDown size={14} strokeWidth={1.5} />
      </button>
      {isSubmitted && (
        <span className="text-xs text-gray-500 ml-1">Спасибо за оценку!</span>
      )}
    </div>
  );
};

// ============ Main ChatMessage Component ============

interface ChatMessageComponentProps {
  message: Message;
  index: number;
  runningCodeId: string | null;
  executionResult?: CodeExecutionResult;
  onRunCode: (code: string, messageId: string, files?: any[]) => void;
  onDownloadCode: (code: string, filename: string) => void;
  onFeedbackSubmit?: (messageId: string, feedback: FeedbackData) => void;
}

export const ChatMessage: React.FC<ChatMessageComponentProps> = ({
  message,
  index,
  runningCodeId,
  executionResult,
  onRunCode,
  onDownloadCode,
  onFeedbackSubmit,
}) => {
  const code = message.result?.code || extractCodeFromMarkdown(message.content || '');
  
  return (
    <div
      id={`message-${message.id}`}
      className={`flex gap-3 mb-4 group animate-fade-in ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
      style={{ animationDelay: `${index * 0.1}s` }}
    >
      {message.role === 'assistant' && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center flex-shrink-0 shadow-md shadow-blue-500/30 ring-1 ring-blue-500/20">
          <span className="text-xs font-bold text-white">AI</span>
        </div>
      )}
      <div
        className={`max-w-3xl rounded-2xl px-6 py-4 transition-all duration-200 ${
          message.role === 'user'
            ? 'bg-gradient-to-br from-blue-600/90 to-blue-700/90 text-white shadow-lg shadow-blue-500/20'
            : message.status === 'error'
            ? 'bg-red-900/30 border-2 border-red-500/60 shadow-lg shadow-red-500/20'
            : 'bg-[#1a1d2e] border border-[#2a2f46] shadow-lg hover:border-[#3a3f56]'
        }`}
      >
        {message.role === 'user' ? (
          <div className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</div>
        ) : (
          <div>
            {message.status === 'streaming' && (
              <div className="flex items-center gap-3 text-gray-300">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span className="text-sm font-medium">Выполняется...</span>
              </div>
            )}
            
            {message.status === 'completed' && (
              <div className="space-y-3">
                {/* Subtasks */}
                {message.subtasks && message.subtasks.length > 0 && (
                  <div className="text-sm mb-3">
                    <div className="text-gray-300 mb-3 font-medium flex items-center gap-2">
                      <CircleCheck size={14} strokeWidth={1.5} className="text-green-400" />
                      <span>Выполненные шаги</span>
                    </div>
                    <div className="space-y-2">
                      {message.subtasks.map((st, idx) => (
                        <div key={idx} className="flex items-start gap-3 text-gray-300 bg-[#0f111b]/40 p-2.5 rounded-lg border border-[#2a2f46]/50">
                          <span className="text-green-400 text-lg mt-0.5 flex-shrink-0">✓</span>
                          <span className="leading-relaxed">{st.subtask}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Code Block */}
                {code && (
                  <CodeBlock
                    code={code}
                    messageId={message.id}
                    files={message.result?.files}
                    runningCodeId={runningCodeId}
                    executionResult={executionResult}
                    onRunCode={onRunCode}
                    onDownloadCode={onDownloadCode}
                  />
                )}

                {/* Thinking trace */}
                {message.thinking && <ThinkingTrace thinking={message.thinking} />}

                {/* Reflection */}
                {message.reflection && (
                  <ReflectionPanel reflection={message.reflection} metadata={message.metadata} />
                )}

                {/* Provider and model info */}
                {message.metadata && (message.metadata.provider || message.metadata.model) && (
                  <ProviderInfo metadata={message.metadata} />
                )}

                {/* Markdown content (when no code) */}
                {message.content && !message.result?.code && !extractCodeFromMarkdown(message.content) && (
                  <div className="prose prose-invert max-w-none">
                    <div 
                      className="text-[15px] leading-relaxed markdown-content"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
                    />
                  </div>
                )}

                {/* Files list */}
                {message.result?.files && Array.isArray(message.result.files) && message.result.files.length > 0 && (
                  <FilesList files={message.result.files} onDownloadCode={onDownloadCode} />
                )}

                {/* Feedback buttons */}
                {onFeedbackSubmit && (
                  <FeedbackButtons message={message} onFeedbackSubmit={onFeedbackSubmit} />
                )}
              </div>
            )}
            
            {message.status === 'error' && (
              <div className="text-red-300 leading-relaxed flex items-start gap-2">
                <CircleX size={18} strokeWidth={1.5} className="flex-shrink-0 mt-0.5" />
                <div className="flex-1">{message.content}</div>
              </div>
            )}
          </div>
        )}
      </div>
      {message.role === 'user' && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gray-600 to-gray-700 flex items-center justify-center flex-shrink-0 shadow-md ring-1 ring-gray-500/20">
          <span className="text-sm">👤</span>
        </div>
      )}
    </div>
  );
};

export default ChatMessage;

