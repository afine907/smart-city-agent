// ─── Geometry ────────────────────────────────────────────────
export interface Point {
  x: number;
  y: number;
}

export interface Position {
  x: number;
  y: number;
  angle: number;
}

// ─── Path System ─────────────────────────────────────────────
export interface LineSegment {
  type: 'line';
  x1: number; y1: number;
  x2: number; y2: number;
  length: number;
}

export interface BezierSegment {
  type: 'bezier';
  x1: number; y1: number;
  cp1x: number; cp1y: number;
  cp2x: number; cp2y: number;
  x2: number; y2: number;
  length: number;
}

export type PathSegment = LineSegment | BezierSegment;

export interface PathDef {
  segments: PathSegment[];
  totalLength: number;
  stopDistance: number;
}

// ─── Vehicle ─────────────────────────────────────────────────
export interface Vehicle {
  id: string;
  approach: number;
  lane: LaneType;
  distance: number;
  baseSpeed: number;
  speed: number;
  color: string;
  emergency: boolean;
  waiting: boolean;
  entryTime: number;
}

export type LaneType = 'left' | 'through' | 'right';

// ─── Scenario ────────────────────────────────────────────────
export interface ScenarioConfig {
  name: string;
  nameCN: string;
  approaches: number;
  hasSignals: boolean;
  phases: readonly string[];
  phaseDuration: number; // seconds per phase
}

// ─── Simulation State ────────────────────────────────────────
export interface SimState {
  vehicles: Vehicle[];
  currentPhase: string;
  phaseTimer: number;
  simStep: number;
  totalGenerated: number;
  totalCompleted: number;
  totalWaitTime: number;
  running: boolean;
}

// ─── SSE Events ──────────────────────────────────────────────
export interface SSEEvent {
  event_type: string;
  agent_id: string;
  timestamp: number;
  data: Record<string, unknown>;
  duration_ms?: number;
}

// ─── Constants ───────────────────────────────────────────────
export const LANE_W = 18;
export const ROAD_W = LANE_W * 6;  // 3 lanes per direction (left/through/right)
export const IX_R = 22;
export const ROAD_LEN = 220;
export const MIN_GAP = 28;
export const ACCEL = 0.12;
export const DECEL = 0.18;
export const BEZIER_SAMPLES = 24;

export const VEHICLE_COLORS = [
  '#00d4ff', '#00ff88', '#ffcc00', '#ff3366', '#bc8cff',
  '#ff8844', '#44ffdd', '#ff44aa', '#88aaff', '#ffaa44',
];
