/**
 * WebSocket hook для real-time коммуникации с backend
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface ProgressUpdate {
  stage: string;
  progress: number;
  message: string;
  data?: Record<string, any>;
}

export interface WebSocketMessage {
  type: string;
  data?: any;
  message?: string;
  stage?: string;
  progress?: number;
  success?: boolean;
  error?: string;
}

interface UseWebSocketOptions {
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onProgress?: (progress: ProgressUpdate) => void;
  onMessage?: (message: WebSocketMessage) => void;
  onError?: (error: string) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  isConnecting: boolean;
  connect: () => void;
  disconnect: () => void;
  sendTask: (task: string, agentType?: string, context?: Record<string, any>, model?: string, provider?: string) => void;
  sendChat: (message: string, history?: Array<{role: string; content: string}>, mode?: string, model?: string, provider?: string) => void;
  sendMessage: (message: WebSocketMessage) => void;
  lastProgress: ProgressUpdate | null;
  error: string | null;
}

const getWebSocketUrl = (): string => {
  const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
  // Извлекаем хост из API URL и создаём WebSocket URL
  const url = new URL(apiUrl);
  const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${url.host}/ws`;
};

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    autoConnect = false,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onProgress,
    onMessage,
    onError,
    onConnect,
    onDisconnect,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [lastProgress, setLastProgress] = useState<ProgressUpdate | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    cleanup();
    setIsConnecting(true);
    setError(null);

    try {
      const wsUrl = getWebSocketUrl();
      console.log('[WebSocket] Connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connected');
        setIsConnected(true);
        setIsConnecting(false);
        reconnectAttemptsRef.current = 0;
        onConnect?.();

        // Heartbeat ping каждые 30 секунд
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          // Handle progress updates
          if (message.type === 'progress') {
            const progress: ProgressUpdate = {
              stage: message.stage || 'unknown',
              progress: message.progress || 0,
              message: message.message || '',
              data: message.data,
            };
            setLastProgress(progress);
            onProgress?.(progress);
          }
          
          // Handle errors
          if (message.type === 'error') {
            const errorMsg = message.message || 'Unknown error';
            setError(errorMsg);
            onError?.(errorMsg);
          }
          
          // Pass all messages to handler
          onMessage?.(message);
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError('WebSocket connection error');
        onError?.('WebSocket connection error');
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected, code:', event.code);
        setIsConnected(false);
        setIsConnecting(false);
        cleanup();
        onDisconnect?.();

        // Автоматический reconnect
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          console.log(`[WebSocket] Reconnecting in ${reconnectInterval}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };
    } catch (e) {
      console.error('[WebSocket] Failed to create connection:', e);
      setIsConnecting(false);
      setError('Failed to create WebSocket connection');
    }
  }, [cleanup, maxReconnectAttempts, reconnectInterval, onConnect, onDisconnect, onError, onMessage, onProgress]);

  const disconnect = useCallback(() => {
    cleanup();
    reconnectAttemptsRef.current = maxReconnectAttempts; // Prevent reconnection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, [cleanup, maxReconnectAttempts]);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[WebSocket] Cannot send message: not connected');
    }
  }, []);

  const sendTask = useCallback((
    task: string,
    agentType?: string,
    context?: Record<string, any>,
    model?: string,
    provider?: string
  ) => {
    setLastProgress(null);
    sendMessage({
      type: 'task',
      data: { task, agent_type: agentType, context, model, provider },
    });
  }, [sendMessage]);

  const sendChat = useCallback((
    message: string,
    history?: Array<{role: string; content: string}>,
    mode?: string,
    model?: string,
    provider?: string
  ) => {
    setLastProgress(null);
    sendMessage({
      type: 'chat',
      data: { message, history, mode, model, provider },
    });
  }, [sendMessage]);

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    isConnected,
    isConnecting,
    connect,
    disconnect,
    sendTask,
    sendChat,
    sendMessage,
    lastProgress,
    error,
  };
}

export default useWebSocket;

