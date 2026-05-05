import type { PathDef, LaneType } from '../../types';
import { LANE_W, IX_R, ROAD_LEN } from '../../types';
import { lineLength } from '../../rendering/helpers';
import type { Scenario } from '../engine';

// Simple 2-phase: NS green alternation
const PHASES = ['NS_GREEN', 'NS_YELLOW', 'SN_GREEN', 'SN_YELLOW'] as const;

function buildStraightPath(cx: number, cy: number, approach: number, lane: LaneType): PathDef {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;

  // Only 2 approaches: 0=N (driving south), 2=S (driving north)
  // Lane layout: left (innermost), right (outermost) — no "through" needed
  const isN = approach === 0;
  const laneX = isN
    ? (lane === 'left' ? cx - LW : cx + LW)
    : (lane === 'left' ? cx + LW : cx - LW);

  const startY = isN ? cy - RL : cy + RL;
  const endY = isN ? cy + RL : cy - RL;
  const dir = isN ? 1 : -1;

  // Segment 0: approach → stop line
  const seg0 = {
    type: 'line' as const,
    x1: laneX, y1: startY, x2: laneX, y2: cy - dir * IR,
    length: lineLength(laneX, startY, laneX, cy - dir * IR),
  };

  // Segment 1: through intersection (straight)
  const seg1 = {
    type: 'line' as const,
    x1: laneX, y1: cy - dir * IR, x2: laneX, y2: cy + dir * IR,
    length: lineLength(laneX, cy - dir * IR, laneX, cy + dir * IR),
  };

  // Segment 2: exit road
  const seg2 = {
    type: 'line' as const,
    x1: laneX, y1: cy + dir * IR, x2: laneX, y2: endY,
    length: lineLength(laneX, cy + dir * IR, laneX, endY),
  };

  const segments = [seg0, seg1, seg2];
  const totalLength = segments.reduce((s, seg) => s + seg.length, 0);
  return { segments, totalLength, stopDistance: seg0.length };
}

export const straightRoadScenario: Scenario = {
  name: 'straightRoad',
  nameCN: '正常道路红绿灯',
  approaches: 2,
  phases: PHASES,
  phaseDuration: 6,

  getPaths(cx: number, cy: number): PathDef[][] {
    const paths: PathDef[][] = [];
    // Approach 0 = N, Approach 1 = S
    for (let a = 0; a < 2; a++) {
      const simApproach = a === 0 ? 0 : 2; // Map to N/S
      paths[a] = [
        buildStraightPath(cx, cy, simApproach, 'left'),
        buildStraightPath(cx, cy, simApproach, 'through'),
        buildStraightPath(cx, cy, simApproach, 'right'),
      ];
    }
    return paths;
  },

  isGreen(phase: string, approach: number, _lane: LaneType): boolean {
    if (phase.includes('YELLOW')) return false;
    if (phase === 'NS_GREEN') return approach === 0;
    if (phase === 'SN_GREEN') return approach === 1;
    return false;
  },

  getPhaseLabel(phase: string): string {
    const labels: Record<string, string> = {
      NS_GREEN: 'North Green', NS_YELLOW: 'North Yellow',
      SN_GREEN: 'South Green', SN_YELLOW: 'South Yellow',
    };
    return labels[phase] ?? phase;
  },
};
