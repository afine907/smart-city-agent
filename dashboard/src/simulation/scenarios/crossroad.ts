import type { PathDef, LaneType } from '../../types';
import { LANE_W, IX_R, ROAD_LEN } from '../../types';
import { lineLength, bezierLength } from '../../rendering/helpers';
import type { Scenario } from '../engine';

// 8-phase NEMA signal
const PHASES = ['NS_LEFT', 'NS_THROUGH', 'NS_YELLOW', 'ALL_RED_1', 'EW_LEFT', 'EW_THROUGH', 'EW_YELLOW', 'ALL_RED_2'] as const;

function buildPathDef(
  cx: number, cy: number,
  approach: number, lane: LaneType,
): PathDef {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;

  // Right-hand traffic: each approach's lanes are on the RIGHT side of the road
  // (from the driver's perspective). Yellow center line at cx/cy separates directions.
  const laneConfigs: Record<number, Record<LaneType, { x: number; y: number; exitX: number; exitY: number; dx: number; dy: number }>> = {
    0: { // From North, driving South — west side of road (x < cx)
      left:    { x: cx - LW * 0.5, y: 0, exitX: cx + RL,  exitY: cy - LW * 0.5, dx: 0, dy: 1 },
      through: { x: cx - LW * 1.5, y: 0, exitX: cx,       exitY: cy + RL,       dx: 0, dy: 1 },
      right:   { x: cx - LW * 2.5, y: 0, exitX: cx - RL,  exitY: cy - LW * 0.5, dx: 0, dy: 1 },
    },
    1: { // From East, driving West — north side of road (y < cy)
      left:    { x: 0, y: cy - LW * 0.5, exitX: cx - LW * 0.5, exitY: cy + RL, dx: -1, dy: 0 },
      through: { x: 0, y: cy - LW * 1.5, exitX: cx - RL,       exitY: cy,      dx: -1, dy: 0 },
      right:   { x: 0, y: cy - LW * 2.5, exitX: cx - LW * 0.5, exitY: cy - RL, dx: -1, dy: 0 },
    },
    2: { // From South, driving North — east side of road (x > cx)
      left:    { x: cx + LW * 0.5, y: 0, exitX: cx - RL,  exitY: cy + LW * 0.5, dx: 0, dy: -1 },
      through: { x: cx + LW * 1.5, y: 0, exitX: cx,       exitY: cy - RL,       dx: 0, dy: -1 },
      right:   { x: cx + LW * 2.5, y: 0, exitX: cx + RL,  exitY: cy + LW * 0.5, dx: 0, dy: -1 },
    },
    3: { // From West, driving East — south side of road (y > cy)
      left:    { x: 0, y: cy + LW * 0.5, exitX: cx + LW * 0.5, exitY: cy - RL, dx: 1, dy: 0 },
      through: { x: 0, y: cy + LW * 1.5, exitX: cx + RL,       exitY: cy,      dx: 1, dy: 0 },
      right:   { x: 0, y: cy + LW * 2.5, exitX: cx + LW * 0.5, exitY: cy + RL, dx: 1, dy: 0 },
    },
  };

  const cfg = laneConfigs[approach][lane];

  // Segment 0: approach road → stop line
  const s0x1 = approach === 1 ? cx + RL : approach === 3 ? cx - RL : cfg.x;
  const s0y1 = approach === 0 ? cy - RL : approach === 2 ? cy + RL : cfg.y;
  const s0x2 = approach === 1 ? cx + IR : approach === 3 ? cx - IR : cfg.x;
  const s0y2 = approach === 0 ? cy - IR : approach === 2 ? cy + IR : cfg.y;

  const seg0 = {
    type: 'line' as const,
    x1: s0x1, y1: s0y1, x2: s0x2, y2: s0y2,
    length: lineLength(s0x1, s0y1, s0x2, s0y2),
  };

  // Segment 1: through intersection
  let seg1: PathDef['segments'][number];

  if (lane === 'through') {
    // Straight through
    const e1x2 = approach === 1 ? cx - IR : approach === 3 ? cx + IR : cfg.x;
    const e1y2 = approach === 0 ? cy + IR : approach === 2 ? cy - IR : cfg.y;
    seg1 = {
      type: 'line' as const,
      x1: s0x2, y1: s0y2, x2: e1x2, y2: e1y2,
      length: lineLength(s0x2, s0y2, e1x2, e1y2),
    };
  } else {
    // Left or right turn — Bezier curve
    // Control points create a smooth 90° arc through the intersection
    let cp1x: number, cp1y: number, cp2x: number, cp2y: number;
    const p3x = approach === 1 ? cx + (lane === 'left' ? LW : -LW)
              : approach === 3 ? cx - (lane === 'left' ? LW : -LW)
              : cfg.exitX;
    const p3y = approach === 0 ? cy - (lane === 'left' ? LW : -LW)
              : approach === 2 ? cy + (lane === 'left' ? LW : -LW)
              : cfg.exitY;

    // Entry tangent control (pulls curve toward the approach direction)
    cp1x = s0x2 + cfg.dx * 15;
    cp1y = s0y2 + cfg.dy * 15;

    // Exit tangent control (pulls curve toward the exit direction)
    const exitDx = approach === 0 || approach === 2
      ? (lane === 'left' ? 1 : -1) : 0;
    const exitDy = approach === 1 || approach === 3
      ? (lane === 'left' ? -1 : 1) : 0;
    cp2x = p3x - exitDx * 15;
    cp2y = p3y - exitDy * 15;

    const bezierSeg = {
      type: 'bezier' as const,
      x1: s0x2, y1: s0y2,
      cp1x, cp1y, cp2x, cp2y,
      x2: p3x, y2: p3y,
      length: 0,
    };
    bezierSeg.length = bezierLength(bezierSeg);
    seg1 = bezierSeg;
  }

  // Segment 2: exit road
  const s2x1 = seg1.type === 'line' ? seg1.x2 : seg1.x2;
  const s2y1 = seg1.type === 'line' ? seg1.y2 : seg1.y2;
  const s2x2 = cfg.exitX;
  const s2y2 = cfg.exitY;

  const seg2 = {
    type: 'line' as const,
    x1: s2x1, y1: s2y1, x2: s2x2, y2: s2y2,
    length: lineLength(s2x1, s2y1, s2x2, s2y2),
  };

  const segments = [seg0, seg1, seg2];
  const totalLength = segments.reduce((s, seg) => s + seg.length, 0);

  return { segments, totalLength, stopDistance: seg0.length };
}

