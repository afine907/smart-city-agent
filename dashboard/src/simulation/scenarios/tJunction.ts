import type { PathDef, LaneType } from '../../types';
import { LANE_W, IX_R, ROAD_LEN } from '../../types';
import { lineLength, bezierLength } from '../../rendering/helpers';
import type { Scenario } from '../engine';

// 6-phase: N/S movements then E movement (no west approach)
const PHASES = ['NS_LEFT', 'NS_THROUGH', 'NS_YELLOW', 'ALL_RED', 'EW_THROUGH', 'EW_YELLOW'] as const;

function buildTPath(cx: number, cy: number, approach: number, lane: LaneType): PathDef {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;

  // T-junction: approaches 0=N, 1=E, 2=S (no West)
  // N/S roads vertical, E road horizontal (from east side)

  const configs: Record<number, Record<LaneType, { sx: number; sy: number; ex: number; ey: number }>> = {
    0: { // From North, driving South
      left:    { sx: cx - LW, sy: cy - RL, ex: cx + RL, ey: cy - LW },
      through: { sx: cx,      sy: cy - RL, ex: cx,      ey: cy + RL },
      right:   { sx: cx + LW, sy: cy - RL, ex: cx - RL, ey: cy + LW },
    },
    1: { // From East, driving West (can only go left or through)
      left:    { sx: cx + RL, sy: cy + LW, ex: cx,      ey: cy + RL },
      through: { sx: cx + RL, sy: cy,      ex: cx - RL, ey: cy },
      right:   { sx: cx + RL, sy: cy - LW, ex: cx,      ey: cy - RL },
    },
    2: { // From South, driving North
      left:    { sx: cx + LW, sy: cy + RL, ex: cx - RL, ey: cy + LW },
      through: { sx: cx,      sy: cy + RL, ex: cx,      ey: cy - RL },
      right:   { sx: cx - LW, sy: cy + RL, ex: cx + RL, ey: cy - LW },
    },
  };

  const cfg = configs[approach][lane];
  if (!cfg) {
    return { segments: [], totalLength: 0, stopDistance: 0 };
  }

  // Segment 0: approach road → stop line
  const s0x2 = approach === 1 ? cx + IR : approach === 0 || approach === 2 ? cfg.sx : cx - IR;
  const s0y2 = approach === 0 ? cy - IR : approach === 2 ? cy + IR : cfg.sy;

  const seg0 = {
    type: 'line' as const,
    x1: cfg.sx, y1: cfg.sy, x2: s0x2, y2: s0y2,
    length: lineLength(cfg.sx, cfg.sy, s0x2, s0y2),
  };

  // Segment 1: through intersection
  let seg1: PathDef['segments'][number];

  if (lane === 'through') {
    const e1x2 = approach === 1 ? cx - IR : cfg.ex;
    const e1y2 = approach === 0 ? cy + IR : approach === 2 ? cy - IR : cfg.ey;
    seg1 = {
      type: 'line' as const,
      x1: s0x2, y1: s0y2, x2: e1x2, y2: e1y2,
      length: lineLength(s0x2, s0y2, e1x2, e1y2),
    };
  } else {
    // Bezier turn
    const dx = approach === 1 ? -1 : 0;
    const dy = approach === 0 ? 1 : approach === 2 ? -1 : 0;
    const exitDx = approach === 0 || approach === 2 ? (lane === 'left' ? 1 : -1) : 0;
    const exitDy = approach === 1 ? (lane === 'left' ? 1 : -1) : 0;

    const cp1x = s0x2 + dx * 15;
    const cp1y = s0y2 + dy * 15;
    const cp2x = cfg.ex - exitDx * 15;
    const cp2y = cfg.ey - exitDy * 15;

    const bezierSeg = {
      type: 'bezier' as const,
      x1: s0x2, y1: s0y2,
      cp1x, cp1y, cp2x, cp2y,
      x2: cfg.ex, y2: cfg.ey,
      length: 0,
    };
    bezierSeg.length = bezierLength(bezierSeg);
    seg1 = bezierSeg;
  }

  // Segment 2: exit road
  const s2x1 = seg1.type === 'line' ? seg1.x2 : seg1.x2;
  const s2y1 = seg1.type === 'line' ? seg1.y2 : seg1.y2;
  const seg2 = {
    type: 'line' as const,
    x1: s2x1, y1: s2y1, x2: cfg.ex, y2: cfg.ey,
    length: lineLength(s2x1, s2y1, cfg.ex, cfg.ey),
  };

  const segments = [seg0, seg1, seg2];
  const totalLength = segments.reduce((s, seg) => s + seg.length, 0);
  return { segments, totalLength, stopDistance: seg0.length };
}

export const tJunctionScenario: Scenario = {
  name: 'tJunction',
  nameCN: '丁字路口',
  approaches: 3,
  phases: PHASES,
  phaseDuration: 5,

  getPaths(cx: number, cy: number): PathDef[][] {
    const paths: PathDef[][] = [];
    for (let a = 0; a < 3; a++) {
      paths[a] = [
        buildTPath(cx, cy, a, 'left'),
        buildTPath(cx, cy, a, 'through'),
        buildTPath(cx, cy, a, 'right'),
      ];
    }
    return paths;
  },

  isGreen(phase: string, approach: number, lane: LaneType): boolean {
    if (phase === 'ALL_RED' || phase.includes('YELLOW')) return false;
    const isNS = approach === 0 || approach === 2;
    const isEW = approach === 1;
    if (isNS && phase === 'NS_LEFT') return lane === 'left';
    if (isNS && phase === 'NS_THROUGH') return lane === 'through' || lane === 'right';
    if (isEW && phase === 'EW_THROUGH') return lane === 'through' || lane === 'left' || lane === 'right';
    return false;
  },

  getPhaseLabel(phase: string): string {
    const labels: Record<string, string> = {
      NS_LEFT: 'NS Left', NS_THROUGH: 'NS Through', NS_YELLOW: 'NS Yellow',
      ALL_RED: 'All Red', EW_THROUGH: 'EW Through', EW_YELLOW: 'EW Yellow',
    };
    return labels[phase] ?? phase;
  },
};
