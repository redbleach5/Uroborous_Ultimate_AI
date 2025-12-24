import React, { createContext, useContext, useState, ReactNode } from 'react';

interface ExecutionInfo {
  agent?: string;
  models?: string[];
}

interface ExecutionContextType {
  executionInfo: ExecutionInfo | null;
  setExecutionInfo: (info: ExecutionInfo | null) => void;
}

const ExecutionContext = createContext<ExecutionContextType | undefined>(undefined);

export function ExecutionProvider({ children }: { children: ReactNode }) {
  const [executionInfo, setExecutionInfo] = useState<ExecutionInfo | null>(null);

  return (
    <ExecutionContext.Provider value={{ executionInfo, setExecutionInfo }}>
      {children}
    </ExecutionContext.Provider>
  );
}

export function useExecutionInfo() {
  const context = useContext(ExecutionContext);
  if (context === undefined) {
    throw new Error('useExecutionInfo must be used within ExecutionProvider');
  }
  return context;
}

