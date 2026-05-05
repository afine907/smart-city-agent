import type { Scenario } from '../simulation/engine';

interface Props {
  scenarios: Scenario[];
  current: string;
  onSelect: (name: string) => void;
}

export function ScenarioSelector({ scenarios, current, onSelect }: Props) {
  return (
    <div className="scenario-selector">
      {scenarios.map(s => (
        <button
          key={s.name}
          className={`scenario-btn ${s.name === current ? 'active' : ''}`}
          onClick={() => onSelect(s.name)}
        >
          {s.nameCN}
        </button>
      ))}
    </div>
  );
}
