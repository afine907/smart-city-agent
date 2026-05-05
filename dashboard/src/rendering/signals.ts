import { ROAD_W, IX_R } from '../types';

const GREEN = '#00ff88';
const RED = '#ff3366';
const YELLOW_COL = '#ffcc00';

interface SignalState {
  green: boolean;
  yellow?: boolean;
}

function drawSignalBox(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  vertical: boolean,
  signals: SignalState[],
): void {
  const w = vertical ? 10 : signals.length * 12;
  const h = vertical ? signals.length * 12 : 10;

  // Housing
  ctx.fillStyle = '#1a1a2e';
  ctx.strokeStyle = '#333355';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(x - w / 2, y - h / 2, w, h, 3);
  ctx.fill();
  ctx.stroke();

  // Lights
  signals.forEach((s, i) => {
    const lx = vertical ? x : x - w / 2 + 6 + i * 12;
    const ly = vertical ? y - h / 2 + 6 + i * 12 : y;

    ctx.beginPath();
    ctx.arc(lx, ly, 3.5, 0, Math.PI * 2);

    if (s.green) {
      ctx.fillStyle = GREEN;
      ctx.shadowColor = GREEN;
      ctx.shadowBlur = 6;
    } else if (s.yellow) {
      ctx.fillStyle = YELLOW_COL;
      ctx.shadowColor = YELLOW_COL;
      ctx.shadowBlur = 6;
    } else {
      ctx.fillStyle = RED;
      ctx.shadowColor = RED;
      ctx.shadowBlur = 6;
    }
    ctx.fill();
    ctx.shadowBlur = 0;
  });
}

export function drawCrossroadSignals(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  phase: string,
): void {
  const halfRoad = ROAD_W / 2;
  const IR = IX_R;

  const isNSGreen = phase.startsWith('NS_') && !phase.includes('YELLOW');
  const isEWGreen = phase.startsWith('EW_') && !phase.includes('YELLOW');
  const isNSYellow = phase === 'NS_YELLOW';
  const isEWYellow = phase === 'EW_YELLOW';
  const isNSLeft = phase === 'NS_LEFT';
  const isEWLeft = phase === 'EW_LEFT';

  // N approach signals
  drawSignalBox(ctx, cx + halfRoad + 14, cy - IR - 10, true, [
    { green: isNSLeft },
    { green: isNSGreen || isNSYellow, yellow: isNSYellow },
  ]);
  // S approach
  drawSignalBox(ctx, cx - halfRoad - 14, cy + IR + 10, true, [
    { green: isNSLeft },
    { green: isNSGreen || isNSYellow, yellow: isNSYellow },
  ]);
  // E approach
  drawSignalBox(ctx, cx + IR + 10, cy + halfRoad + 14, false, [
    { green: isEWLeft },
    { green: isEWGreen || isEWYellow, yellow: isEWYellow },
  ]);
  // W approach
  drawSignalBox(ctx, cx - IR - 10, cy - halfRoad - 14, false, [
    { green: isEWLeft },
    { green: isEWGreen || isEWYellow, yellow: isEWYellow },
  ]);

  // Phase name in center
  const phaseColor = phase.includes('NS') ? GREEN : phase.includes('EW') ? '#00d4ff' : YELLOW_COL;
  ctx.font = '700 10px "SF Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = phaseColor;
  ctx.fillText(phase, cx, cy);
}

export function drawTJunctionSignals(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  phase: string,
): void {
  const halfRoad = ROAD_W / 2;
  const IR = IX_R;

  const isNSGreen = phase.startsWith('NS_') && !phase.includes('YELLOW');
  const isEWGreen = phase === 'EW_THROUGH';
  const isNSYellow = phase === 'NS_YELLOW';
  const isEWYellow = phase === 'EW_YELLOW';

  drawSignalBox(ctx, cx + halfRoad + 14, cy - IR - 10, true, [
    { green: phase === 'NS_LEFT' },
    { green: isNSGreen || isNSYellow, yellow: isNSYellow },
  ]);
  drawSignalBox(ctx, cx - halfRoad - 14, cy + IR + 10, true, [
    { green: phase === 'NS_LEFT' },
    { green: isNSGreen || isNSYellow, yellow: isNSYellow },
  ]);
  drawSignalBox(ctx, cx + IR + 10, cy + halfRoad + 14, false, [
    { green: isEWGreen || isEWYellow, yellow: isEWYellow },
  ]);

  ctx.font = '700 10px "SF Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#00ff88';
  ctx.fillText(phase, cx, cy);
}

export function drawStraightSignals(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  phase: string,
): void {
  const halfRoad = ROAD_W / 2;
  const IR = IX_R;

  const nGreen = phase === 'NS_GREEN';
  const sGreen = phase === 'SN_GREEN';
  const nYellow = phase === 'NS_YELLOW';
  const sYellow = phase === 'SN_YELLOW';

  drawSignalBox(ctx, cx + halfRoad + 14, cy - IR, true, [
    { green: nGreen || nYellow, yellow: nYellow },
  ]);
  drawSignalBox(ctx, cx - halfRoad - 14, cy + IR, true, [
    { green: sGreen || sYellow, yellow: sYellow },
  ]);

  ctx.font = '700 10px "SF Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#00ff88';
  ctx.fillText(phase, cx, cy);
}
