import { useState, useCallback } from 'react';
import { CrewDashboard } from './components/CrewDashboard';

export default function App() {
  const [running, setRunning] = useState(false);

  const handleStart = useCallback(async () => {
    if (running) {
      await fetch('/api/simulation/stop', { method: 'POST' });
      setRunning(false);
    } else {
      const res = await fetch('/api/simulation/start?mode=crewai&steps=200', { method: 'POST' });
      if (res.ok) {
        setRunning(true);
      }
    }
  }, [running]);

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1 className="title">Traffic Agent</h1>
          <span className="subtitle">CrewAI Multi-Agent Controller</span>
        </div>
        <div className="header-right">
          <button className="btn btn-start" onClick={handleStart}>
            {running ? 'Stop' : 'Start'}
          </button>
        </div>
      </header>

      <main className="main">
        <CrewDashboard running={running} />
      </main>
    </div>
  );
}
