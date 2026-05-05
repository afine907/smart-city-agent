import type { Position, PathDef, BezierSegment } from '../types';
import { BEZIER_SAMPLES } from '../types';

// ─── Cubic Bezier Evaluation ─────────────────────────────────

export function cubicBezierPoint(
  x1: number, y1: number,
  cp1x: number, cp1y: number,
  cp2x: number, cp2y: number,
  x2: number, y2: number,
  t: number,
): { x: number; y: number } {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const mt3 = mt2 * mt;
  const t2 = t * t;
  const t3 = t2 * t;
  return {
    x: mt3 * x1 + 3 * mt2 * t * cp1x + 3 * mt * t2 * cp2x + t3 * x2,
    y: mt3 * y1 + 3 * mt2 * t * cp1y + 3 * mt * t2 * cp2y + t3 * y2,
  };
}

export function cubicBezierAngle(
  x1: number, y1: number,
  cp1x: number, cp1y: number,
  cp2x: number, cp2y: number,
  x2: number, y2: number,
  t: number,
): number {
  const mt = 1 - t;
  const dx =
    3 * mt * mt * (cp1x - x1) +
    6 * mt * t * (cp2x - cp1x) +
    3 * t * t * (x2 - cp2x);
  const dy =
    3 * mt * mt * (cp1y - y1) +
    6 * mt * t * (cp2y - cp1y) +
    3 * t * t * (y2 - cp2y);
  return Math.atan2(dy, dx);
}

export function bezierLength(seg: BezierSegment): number {
  const { x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2 } = seg;
  let len = 0;
  let prev = cubicBezierPoint(x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2, 0);
  for (let i = 1; i <= BEZIER_SAMPLES; i++) {
    const t = i / BEZIER_SAMPLES;
    const cur = cubicBezierPoint(x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2, t);
    len += Math.hypot(cur.x - prev.x, cur.y - prev.y);
    prev = cur;
  }
  return len;
}

export function lineLength(x1: number, y1: number, x2: number, y2: number): number {
  return Math.hypot(x2 - x1, y2 - y1);
}

// ─── Path Interpolation ──────────────────────────────────────

export function getPositionOnPath(path: PathDef, distance: number): Position {
  let remaining = Math.max(0, Math.min(distance, path.totalLength));

  for (const seg of path.segments) {
    if (remaining > seg.length) {
      remaining -= seg.length;
      continue;
    }

    const t = seg.length > 0 ? remaining / seg.length : 0;

    if (seg.type === 'line') {
      return {
        x: seg.x1 + t * (seg.x2 - seg.x1),
        y: seg.y1 + t * (seg.y2 - seg.y1),
        angle: Math.atan2(seg.y2 - seg.y1, seg.x2 - seg.x1),
      };
    } else {
      const pos = cubicBezierPoint(
        seg.x1, seg.y1, seg.cp1x, seg.cp1y, seg.cp2x, seg.cp2y, seg.x2, seg.y2, t,
      );
      const angle = cubicBezierAngle(
        seg.x1, seg.y1, seg.cp1x, seg.cp1y, seg.cp2x, seg.cp2y, seg.x2, seg.y2, t,
      );
      return { ...pos, angle };
    }
  }

  // Fallback: at end of last segment
  const last = path.segments[path.segments.length - 1];
  if (!last) return { x: 0, y: 0, angle: 0 };
  if (last.type === 'line') {
    return { x: last.x2, y: last.y2, angle: Math.atan2(last.y2 - last.y1, last.x2 - last.x1) };
  }
  return {
    x: last.x2, y: last.y2,
    angle: cubicBezierAngle(last.x1, last.y1, last.cp1x, last.cp1y, last.cp2x, last.cp2y, last.x2, last.y2, 1),
  };
}

// ─── Canvas Helpers ──────────────────────────────────────────

export function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}
