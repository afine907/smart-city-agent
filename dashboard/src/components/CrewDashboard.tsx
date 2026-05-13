import { useState, useEffect } from 'react';
import { AgentFlow } from 'agent-sse-flow';
import 'agent-sse-flow/style.css';

interface PipelineMetrics {
  layer: string;
  rule_hit_rate: number;
  cache_hit_rate: number;
  llm_calls: number;
  total_decisions: number;
}

interface IntersectionState {
  phase: string;
  queue_total: number;
}

interface SimState {
  step: number;
  intersections: Record<string, IntersectionState>;
  pipeline: PipelineMetrics;
}

interface Props {
  running: boolean;
}

export function CrewDashboard({ running }: Props) {
  const [state, setState] = useState<SimState | null>(null);

  useEffect(() => {
    if (!running) {
      setState(null);
      return;
    }

    const poll = async () => {
      try {
        const res = await fetch('/api/simulation/state');
        if (res.ok) {
          const data = await res.json();
          if (data && data.step !== undefined) {
            setState(data);
          }
        }
      } catch {
        // server not ready yet
      }
    };

    poll();
    const interval = setInterval(poll, 500);
    return () => clearInterval(interval);
  }, [running]);

  const pipeline = state?.pipeline;

  return (
    <div className="crew-dashboard">
      <div className="crew-flow">
        <AgentFlow
          url="/api/crewai/stream"
          theme="dark"
          autoConnect={running}
          maxEvents={10000}
        />
      </div>

      <div className="crew-sidebar">
        {pipeline && (
          <div className="pipeline-panel">
            <div className="pipeline-title">Pipeline Stats</div>
            <div className="pipeline-layer">
              Active Layer:
              <span className={`layer-badge layer-${pipeline.layer}`}>
                {pipeline.layer.toUpperCase()}
              </span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Rule Hits</span>
              <span className="stat-value">{(pipeline.rule_hit_rate * 100).toFixed(0)}%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Cache Hits</span>
              <span className="stat-value">{(pipeline.cache_hit_rate * 100).toFixed(0)}%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">LLM Calls</span>
              <span className="stat-value">{pipeline.llm_calls}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Decisions</span>
              <span className="stat-value">{pipeline.total_decisions}</span>
            </div>
          </div>
        )}

        {state?.intersections && (
          <div className="ix-panel">
            <div className="pipeline-title">Intersections</div>
            {Object.entries(state.intersections).map(([id, ix]) => (
              <div key={id} className="ix-row">
                <span className={`ix-phase-dot ${ix.phase.includes('NS') ? 'ns' : 'ew'}`} />
                <span className="ix-id">{id}</span>
                <span className="ix-queue">Q: {ix.queue_total}</span>
              </div>
            ))}
          </div>
        )}

        {state && (
          <div className="step-indicator">
            Step: {state.step}
          </div>
        )}
      </div>
    </div>
  );
}
