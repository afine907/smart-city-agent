import { useState, useEffect, useRef, useCallback } from 'react';

interface AgentEvent {
  id: number;
  type: string;
  agentName?: string;
  agentColor?: string;
  tool?: string;
  args?: unknown;
  argsJson?: string;
  message?: string;
  result?: string;
  duration?: number;
  timestamp?: number;
}

interface AgentFlowProps {
  url: string;
  theme?: 'light' | 'dark';
  autoConnect?: boolean;
  maxEvents?: number;
  renderMessage?: (message: string) => React.ReactNode;
  renderResult?: (result: string) => React.ReactNode;
}

const ICONS: Record<string, string> = {
  start: 'M8 5v14l11-7z',
  thinking: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  tool_call: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
  tool_result: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  message: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
  error: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  end: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z',
};

function EventIcon({ type }: { type: string }) {
  return (
    <span className="agent-flow__event-icon">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d={ICONS[type] || ICONS.message} />
      </svg>
    </span>
  );
}

function EventItem({ event, renderMessage, renderResult }: {
  event: AgentEvent;
  renderMessage?: (msg: string) => React.ReactNode;
  renderResult?: (res: string) => React.ReactNode;
}) {
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false }) : null;

  return (
    <div className={`agent-flow__event agent-flow__event--${event.type}`}>
      <EventIcon type={event.type} />
      <div className="agent-flow__event-content">
        <div className="agent-flow__event-header">
          <span className="agent-flow__event-type">{event.type}</span>
          {event.agentName && (
            <span className="agent-flow__agent-badge" style={event.agentColor ? { background: event.agentColor } : undefined}>
              {event.agentName}
            </span>
          )}
          {event.duration !== undefined && <span className="agent-flow__duration">{event.duration}ms</span>}
          {time && <span className="agent-flow__event-time">{time}</span>}
        </div>
        {event.message && (
          <div className="agent-flow__event-message">
            {renderMessage ? renderMessage(event.message) : <span>{event.message}</span>}
          </div>
        )}
        {event.tool && (
          <div className="agent-flow__event-tool">
            <div className="agent-flow__tool-header">
              <span className="agent-flow__tool-name">{event.tool}</span>
            </div>
            {event.argsJson && (
              <pre className="agent-flow__tool-args">{event.argsJson}</pre>
            )}
          </div>
        )}
        {event.result && (
          <div className="agent-flow__event-result">
            <div className="agent-flow__event-result-content">
              {renderResult ? renderResult(event.result) : <span>{event.result}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AgentFlow({
  url,
  theme = 'dark',
  autoConnect = false,
  maxEvents = 100000,
  renderMessage,
  renderResult,
}: AgentFlowProps) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState('disconnected');
  const eventsRef = useRef<AgentEvent[]>([]);
  const bufferRef = useRef<AgentEvent[]>([]);
  const rafRef = useRef<number | null>(null);
  const idRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      esRef.current?.close();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const flush = useCallback(() => {
    const buf = bufferRef.current;
    if (buf.length === 0 || !aliveRef.current) return;
    bufferRef.current = [];
    const newEvents = [...eventsRef.current, ...buf];
    eventsRef.current = newEvents.length > maxEvents
      ? newEvents.slice(newEvents.length - maxEvents)
      : newEvents;
    setEvents([...eventsRef.current]);
  }, [maxEvents]);

  const connect = useCallback(() => {
    esRef.current?.close();
    setStatus('connecting');
    const es = new EventSource(url);
    esRef.current = es;
    es.onopen = () => { if (aliveRef.current) setStatus('connected'); };
    es.onmessage = (e) => {
      if (!aliveRef.current) return;
      try {
        const data = JSON.parse(e.data);
        bufferRef.current.push({
          ...data,
          id: idRef.current++,
          timestamp: data.timestamp || Date.now(),
          argsJson: data.args ? JSON.stringify(data.args, null, 2) : undefined,
        });
        if (!rafRef.current) {
          rafRef.current = requestAnimationFrame(() => { rafRef.current = null; flush(); });
        }
      } catch { /* ignore */ }
    };
    es.onerror = () => {
      if (aliveRef.current) { setStatus('error'); es.close(); esRef.current = null; }
    };
  }, [url, flush]);

  useEffect(() => { if (autoConnect) connect(); }, [autoConnect, connect]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length]);

  return (
    <div className={`agent-flow agent-flow--${theme}`}>
      <div className="agent-flow__header">
        <div className="agent-flow__header-left">
          <span className="agent-flow__status">
            <span className={`agent-flow__status-dot agent-flow__status-dot--${status}`} />
            {status}
          </span>
          <span className="agent-flow__event-count">{events.length} events</span>
        </div>
        <div className="agent-flow__header-right">
          {status === 'disconnected' && (
            <button className="agent-flow__connect-btn" onClick={connect}>Connect</button>
          )}
        </div>
      </div>
      <div className="agent-flow__events-wrapper">
        <div ref={scrollRef} className="agent-flow__events">
          {events.length === 0 ? (
            <div className="agent-flow__empty">No events yet. Waiting for agent...</div>
          ) : (
            <div className="agent-flow__events-list">
              {events.map((evt) => (
                <div
                  key={evt.id}
                  className="agent-flow__event-row"
                >
                  <EventItem event={evt} renderMessage={renderMessage} renderResult={renderResult} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
