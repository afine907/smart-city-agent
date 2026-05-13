declare module 'agent-sse-flow' {
  import { ComponentType } from 'react';

  interface AgentFlowProps {
    url: string;
    theme?: 'light' | 'dark';
    autoConnect?: boolean;
    maxEvents?: number;
    onError?: (error: Error) => void;
    onStatusChange?: (status: string) => void;
  }

  export const AgentFlow: ComponentType<AgentFlowProps>;
}
