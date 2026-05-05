import { ROAD_W, ROAD_LEN } from '../types';

const ROAD_COLOR = '#18182a';
const ROAD_EDGE = '#252540';
const SIDEWALK = '#12121e';
const GRASS = '#0d1a0d';

export function drawBackground(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, 0, w, h);
}

export function drawCrossroad(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const roadEnd = ROAD_LEN;

  // Grass
  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  // Sidewalks
  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(cx - halfRoad - 8, cy - roadEnd, ROAD_W + 16, roadEnd * 2);
  ctx.fillRect(cx - roadEnd, cy - halfRoad - 8, roadEnd * 2, ROAD_W + 16);

  // N-S road
  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(cx - halfRoad, cy - roadEnd, ROAD_W, roadEnd * 2);

  // E-W road
  ctx.fillRect(cx - roadEnd, cy - halfRoad, roadEnd * 2, ROAD_W);

  // Intersection box
  ctx.fillRect(cx - halfRoad, cy - halfRoad, ROAD_W, ROAD_W);

  // Road edges
  ctx.strokeStyle = ROAD_EDGE;
  ctx.lineWidth = 1.5;
  // N-S edges
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - roadEnd); ctx.lineTo(cx - halfRoad, cy + roadEnd);
  ctx.moveTo(cx + halfRoad, cy - roadEnd); ctx.lineTo(cx + halfRoad, cy + roadEnd);
  // E-W edges
  ctx.moveTo(cx - roadEnd, cy - halfRoad); ctx.lineTo(cx + roadEnd, cy - halfRoad);
  ctx.moveTo(cx - roadEnd, cy + halfRoad); ctx.lineTo(cx + roadEnd, cy + halfRoad);
  ctx.stroke();
}

export function drawTJunction(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const roadEnd = ROAD_LEN;

  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(cx - halfRoad - 8, cy - roadEnd, ROAD_W + 16, roadEnd + halfRoad + 8);
  ctx.fillRect(cx - roadEnd, cy - halfRoad - 8, roadEnd * 2, ROAD_W + 16);

  // N-S road (full length)
  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(cx - halfRoad, cy - roadEnd, ROAD_W, roadEnd + halfRoad);

  // E-W road (from east to center)
  ctx.fillRect(cx - halfRoad, cy - halfRoad, roadEnd + halfRoad, ROAD_W);

  // Intersection
  ctx.fillRect(cx - halfRoad, cy - halfRoad, ROAD_W, ROAD_W);

  // Edges
  ctx.strokeStyle = ROAD_EDGE;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - roadEnd); ctx.lineTo(cx - halfRoad, cy + halfRoad);
  ctx.moveTo(cx + halfRoad, cy - roadEnd); ctx.lineTo(cx + halfRoad, cy + halfRoad);
  ctx.moveTo(cx - halfRoad, cy - halfRoad); ctx.lineTo(cx + roadEnd, cy - halfRoad);
  ctx.moveTo(cx - halfRoad, cy + halfRoad); ctx.lineTo(cx + roadEnd, cy + halfRoad);
  ctx.stroke();
}

export function drawRoundabout(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const roadEnd = ROAD_LEN;
  const ringR = 50;

  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  // Approach roads
  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(cx - halfRoad - 8, cy - roadEnd, ROAD_W + 16, roadEnd - ringR);
  ctx.fillRect(cx - halfRoad - 8, cy + ringR, ROAD_W + 16, roadEnd - ringR);
  ctx.fillRect(cx - roadEnd, cy - halfRoad - 8, roadEnd - ringR, ROAD_W + 16);
  ctx.fillRect(cx + ringR, cy - halfRoad - 8, roadEnd - ringR, ROAD_W + 16);

  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(cx - halfRoad, cy - roadEnd, ROAD_W, roadEnd - ringR);
  ctx.fillRect(cx - halfRoad, cy + ringR, ROAD_W, roadEnd - ringR);
  ctx.fillRect(cx - roadEnd, cy - halfRoad, roadEnd - ringR, ROAD_W);
  ctx.fillRect(cx + ringR, cy - halfRoad, roadEnd - ringR, ROAD_W);

  // Ring road
  ctx.beginPath();
  ctx.arc(cx, cy, ringR + halfRoad, 0, Math.PI * 2);
  ctx.fillStyle = ROAD_COLOR;
  ctx.fill();

  // Central island
  ctx.beginPath();
  ctx.arc(cx, cy, ringR - halfRoad, 0, Math.PI * 2);
  ctx.fillStyle = '#1a3a1a';
  ctx.fill();
  ctx.strokeStyle = ROAD_EDGE;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

export function drawXIntersection(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const roadEnd = ROAD_LEN;
  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  // Diagonal roads (NE-SW and NW-SE)
  ctx.save();
  ctx.translate(cx, cy);

  // NE-SW road
  ctx.rotate(-Math.PI / 4);
  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(-halfRoad - 8, -roadEnd, ROAD_W + 16, roadEnd * 2);
  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(-halfRoad, -roadEnd, ROAD_W, roadEnd * 2);

  // NW-SE road
  ctx.rotate(Math.PI / 2);
  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(-halfRoad - 8, -roadEnd, ROAD_W + 16, roadEnd * 2);
  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(-halfRoad, -roadEnd, ROAD_W, roadEnd * 2);

  ctx.restore();

  // Central intersection area
  ctx.fillStyle = ROAD_COLOR;
  ctx.beginPath();
  ctx.arc(cx, cy, halfRoad * 1.4, 0, Math.PI * 2);
  ctx.fill();
}

export function drawStraightRoad(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  const halfRoad = ROAD_W / 2;
  const roadEnd = ROAD_LEN;

  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  ctx.fillStyle = SIDEWALK;
  ctx.fillRect(cx - halfRoad - 8, cy - roadEnd, ROAD_W + 16, roadEnd * 2);

  // N-S road
  ctx.fillStyle = ROAD_COLOR;
  ctx.fillRect(cx - halfRoad, cy - roadEnd, ROAD_W, roadEnd * 2);

  // Edges
  ctx.strokeStyle = ROAD_EDGE;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx - halfRoad, cy - roadEnd); ctx.lineTo(cx - halfRoad, cy + roadEnd);
  ctx.moveTo(cx + halfRoad, cy - roadEnd); ctx.lineTo(cx + halfRoad, cy + roadEnd);
  ctx.stroke();
}
