import type { Vehicle, LaneType } from '../types';
import type { Scenario } from './engine';

// ─── Types ──────────────────────────────────────────────────

export interface QueueLengths {
  /** Total waiting vehicles per approach */
  byApproach: number[];
  /** Total waiting vehicles per (approach, lane) */
  byLane: Map<string, number>;
  /** Total waiting vehicles across all approaches */
  total: number;
}

export interface TrafficState {
  vehicles: Vehicle[];
  currentPhase: string;
  phaseTimer: number;
  simStep: number;
  queues: QueueLengths;
}

export interface ControllerDecision {
  phase: string;
  duration: number;
}

export interface SignalController {
  readonly name: string;
  decide(state: TrafficState, scenario: Scenario): ControllerDecision | null;
}

// ─── Helpers ────────────────────────────────────────────────

const LANE_TYPES: LaneType[] = ['left', 'through', 'right'];

export function analyzeQueues(vehicles: Vehicle[], approaches: number): QueueLengths {
  const byApproach = new Array(approaches).fill(0) as number[];
  const byLane = new Map<string, number>();

  for (const v of vehicles) {
    if (!v.waiting) continue;
    const key = `${v.approach}_${v.lane}`;
    byLane.set(key, (byLane.get(key) ?? 0) + 1);
    if (v.approach < approaches) {
      byApproach[v.approach]++;
    }
  }

  const total = byApproach.reduce((s, n) => s + n, 0);
  return { byApproach, byLane, total };
}

function isGreenPhase(phase: string): boolean {
  return !phase.includes('YELLOW') && !phase.startsWith('ALL_RED');
}

// ─── Fixed Timer Controller ─────────────────────────────────

export class FixedTimerController implements SignalController {
  readonly name = 'Fixed Timer';

  decide(): ControllerDecision | null {
    return null; // Let engine use its default phase cycling
  }
}

// ─── Adaptive Controller ────────────────────────────────────

export class AdaptiveController implements SignalController {
  readonly name = 'Adaptive';

  private readonly minGreen = 3;
  private readonly maxGreen = 15;
  private readonly switchThreshold = 3; // Min queue to justify a switch

  decide(state: TrafficState, scenario: Scenario): ControllerDecision | null {
    const { currentPhase, phaseTimer, queues } = state;

    // Roundabout has no signals — nothing to control
    if (scenario.phases.length === 1 && scenario.phases[0] === 'CIRCULAR') {
      return null;
    }

    // Don't switch during yellow/all-red — let them play out
    if (!isGreenPhase(currentPhase)) {
      return null;
    }

    // Don't switch before minimum green time
    if (phaseTimer < this.minGreen) {
      return null;
    }

    // Compute demand for each green phase
    const demands = this.computePhaseDemands(scenario, queues);

    // Find best phase (highest demand)
    let bestPhase = currentPhase;
    let bestDemand = demands.get(currentPhase) ?? 0;

    for (const [phase, demand] of demands) {
      if (demand > bestDemand) {
        bestDemand = demand;
        bestPhase = phase;
      }
    }

    // If current phase still has enough demand and under max green, extend
    const currentDemand = demands.get(currentPhase) ?? 0;
    if (currentDemand > 0 && phaseTimer < this.maxGreen && bestPhase === currentPhase) {
      return { phase: currentPhase, duration: this.maxGreen };
    }

    // Switch if another phase has significantly more demand
    if (bestPhase !== currentPhase && bestDemand > this.switchThreshold) {
      return { phase: bestPhase, duration: this.maxGreen };
    }

    // Current phase exhausted or no strong demand anywhere — let engine cycle
    if (phaseTimer >= this.maxGreen) {
      return null;
    }

    // Keep current phase
    return { phase: currentPhase, duration: this.maxGreen };
  }

  private computePhaseDemands(
    scenario: Scenario,
    queues: QueueLengths,
  ): Map<string, number> {
    const demands = new Map<string, number>();

    for (const phase of scenario.phases) {
      if (!isGreenPhase(phase)) continue;

      let demand = 0;
      for (let approach = 0; approach < scenario.approaches; approach++) {
        for (const lane of LANE_TYPES) {
          if (scenario.isGreen(phase, approach, lane)) {
            const key = `${approach}_${lane}`;
            demand += queues.byLane.get(key) ?? 0;
          }
        }
      }
      demands.set(phase, demand);
    }

    return demands;
  }
}
