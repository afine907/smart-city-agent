import type { PathDef, LaneType, SimState } from '../types';
import { MIN_GAP, ACCEL, DECEL } from '../types';
import { createVehicle, createEmergency } from './vehicle';
import type { SignalController, TrafficState } from './controller';
import { analyzeQueues } from './controller';

export interface Scenario {
  readonly name: string;
  readonly nameCN: string;
  readonly approaches: number;
  readonly phases: readonly string[];
  readonly phaseDuration: number;
  getPaths(cx: number, cy: number): PathDef[][];
  isGreen(phase: string, approach: number, lane: LaneType): boolean;
  getPhaseLabel(phase: string): string;
}

export class SimulationEngine {
  private scenario: Scenario;
  private paths: PathDef[][] = [];

  state: SimState = {
    vehicles: [],
    currentPhase: '',
    phaseTimer: 0,
    simStep: 0,
    totalGenerated: 0,
    totalCompleted: 0,
    totalWaitTime: 0,
    running: false,
  };

  controller: SignalController | null = null;

  private spawnTimer = 0;
  private phaseIndex = 0;

  constructor(scenario: Scenario) {
    this.scenario = scenario;
    this.state.currentPhase = scenario.phases[0];
  }

  setCenter(cx: number, cy: number): void {
    this.paths = this.scenario.getPaths(cx, cy);
  }

  getPaths(): PathDef[][] {
    return this.paths;
  }

  getPath(approach: number, lane: LaneType): PathDef | undefined {
    const laneIdx = lane === 'left' ? 0 : lane === 'through' ? 1 : 2;
    return this.paths[approach]?.[laneIdx];
  }

  private isGreen(approach: number, lane: LaneType): boolean {
    return this.scenario.isGreen(this.state.currentPhase, approach, lane);
  }

  spawn(): void {
    const laneTypes: LaneType[] = ['left', 'through', 'right'];

    for (let approach = 0; approach < this.scenario.approaches; approach++) {
      for (const lane of laneTypes) {
        const prob = lane === 'through' ? 0.4 : lane === 'left' ? 0.15 : 0.12;
        if (Math.random() < prob) {
          const path = this.getPath(approach, lane);
          if (!path) continue;

          const canSpawn = !this.state.vehicles.some(
            v => v.approach === approach && v.lane === lane && v.distance < 45,
          );
          if (canSpawn) {
            this.state.vehicles.push(createVehicle(approach, lane));
            this.state.totalGenerated++;
          }
        }
      }
    }

    if (this.state.vehicles.length > 150) {
      this.state.vehicles = this.state.vehicles.slice(-100);
    }
  }

  spawnEmergency(): void {
    const approach = Math.floor(Math.random() * this.scenario.approaches);
    this.state.vehicles.push(createEmergency(approach));
  }

  update(): void {
    const { vehicles } = this.state;

    for (let i = vehicles.length - 1; i >= 0; i--) {
      const v = vehicles[i];
      const path = this.getPath(v.approach, v.lane);
      if (!path) continue;

      // Emergency preemption
      if (v.emergency && v.distance > path.stopDistance * 0.3) {
        const targetPhase = (v.approach === 0 || v.approach === 2)
          ? 'NS_THROUGH' : 'EW_THROUGH';
        if (this.scenario.phases.includes(targetPhase) &&
            this.state.currentPhase !== targetPhase) {
          this.state.currentPhase = targetPhase;
          this.state.phaseTimer = 0;
        }
      }

      // Target speed
      let targetSpeed = v.baseSpeed;

      // Red light deceleration
      const shouldStop = !v.emergency && !this.isGreen(v.approach, v.lane);
      const distToStop = path.stopDistance - v.distance;
      if (shouldStop && distToStop > 0 && distToStop < 40) {
        targetSpeed = v.baseSpeed * Math.max(0, distToStop / 40);
      }

      // Car-following
      let minGap = Infinity;
      for (const other of vehicles) {
        if (other === v || other.approach !== v.approach || other.lane !== v.lane) continue;
        if (other.distance <= v.distance) continue;
        const gap = other.distance - v.distance;
        if (gap < minGap) minGap = gap;
      }
      if (minGap < MIN_GAP) {
        targetSpeed = 0;
      } else if (minGap < MIN_GAP * 2) {
        targetSpeed = Math.min(targetSpeed, v.baseSpeed * (minGap - MIN_GAP) / MIN_GAP);
      }

      // Smooth accel/decel
      if (v.speed < targetSpeed) {
        v.speed = Math.min(v.speed + ACCEL, targetSpeed);
      } else if (v.speed > targetSpeed) {
        v.speed = Math.max(v.speed - DECEL, targetSpeed);
      }

      v.waiting = v.speed < 0.05;
      v.distance += v.speed;

      // Remove completed
      if (v.distance >= path.totalLength) {
        this.state.totalCompleted++;
        this.state.totalWaitTime += (Date.now() - v.entryTime) / 1000;
        vehicles.splice(i, 1);
      }
    }
  }

  step(dt: number): void {
    // Spawn
    this.spawnTimer += dt;
    if (this.spawnTimer >= 0.4) {
      this.spawn();
      this.spawnTimer = 0;
    }

    // Phase control
    this.state.phaseTimer += dt;

    let controllerHandled = false;
    if (this.controller) {
      const trafficState = this.buildTrafficState();
      const decision = this.controller.decide(trafficState, this.scenario);
      if (decision) {
        if (decision.phase !== this.state.currentPhase) {
          this.state.currentPhase = decision.phase;
          this.state.phaseTimer = 0;
        }
        controllerHandled = true;
      }
    }

    // Default phase cycling — only when no controller or controller returned null
    if (!controllerHandled && this.state.phaseTimer >= this.scenario.phaseDuration) {
      this.phaseIndex = (this.phaseIndex + 1) % this.scenario.phases.length;
      this.state.currentPhase = this.scenario.phases[this.phaseIndex];
      this.state.phaseTimer = 0;
    }

    this.update();
    this.state.simStep++;
  }

  buildTrafficState(): TrafficState {
    return {
      vehicles: this.state.vehicles,
      currentPhase: this.state.currentPhase,
      phaseTimer: this.state.phaseTimer,
      simStep: this.state.simStep,
      queues: analyzeQueues(this.state.vehicles, this.scenario.approaches),
    };
  }

  reset(): void {
    this.state = {
      vehicles: [],
      currentPhase: this.scenario.phases[0],
      phaseTimer: 0,
      simStep: 0,
      totalGenerated: 0,
      totalCompleted: 0,
      totalWaitTime: 0,
      running: false,
    };
    this.phaseIndex = 0;
    this.spawnTimer = 0;
  }

  getMetrics() {
    const avgWait = this.state.totalCompleted > 0
      ? this.state.totalWaitTime / this.state.totalCompleted
      : 0;
    const throughput = this.state.simStep > 0
      ? (this.state.totalCompleted / this.state.simStep) * 60
      : 0;
    return {
      vehicles: this.state.vehicles.length,
      completed: this.state.totalCompleted,
      avgWait,
      throughput,
      simStep: this.state.simStep,
      phase: this.state.currentPhase,
    };
  }
}
