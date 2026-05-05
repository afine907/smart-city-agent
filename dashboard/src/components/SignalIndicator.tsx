interface Props {
  phase: string;
  phaseTimer: number;
  phaseDuration: number;
  getPhaseLabel: (phase: string) => string;
}

export function SignalIndicator({ phase, phaseTimer, phaseDuration, getPhaseLabel }: Props) {
  const progress = phaseDuration > 0 ? Math.min(phaseTimer / phaseDuration, 1) : 0;
  const isGreen = phase.includes('THROUGH') || phase.includes('LEFT') || phase === 'NS_GREEN' || phase === 'SN_GREEN' || phase === 'CIRCULAR';
  const isYellow = phase.includes('YELLOW');
  const color = isYellow ? '#ffcc00' : isGreen ? '#00ff88' : '#ff3366';

  return (
    <div className="signal-indicator">
      <div className="signal-phase" style={{ color }}>
        {getPhaseLabel(phase)}
      </div>
      <div className="signal-timer">
        <div className="signal-bar">
          <div
            className="signal-fill"
            style={{ width: `${(1 - progress) * 100}%`, backgroundColor: color }}
          />
        </div>
      </div>
    </div>
  );
}
