import type { Scenario } from '../engine';
import { crossroadScenario } from './crossroad';
import { tJunctionScenario } from './tJunction';
import { roundaboutScenario } from './roundabout';
import { xIntersectionScenario } from './xIntersection';
import { straightRoadScenario } from './straightRoad';

export const scenarios: Record<string, Scenario> = {
  crossroad: crossroadScenario,
  tJunction: tJunctionScenario,
  roundabout: roundaboutScenario,
  xIntersection: xIntersectionScenario,
  straightRoad: straightRoadScenario,
};

export const scenarioList = Object.values(scenarios);

export function getScenario(name: string): Scenario {
  return scenarios[name] ?? crossroadScenario;
}
