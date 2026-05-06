import type { SSEEvent } from '../types';

interface Props {
  events: SSEEvent[];
}

export function EventLog({ events }: Props) {
  return (
    <div className="event-log">
      <div className="event-log-title">Agent Events</div>
      <div className="event-log-list">
        {events.slice(-10).reverse().map((e, i) => (
          <div key={i} className="event-item">
            <span className="event-type">{e.event_type}</span>
            <span className="event-agent">{e.agent_id}</span>
            <span className="event-detail">
              {typeof e.data?.decision === 'object'
                ? JSON.stringify(e.data.decision)
                : typeof e.data?.thought === 'string'
                  ? e.data.thought
                  : JSON.stringify(e.data).slice(0, 60)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
