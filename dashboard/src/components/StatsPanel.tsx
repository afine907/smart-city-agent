interface Props {
  vehicles: number;
  completed: number;
  avgWait: number;
  throughput: number;
  simStep: number;
}

export function StatsPanel({ vehicles, completed, avgWait, throughput, simStep }: Props) {
  return (
    <div className="stats-panel">
      <div className="stat-item">
        <span className="stat-label">Vehicles</span>
        <span className="stat-value" id="s3">{vehicles}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Completed</span>
        <span className="stat-value" id="s1">{completed}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Avg Wait</span>
        <span className="stat-value" id="s2">{avgWait.toFixed(1)}s</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Throughput</span>
        <span className="stat-value" id="s6">{throughput.toFixed(1)}/min</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Step</span>
        <span className="stat-value" id="s5">{simStep}</span>
      </div>
    </div>
  );
}
