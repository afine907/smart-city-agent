import { useEffect, useRef, useState, useCallback } from 'react';
import type { SSEEvent } from './types';

export interface UseSSEReturn {
  connected: boolean;
  events: SSEEvent[];
  addEventListener: (type: string, handler: (event: SSEEvent) => void) => () => void;
}

export function useSSE(url: string): UseSSEReturn {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const handlersRef = useRef<Map<string, Set<(e: SSEEvent) => void>>>(new Map());
  const esRef = useRef<EventSource | null>(null);

  const addEventListener = useCallback((type: string, handler: (event: SSEEvent) => void) => {
    if (!handlersRef.current.has(type)) {
      handlersRef.current.set(type, new Set());
    }
    handlersRef.current.get(type)!.add(handler);
    return () => {
      handlersRef.current.get(type)?.delete(handler);
    };
  }, []);

  useEffect(() => {
    const es = new EventSource(url);
    esRef.current = es;

    const eventTypes = [
      'thinking', 'decision', 'conflict', 'coordination', 'metrics',
      'simulation_start', 'simulation_step', 'simulation_end', 'keepalive',
    ];

    const handleEvent = (type: string) => (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as SSEEvent;
        setEvents(prev => [...prev.slice(-99), data]);
        handlersRef.current.get(type)?.forEach(h => h(data));
      } catch {
        // ignore parse errors
      }
    };

    for (const type of eventTypes) {
      es.addEventListener(type, handleEvent(type));
    }

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [url]);

  return { connected, events, addEventListener };
}
