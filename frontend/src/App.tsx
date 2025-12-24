import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MainLayout } from './components/MainLayout';
import { ExecutionProvider } from './state/executionContext';
import './App.css';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ExecutionProvider>
        <MainLayout />
      </ExecutionProvider>
    </QueryClientProvider>
  );
}

export default App;

