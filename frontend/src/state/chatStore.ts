import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ChatRole = 'user' | 'assistant';

// Reflection data from agent self-correction
export interface ReflectionData {
  completeness: number;    // 0-100: How complete is the solution
  correctness: number;     // 0-100: How correct is the solution
  quality: number;         // 0-100: Code/text quality
  overall_score: number;   // 0-100: Weighted overall score
  quality_level: 'excellent' | 'good' | 'acceptable' | 'poor' | 'failed';
  issues: string[];        // Identified issues
  improvements: string[];  // Suggested improvements
  should_retry: boolean;
  retry_suggestion?: string;
  timestamp?: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: number;
  status?: 'pending' | 'streaming' | 'completed' | 'error';
  result?: any;
  subtasks?: Array<{ subtask: string; status: string; result?: any }>;
  thinking?: string; // Thinking/reasoning trace
  reflection?: ReflectionData; // Agent reflection/self-correction data
  metadata?: {
    provider?: string;
    model?: string;
    thinking_mode?: boolean;
    thinking_native?: boolean;
    thinking_emulated?: boolean;
    reflection_attempts?: number; // How many correction attempts were made
    corrected?: boolean; // Was the result corrected
    execution_time?: number; // Execution time in seconds
  };
}

export type ChatMode = 'chat' | 'task' | 'agent' | 'batch';

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: number;
  mode?: ChatMode;
  agentType?: string; // For agent mode
}

interface ChatState {
  conversations: Record<string, Conversation>;
  currentId: string | null;
  currentMode: ChatMode;
  createConversation: (title?: string, mode?: ChatMode) => string;
  setCurrentConversation: (id: string) => void;
  setCurrentMode: (mode: ChatMode) => void;
  renameConversation: (id: string, title: string) => void;
  deleteConversation: (id: string) => void;
  clearConversation: (id: string) => void;
  addMessage: (conversationId: string, message: ChatMessage) => void;
  updateMessage: (conversationId: string, messageId: string, patch: Partial<ChatMessage>) => void;
}

const createDefaultConversation = (mode: ChatMode = 'chat'): Conversation => {
  const id = `conv-${Date.now()}`;
  const modeTitles: Record<ChatMode, string> = {
    chat: 'Новый чат',
    task: 'Новая задача',
    agent: 'Новый агент',
    batch: 'Пакетная обработка',
  };
  return {
    id,
    title: modeTitles[mode],
    messages: [],
    updatedAt: Date.now(),
    mode,
  };
};

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: { },
      currentId: null,
      currentMode: 'chat',

      createConversation: (title?: string, mode?: ChatMode) => {
        const currentMode = mode || get().currentMode;
        const conv = createDefaultConversation(currentMode);
        conv.title = title?.trim() || conv.title;
        set((state) => ({
          conversations: { ...state.conversations, [conv.id]: conv },
          currentId: conv.id,
          currentMode: currentMode,
        }));
        return conv.id;
      },

      setCurrentMode: (mode: ChatMode) => {
        set({ currentMode: mode });
        // Update current conversation mode if exists
        // Don't create new conversations when switching modes
        const currentId = get().currentId;
        if (currentId) {
          const conv = get().conversations[currentId];
          if (conv) {
            set((state) => ({
              conversations: {
                ...state.conversations,
                [currentId]: { ...conv, mode },
              },
            }));
          }
        }
        // If no conversation exists, it will be created when user sends first message
      },

      setCurrentConversation: (id: string) => {
        const exists = get().conversations[id];
        if (exists) {
          set({ 
            currentId: id,
            currentMode: exists.mode || 'chat',
          });
        }
      },

      renameConversation: (id: string, title: string) => {
        set((state) => {
          const conv = state.conversations[id];
          if (!conv) return state;
          return {
            conversations: {
              ...state.conversations,
              [id]: { ...conv, title: title.trim() || conv.title, updatedAt: Date.now() },
            },
          };
        });
      },

      deleteConversation: (id: string) => {
        set((state) => {
          const { [id]: deleted, ...rest } = state.conversations;
          const remainingIds = Object.keys(rest);
          let newCurrentId = state.currentId;
          
          // If deleting current conversation, switch to another one
          if (state.currentId === id) {
            newCurrentId = remainingIds.length > 0 
              ? remainingIds.sort((a, b) => {
                  // Sort by updatedAt descending to get most recent
                  const convA = rest[a];
                  const convB = rest[b];
                  return (convB?.updatedAt || 0) - (convA?.updatedAt || 0);
                })[0]
              : null;
          }
          
          return {
            conversations: rest,
            currentId: newCurrentId,
          };
        });
      },

      clearConversation: (id: string) => {
        set((state) => {
          const conv = state.conversations[id];
          if (!conv) return state;
          return {
            conversations: {
              ...state.conversations,
              [id]: { ...conv, messages: [], updatedAt: Date.now() },
            },
          };
        });
      },

      addMessage: (conversationId: string, message: ChatMessage) => {
        set((state) => {
          const conv = state.conversations[conversationId];
          if (!conv) return state;
          return {
            conversations: {
              ...state.conversations,
              [conversationId]: {
                ...conv,
                messages: [...conv.messages, message],
                updatedAt: Date.now(),
              },
            },
          };
        });
      },

      updateMessage: (conversationId: string, messageId: string, patch: Partial<ChatMessage>) => {
        set((state) => {
          const conv = state.conversations[conversationId];
          if (!conv) return state;
          return {
            conversations: {
              ...state.conversations,
              [conversationId]: {
                ...conv,
                messages: conv.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m)),
                updatedAt: Date.now(),
              },
            },
          };
        });
      },
    }),
    {
      name: 'aillm-chat-store',
    }
  )
);

