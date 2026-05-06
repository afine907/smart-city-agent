import { LANE_W, ROAD_W, IX_R, ROAD_LEN } from '../types';

const YELLOW = '#cc9900';
const WHITE_DASH = '#2a2a4a';
const WHITE_SOLID = '#3a3a5a';
const CROSSWALK = '#1e1e3a';

export function drawCrossroadMarkings(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;
  const halfRoad = ROAD_W / 2;

  // ─── Yellow center lines (N-S) ─────────────────────────────
  ctx.strokeStyle = YELLOW;
  ctx.lineWidth = 2;
  ctx.setLineDash([]);
  // North approach
  ctx.beginPath();
  ctx.moveTo(cx, cy - RL); ctx.lineTo(cx, cy - halfRoad);
  // South approach
  ctx.moveTo(cx, cy + halfRoad); ctx.lineTo(cx, cy + RL);
  ctx.stroke();

  // ─── Yellow center lines (E-W) ─────────────────────────────
  // East approach
  ctx.beginPath();
  ctx.moveTo(cx + halfRoad, cy); ctx.lineTo(cx + RL, cy);
  // West approach
  ctx.moveTo(cx - RL, cy); ctx.lineTo(cx - halfRoad, cy);
  ctx.stroke();

  // ─── White dashed lane dividers (between lanes in same direction) ────
  ctx.strokeStyle = WHITE_DASH;
  ctx.lineWidth = 1;
  ctx.setLineDash([8, 12]);

  // N-S dividers: 2 dividers per side (separating left/through/right)
  for (const dx of [-LW, -LW * 2, LW, LW * 2]) {
    ctx.beginPath();
    ctx.moveTo(cx + dx, cy - RL); ctx.lineTo(cx + dx, cy - halfRoad);
    ctx.moveTo(cx + dx, cy + halfRoad); ctx.lineTo(cx + dx, cy + RL);
    ctx.stroke();
  }

  // E-W dividers
  for (const dy of [-LW, -LW * 2, LW, LW * 2]) {
    ctx.beginPath();
    ctx.moveTo(cx - RL, cy + dy); ctx.lineTo(cx - halfRoad, cy + dy);
    ctx.moveTo(cx + halfRoad, cy + dy); ctx.lineTo(cx + RL, cy + dy);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // ─── Crosswalks ────────────────────────────────────────────
  drawCrosswalk(ctx, cx, cy - halfRoad - 4, true);
  drawCrosswalk(ctx, cx, cy + halfRoad + 4, true);
  drawCrosswalk(ctx, cx - halfRoad - 4, cy, false);
  drawCrosswalk(ctx, cx + halfRoad + 4, cy, false);

  // ─── Stop lines ────────────────────────────────────────────
  ctx.strokeStyle = WHITE_SOLID;
  ctx.lineWidth = 2.5;
  // North
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - IR); ctx.lineTo(cx + halfRoad, cy - IR);
  // South
  ctx.moveTo(cx - halfRoad, cy + IR); ctx.lineTo(cx + halfRoad, cy + IR);
  // East
  ctx.moveTo(cx + IR, cy - halfRoad); ctx.lineTo(cx + IR, cy + halfRoad);
  // West
  ctx.moveTo(cx - IR, cy - halfRoad); ctx.lineTo(cx - IR, cy + halfRoad);
  ctx.stroke();
}

