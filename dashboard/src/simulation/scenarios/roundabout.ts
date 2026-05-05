import type { PathDef, LaneType } from '../../types';
import { LANE_W, IX_R, ROAD_LEN } from '../../types';
import { lineLength, bezierLength } from '../../rendering/helpers';
import type { Scenario } from '../engine';

// Roundabout has no signal phases — yield on entry
const PHASES = ['CIRCULAR'] as const;
const RING_R = 50; // roundabout ring radius

function buildRoundaboutPath(cx: number, cy: number, approach: number, exitApproach: number): PathDef {
  const LW = LANE_W;
  const RL = ROAD_LEN;
  const IR = IX_R;

  // Approach roads: 0=N(top), 1=E(right), 2=S(bottom), 3=W(left)
  const approachStarts = [
    { x: cx, y: cy - RL },     // N
    { x: cx + RL, y: cy },     // E
    { x: cx, y: cy + RL },     // S
    { x: cx - RL, y: cy },     // W
  ];

  const approachEntries = [
    { x: cx + LW, y: cy - RING_R - IR }, // N entry (right lane)
    { x: cx + RING_R + IR, y: cy + LW }, // E entry
    { x: cx - LW, y: cy + RING_R + IR }, // S entry
    { x: cx - RING_R - IR, y: cy - LW }, // W entry
  ];

  // Ring entry points (where approach meets the ring)
  const ringEntries = [
    { x: cx + LW, y: cy - RING_R }, // N
    { x: cx + RING_R, y: cy + LW }, // E
    { x: cx - LW, y: cy + RING_R }, // S
    { x: cx - RING_R, y: cy - LW }, // W
  ];

  // Ring exit points
  const ringExits = [
    { x: cx - LW, y: cy - RING_R }, // N exit
    { x: cx + RING_R, y: cy - LW }, // E exit
    { x: cx + LW, y: cy + RING_R }, // S exit
    { x: cx - RING_R, y: cy + LW }, // W exit
  ];

  const exitEnds = [
    { x: cx, y: cy - RL },     // N
    { x: cx + RL, y: cy },     // E
    { x: cx, y: cy + RL },     // S
    { x: cx - RL, y: cy },     // W
  ];

  const start = approachStarts[approach];
  const entry = approachEntries[approach];
  const ringEntry = ringEntries[approach];
  const ringExit = ringExits[exitApproach];
  const exitEnd = exitEnds[exitApproach];

  // Segment 0: approach road → ring entry
  const seg0 = {
    type: 'line' as const,
    x1: start.x, y1: start.y, x2: entry.x, y2: entry.y,
    length: lineLength(start.x, start.y, entry.x, entry.y),
  };

  // Segment 1: ring arc (counterclockwise from entry to exit)
  // Simplified: use a Bezier curve through the ring
  const cp1x = ringEntry.x + (ringEntry.x - cx) * 0.3;
  const cp1y = ringEntry.y + (ringEntry.y - cy) * 0.3;
  const cp2x = ringExit.x + (ringExit.x - cx) * 0.3;
  const cp2y = ringExit.y + (ringExit.y - cy) * 0.3;

  const seg1 = {
    type: 'bezier' as const,
    x1: ringEntry.x, y1: ringEntry.y,
    cp1x, cp1y, cp2x, cp2y,
    x2: ringExit.x, y2: ringExit.y,
    length: 0,
  };
  seg1.length = bezierLength(seg1);

  // Segment 2: ring exit → road end
  const seg2 = {
    type: 'line' as const,
    x1: ringExit.x, y1: ringExit.y, x2: exitEnd.x, y2: exitEnd.y,
    length: lineLength(ringExit.x, ringExit.y, exitEnd.x, exitEnd.y),
  };

  const segments = [seg0, seg1, seg2];
  const totalLength = segments.reduce((s, seg) => s + seg.length, 0);
  return { segments, totalLength, stopDistance: seg0.length };
}

export const roundaboutScenario: Scenario = {
  name: 'roundabout',
  nameCN: '环形路口',
  approaches: 4,
  phases: PHASES,
  phaseDuration: 999, // No phase cycling

  getPaths(cx: number, cy: number): PathDef[][] {
    const paths: PathDef[][] = [];
    for (let a = 0; a < 4; a++) {
      // Each approach can exit to any of the other 3 roads
      // For simplicity: left → next CCW, through → opposite, right → next CW
      const exits = [(a + 3) % 4, (a + 2) % 4, (a + 1) % 4]; // left, through, right
      paths[a] = exits.map(exit => buildRoundaboutPath(cx, cy, a, exit));
    }
    return paths;
  },

  isGreen(_phase: string, _approach: number, _lane: LaneType): boolean {
    // Roundabout: always "green" — yield logic handled in engine
    return true;
  },

  getPhaseLabel(_phase: string): string {
    return 'Roundabout (Yield)';
  },
};