export const crossroadScenario: Scenario = {
  name: 'crossroad',
  nameCN: '十字路口',
  approaches: 4,
  phases: PHASES,
  phaseDuration: 5,

  getPaths(cx: number, cy: number): PathDef[][] {
    const paths: PathDef[][] = [];
    for (let a = 0; a < 4; a++) {
      paths[a] = [
        buildPathDef(cx, cy, a, 'left'),
        buildPathDef(cx, cy, a, 'through'),
        buildPathDef(cx, cy, a, 'right'),
      ];
    }
    return paths;
  },

  isGreen(phase: string, approach: number, lane: LaneType): boolean {
    if (phase === 'ALL_RED_1' || phase === 'ALL_RED_2' || phase.includes('YELLOW')) return false;
    const isNS = approach === 0 || approach === 2;
    const isEW = approach === 1 || approach === 3;
    if (isNS && phase === 'NS_LEFT') return lane === 'left';
    if (isNS && phase === 'NS_THROUGH') return lane === 'through' || lane === 'right';
    if (isEW && phase === 'EW_LEFT') return lane === 'left';
    if (isEW && phase === 'EW_THROUGH') return lane === 'through' || lane === 'right';
    return false;
  },

  getPhaseLabel(phase: string): string {
    const labels: Record<string, string> = {
      NS_LEFT: 'NS Left',
      NS_THROUGH: 'NS Through',
      NS_YELLOW: 'NS Yellow',
      ALL_RED_1: 'All Red',
      EW_LEFT: 'EW Left',
      EW_THROUGH: 'EW Through',
      EW_YELLOW: 'EW Yellow',
      ALL_RED_2: 'All Red',
    };
    return labels[phase] ?? phase;
  },
};
