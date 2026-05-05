import { useState, useCallback, useMemo } from 'react';
import { IntersectionCanvas } from './components/IntersectionCanvas';
import { StatsPanel } from './components/StatsPanel';
import { SignalIndicator } from './components/SignalIndicator';
import { EventLog } from './components/EventLog';
import { ScenarioSelector } from './components/ScenarioSelector';
import { scenarioList, getScenario } from './simulation/scenarios';
import type { Scenario } from './simulation/engine';
import type { SignalController } from './simulation/controller';
import { FixedTimerController, AdaptiveController } from './simulation/controller';
import { useSSE } from './sse';

interface Metrics {
  vehicles: number;
  completed: number;
  avgWait: number;
  throughput: number;
  simStep: number;
  phase: string;
}

type ControllerMode = 'fixed' | 'adaptive';

const CONTROLLER_MAP: Record<ControllerMode, () => SignalController> = {
  fixed: () => new FixedTimerController(),
  adaptive: () => new AdaptiveController(),
};

export default function App() {
  const [scenarioName, setScenarioName] = useState('crossroad');
  const [scenario, setScenario] = useState<Scenario>(() => getScenario('crossroad'));
  const [controllerMode, setControllerMode] = useState<ControllerMode>('fixed');
  const [metrics, setMetrics] = useState<Metrics>({
    vehicles: 0, completed: 0, avgWait: 0, throughput: 0, simStep: 0, phase: '',
  });
  const [running, setRunning] = useState(false);

  const controller = useMemo(() => CONTROLLER_MAP[controllerMode](), [controllerMode]);

  const { connected, events: sseEvents } = useSSE('/api/events/stream');

  const handleScenarioChange = useCallback((name: string) => {
    setScenarioName(name);
    setScenario(getScenario(name));
    setRunning(false);
  }, []);

  const handleMetrics = useCallback((m: Metrics) => {
    setMetrics(m);
  }, []);

  const handleStart = useCallback(() => {
    setRunning(prev => !prev);
  }, []);

  const handleEmergency = useCallback(() => {
    const canvas = document.querySelector('canvas');
    if (canvas) {
      const engine = (canvas as unknown as Record<string, unknown>).__engine as { spawnEmergency: () => void } | null;
      engine?.spawnEmergency();
    }
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1 className="title">Traffic Agent</h1>
          <span className="subtitle">LLM Traffic Controller</span>
        </div>
        <div className="header-center">
          <ScenarioSelector
            scenarios={scenarioList}
            current={scenarioName}
            onSelect={handleScenarioChange}
          />
        </div>
        <div className="header-right">
          <div className="controller-toggle">
            <button
              className={`btn btn-mode ${controllerMode === 'fixed' ? 'active' : ''}`}
              onClick={() => setControllerMode('fixed')}
            >
              Fixed
            </button>
            <button
              className={`btn btn-mode ${controllerMode === 'adaptive' ? 'active' : ''}`}
              onClick={() => setControllerMode('adaptive')}
            >
              Adaptive
            </button>
          </div>
          <div className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <button className="btn btn-start" onClick={handleStart}>
            {running ? '⏸ Pause' : '▶ Start'}
          </button>
          <button className="btn btn-emergency" onClick={handleEmergency}>
            🚑 Emergency
          </button>
        </div>
      </header>

      <main className="main">
        <IntersectionCanvas
          scenario={scenario}
          controller={controller}
          onMetrics={handleMetrics}
        />
      </main>

      <aside className="sidebar">
        <SignalIndicator
          phase={metrics.phase}
          phaseTimer={0}
          phaseDuration={scenario.phaseDuration}
          getPhaseLabel={scenario.getPhaseLabel}
        />
        <StatsPanel
          vehicles={metrics.vehicles}
          completed={metrics.completed}
          avgWait={metrics.avgWait}
          throughput={metrics.throughput}
          simStep={metrics.simStep}
        />
        <EventLog events={sseEvents} />
      </aside>
    </div>
  );
}