export function drawTJunctionMarkings(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;
  const halfRoad = ROAD_W / 2;

  // Yellow center lines (N-S)
  ctx.strokeStyle = YELLOW;
  ctx.lineWidth = 2;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(cx, cy - RL); ctx.lineTo(cx, cy + halfRoad);
  ctx.stroke();

  // Yellow center lines (E-W, from east)
  ctx.beginPath();
  ctx.moveTo(cx + halfRoad, cy); ctx.lineTo(cx + RL, cy);
  ctx.stroke();

  // White dividers
  ctx.strokeStyle = WHITE_DASH;
  ctx.lineWidth = 1;
  ctx.setLineDash([8, 12]);
  for (const dx of [-LW, -LW * 2, LW, LW * 2]) {
    ctx.beginPath();
    ctx.moveTo(cx + dx, cy - RL); ctx.lineTo(cx + dx, cy - halfRoad);
    ctx.moveTo(cx + dx, cy + halfRoad); ctx.lineTo(cx + dx, cy + RL);
    ctx.stroke();
  }
  for (const dy of [-LW, -LW * 2, LW, LW * 2]) {
    ctx.beginPath();
    ctx.moveTo(cx - halfRoad, cy + dy); ctx.lineTo(cx + RL, cy + dy);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // Stop lines
  ctx.strokeStyle = WHITE_SOLID;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - IR); ctx.lineTo(cx + halfRoad, cy - IR);
  ctx.moveTo(cx + IR, cy - halfRoad); ctx.lineTo(cx + IR, cy + halfRoad);
  ctx.stroke();
}

export function drawRoundaboutMarkings(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const ringR = 50;

  // Yield lines at entries
  ctx.strokeStyle = WHITE_SOLID;
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 4]);

  // N entry
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - ringR - 2); ctx.lineTo(cx + halfRoad, cy - ringR - 2);
  // S entry
  ctx.moveTo(cx - halfRoad, cy + ringR + 2); ctx.lineTo(cx + halfRoad, cy + ringR + 2);
  // E entry
  ctx.moveTo(cx + ringR + 2, cy - halfRoad); ctx.lineTo(cx + ringR + 2, cy + halfRoad);
  // W entry
  ctx.moveTo(cx - ringR - 2, cy - halfRoad); ctx.lineTo(cx - ringR - 2, cy + halfRoad);
  ctx.stroke();
  ctx.setLineDash([]);

  // Direction arrows on ring
  ctx.fillStyle = '#3a3a5a';
  ctx.font = '14px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('↻', cx + ringR + 22, cy);
  ctx.fillText('↻', cx - ringR - 22, cy);
  ctx.fillText('↻', cx, cy - ringR - 22);
  ctx.fillText('↻', cx, cy + ringR + 22);
}

export function drawStraightRoadMarkings(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const LW = LANE_W;
  const IR = IX_R;
  const RL = ROAD_LEN;
  const halfRoad = ROAD_W / 2;

  // Yellow center line
  ctx.strokeStyle = YELLOW;
  ctx.lineWidth = 2;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(cx, cy - RL); ctx.lineTo(cx, cy - halfRoad);
  ctx.moveTo(cx, cy + halfRoad); ctx.lineTo(cx, cy + RL);
  ctx.stroke();

  // White dividers
  ctx.strokeStyle = WHITE_DASH;
  ctx.lineWidth = 1;
  ctx.setLineDash([8, 12]);
  for (const dx of [-LW, -LW * 2, LW, LW * 2]) {
    ctx.beginPath();
    ctx.moveTo(cx + dx, cy - RL); ctx.lineTo(cx + dx, cy - halfRoad);
    ctx.moveTo(cx + dx, cy + halfRoad); ctx.lineTo(cx + dx, cy + RL);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // Stop lines
  ctx.strokeStyle = WHITE_SOLID;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - IR); ctx.lineTo(cx + halfRoad, cy - IR);
  ctx.moveTo(cx - halfRoad, cy + IR); ctx.lineTo(cx + halfRoad, cy + IR);
  ctx.stroke();
}

function drawCrosswalk(ctx: CanvasRenderingContext2D, x: number, y: number, horizontal: boolean): void {
  ctx.fillStyle = CROSSWALK;
  const stripeW = 3;
  const stripeLen = 18;
  const gap = 5;
  const count = 5;

  for (let i = 0; i < count; i++) {
    if (horizontal) {
      ctx.fillRect(x - stripeLen / 2 + i * (stripeW + gap) - (count * (stripeW + gap)) / 2, y - 2, stripeW, 4);
    } else {
      ctx.fillRect(x - 2, y - stripeLen / 2 + i * (stripeW + gap) - (count * (stripeW + gap)) / 2, 4, stripeW);
    }
  }
}
