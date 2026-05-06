import type { PathDef, LaneType } from '../../types';
import { LANE_W, IX_R, ROAD_LEN } from '../../types';
import { lineLength, bezierLength } from '../../rendering/helpers';
import type { Scenario } from '../engine';

// 8-phase for diagonal intersection
const PHASES = ['NE_SW_LEFT', 'NE_SW_THROUGH', 'NE_SW_YELLOW', 'ALL_RED_1', 'NW_SE_LEFT', 'NW_SE_THROUGH', 'NW_SE_YELLOW', 'ALL_RED_2'] as const;

function buildXPath(cx: number, cy: number, approach: number, lane: LaneType): PathDef {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;

  // Diagonal approaches: 0=NE, 1=SE, 2=SW, 3=NW
  const angles = [-Math.PI / 4, Math.PI / 4, 3 * Math.PI / 4, -3 * Math.PI / 4];
  const ang = angles[approach];
  const perpAng = ang + Math.PI / 2;

  // Start position (road edge)
  const sx = cx + Math.cos(ang) * RL;
  const sy = cy - Math.sin(ang) * RL;

  // Lane offset (perpendicular to road direction)
  const lo = lane === 'left' ? -LW : lane === 'right' ? LW : 0;
  const lox = Math.cos(perpAng) * lo;
  const loy = -Math.sin(perpAng) * lo;

  // Entry to intersection
  const ex = cx + Math.cos(ang) * IR + lox;
  const ey = cy - Math.sin(ang) * IR + loy;

  // Exit depends on turn direction
  let exitAng: number;
  if (lane === 'through') {
    exitAng = ang + Math.PI;
  } else if (lane === 'left') {
    exitAng = ang + Math.PI / 2;
  } else {
    exitAng = ang - Math.PI / 2;
  }

  const exitX = cx + Math.cos(exitAng) * IR + lox;
  const exitY = cy - Math.sin(exitAng) * IR + loy;
  const endX = cx + Math.cos(exitAng) * RL;
  const endY = cy - Math.sin(exitAng) * RL;

  // Segment 0: approach
  const seg0 = {
    type: 'line' as const,
    x1: sx + lox, y1: sy + loy, x2: ex, y2: ey,
    length: lineLength(sx + lox, sy + loy, ex, ey),
  };

  // Segment 1: through intersection
  let seg1: PathDef['segments'][number];
  if (lane === 'through') {
    seg1 = {
      type: 'line' as const,
      x1: ex, y1: ey, x2: exitX, y2: exitY,
      length: lineLength(ex, ey, exitX, exitY),
    };
  } else {
    const cp1x = ex + Math.cos(ang) * 15;
    const cp1y = ey - Math.sin(ang) * 15;
    const cp2x = exitX - Math.cos(exitAng) * 15;
    const cp2y = exitY + Math.sin(exitAng) * 15;
    const bezierSeg = {
      type: 'bezier' as const,
      x1: ex, y1: ey, cp1x, cp1y, cp2x, cp2y, x2: exitX, y2: exitY,
      length: 0,
    };
    bezierSeg.length = bezierLength(bezierSeg);
    seg1 = bezierSeg;
  }

  // Segment 2: exit road
  const seg2 = {
    type: 'line' as const,
    x1: exitX, y1: exitY, x2: endX, y2: endY,
    length: lineLength(exitX, exitY, endX, endY),
  };

  const segments = [seg0, seg1, seg2];
  const totalLength = segments.reduce((s, seg) => s + seg.length, 0);
  return { segments, totalLength, stopDistance: seg0.length };
}

export const xIntersectionScenario: Scenario = {
  name: 'xIntersection',
  nameCN: 'X型路口',
  approaches: 4,
  phases: PHASES,
  phaseDuration: 5,

  getPaths(cx: number, cy: number): PathDef[][] {
    const paths: PathDef[][] = [];
    for (let a = 0; a < 4; a++) {
      paths[a] = [
        buildXPath(cx, cy, a, 'left'),
        buildXPath(cx, cy, a, 'through'),
        buildXPath(cx, cy, a, 'right'),
      ];
    }
    return paths;
  },

  isGreen(phase: string, approach: number, lane: LaneType): boolean {
    if (phase === 'ALL_RED_1' || phase === 'ALL_RED_2' || phase.includes('YELLOW')) return false;
    const isGroup1 = approach === 0 || approach === 2; // NE-SW
    const isGroup2 = approach === 1 || approach === 3; // NW-SE
    if (isGroup1 && phase === 'NE_SW_LEFT') return lane === 'left';
    if (isGroup1 && phase === 'NE_SW_THROUGH') return lane === 'through' || lane === 'right';
    if (isGroup2 && phase === 'NW_SE_LEFT') return lane === 'left';
    if (isGroup2 && phase === 'NW_SE_THROUGH') return lane === 'through' || lane === 'right';
    return false;
  },

  getPhaseLabel(phase: string): string {
    const labels: Record<string, string> = {
      NE_SW_LEFT: 'NE-SW Left', NE_SW_THROUGH: 'NE-SW Through', NE_SW_YELLOW: 'NE-SW Yellow',
      ALL_RED_1: 'All Red', NW_SE_LEFT: 'NW-SE Left', NW_SE_THROUGH: 'NW-SE Through',
      NW_SE_YELLOW: 'NW-SE Yellow', ALL_RED_2: 'All Red',
    };
    return labels[phase] ?? phase;
  },
};
